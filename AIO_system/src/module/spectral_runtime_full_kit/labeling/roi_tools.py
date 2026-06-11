from __future__ import annotations

from collections import deque
from typing import Any, Sequence

import numpy as np

from labeling.schema import RoiRect


def normalize_band_range(*, band_count: int, band_start: int, band_end: int) -> tuple[int, int]:
    if band_count <= 0:
        raise ValueError("band_count must be positive.")
    start = int(np.clip(min(int(band_start), int(band_end)), 0, band_count - 1))
    end = int(np.clip(max(int(band_start), int(band_end)), 0, band_count - 1))
    return start, end


def build_bounded_rectangle_roi(
    *,
    start_point: tuple[int, int],
    end_point: tuple[int, int],
    image_width: int,
    image_height: int,
) -> RoiRect:
    width = int(image_width)
    height = int(image_height)
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid image size: width={image_width}, height={image_height}")

    x0 = int(np.clip(min(start_point[0], end_point[0]), 0, width - 1))
    y0 = int(np.clip(min(start_point[1], end_point[1]), 0, height - 1))
    x1 = int(np.clip(max(start_point[0], end_point[0]), 0, width - 1))
    y1 = int(np.clip(max(start_point[1], end_point[1]), 0, height - 1))

    roi_w = max(1, x1 - x0 + 1)
    roi_h = max(1, y1 - y0 + 1)
    return RoiRect(x=x0, y=y0, width=roi_w, height=roi_h)


def rasterize_polygon_mask(
    *,
    height: int,
    width: int,
    points: Sequence[tuple[int, int]],
) -> np.ndarray:
    h = int(height)
    w = int(width)
    if h <= 0 or w <= 0:
        raise ValueError(f"Invalid mask shape: height={height}, width={width}")
    if len(points) < 3:
        raise ValueError("Polygon requires at least 3 points.")

    pts = np.asarray([[float(x), float(y)] for x, y in points], dtype=np.float32)
    px = np.clip(pts[:, 0], 0.0, float(w - 1))
    py = np.clip(pts[:, 1], 0.0, float(h - 1))
    next_px = np.roll(px, -1)
    next_py = np.roll(py, -1)

    yy, xx = np.meshgrid(
        np.arange(h, dtype=np.float32) + 0.5,
        np.arange(w, dtype=np.float32) + 0.5,
        indexing="ij",
    )
    inside = np.zeros((h, w), dtype=bool)
    eps = 1e-12
    for idx in range(len(px)):
        yi = float(py[idx])
        yj = float(next_py[idx])
        xi = float(px[idx])
        xj = float(next_px[idx])
        crossings = (yi > yy) != (yj > yy)
        denom = (yj - yi) if abs(yj - yi) > eps else eps
        x_intersect = (xj - xi) * (yy - yi) / denom + xi
        inside ^= crossings & (xx < x_intersect)
    return inside


def rasterize_freehand_lasso(
    *,
    height: int,
    width: int,
    points: Sequence[tuple[int, int]],
) -> np.ndarray:
    """Rasterize a freehand lasso path to a closed boolean mask."""
    if len(points) < 3:
        raise ValueError("Freehand lasso requires at least 3 points.")
    return rasterize_polygon_mask(height=height, width=width, points=points)


def paint_brush_disk(
    mask: np.ndarray,
    *,
    center_x: int,
    center_y: int,
    radius: int,
) -> np.ndarray:
    arr = np.asarray(mask, dtype=bool)
    if arr.ndim != 2:
        raise ValueError(f"mask must be 2D, got shape={arr.shape!r}")
    if not arr.flags.writeable:
        arr = arr.copy()
    h, w = int(arr.shape[0]), int(arr.shape[1])
    cx = int(np.clip(center_x, 0, max(0, w - 1)))
    cy = int(np.clip(center_y, 0, max(0, h - 1)))
    r = max(1, int(radius))

    x0 = max(0, cx - r)
    y0 = max(0, cy - r)
    x1 = min(w - 1, cx + r)
    y1 = min(h - 1, cy + r)
    yy, xx = np.ogrid[y0 : y1 + 1, x0 : x1 + 1]
    disk = ((xx - cx) ** 2 + (yy - cy) ** 2) <= (r ** 2)
    arr[y0 : y1 + 1, x0 : x1 + 1] |= disk
    return arr


