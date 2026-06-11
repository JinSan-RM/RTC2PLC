from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class PixelFilterParams:
    enable_intensity: bool = False
    intensity_band_start: int | None = None
    intensity_band_end: int | None = None
    intensity_min: float | None = None
    intensity_max: float | None = None
    intensity_min_percentile: float = 1.0
    intensity_max_percentile: float = 99.0

    enable_saturation: bool = False
    saturation_band_start: int | None = None
    saturation_band_end: int | None = None
    saturation_low: float | None = None
    saturation_high: float | None = None
    saturation_min_bands: int = 1

    enable_snv: bool = False
    snv_band_start: int | None = None
    snv_band_end: int | None = None
    snv_zmin: float = 0.0
    snv_zmax: float = 3.5
    snv_min_std: float = 1e-6


@dataclass(slots=True)
class PixelQualityResult:
    mask: np.ndarray
    summary: dict[str, object]


def compute_pixel_quality_mask(
    *,
    data: np.ndarray,
    params: PixelFilterParams,
    band_axis: int = -1,
) -> PixelQualityResult:
    array = np.asarray(data, dtype=np.float32)
    if array.ndim != 3:
        raise ValueError(f"Expected 3D data for pixel filtering, got shape={array.shape!r}")

    normalized_band_axis = int(band_axis)
    if normalized_band_axis < 0:
        normalized_band_axis += array.ndim
    if normalized_band_axis < 0 or normalized_band_axis >= array.ndim:
        raise ValueError(f"Invalid band_axis={band_axis} for shape={array.shape!r}")

    moved = np.moveaxis(array, normalized_band_axis, -1)
    shape_2d = moved.shape[:-1]
    band_count = int(moved.shape[-1])
    spectra = moved.reshape(-1, band_count)
    valid = np.all(np.isfinite(spectra), axis=1)
    combined_mask = np.ones((spectra.shape[0],), dtype=bool)

    summary: dict[str, object] = {
        "total_pixels": int(spectra.shape[0]),
        "finite_pixels": int(np.sum(valid)),
        "enabled": {
            "intensity": bool(params.enable_intensity),
            "saturation": bool(params.enable_saturation),
            "snv": bool(params.enable_snv),
        },
    }

    if params.enable_intensity:
        intensity_slice = _resolve_band_slice(
            band_count=band_count,
            start=params.intensity_band_start,
            end=params.intensity_band_end,
        )
        intensity_values = np.mean(spectra[:, intensity_slice], axis=1)
        lower = (
            float(params.intensity_min)
            if params.intensity_min is not None
            else float(np.percentile(intensity_values[valid], float(params.intensity_min_percentile)))
        )
        upper = (
            float(params.intensity_max)
            if params.intensity_max is not None
            else float(np.percentile(intensity_values[valid], float(params.intensity_max_percentile)))
        )
        intensity_keep = valid & (intensity_values >= lower) & (intensity_values <= upper)
        combined_mask &= intensity_keep
        summary["intensity"] = {
            "band_start": int(intensity_slice.start),
            "band_end": int(intensity_slice.stop - 1),
            "lower": lower,
            "upper": upper,
            "keep_pixels": int(np.sum(intensity_keep)),
            "drop_pixels": int(np.sum(valid & ~intensity_keep)),
        }

    if params.enable_saturation:
        saturation_slice = _resolve_band_slice(
            band_count=band_count,
            start=params.saturation_band_start,
            end=params.saturation_band_end,
        )
        selected = spectra[:, saturation_slice]
        low = (
            float(params.saturation_low)
            if params.saturation_low is not None
            else float(np.percentile(selected[valid], 0.1))
        )
        high = (
            float(params.saturation_high)
            if params.saturation_high is not None
            else float(np.percentile(selected[valid], 99.9))
        )
        min_bands = max(1, int(params.saturation_min_bands))
        saturated_counts = np.sum((selected <= low) | (selected >= high), axis=1)
        saturated = valid & (saturated_counts >= min_bands)
        saturation_keep = valid & ~saturated
        combined_mask &= saturation_keep
        summary["saturation"] = {
            "band_start": int(saturation_slice.start),
            "band_end": int(saturation_slice.stop - 1),
            "low": low,
            "high": high,
            "min_bands": min_bands,
            "drop_pixels": int(np.sum(saturated)),
            "keep_pixels": int(np.sum(saturation_keep)),
        }

    if params.enable_snv:
        snv_slice = _resolve_band_slice(
            band_count=band_count,
            start=params.snv_band_start,
            end=params.snv_band_end,
        )
        selected = spectra[:, snv_slice]
        mean = np.mean(selected, axis=1)
        std = np.std(selected, axis=1)
        std_ok = std > float(params.snv_min_std)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = (selected - mean[:, None]) / std[:, None]
        max_abs_z = np.max(np.abs(z), axis=1)
        zmin = float(params.snv_zmin)
        zmax = float(params.snv_zmax)
        if zmax < zmin:
            zmin, zmax = zmax, zmin
        snv_keep = valid & std_ok & (max_abs_z >= zmin) & (max_abs_z <= zmax)
        combined_mask &= snv_keep
        summary["snv"] = {
            "band_start": int(snv_slice.start),
            "band_end": int(snv_slice.stop - 1),
            "zmin": zmin,
            "zmax": zmax,
            "min_std": float(params.snv_min_std),
            "drop_pixels": int(np.sum(valid & ~snv_keep)),
            "keep_pixels": int(np.sum(snv_keep)),
        }

    final_mask = valid & combined_mask
    summary["mask_keep_pixels"] = int(np.sum(final_mask))
    summary["mask_drop_pixels"] = int(np.sum(valid & ~final_mask))
    summary["mask_keep_ratio"] = (
        float(np.sum(final_mask)) / float(np.sum(valid)) if np.sum(valid) > 0 else 0.0
    )
    summary["mask_drop_ratio"] = (
        float(np.sum(valid & ~final_mask)) / float(np.sum(valid)) if np.sum(valid) > 0 else 0.0
    )

    return PixelQualityResult(mask=final_mask.reshape(shape_2d), summary=summary)


def apply_quality_mask_to_prediction(
    *,
    class_map: np.ndarray,
    confidence_map: np.ndarray,
    mask: np.ndarray,
    unknown_index: int = -1,
) -> tuple[np.ndarray, np.ndarray]:
    class_arr = np.asarray(class_map)
    conf_arr = np.asarray(confidence_map)
    mask_arr = np.asarray(mask, dtype=bool)
    if class_arr.shape != conf_arr.shape or class_arr.shape != mask_arr.shape:
        raise ValueError("class_map, confidence_map, and mask must have matching shapes.")
    updated_class = class_arr.astype(np.int16, copy=True)
    updated_conf = conf_arr.astype(np.float32, copy=True)
    drop = ~mask_arr
    updated_class[drop] = int(unknown_index)
    updated_conf[drop] = 0.0
    return updated_class, updated_conf


def _resolve_band_slice(*, band_count: int, start: int | None, end: int | None) -> slice:
    if band_count <= 0:
        raise ValueError("band_count must be positive.")
    normalized_start = 0 if start is None else max(0, min(int(start), band_count - 1))
    normalized_end = (band_count - 1) if end is None else max(0, min(int(end), band_count - 1))
    if normalized_end < normalized_start:
        normalized_start, normalized_end = normalized_end, normalized_start
    return slice(normalized_start, normalized_end + 1)
