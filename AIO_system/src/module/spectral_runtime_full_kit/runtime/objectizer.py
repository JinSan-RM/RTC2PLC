from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np
from scipy import ndimage


DEFAULT_IGNORED_CLASS_NAMES: tuple[str, ...] = ("background",)


@dataclass(slots=True)
class ObjectRecord:
    object_id: int
    class_index: int
    class_name: str
    pixel_count: int
    confidence_mean: float
    confidence_max: float
    class_fraction: float
    object_confidence: float
    bbox_xywh: list[int]
    centroid_xy: list[float]
    frame_range: list[int]
    timestamp_range_s: list[float] | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ObjectizationResult:
    object_map: np.ndarray
    objects: list[ObjectRecord]
    dropped_small_components: int
    dropped_shape_components: int = 0
    dropped_class_fraction_components: int = 0
    dropped_low_confidence_components: int = 0
    suppressed_overlap_components: int = 0

    def to_dict(self) -> dict[str, object]:
        class_counts: dict[str, int] = {}
        for item in self.objects:
            class_counts[item.class_name] = class_counts.get(item.class_name, 0) + 1
        return {
            "total_objects": len(self.objects),
            "dropped_small_components": int(self.dropped_small_components),
            "dropped_shape_components": int(self.dropped_shape_components),
            "dropped_class_fraction_components": int(self.dropped_class_fraction_components),
            "dropped_low_confidence_components": int(self.dropped_low_confidence_components),
            "suppressed_overlap_components": int(self.suppressed_overlap_components),
            "objects_per_class": class_counts,
            "objects": [item.to_dict() for item in self.objects],
        }


