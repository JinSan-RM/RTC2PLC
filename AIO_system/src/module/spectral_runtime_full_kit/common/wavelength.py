from __future__ import annotations

import math
from typing import Mapping

import numpy as np


def normalize_wavelength_range(value: object) -> tuple[float, float] | None:
    if value is None:
        return None

    if isinstance(value, Mapping):
        nested = value.get("wavelength_range_nm")
        normalized_nested = normalize_wavelength_range(nested)
        if normalized_nested is not None:
            return normalized_nested
        return _normalize_pair(value.get("wavelength_start_nm"), value.get("wavelength_end_nm"))

    if isinstance(value, (list, tuple)) and len(value) == 2:
        return _normalize_pair(value[0], value[1])

    return None


def resolve_wavelength_range(*candidates: object) -> tuple[float, float] | None:
    for candidate in candidates:
        normalized = normalize_wavelength_range(candidate)
        if normalized is not None:
            return normalized
    return None


def wavelength_for_band(
    *,
    band_index: int,
    band_count: int,
    wavelength_range_nm: tuple[float, float] | None,
) -> float | None:
    if wavelength_range_nm is None:
        return None
    if band_count <= 0 or band_index < 0 or band_index >= band_count:
        return None

    start_nm, end_nm = wavelength_range_nm
    if band_count == 1:
        return float(start_nm)
    ratio = float(band_index) / float(band_count - 1)
    return float(start_nm + (end_nm - start_nm) * ratio)


def build_wavelength_axis(
    *,
    band_count: int,
    wavelength_range_nm: tuple[float, float] | None,
) -> np.ndarray | None:
    if wavelength_range_nm is None or band_count <= 0:
        return None

    start_nm, end_nm = wavelength_range_nm
    if band_count == 1:
        return np.asarray([float(start_nm)], dtype=np.float32)
    return np.linspace(float(start_nm), float(end_nm), num=int(band_count), dtype=np.float32)


def _normalize_pair(start_raw: object, end_raw: object) -> tuple[float, float] | None:
    try:
        start = float(start_raw)  # type: ignore[arg-type]
        end = float(end_raw)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return None

    if not math.isfinite(start) or not math.isfinite(end):
        return None
    if end <= start:
        return None
    return (float(start), float(end))
