from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(slots=True)
class ObjectBox:
    object_id: str
    class_name: str
    bbox_xywh: tuple[float, float, float, float]
    confidence: float | None = None
    source: str | None = None


def evaluate_object_detections(
    *,
    detections: Iterable[ObjectBox],
    ground_truths: Iterable[ObjectBox],
    iou_threshold: float = 0.5,
    class_aware: bool = True,
) -> dict[str, object]:
    threshold = float(iou_threshold)
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError(f"iou_threshold must be in [0, 1], got {threshold}.")

    det_rows = sorted(
        list(detections),
        key=lambda item: float(item.confidence) if item.confidence is not None else 0.0,
        reverse=True,
    )
    gt_rows = list(ground_truths)
    matched_gt: set[int] = set()
    matches: list[dict[str, object]] = []
    false_positives: list[dict[str, object]] = []

    for det_index, det in enumerate(det_rows):
        best_index = -1
        best_iou = 0.0
        for gt_index, gt in enumerate(gt_rows):
            if gt_index in matched_gt:
                continue
            if class_aware and _normalize_class(det.class_name) != _normalize_class(gt.class_name):
                continue
            iou = bbox_iou_xywh(det.bbox_xywh, gt.bbox_xywh)
            if iou > best_iou:
                best_iou = iou
                best_index = gt_index

        if best_index >= 0 and best_iou >= threshold:
            matched_gt.add(best_index)
            gt = gt_rows[best_index]
            matches.append(
                {
                    "detection_id": det.object_id,
                    "ground_truth_id": gt.object_id,
                    "class": det.class_name,
                    "iou": best_iou,
                    "confidence": det.confidence,
                }
            )
        else:
            false_positives.append(_box_to_payload(det, index=det_index))

    false_negatives = [
        _box_to_payload(gt, index=gt_index)
        for gt_index, gt in enumerate(gt_rows)
        if gt_index not in matched_gt
    ]

    per_class = _build_per_class_metrics(
        detections=det_rows,
        ground_truths=gt_rows,
        matches=matches,
        false_positives=false_positives,
        false_negatives=false_negatives,
    )
    tp = len(matches)
    fp = len(false_positives)
    fn = len(false_negatives)
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    f1 = _f1(precision, recall)

    return {
        "iou_threshold": threshold,
        "class_aware": bool(class_aware),
        "total_detections": len(det_rows),
        "total_ground_truths": len(gt_rows),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "macro_precision": _mean([row["precision"] for row in per_class.values()]),
        "macro_recall": _mean([row["recall"] for row in per_class.values()]),
        "macro_f1": _mean([row["f1"] for row in per_class.values()]),
        "per_class": per_class,
        "matches": matches,
        "unmatched_detections": false_positives,
        "unmatched_ground_truths": false_negatives,
    }


def bbox_iou_xywh(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    lx, ly, lw, lh = _normalize_bbox(left)
    rx, ry, rw, rh = _normalize_bbox(right)
    left_x2 = lx + lw
    left_y2 = ly + lh
    right_x2 = rx + rw
    right_y2 = ry + rh

    inter_w = max(0.0, min(left_x2, right_x2) - max(lx, rx))
    inter_h = max(0.0, min(left_y2, right_y2) - max(ly, ry))
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0
    union = (lw * lh) + (rw * rh) - inter_area
    return _safe_ratio(inter_area, union)


def object_box_from_payload(payload: dict[str, Any], *, default_id: str, source: str | None = None) -> ObjectBox:
    bbox = payload.get("bbox")
    if not isinstance(bbox, list | tuple) or len(bbox) < 4:
        raise ValueError(f"object bbox must be a 4-item list, got {bbox!r}.")
    class_name = payload.get("class", payload.get("class_name", "unknown"))
    confidence = payload.get("confidence")
    return ObjectBox(
        object_id=str(payload.get("object_id", payload.get("id", default_id))),
        class_name=str(class_name),
        bbox_xywh=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
        confidence=float(confidence) if isinstance(confidence, int | float) else None,
        source=source,
    )


def _build_per_class_metrics(
    *,
    detections: list[ObjectBox],
    ground_truths: list[ObjectBox],
    matches: list[dict[str, object]],
    false_positives: list[dict[str, object]],
    false_negatives: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    class_names = {
        _normalize_class(item.class_name): item.class_name
        for item in [*detections, *ground_truths]
    }
    for row in [*false_positives, *false_negatives]:
        class_names.setdefault(_normalize_class(str(row.get("class", "unknown"))), str(row.get("class", "unknown")))

    result: dict[str, dict[str, object]] = {}
    for normalized, display_name in sorted(class_names.items()):
        tp = sum(1 for row in matches if _normalize_class(str(row.get("class", ""))) == normalized)
        fp = sum(1 for row in false_positives if _normalize_class(str(row.get("class", ""))) == normalized)
        fn = sum(1 for row in false_negatives if _normalize_class(str(row.get("class", ""))) == normalized)
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        result[display_name] = {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
        }
    return result


def _box_to_payload(item: ObjectBox, *, index: int) -> dict[str, object]:
    return {
        "index": int(index),
        "id": item.object_id,
        "class": item.class_name,
        "bbox": [float(v) for v in item.bbox_xywh],
        "confidence": item.confidence,
        "source": item.source,
    }


def _normalize_bbox(value: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x, y, w, h = value
    return float(x), float(y), max(0.0, float(w)), max(0.0, float(h))


def _normalize_class(value: str) -> str:
    return str(value).strip().lower()


def _safe_ratio(numerator: float, denominator: float) -> float:
    if float(denominator) <= 0.0:
        return 0.0
    return float(numerator) / float(denominator)


def _f1(precision: float, recall: float) -> float:
    return _safe_ratio(2.0 * float(precision) * float(recall), float(precision) + float(recall))


def _mean(values: Iterable[float]) -> float:
    rows = [float(value) for value in values]
    if not rows:
        return 0.0
    return sum(rows) / float(len(rows))