def build_region_grow_sam_mask(
    *,
    data: np.ndarray,
    seed_y: int,
    seed_x: int,
    band_start: int,
    band_end: int,
    sam_threshold_deg: float,
    max_pixels: int,
    base_mask: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    array = np.asarray(data, dtype=np.float32)
    if array.ndim != 3:
        raise ValueError(f"Expected 3D array (frames,width,bands), got shape={array.shape!r}")
    h, w, band_count = int(array.shape[0]), int(array.shape[1]), int(array.shape[2])
    if h <= 0 or w <= 0 or band_count <= 0:
        raise ValueError(f"Invalid data shape: {array.shape!r}")

    sy = int(seed_y)
    sx = int(seed_x)
    if sy < 0 or sy >= h or sx < 0 or sx >= w:
        raise ValueError(f"Seed out of bounds: ({sy},{sx}) for shape={(h, w)}")

    start, end = normalize_band_range(band_count=band_count, band_start=band_start, band_end=band_end)
    threshold = float(max(0.0, sam_threshold_deg))
    max_region_pixels = max(1, int(max_pixels))

    spectra = np.asarray(array[:, :, start : end + 1], dtype=np.float32)
    valid = np.all(np.isfinite(spectra), axis=2)
    if base_mask is not None:
        base = np.asarray(base_mask, dtype=bool)
        if base.shape != (h, w):
            raise ValueError(f"base_mask shape mismatch: expected {(h, w)!r}, got {base.shape!r}")
        valid &= base
    if not valid[sy, sx]:
        raise ValueError("Seed pixel is invalid under current mask.")

    seed = spectra[sy, sx, :]
    seed_norm = float(np.linalg.norm(seed))
    if not np.isfinite(seed_norm) or seed_norm <= 1e-12:
        raise ValueError("Seed spectrum norm is zero or invalid.")
    pixel_norm = np.linalg.norm(spectra, axis=2)
    dot = np.sum(spectra * seed.reshape(1, 1, -1), axis=2)
    with np.errstate(divide="ignore", invalid="ignore"):
        cosine = dot / (pixel_norm * seed_norm)
    cosine = np.clip(np.nan_to_num(cosine, nan=-1.0), -1.0, 1.0)
    sam_deg = np.degrees(np.arccos(cosine))
    candidates = valid & (sam_deg <= threshold)
    if not candidates[sy, sx]:
        raise ValueError("Seed does not satisfy the SAM threshold.")

    region = np.zeros((h, w), dtype=bool)
    visited = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()
    q.append((sy, sx))
    visited[sy, sx] = True

    count = 0
    neighbors = (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )
    while q and count < max_region_pixels:
        y, x = q.popleft()
        if not candidates[y, x]:
            continue
        region[y, x] = True
        count += 1
        for dy, dx in neighbors:
            ny = y + dy
            nx = x + dx
            if ny < 0 or ny >= h or nx < 0 or nx >= w:
                continue
            if visited[ny, nx]:
                continue
            visited[ny, nx] = True
            if candidates[ny, nx]:
                q.append((ny, nx))

    summary: dict[str, Any] = {
        "seed_y": sy,
        "seed_x": sx,
        "band_start": start,
        "band_end": end,
        "sam_threshold_deg": threshold,
        "max_pixels": max_region_pixels,
        "candidate_pixels": int(np.sum(candidates)),
        "grown_pixels": int(np.sum(region)),
        "grown_ratio": float(np.sum(region)) / float(region.size) if region.size > 0 else 0.0,
    }
    return region, summary

# 손떨림 사후 보정을 위한 함수들
def _filter_points_by_distance(
    points: Sequence[tuple[int, int]],
    *,
    min_distance_px: float = 3.0,
) -> list[tuple[int, int]]:
    filtered: list[tuple[int, int]] = []
    last_point: tuple[int, int] | None = None
    min_distance_sq = float(min_distance_px) * float(min_distance_px)
    for raw_x, raw_y in points:
        point = (int(raw_x), int(raw_y))
        
        if last_point is None:
            filtered.append(point)
            last_point = point
            continue
        dx = point[0] - last_point[0]
        dy = point[1] - last_point[1]
        if dx * dx + dy * dy >= min_distance_sq:
            filtered.append(point)
            last_point = point

    return filtered


def _moving_average_points(
    points: Sequence[tuple[int, int]],
    *,
    window_radius: int = 2,
) -> list[tuple[int, int]]:
    smoothed: list[tuple[int, int]] = []
    radius = max(1, int(window_radius))
    for index in range(len(points)):
        window = points[max(0, index - radius) : min(len(points), index + radius + 1)]
        avg_x = round(sum(point[0] for point in window) / len(window))
        avg_y = round(sum(point[1] for point in window) / len(window))
        smoothed.append((int(avg_x), int(avg_y)))
    return smoothed


def smooth_freehand_points(
    points: Sequence[tuple[int, int]],
    *,
    min_distance_px: float = 3.0,
    window_radius: int = 2,
) -> list[tuple[int, int]]:
    if len(points) < 8:
        return list(points)

    filtered = _filter_points_by_distance(points, min_distance_px=min_distance_px)
    if len(filtered) < 8:
        return filtered if len(filtered) >= 3 else list(points)

    smoothed = _moving_average_points(filtered, window_radius=window_radius)
    return smoothed if len(smoothed) >= 3 else list(points)

