from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


DEFAULT_IGNORED_CLASS_NAMES: tuple[str, ...] = ("background",)

DEFAULT_CLASS_COLORS: tuple[tuple[int, int, int], ...] = (
    (230, 57, 70),
    (29, 53, 87),
    (69, 123, 157),
    (42, 157, 143),
    (233, 196, 106),
    (244, 162, 97),
    (38, 70, 83),
)


@dataclass(slots=True)
class PixelInferenceResult:
    class_map: np.ndarray
    confidence_map: np.ndarray
    class_names: list[str]
    threshold: float
    unknown_index: int = -1
    low_confidence_pixels: int = 0
    ignored_pixels: int = 0
    invalid_x_pixels: int = 0


def infer_pixel_map(
    *,
    model: Any,
    cube: np.ndarray,
    confidence_threshold: float = 0.0,
    batch_size: int = 8192,
    unknown_index: int = -1,
    ignored_class_names: Sequence[str] | None = DEFAULT_IGNORED_CLASS_NAMES,
    valid_x_min: int | None = None,
    valid_x_max: int | None = None,
) -> PixelInferenceResult:
    frame_count, _band_count, spatial_width, spectra = _prepare_pixel_spectra(cube)
    threshold = _normalize_confidence_threshold(confidence_threshold)
    normalized_batch_size = max(1, int(batch_size))

    predicted_chunks: list[np.ndarray] = []
    probability_chunks: list[np.ndarray] = []
    for start in range(0, spectra.shape[0], normalized_batch_size):
        stop = min(start + normalized_batch_size, spectra.shape[0])
        chunk = spectra[start:stop]
        predicted_chunks.append(np.asarray(model.predict(chunk), dtype=np.int64))
        probability_chunks.append(np.asarray(model.predict_proba(chunk), dtype=np.float32))

    predicted = np.concatenate(predicted_chunks, axis=0)
    probabilities = np.concatenate(probability_chunks, axis=0)
    return _build_pixel_inference_result(
        model=model,
        predicted=predicted,
        probabilities=probabilities,
        frame_count=frame_count,
        spatial_width=spatial_width,
        threshold=threshold,
        unknown_index=unknown_index,
        ignored_class_names=ignored_class_names,
        valid_x_min=valid_x_min,
        valid_x_max=valid_x_max,
    )


def infer_pixel_map_from_probabilities(
    *,
    model: Any,
    cube: np.ndarray,
    confidence_threshold: float = 0.0,
    batch_size: int = 8192,
    unknown_index: int = -1,
    ignored_class_names: Sequence[str] | None = DEFAULT_IGNORED_CLASS_NAMES,
    valid_x_min: int | None = None,
    valid_x_max: int | None = None,
) -> PixelInferenceResult:
    """Infer a pixel map using one probability pass.

    PLS-DA predicts classes with argmax over the same score/probability order, so
    smooth live preview can avoid running both predict() and predict_proba().
    """
    frame_count, _band_count, spatial_width, spectra = _prepare_pixel_spectra(cube)
    threshold = _normalize_confidence_threshold(confidence_threshold)
    normalized_batch_size = max(1, int(batch_size))

    probability_chunks: list[np.ndarray] = []
    for start in range(0, spectra.shape[0], normalized_batch_size):
        stop = min(start + normalized_batch_size, spectra.shape[0])
        probability_chunks.append(np.asarray(model.predict_proba(spectra[start:stop]), dtype=np.float32))

    probabilities = np.concatenate(probability_chunks, axis=0)
    if probabilities.ndim != 2:
        raise ValueError(f"Expected predict_proba output to be 2D, got shape={probabilities.shape!r}")
    predicted = np.argmax(probabilities, axis=1).astype(np.int64, copy=False)
    return _build_pixel_inference_result(
        model=model,
        predicted=predicted,
        probabilities=probabilities,
        frame_count=frame_count,
        spatial_width=spatial_width,
        threshold=threshold,
        unknown_index=unknown_index,
        ignored_class_names=ignored_class_names,
        valid_x_min=valid_x_min,
        valid_x_max=valid_x_max,
    )