def objectize_class_map(
    *,
    class_map: np.ndarray,
    confidence_map: np.ndarray,
    class_names: Sequence[str],
    unknown_index: int = -1,
    min_area: int = 25,
    connectivity: int = 8,
    opening_size: int = 0,
    closing_size: int = 0,
    timestamps_s: np.ndarray | None = None,
    ignored_class_names: Sequence[str] | None = DEFAULT_IGNORED_CLASS_NAMES,
    min_bbox_width: int = 1,
    min_bbox_height: int = 1,
    max_bbox_aspect_ratio: float | None = None,
    min_class_fraction: float = 0.0,
    object_confidence_threshold: float = 0.0,
    suppress_iou_threshold: float | None = None,
    suppress_containment_threshold: float | None = None,
    suppress_across_classes: bool = False,
) -> ObjectizationResult:
    class_map_array = np.asarray(class_map, dtype=np.int16)
    confidence_map_array = np.asarray(confidence_map, dtype=np.float32)

    if class_map_array.ndim != 2:
        raise ValueError("class_map must be a 2D array.")
    if confidence_map_array.shape != class_map_array.shape:
        raise ValueError("confidence_map must have the same shape as class_map.")
    if connectivity not in (4, 8):
        raise ValueError(f"connectivity must be 4 or 8, got {connectivity}.")
    if timestamps_s is not None:
        timeline = np.asarray(timestamps_s, dtype=np.float64)
        if timeline.ndim != 1:
            raise ValueError("timestamps_s must be a 1D array.")
        if timeline.shape[0] != class_map_array.shape[0]:
            raise ValueError(
                "timestamps_s length must match frame axis. "
                f"timestamps={timeline.shape[0]}, frames={class_map_array.shape[0]}"
            )
    else:
        timeline = None

    min_area_value = max(1, int(min_area))
    structure = _connectivity_structure(connectivity)
    object_map = np.full(class_map_array.shape, -1, dtype=np.int32)
    objects: list[ObjectRecord] = []
    dropped_small_components = 0
    dropped_shape_components = 0
    dropped_class_fraction_components = 0
    dropped_low_confidence_components = 0
    next_object_id = 0
    min_width_value = max(1, int(min_bbox_width))
    min_height_value = max(1, int(min_bbox_height))
    max_aspect_value = _normalize_max_aspect_ratio(max_bbox_aspect_ratio)
    min_class_fraction_value = _normalize_unit_threshold(min_class_fraction)
    object_confidence_threshold_value = _normalize_unit_threshold(object_confidence_threshold)
    suppress_iou_value = _normalize_optional_unit_threshold(suppress_iou_threshold)
    suppress_containment_value = _normalize_optional_unit_threshold(suppress_containment_threshold)

    for class_index, class_name in enumerate(class_names):
        if _is_ignored_class_name(class_name, ignored_class_names):
            continue
        base_mask = class_map_array == class_index
        if not np.any(base_mask):
            continue
        mask = _apply_morphology(
            base_mask,
            structure=structure,
            opening_size=max(0, int(opening_size)),
            closing_size=max(0, int(closing_size)),
        )
        if not np.any(mask):
            continue

        labeled, component_count = ndimage.label(mask, structure=structure)
        slices = ndimage.find_objects(labeled)
        for label_id in range(1, component_count + 1):
            component_slice = slices[label_id - 1]
            if component_slice is None:
                continue

            local_labels = labeled[component_slice]
            local_conf = confidence_map_array[component_slice]
            local_class_map = class_map_array[component_slice]
            component_mask = local_labels == label_id
            pixel_count = int(np.count_nonzero(component_mask))
            if pixel_count < min_area_value:
                dropped_small_components += 1
                continue

            y0 = int(component_slice[0].start)
            y1 = int(component_slice[0].stop)
            x0 = int(component_slice[1].start)
            x1 = int(component_slice[1].stop)
            width = int(x1 - x0)
            height = int(y1 - y0)
            if _fails_shape_filter(
                width=width,
                height=height,
                min_bbox_width=min_width_value,
                min_bbox_height=min_height_value,
                max_bbox_aspect_ratio=max_aspect_value,
            ):
                dropped_shape_components += 1
                continue

            original_class_mask = np.logical_and(component_mask, local_class_map == int(class_index))
            class_pixel_count = int(np.count_nonzero(original_class_mask))
            class_fraction = float(class_pixel_count) / float(pixel_count) if pixel_count > 0 else 0.0
            if class_fraction < min_class_fraction_value:
                dropped_class_fraction_components += 1
                continue

            ys, xs = np.where(component_mask)
            centroid_x = float(x0 + np.mean(xs))
            centroid_y = float(y0 + np.mean(ys))
            frame_start = int(y0 + int(np.min(ys)))
            frame_end = int(y0 + int(np.max(ys)))

            conf_values = local_conf[original_class_mask] if class_pixel_count > 0 else local_conf[component_mask]
            confidence_mean = float(np.mean(conf_values))
            confidence_max = float(np.max(conf_values))
            object_confidence = float(confidence_mean * class_fraction)
            if object_confidence < object_confidence_threshold_value:
                dropped_low_confidence_components += 1
                continue
            timestamp_range = None
            if timeline is not None:
                timestamp_range = [
                    float(timeline[frame_start]),
                    float(timeline[frame_end]),
                ]

            object_map_slice = object_map[component_slice]
            object_map_slice[component_mask] = next_object_id

            objects.append(
                ObjectRecord(
                    object_id=next_object_id,
                    class_index=class_index,
                    class_name=str(class_name),
                    pixel_count=pixel_count,
                    confidence_mean=confidence_mean,
                    confidence_max=confidence_max,
                    class_fraction=class_fraction,
                    object_confidence=object_confidence,
                    bbox_xywh=[x0, y0, width, height],
                    centroid_xy=[centroid_x, centroid_y],
                    frame_range=[frame_start, frame_end],
                    timestamp_range_s=timestamp_range,
                )
            )
            next_object_id += 1

    # Keep unknown pixels in object map as -1 to align with replay-first downstream logic.
    object_map[class_map_array == int(unknown_index)] = -1
    objects, object_map, suppressed_overlap_components = _suppress_overlapping_objects(
        objects=objects,
        object_map=object_map,
        iou_threshold=suppress_iou_value,
        containment_threshold=suppress_containment_value,
        suppress_across_classes=bool(suppress_across_classes),
    )
    return ObjectizationResult(
        object_map=object_map,
        objects=objects,
        dropped_small_components=dropped_small_components,
        dropped_shape_components=dropped_shape_components,
        dropped_class_fraction_components=dropped_class_fraction_components,
        dropped_low_confidence_components=dropped_low_confidence_components,
        suppressed_overlap_components=suppressed_overlap_components,
    )


def _normalize_unit_threshold(value: float) -> float:
    parsed = float(value)
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return parsed


def _normalize_optional_unit_threshold(value: float | None) -> float | None:
    if value is None:
        return None
    parsed = _normalize_unit_threshold(float(value))
    if parsed <= 0.0:
        return None
    return parsed


def _normalize_max_aspect_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed <= 0.0:
        return None
    return max(1.0, parsed)


def _fails_shape_filter(
    *,
    width: int,
    height: int,
    min_bbox_width: int,
    min_bbox_height: int,
    max_bbox_aspect_ratio: float | None,
) -> bool:
    if int(width) < int(min_bbox_width):
        return True
    if int(height) < int(min_bbox_height):
        return True
    if max_bbox_aspect_ratio is None:
        return False
    long_side = float(max(int(width), int(height)))
    short_side = float(max(1, min(int(width), int(height))))
    return (long_side / short_side) > float(max_bbox_aspect_ratio)


