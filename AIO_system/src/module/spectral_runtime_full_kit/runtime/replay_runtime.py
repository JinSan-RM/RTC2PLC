from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from runtime.objectizer import ObjectizationResult, objectize_class_map
from runtime.pixel_inference import infer_pixel_map, summarize_pixel_map
from runtime.positioning import RuntimePositionConfig, build_position_payload

_RELATIVE_TIMESTAMP_MAX_S = 24 * 60 * 60


@dataclass(slots=True)
class RuntimeWindowResult:
    window_index: int
    frame_start: int
    frame_end: int
    event: dict[str, object]
    pixel_summary: dict[str, object]
    object_summary: dict[str, object]


def build_window_ranges(frame_count: int, window_size: int, stride: int) -> list[tuple[int, int]]:
    if frame_count <= 0:
        raise ValueError("frame_count must be positive.")
    normalized_window_size = max(1, int(window_size))
    normalized_stride = max(1, int(stride))

    ranges: list[tuple[int, int]] = []
    start = 0
    while start < frame_count:
        end = min(start + normalized_window_size, frame_count)
        ranges.append((start, end))
        if end >= frame_count:
            break
        start += normalized_stride
    return ranges


def run_replay_runtime(
    *,
    cube: np.ndarray,
    timestamps_s: np.ndarray,
    model: Any,
    window_size: int,
    stride: int,
    confidence_threshold: float = 0.5,
    min_area: int = 25,
    connectivity: int = 8,
    opening_size: int = 0,
    closing_size: int = 0,
    valid_x_min: int | None = None,
    valid_x_max: int | None = None,
    min_bbox_width: int = 1,
    min_bbox_height: int = 1,
    max_bbox_aspect_ratio: float | None = None,
    min_class_fraction: float = 0.0,
    object_confidence_threshold: float = 0.0,
    suppress_iou_threshold: float | None = None,
    suppress_containment_threshold: float | None = None,
    suppress_across_classes: bool = False,
    position_config: RuntimePositionConfig | None = None,
    session_created_at_utc: datetime | None = None,
) -> list[RuntimeWindowResult]:
    cube_array = np.asarray(cube)
    timeline = np.asarray(timestamps_s, dtype=np.float64)
    if cube_array.ndim != 3:
        raise ValueError("cube must be a 3D array: (frame_count, band_count, spatial_width).")
    if timeline.ndim != 1:
        raise ValueError("timestamps_s must be a 1D array.")
    if timeline.shape[0] != cube_array.shape[0]:
        raise ValueError(
            "timestamps_s length must match cube frame axis. "
            f"timestamps={timeline.shape[0]}, frames={cube_array.shape[0]}"
        )
    timeline = normalize_relative_timestamps(timeline)

    results: list[RuntimeWindowResult] = []
    window_ranges = build_window_ranges(
        frame_count=int(cube_array.shape[0]),
        window_size=window_size,
        stride=stride,
    )
    for window_index, (frame_start, frame_end_exclusive) in enumerate(window_ranges):
        frame_end = frame_end_exclusive - 1
        cube_window = cube_array[frame_start:frame_end_exclusive]
        timeline_window = timeline[frame_start:frame_end_exclusive]
        pixel_result = infer_pixel_map(
            model=model,
            cube=cube_window,
            confidence_threshold=confidence_threshold,
            valid_x_min=valid_x_min,
            valid_x_max=valid_x_max,
        )
        object_result = objectize_class_map(
            class_map=pixel_result.class_map,
            confidence_map=pixel_result.confidence_map,
            class_names=pixel_result.class_names,
            min_area=min_area,
            connectivity=connectivity,
            opening_size=opening_size,
            closing_size=closing_size,
            min_bbox_width=min_bbox_width,
            min_bbox_height=min_bbox_height,
            max_bbox_aspect_ratio=max_bbox_aspect_ratio,
            min_class_fraction=min_class_fraction,
            object_confidence_threshold=object_confidence_threshold,
            suppress_iou_threshold=suppress_iou_threshold,
            suppress_containment_threshold=suppress_containment_threshold,
            suppress_across_classes=suppress_across_classes,
            timestamps_s=timeline_window,
        )
        event = build_runtime_event(
            object_result=object_result,
            class_names=pixel_result.class_names,
            window_index=window_index,
            frame_start=frame_start,
            frame_end=frame_end,
            timestamp_monotonic_s=float(timeline_window[-1]),
            session_created_at_utc=session_created_at_utc,
            position_config=position_config,
        )
        results.append(
            RuntimeWindowResult(
                window_index=window_index,
                frame_start=frame_start,
                frame_end=frame_end,
                event=event,
                pixel_summary=summarize_pixel_map(pixel_result),
                object_summary=object_result.to_dict(),
            )
        )
    return results