def _prepare_pixel_spectra(cube: np.ndarray) -> tuple[int, int, int, np.ndarray]:
    cube = np.asarray(cube)
    if cube.ndim != 3:
        raise ValueError("Expected cube shaped as (frame_count, band_count, spatial_width).")
    if cube.shape[0] <= 0 or cube.shape[1] <= 0 or cube.shape[2] <= 0:
        raise ValueError(f"Invalid cube shape: {cube.shape!r}")

    frame_count, band_count, spatial_width = cube.shape
    spectra = np.transpose(cube, (0, 2, 1)).reshape(-1, band_count).astype(np.float32, copy=False)
    return int(frame_count), int(band_count), int(spatial_width), spectra


def _normalize_confidence_threshold(confidence_threshold: float) -> float:
    threshold = float(confidence_threshold)
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError(f"confidence_threshold must be in [0, 1], got {threshold}.")
    return threshold


def _build_pixel_inference_result(
    *,
    model: Any,
    predicted: np.ndarray,
    probabilities: np.ndarray,
    frame_count: int,
    spatial_width: int,
    threshold: float,
    unknown_index: int,
    ignored_class_names: Sequence[str] | None,
    valid_x_min: int | None,
    valid_x_max: int | None,
) -> PixelInferenceResult:
    if probabilities.ndim != 2:
        raise ValueError(f"Expected predict_proba output to be 2D, got shape={probabilities.shape!r}")
    if probabilities.shape[0] != predicted.shape[0]:
        raise ValueError(
            "predict and predict_proba sample counts do not match: "
            f"{predicted.shape[0]} != {probabilities.shape[0]}"
        )
    if probabilities.shape[1] <= 0:
        raise ValueError("predict_proba must return at least one class column.")

    class_names = _resolve_class_names(model=model, n_classes=probabilities.shape[1])
    confidence = np.max(probabilities, axis=1).astype(np.float32, copy=False)
    ignored_indices = _ignored_class_indices(class_names=class_names, ignored_class_names=ignored_class_names)
    low_confidence_mask = confidence < threshold
    if ignored_indices:
        ignored_prediction_mask = np.isin(predicted, np.asarray(sorted(ignored_indices), dtype=np.int64))
    else:
        ignored_prediction_mask = np.zeros(predicted.shape, dtype=bool)
    valid_x_exclusion_mask = _build_valid_x_exclusion_mask(
        frame_count=frame_count,
        spatial_width=spatial_width,
        valid_x_min=valid_x_min,
        valid_x_max=valid_x_max,
    ).reshape(-1)

    class_map_flat = predicted.astype(np.int16, copy=True)
    unknown_mask = low_confidence_mask | ignored_prediction_mask | valid_x_exclusion_mask
    class_map_flat[unknown_mask] = int(unknown_index)

    low_confidence_count = int(np.sum(low_confidence_mask & ~ignored_prediction_mask & ~valid_x_exclusion_mask))
    ignored_count = int(np.sum(ignored_prediction_mask))
    invalid_x_count = int(np.sum(valid_x_exclusion_mask & ~ignored_prediction_mask))

    class_map = class_map_flat.reshape(frame_count, spatial_width)
    confidence_map = confidence.reshape(frame_count, spatial_width)
    return PixelInferenceResult(
        class_map=class_map,
        confidence_map=confidence_map,
        class_names=class_names,
        threshold=threshold,
        unknown_index=int(unknown_index),
        low_confidence_pixels=low_confidence_count,
        ignored_pixels=ignored_count,
        invalid_x_pixels=invalid_x_count,
    )


