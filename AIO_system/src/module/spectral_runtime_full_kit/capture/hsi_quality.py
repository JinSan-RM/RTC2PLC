from __future__ import annotations

from typing import Any, Mapping

import numpy as np


def compute_hsi_quality_summary(
    cube: np.ndarray,
    *,
    high_clip_ratio: float = 0.99,
    low_clip_ratio: float = 0.01,
    dead_band_std_epsilon: float = 1e-6,
    head_count: int = 12,
) -> dict[str, object]:
    array = np.asarray(cube)
    if array.ndim != 3:
        raise ValueError(f"Expected 3D cube (frame, band, spatial), got shape={array.shape!r}")

    frame_count, band_count, spatial_width = int(array.shape[0]), int(array.shape[1]), int(array.shape[2])
    if frame_count <= 0 or band_count <= 0 or spatial_width <= 0:
        raise ValueError(f"Invalid cube shape for quality summary: {array.shape!r}")

    values = array.astype(np.float32, copy=False)
    frame_means = np.mean(values, axis=(1, 2))
    band_means = np.mean(values, axis=(0, 2))
    band_stds = np.std(values, axis=(0, 2))
    flat = values.reshape(-1)

    dtype = array.dtype
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        sensor_min = float(info.min)
        sensor_max = float(info.max)
        sensor_bits = int(info.bits)
    else:
        sensor_min = float(np.min(flat))
        sensor_max = float(np.max(flat))
        sensor_bits = None

    high_ratio = float(np.clip(high_clip_ratio, 0.0, 1.0))
    low_ratio = float(np.clip(low_clip_ratio, 0.0, 1.0))
    if low_ratio > high_ratio:
        low_ratio, high_ratio = high_ratio, low_ratio
    sensor_span = max(sensor_max - sensor_min, 1e-12)
    high_threshold = sensor_min + sensor_span * high_ratio
    low_threshold = sensor_min + sensor_span * low_ratio

    sat_high_ratio = float(np.mean(values >= high_threshold))
    sat_low_ratio = float(np.mean(values <= low_threshold))
    band_high_saturation_ratio = np.mean(values >= high_threshold, axis=(0, 2))

    p01 = float(np.percentile(flat, 1.0))
    p50 = float(np.percentile(flat, 50.0))
    p99 = float(np.percentile(flat, 99.0))
    used_dynamic_range = max(0.0, p99 - p01)
    dynamic_range_ratio = float(used_dynamic_range / sensor_span) if sensor_span > 0 else 0.0

    frame_mean_mean = float(np.mean(frame_means))
    frame_mean_std = float(np.std(frame_means))
    frame_mean_cv = float(frame_mean_std / max(abs(frame_mean_mean), 1e-12))

    dead_band_count = int(np.sum(band_stds <= float(dead_band_std_epsilon)))
    dead_band_ratio = float(dead_band_count / max(1, band_count))
    max_saturated_band_index = int(np.argmax(band_high_saturation_ratio))
    max_saturated_band_ratio = float(band_high_saturation_ratio[max_saturated_band_index])

    exposure_status = _resolve_exposure_status(
        sat_high_ratio=sat_high_ratio,
        sat_low_ratio=sat_low_ratio,
        dynamic_range_ratio=dynamic_range_ratio,
    )

    head = max(1, min(int(head_count), band_count))
    return {
        "schema_version": "hsi_quality.v1",
        "shape": {
            "frame_count": frame_count,
            "band_count": band_count,
            "spatial_width": spatial_width,
        },
        "dtype": str(dtype),
        "sensor_range": {
            "min": sensor_min,
            "max": sensor_max,
            "bits": sensor_bits,
        },
        "intensity": {
            "min": float(np.min(flat)),
            "max": float(np.max(flat)),
            "mean": float(np.mean(flat)),
            "std": float(np.std(flat)),
            "p01": p01,
            "p50": p50,
            "p99": p99,
        },
        "saturation": {
            "high_threshold": high_threshold,
            "low_threshold": low_threshold,
            "high_ratio": sat_high_ratio,
            "low_ratio": sat_low_ratio,
            "max_saturated_band_index": max_saturated_band_index,
            "max_saturated_band_ratio": max_saturated_band_ratio,
            "band_high_ratio_head": [
                float(v) for v in band_high_saturation_ratio[:head].tolist()
            ],
        },
        "dynamic_range": {
            "used": used_dynamic_range,
            "total": sensor_span,
            "used_ratio": dynamic_range_ratio,
        },
        "temporal": {
            "frame_mean_min": float(np.min(frame_means)),
            "frame_mean_max": float(np.max(frame_means)),
            "frame_mean_std": frame_mean_std,
            "frame_mean_cv": frame_mean_cv,
        },
        "spectral": {
            "dead_band_count": dead_band_count,
            "dead_band_ratio": dead_band_ratio,
            "band_mean_head": [float(v) for v in band_means[:head].tolist()],
            "band_std_head": [float(v) for v in band_stds[:head].tolist()],
        },
        "exposure_status": exposure_status,
    }


def format_hsi_quality_brief(summary: Mapping[str, Any] | None) -> str:
    if not isinstance(summary, Mapping):
        return "hsi_quality=n/a"
    status = str(summary.get("exposure_status", "unknown"))

    saturation = summary.get("saturation", {})
    if not isinstance(saturation, Mapping):
        saturation = {}
    dynamic = summary.get("dynamic_range", {})
    if not isinstance(dynamic, Mapping):
        dynamic = {}

    high_ratio = _to_float(saturation.get("high_ratio"), 0.0)
    low_ratio = _to_float(saturation.get("low_ratio"), 0.0)
    used_ratio = _to_float(dynamic.get("used_ratio"), 0.0)
    return (
        "hsi_quality:"
        f" status={status},"
        f" sat_high={high_ratio * 100.0:.2f}%,"
        f" sat_low={low_ratio * 100.0:.2f}%,"
        f" dynamic_used={used_ratio * 100.0:.2f}%"
    )


def _resolve_exposure_status(
    *,
    sat_high_ratio: float,
    sat_low_ratio: float,
    dynamic_range_ratio: float,
) -> str:
    if sat_high_ratio >= 0.01:
        return "high_clip_risk"
    if sat_low_ratio >= 0.60:
        return "low_clip_risk"
    if dynamic_range_ratio < 0.10:
        return "low_contrast"
    return "ok"


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return float(default)