def _suppress_overlapping_objects(
    *,
    objects: list[ObjectRecord],
    object_map: np.ndarray,
    iou_threshold: float | None,
    containment_threshold: float | None,
    suppress_across_classes: bool,
) -> tuple[list[ObjectRecord], np.ndarray, int]:
    if not objects or (iou_threshold is None and containment_threshold is None):
        return objects, object_map, 0

    ranked = sorted(
        objects,
        key=lambda item: (
            float(item.object_confidence),
            float(item.confidence_mean),
            int(item.pixel_count),
        ),
        reverse=True,
    )
    kept: list[ObjectRecord] = []
    suppressed_ids: set[int] = set()

    for candidate in ranked:
        should_drop = False
        for existing in kept:
            if not suppress_across_classes and int(candidate.class_index) != int(existing.class_index):
                continue
            if iou_threshold is not None and _bbox_iou(candidate.bbox_xywh, existing.bbox_xywh) >= iou_threshold:
                should_drop = True
                break
            if (
                containment_threshold is not None
                and _bbox_containment(candidate.bbox_xywh, existing.bbox_xywh) >= containment_threshold
            ):
                should_drop = True
                break
        if should_drop:
            suppressed_ids.add(int(candidate.object_id))
        else:
            kept.append(candidate)

    if not suppressed_ids:
        return objects, object_map, 0

    kept.sort(key=lambda item: int(item.object_id))
    remapped = np.full(object_map.shape, -1, dtype=object_map.dtype)
    for new_id, item in enumerate(kept):
        old_id = int(item.object_id)
        remapped[object_map == old_id] = int(new_id)
        item.object_id = int(new_id)
    return kept, remapped, len(suppressed_ids)


def _bbox_iou(left: Sequence[int], right: Sequence[int]) -> float:
    intersection = _bbox_intersection_area(left, right)
    if intersection <= 0.0:
        return 0.0
    left_area = _bbox_area(left)
    right_area = _bbox_area(right)
    union = left_area + right_area - intersection
    if union <= 0.0:
        return 0.0
    return intersection / union


def _bbox_containment(left: Sequence[int], right: Sequence[int]) -> float:
    intersection = _bbox_intersection_area(left, right)
    if intersection <= 0.0:
        return 0.0
    smaller_area = min(_bbox_area(left), _bbox_area(right))
    if smaller_area <= 0.0:
        return 0.0
    return intersection / smaller_area


def _bbox_intersection_area(left: Sequence[int], right: Sequence[int]) -> float:
    lx, ly, lw, lh = [float(v) for v in left[:4]]
    rx, ry, rw, rh = [float(v) for v in right[:4]]
    left_x2 = lx + max(0.0, lw)
    left_y2 = ly + max(0.0, lh)
    right_x2 = rx + max(0.0, rw)
    right_y2 = ry + max(0.0, rh)
    width = max(0.0, min(left_x2, right_x2) - max(lx, rx))
    height = max(0.0, min(left_y2, right_y2) - max(ly, ry))
    return width * height


def _bbox_area(value: Sequence[int]) -> float:
    _, _, width, height = [float(v) for v in value[:4]]
    return max(0.0, width) * max(0.0, height)


def _is_ignored_class_name(class_name: str, ignored_class_names: Sequence[str] | None) -> bool:
    if ignored_class_names is None:
        return False
    ignored = {_normalize_class_name(name) for name in ignored_class_names if str(name).strip()}
    return _normalize_class_name(class_name) in ignored


def _normalize_class_name(name: str) -> str:
    return str(name).strip().lower()


def _connectivity_structure(connectivity: int) -> np.ndarray:
    if connectivity == 4:
        return np.asarray(
            [
                [0, 1, 0],
                [1, 1, 1],
                [0, 1, 0],
            ],
            dtype=np.uint8,
        )
    return np.ones((3, 3), dtype=np.uint8)


def _apply_morphology(
    mask: np.ndarray,
    *,
    structure: np.ndarray,
    opening_size: int,
    closing_size: int,
) -> np.ndarray:
    result = np.asarray(mask, dtype=bool)
    if opening_size > 1:
        opening_structure = np.ones((opening_size, opening_size), dtype=np.uint8)
        result = ndimage.binary_opening(result, structure=opening_structure)
    if closing_size > 1:
        closing_structure = np.ones((closing_size, closing_size), dtype=np.uint8)
        result = ndimage.binary_closing(result, structure=closing_structure)
    if structure is not None:
        result = ndimage.binary_fill_holes(result, structure=structure)
    return np.asarray(result, dtype=bool)