def summarize_pixel_map(result: PixelInferenceResult) -> dict[str, object]:
    class_map = np.asarray(result.class_map)
    confidence = np.asarray(result.confidence_map)
    if class_map.shape != confidence.shape:
        raise ValueError("class_map and confidence_map must have matching shapes.")

    total_pixels = int(class_map.size)
    unknown_count = int(np.sum(class_map == result.unknown_index))
    known_mask = class_map != result.unknown_index
    known_count = int(np.sum(known_mask))
    low_confidence_count = max(0, int(result.low_confidence_pixels))
    ignored_count = max(0, int(result.ignored_pixels))
    invalid_x_count = max(0, int(result.invalid_x_pixels))
    reason_count = low_confidence_count + ignored_count + invalid_x_count
    if reason_count <= 0 and unknown_count > 0:
        actionable_unknown_count = unknown_count
    else:
        actionable_unknown_count = low_confidence_count

    per_class_rows: list[dict[str, object]] = []
    for class_index, class_name in enumerate(result.class_names):
        count = int(np.sum(class_map == class_index))
        per_class_rows.append(
            {
                "class_index": class_index,
                "class_name": class_name,
                "pixel_count": count,
                "pixel_ratio": (float(count) / float(total_pixels)) if total_pixels > 0 else 0.0,
            }
        )

    if known_count > 0:
        known_conf = confidence[known_mask]
        confidence_stats = {
            "mean": float(np.mean(known_conf)),
            "std": float(np.std(known_conf)),
            "p05": float(np.percentile(known_conf, 5)),
            "p95": float(np.percentile(known_conf, 95)),
        }
    else:
        confidence_stats = {"mean": 0.0, "std": 0.0, "p05": 0.0, "p95": 0.0}

    return {
        "frame_count": int(class_map.shape[0]),
        "spatial_width": int(class_map.shape[1]),
        "total_pixels": total_pixels,
        "known_pixels": known_count,
        "unknown_pixels": unknown_count,
        "unknown_ratio": (float(unknown_count) / float(total_pixels)) if total_pixels > 0 else 0.0,
        "low_confidence_pixels": low_confidence_count,
        "low_confidence_ratio": (float(low_confidence_count) / float(total_pixels)) if total_pixels > 0 else 0.0,
        "ignored_pixels": ignored_count,
        "ignored_ratio": (float(ignored_count) / float(total_pixels)) if total_pixels > 0 else 0.0,
        "invalid_x_pixels": invalid_x_count,
        "invalid_x_ratio": (float(invalid_x_count) / float(total_pixels)) if total_pixels > 0 else 0.0,
        "actionable_unknown_pixels": actionable_unknown_count,
        "actionable_unknown_ratio": (
            float(actionable_unknown_count) / float(total_pixels) if total_pixels > 0 else 0.0
        ),
        "threshold": float(result.threshold),
        "class_names": list(result.class_names),
        "per_class": per_class_rows,
        "confidence_stats_known_pixels": confidence_stats,
    }


def build_pixel_overlay(
    *,
    preview: np.ndarray,
    class_map: np.ndarray,
    confidence_map: np.ndarray,
    alpha: float = 0.45,
    unknown_index: int = -1,
    class_colors: dict[int, tuple[int, int, int]] | None = None,
) -> np.ndarray:
    preview_array = np.asarray(preview)
    class_map_array = np.asarray(class_map)
    confidence_array = np.asarray(confidence_map)

    if preview_array.ndim != 3 or preview_array.shape[2] != 3:
        raise ValueError("Expected preview image shaped as (frame_count, spatial_width, 3).")
    if class_map_array.shape != preview_array.shape[:2]:
        raise ValueError("class_map shape must match preview spatial shape.")
    if confidence_array.shape != class_map_array.shape:
        raise ValueError("confidence_map shape must match class_map shape.")

    normalized_alpha = float(alpha)
    if normalized_alpha < 0.0 or normalized_alpha > 1.0:
        raise ValueError(f"alpha must be in [0, 1], got {normalized_alpha}.")

    overlay = preview_array.astype(np.float32, copy=True)
    known_indices = class_map_array[class_map_array >= 0]
    if known_indices.size > 0:
        n_classes = int(np.max(known_indices)) + 1
    else:
        n_classes = 0
    colors = class_colors or _build_default_color_map(n_classes)
    for class_index, color in colors.items():
        mask = class_map_array == int(class_index)
        if not np.any(mask):
            continue
        confidence_scale = np.clip(confidence_array[mask], 0.0, 1.0) * normalized_alpha
        class_color = np.asarray(color, dtype=np.float32).reshape(1, 3)
        base = overlay[mask]
        overlay[mask] = (base * (1.0 - confidence_scale[:, None])) + (class_color * confidence_scale[:, None])

    unknown_mask = class_map_array == int(unknown_index)
    if np.any(unknown_mask):
        overlay[unknown_mask] = overlay[unknown_mask] * 0.75

    return np.clip(np.round(overlay), 0, 255).astype(np.uint8, copy=False)