def build_runtime_event(
    *,
    object_result: ObjectizationResult,
    class_names: list[str],
    window_index: int,
    frame_start: int,
    frame_end: int,
    timestamp_monotonic_s: float,
    session_created_at_utc: datetime | None,
    position_config: RuntimePositionConfig | None = None,
) -> dict[str, object]:
    timestamp_ms, timestamp_iso = resolve_event_timestamp(
        timestamp_monotonic_s=timestamp_monotonic_s,
        session_created_at_utc=session_created_at_utc,
    )
    objects: list[dict[str, object]] = []
    for item in object_result.objects:
        global_frame_range = [
            int(frame_start + int(item.frame_range[0])),
            int(frame_start + int(item.frame_range[1])),
        ]
        global_bbox = [
            int(item.bbox_xywh[0]),
            int(item.bbox_xywh[1] + frame_start),
            int(item.bbox_xywh[2]),
            int(item.bbox_xywh[3]),
        ]
        global_centroid = [
            float(item.centroid_xy[0]),
            float(item.centroid_xy[1] + frame_start),
        ]
        timestamp_range = None
        if item.timestamp_range_s is not None:
            timestamp_range = [float(v) for v in item.timestamp_range_s]
        position_payload = build_position_payload(
            bbox_xywh=global_bbox,
            centroid_xy=global_centroid,
            frame_range=global_frame_range,
            timestamp_range_s=timestamp_range,
            config=position_config,
        )
        row: dict[str, object] = {
            "object_id": int(item.object_id),
            "class": str(class_names[item.class_index]) if item.class_index < len(class_names) else str(item.class_name),
            "confidence": float(item.object_confidence),
            "confidence_mean": float(item.confidence_mean),
            "confidence_max": float(item.confidence_max),
            "class_fraction": float(item.class_fraction),
            "bbox": global_bbox,
            "centroid": global_centroid,
            "position": position_payload,
            "pixel_count": int(item.pixel_count),
            "frame_range": global_frame_range,
        }
        if timestamp_range is not None:
            row["timestamp_range_s"] = timestamp_range
        objects.append(row)

    objects.sort(key=lambda item: int(item["frame_range"][0]))  # type: ignore[index]
    return {
        "timestamp": int(timestamp_ms),
        "timestamp_iso": timestamp_iso,
        "timestamp_monotonic_s": float(timestamp_monotonic_s),
        "window_index": int(window_index),
        "frame_range": [int(frame_start), int(frame_end)],
        "objects": objects,
    }


def summarize_runtime_results(results: list[RuntimeWindowResult]) -> dict[str, object]:
    total_objects = 0
    total_dropped = 0
    total_dropped_shape = 0
    total_dropped_class_fraction = 0
    total_dropped_low_confidence = 0
    total_suppressed_overlap = 0
    objects_per_class: dict[str, int] = {}
    windows: list[dict[str, object]] = []

    for item in results:
        event = item.event
        objects = event.get("objects", [])
        object_count = len(objects) if isinstance(objects, list) else 0
        total_objects += object_count
        dropped = int(item.object_summary.get("dropped_small_components", 0))
        total_dropped += dropped
        dropped_shape = int(item.object_summary.get("dropped_shape_components", 0))
        total_dropped_shape += dropped_shape
        dropped_class_fraction = int(item.object_summary.get("dropped_class_fraction_components", 0))
        total_dropped_class_fraction += dropped_class_fraction
        dropped_low_confidence = int(item.object_summary.get("dropped_low_confidence_components", 0))
        total_dropped_low_confidence += dropped_low_confidence
        suppressed_overlap = int(item.object_summary.get("suppressed_overlap_components", 0))
        total_suppressed_overlap += suppressed_overlap
        if isinstance(objects, list):
            for obj in objects:
                if isinstance(obj, dict):
                    class_name = str(obj.get("class", "unknown"))
                    objects_per_class[class_name] = objects_per_class.get(class_name, 0) + 1
        windows.append(
            {
                "window_index": int(item.window_index),
                "frame_range": [int(item.frame_start), int(item.frame_end)],
                "timestamp": int(event.get("timestamp", 0)),
                "timestamp_iso": str(event.get("timestamp_iso", "")),
                "object_count": object_count,
                "dropped_small_components": dropped,
                "dropped_shape_components": dropped_shape,
                "dropped_class_fraction_components": dropped_class_fraction,
                "dropped_low_confidence_components": dropped_low_confidence,
                "suppressed_overlap_components": suppressed_overlap,
            }
        )

    return {
        "window_count": len(results),
        "total_objects": total_objects,
        "total_dropped_small_components": total_dropped,
        "total_dropped_shape_components": total_dropped_shape,
        "total_dropped_class_fraction_components": total_dropped_class_fraction,
        "total_dropped_low_confidence_components": total_dropped_low_confidence,
        "total_suppressed_overlap_components": total_suppressed_overlap,
        "objects_per_class": objects_per_class,
        "windows": windows,
    }


def parse_session_created_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_relative_timestamps(timestamps_s: np.ndarray) -> np.ndarray:
    timeline = np.asarray(timestamps_s, dtype=np.float64)
    if timeline.size <= 0:
        return timeline
    if float(timeline[0]) <= _RELATIVE_TIMESTAMP_MAX_S:
        return timeline
    return timeline - float(timeline[0])


def resolve_event_timestamp(
    *,
    timestamp_monotonic_s: float,
    session_created_at_utc: datetime | None,
) -> tuple[int, str]:
    if session_created_at_utc is None:
        epoch_ms = int(round(float(timestamp_monotonic_s) * 1000.0))
        return epoch_ms, f"monotonic+{timestamp_monotonic_s:.6f}s"

    dt = session_created_at_utc + timedelta(seconds=float(timestamp_monotonic_s))
    epoch_ms = int(dt.timestamp() * 1000.0)
    return epoch_ms, dt.isoformat()
