from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

from .paths import ensure_directory


def resolve_rgb_bands(
    band_count: int,
    requested: Iterable[int] | None = None,
) -> tuple[int, int, int]:
    if requested is None:
        requested = (
            max(0, band_count // 6),
            max(0, band_count // 2),
            max(0, (band_count * 5) // 6),
        )

    rgb_bands = tuple(int(band) for band in requested)
    if len(rgb_bands) != 3:
        raise ValueError("Pseudo-RGB requires exactly three band indices.")
    for band in rgb_bands:
        if band < 0 or band >= band_count:
            raise ValueError(f"Band index {band} is out of range for band_count={band_count}.")
    return rgb_bands


def build_pseudo_rgb_preview(
    cube: np.ndarray,
    rgb_bands: Iterable[int] | None = None,
) -> np.ndarray:
    if cube.ndim != 3:
        raise ValueError("Expected a cube shaped as (frame_count, band_count, spatial_width).")

    normalized_rgb_bands = resolve_rgb_bands(cube.shape[1], rgb_bands)
    preview = np.moveaxis(cube[:, normalized_rgb_bands, :], 1, -1).astype(np.float32)
    return normalize_preview(preview)


def normalize_preview(image: np.ndarray) -> np.ndarray:
    if image.ndim != 3 or image.shape[-1] != 3:
        raise ValueError("Expected a preview image with shape (..., ..., 3).")

    normalized = image.copy()
    for channel_index in range(3):
        channel = normalized[..., channel_index]
        low = float(np.percentile(channel, 1.0))
        high = float(np.percentile(channel, 99.0))
        if high <= low:
            normalized[..., channel_index] = 0.0
            continue
        normalized[..., channel_index] = (channel - low) / (high - low)

    normalized = np.clip(normalized, 0.0, 1.0)
    return np.round(normalized * 255.0).astype(np.uint8)


def save_preview_png(preview: np.ndarray, path: Path) -> Path:
    from PIL import Image

    ensure_directory(path.parent)
    Image.fromarray(preview, mode="RGB").save(path)
    return path