def _resolve_class_names(*, model: Any, n_classes: int) -> list[str]:
    class_names: list[str] | None = None
    if hasattr(model, "class_names"):
        try:
            maybe = list(getattr(model, "class_names"))
            class_names = [str(name) for name in maybe]
        except Exception:
            class_names = None
    if class_names is None and hasattr(model, "classifier"):
        classifier = getattr(model, "classifier")
        if classifier is not None and hasattr(classifier, "class_names"):
            try:
                maybe = list(classifier.class_names)
                class_names = [str(name) for name in maybe]
            except Exception:
                class_names = None

    if class_names is None:
        class_names = [f"class_{index}" for index in range(n_classes)]
    if len(class_names) != n_classes:
        class_names = [f"class_{index}" for index in range(n_classes)]
    return class_names


def _ignored_class_indices(
    *,
    class_names: Sequence[str],
    ignored_class_names: Sequence[str] | None,
) -> set[int]:
    if ignored_class_names is None:
        return set()
    ignored = {_normalize_class_name(name) for name in ignored_class_names if str(name).strip()}
    if not ignored:
        return set()
    return {index for index, class_name in enumerate(class_names) if _normalize_class_name(class_name) in ignored}


def _normalize_class_name(name: str) -> str:
    return str(name).strip().lower()


def _build_valid_x_exclusion_mask(
    *,
    frame_count: int,
    spatial_width: int,
    valid_x_min: int | None,
    valid_x_max: int | None,
) -> np.ndarray:
    x_min, x_max = _normalize_valid_x_range(
        spatial_width=spatial_width,
        valid_x_min=valid_x_min,
        valid_x_max=valid_x_max,
    )
    mask = np.zeros((int(frame_count), int(spatial_width)), dtype=bool)
    if x_min > 0:
        mask[:, :x_min] = True
    if x_max < spatial_width:
        mask[:, x_max:] = True
    return mask


def _normalize_valid_x_range(
    *,
    spatial_width: int,
    valid_x_min: int | None,
    valid_x_max: int | None,
) -> tuple[int, int]:
    width = int(spatial_width)
    if width <= 0:
        raise ValueError(f"spatial_width must be positive, got {width}.")
    x_min = 0 if valid_x_min is None else int(valid_x_min)
    x_max = width if valid_x_max is None or int(valid_x_max) <= 0 else int(valid_x_max)
    x_min = min(max(0, x_min), width)
    x_max = min(max(0, x_max), width)
    if x_min >= x_max:
        raise ValueError(f"valid x range must contain at least one pixel, got [{x_min}, {x_max}) for width={width}.")
    return x_min, x_max


def _build_default_color_map(n_classes: int) -> dict[int, tuple[int, int, int]]:
    normalized_classes = max(0, int(n_classes))
    return {
        class_index: DEFAULT_CLASS_COLORS[class_index % len(DEFAULT_CLASS_COLORS)]
        for class_index in range(normalized_classes)
    }
