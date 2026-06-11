from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class ReflectanceDiagnostics:
    invalid_denominator_ratio: float
    negative_denominator_ratio: float
    non_finite_ratio: float
    clip_low_ratio: float
    clip_high_ratio: float
    denominator_min: float
    denominator_p01: float
    denominator_mean: float
    denominator_p99: float
    denominator_max: float
    reflectance_min: float
    reflectance_p01: float
    reflectance_p50: float
    reflectance_p99: float
    reflectance_max: float

    def to_dict(self) -> dict[str, float]:
        return {
            "invalid_denominator_ratio": float(self.invalid_denominator_ratio),
            "negative_denominator_ratio": float(self.negative_denominator_ratio),
            "non_finite_ratio": float(self.non_finite_ratio),
            "clip_low_ratio": float(self.clip_low_ratio),
            "clip_high_ratio": float(self.clip_high_ratio),
            "denominator_min": float(self.denominator_min),
            "denominator_p01": float(self.denominator_p01),
            "denominator_mean": float(self.denominator_mean),
            "denominator_p99": float(self.denominator_p99),
            "denominator_max": float(self.denominator_max),
            "reflectance_min": float(self.reflectance_min),
            "reflectance_p01": float(self.reflectance_p01),
            "reflectance_p50": float(self.reflectance_p50),
            "reflectance_p99": float(self.reflectance_p99),
            "reflectance_max": float(self.reflectance_max),
        }


@dataclass(slots=True)
class ReflectanceResult:
    cube: np.ndarray
    valid_denominator_mask: np.ndarray
    diagnostics: ReflectanceDiagnostics


def compute_reflectance(
    raw_cube: np.ndarray,
    dark_reference: np.ndarray,
    white_reference: np.ndarray,
    *,
    epsilon: float = 1e-6,
    clip_min: float = 0.0,
    clip_max: float = 1.5,
    invalid_fill: float = 0.0,
) -> np.ndarray:
    return compute_reflectance_with_diagnostics(
        raw_cube=raw_cube,
        dark_reference=dark_reference,
        white_reference=white_reference,
        epsilon=epsilon,
        clip_min=clip_min,
        clip_max=clip_max,
        invalid_fill=invalid_fill,
    ).cube


def compute_reflectance_with_diagnostics(
    raw_cube: np.ndarray,
    dark_reference: np.ndarray,
    white_reference: np.ndarray,
    *,
    epsilon: float = 1e-6,
    clip_min: float = 0.0,
    clip_max: float = 1.5,
    invalid_fill: float = 0.0,
) -> ReflectanceResult:
    if epsilon <= 0:
        raise ValueError("epsilon must be positive.")
    if clip_max <= clip_min:
        raise ValueError("clip_max must be greater than clip_min.")

    cube = _normalize_cube(raw_cube, "raw_cube")
    dark = _normalize_reference(dark_reference, cube.shape[1:], "dark_reference")
    white = _normalize_reference(white_reference, cube.shape[1:], "white_reference")

    denominator = white - dark
    valid_mask = np.abs(denominator) >= epsilon
    safe_denominator = np.where(valid_mask, denominator, 1.0)
    raw_reflectance = (cube - dark) / safe_denominator
    raw_reflectance = np.where(valid_mask, raw_reflectance, invalid_fill)
    diagnostics = _build_reflectance_diagnostics(
        denominator=denominator,
        valid_mask=valid_mask,
        raw_reflectance=raw_reflectance,
        clip_min=clip_min,
        clip_max=clip_max,
    )
    reflectance = np.clip(raw_reflectance, clip_min, clip_max)
    return ReflectanceResult(
        cube=np.ascontiguousarray(reflectance.astype(np.float32, copy=False)),
        valid_denominator_mask=np.ascontiguousarray(valid_mask.astype(bool, copy=False)),
        diagnostics=diagnostics,
    )


def reflectance_to_absorbance(
    reflectance_cube: np.ndarray,
    *,
    epsilon: float = 1e-6,
    clip_max: float = 10.0,
) -> np.ndarray:
    if epsilon <= 0:
        raise ValueError("epsilon must be positive.")
    if clip_max <= 0:
        raise ValueError("clip_max must be positive.")

    reflectance = _normalize_cube(reflectance_cube, "reflectance_cube")
    safe_reflectance = np.clip(reflectance, epsilon, None)
    absorbance = -np.log10(safe_reflectance)
    absorbance = np.clip(absorbance, 0.0, clip_max)
    return np.ascontiguousarray(absorbance.astype(np.float32, copy=False))


def _normalize_cube(cube: np.ndarray, name: str) -> np.ndarray:
    if cube.ndim != 3:
        raise ValueError(f"{name} must be a 3D array (frame_count, band_count, spatial_width).")
    if cube.shape[0] <= 0 or cube.shape[1] <= 0 or cube.shape[2] <= 0:
        raise ValueError(f"{name} must have positive dimensions, got shape={cube.shape!r}.")
    return cube.astype(np.float32, copy=False)


def _normalize_reference(
    reference: np.ndarray,
    expected_hw: tuple[int, int],
    name: str,
) -> np.ndarray:
    normalized = reference.astype(np.float32, copy=False)
    if normalized.ndim == 2:
        if normalized.shape != expected_hw:
            raise ValueError(
                f"{name} shape mismatch: expected {expected_hw!r}, got {normalized.shape!r}."
            )
        return normalized[None, :, :]

    if normalized.ndim == 3:
        if normalized.shape[1:] != expected_hw:
            raise ValueError(
                f"{name} shape mismatch: expected frame axis + {expected_hw!r}, "
                f"got {normalized.shape!r}."
            )
        return normalized

    raise ValueError(f"{name} must be 2D or 3D, got ndim={normalized.ndim}.")


def _build_reflectance_diagnostics(
    *,
    denominator: np.ndarray,
    valid_mask: np.ndarray,
    raw_reflectance: np.ndarray,
    clip_min: float,
    clip_max: float,
) -> ReflectanceDiagnostics:
    den = denominator.astype(np.float32, copy=False)
    finite_den = den[np.isfinite(den)]
    if finite_den.size == 0:
        finite_den = np.asarray([0.0], dtype=np.float32)

    finite_ref_mask = np.isfinite(raw_reflectance)
    finite_ref = raw_reflectance[finite_ref_mask]
    if finite_ref.size == 0:
        finite_ref = np.asarray([0.0], dtype=np.float32)

    return ReflectanceDiagnostics(
        invalid_denominator_ratio=float(1.0 - np.mean(valid_mask)),
        negative_denominator_ratio=float(np.mean(den < 0.0)),
        non_finite_ratio=float(1.0 - np.mean(finite_ref_mask)),
        clip_low_ratio=float(np.mean(finite_ref < float(clip_min))),
        clip_high_ratio=float(np.mean(finite_ref > float(clip_max))),
        denominator_min=float(np.min(finite_den)),
        denominator_p01=float(np.percentile(finite_den, 1.0)),
        denominator_mean=float(np.mean(finite_den)),
        denominator_p99=float(np.percentile(finite_den, 99.0)),
        denominator_max=float(np.max(finite_den)),
        reflectance_min=float(np.min(finite_ref)),
        reflectance_p01=float(np.percentile(finite_ref, 1.0)),
        reflectance_p50=float(np.percentile(finite_ref, 50.0)),
        reflectance_p99=float(np.percentile(finite_ref, 99.0)),
        reflectance_max=float(np.max(finite_ref)),
    )
