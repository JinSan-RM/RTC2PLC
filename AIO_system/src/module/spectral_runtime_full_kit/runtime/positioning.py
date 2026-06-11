from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence


@dataclass(slots=True)
class RuntimePositionConfig:
    x_mm_per_pixel: float | None = None
    y_mm_per_frame: float | None = None
    belt_speed_mm_s: float | None = None
    x_origin_mm: float = 0.0
    y_origin_mm: float = 0.0
    encoder_counts_per_mm: float | None = None
    encoder_origin_count: float | None = None
    nozzle_origin_x_mm: float | None = None
    nozzle_pitch_mm: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def has_world_mapping(self) -> bool:
        return self.x_mm_per_pixel is not None or self.y_mm_per_frame is not None or self.belt_speed_mm_s is not None


def build_position_payload(
    *,
    bbox_xywh: Sequence[int],
    centroid_xy: Sequence[float],
    frame_range: Sequence[int],
    timestamp_range_s: Sequence[float] | None,
    config: RuntimePositionConfig | None,
) -> dict[str, object]:
    bbox = [int(value) for value in bbox_xywh]
    centroid = [float(centroid_xy[0]), float(centroid_xy[1])]
    payload: dict[str, object] = {
        "bbox_px": bbox,
        "centroid_px": centroid,
    }
    if config is None:
        return payload

    x_mm = _resolve_x_mm(centroid_x_px=centroid[0], config=config)
    y_mm = _resolve_y_mm(
        centroid_y_px=centroid[1],
        frame_range=frame_range,
        timestamp_range_s=timestamp_range_s,
        config=config,
    )
    if x_mm is not None or y_mm is not None:
        payload["centroid_world"] = {
            "x_mm": x_mm,
            "y_mm": y_mm,
        }
    if x_mm is not None and y_mm is not None:
        payload["centroid_mm"] = [float(x_mm), float(y_mm)]

    bbox_mm = _resolve_bbox_mm(bbox_xywh=bbox, timestamp_range_s=timestamp_range_s, config=config)
    if bbox_mm is not None:
        payload["bbox_mm"] = bbox_mm

    encoder_count = _resolve_encoder_count(y_mm=y_mm, config=config)
    if encoder_count is not None:
        payload["encoder_count"] = int(round(encoder_count))

    nozzle_index = _resolve_nozzle_index(x_mm=x_mm, config=config)
    if nozzle_index is not None:
        payload["nozzle_index"] = int(nozzle_index)

    return payload


def _resolve_x_mm(*, centroid_x_px: float, config: RuntimePositionConfig) -> float | None:
    if config.x_mm_per_pixel is None:
        return None
    return float(config.x_origin_mm) + (float(centroid_x_px) * float(config.x_mm_per_pixel))


def _resolve_y_mm(
    *,
    centroid_y_px: float,
    frame_range: Sequence[int],
    timestamp_range_s: Sequence[float] | None,
    config: RuntimePositionConfig,
) -> float | None:
    if config.belt_speed_mm_s is not None and timestamp_range_s is not None and len(timestamp_range_s) >= 2:
        midpoint_s = (float(timestamp_range_s[0]) + float(timestamp_range_s[1])) / 2.0
        return float(config.y_origin_mm) + (midpoint_s * float(config.belt_speed_mm_s))
    if config.y_mm_per_frame is not None:
        return float(config.y_origin_mm) + (float(centroid_y_px) * float(config.y_mm_per_frame))
    return None


def _resolve_bbox_mm(
    *,
    bbox_xywh: Sequence[int],
    timestamp_range_s: Sequence[float] | None,
    config: RuntimePositionConfig,
) -> list[float] | None:
    if config.x_mm_per_pixel is None:
        return None
    x0, y0, width, height = [int(value) for value in bbox_xywh]
    x_mm = float(config.x_origin_mm) + (float(x0) * float(config.x_mm_per_pixel))
    width_mm = float(width) * float(config.x_mm_per_pixel)

    y_mm: float | None = None
    height_mm: float | None = None
    if config.belt_speed_mm_s is not None and timestamp_range_s is not None and len(timestamp_range_s) >= 2:
        start_s = float(timestamp_range_s[0])
        end_s = float(timestamp_range_s[1])
        y_mm = float(config.y_origin_mm) + (start_s * float(config.belt_speed_mm_s))
        height_mm = max(0.0, end_s - start_s) * float(config.belt_speed_mm_s)
    elif config.y_mm_per_frame is not None:
        y_mm = float(config.y_origin_mm) + (float(y0) * float(config.y_mm_per_frame))
        height_mm = float(height) * float(config.y_mm_per_frame)

    if y_mm is None or height_mm is None:
        return None
    return [float(x_mm), float(y_mm), float(width_mm), float(height_mm)]


def _resolve_encoder_count(*, y_mm: float | None, config: RuntimePositionConfig) -> float | None:
    if y_mm is None or config.encoder_counts_per_mm is None:
        return None
    origin = 0.0 if config.encoder_origin_count is None else float(config.encoder_origin_count)
    return origin + (float(y_mm) * float(config.encoder_counts_per_mm))


def _resolve_nozzle_index(*, x_mm: float | None, config: RuntimePositionConfig) -> int | None:
    if x_mm is None or config.nozzle_pitch_mm is None:
        return None
    pitch = float(config.nozzle_pitch_mm)
    if pitch <= 0.0:
        return None
    origin = 0.0 if config.nozzle_origin_x_mm is None else float(config.nozzle_origin_x_mm)
    return int(round((float(x_mm) - origin) / pitch))
