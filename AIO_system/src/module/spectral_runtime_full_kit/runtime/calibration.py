from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from calibration.reflectance import compute_reflectance_with_diagnostics, reflectance_to_absorbance
from models.bundle import ModelBundleManifest


@dataclass(slots=True)
class RuntimeCalibrationContext:
    input_kind: str = "raw"
    dark_reference: np.ndarray | None = None
    white_reference: np.ndarray | None = None
    epsilon: float = 1e-6
    clip_min: float = 0.0
    clip_max: float = 1.5
    invalid_fill: float = 0.0
    absorbance_clip_max: float = 10.0
    reference_paths: dict[str, str] = field(default_factory=dict)

    @property
    def requires_calibration(self) -> bool:
        return normalize_runtime_input_kind(self.input_kind) in {"reflectance", "absorbance"}

    def to_summary(self) -> dict[str, object]:
        return {
            "input_kind": normalize_runtime_input_kind(self.input_kind),
            "requires_calibration": self.requires_calibration,
            "epsilon": float(self.epsilon),
            "clip_min": float(self.clip_min),
            "clip_max": float(self.clip_max),
            "invalid_fill": float(self.invalid_fill),
            "absorbance_clip_max": float(self.absorbance_clip_max),
            "reference_paths": dict(self.reference_paths),
        }


@dataclass(slots=True)
class RuntimeCalibrationResult:
    cube: np.ndarray
    summary: dict[str, object]


def normalize_runtime_input_kind(value: object) -> str:
    normalized = str(value or "raw").strip().lower()
    if normalized not in {"raw", "reflectance", "absorbance"}:
        raise ValueError("model input kind must be one of: raw, reflectance, absorbance.")
    return normalized


def resolve_model_input_kind(training_metadata: dict[str, object] | None) -> str:
    payload = training_metadata or {}
    for key in ("model_input_kind", "input_kind", "training_input_kind"):
        value = payload.get(key)
        if value is not None:
            return normalize_runtime_input_kind(value)
    return "raw"


def build_runtime_calibration_context(
    *,
    bundle_dir: Path,
    manifest: ModelBundleManifest,
) -> RuntimeCalibrationContext:
    input_kind = resolve_model_input_kind(manifest.training_metadata)
    if input_kind == "raw":
        return RuntimeCalibrationContext(input_kind="raw")

    root = Path(bundle_dir)
    dark_path = (root / manifest.calibration.dark.mean.path).resolve()
    white_path = (root / manifest.calibration.white.mean.path).resolve()
    dark = np.load(dark_path, allow_pickle=False).astype(np.float32, copy=False)
    white = np.load(white_path, allow_pickle=False).astype(np.float32, copy=False)
    if dark.ndim != 2 or white.ndim != 2:
        raise ValueError(
            "runtime calibration references must be 2D mean arrays: "
            f"dark={dark.shape!r}, white={white.shape!r}"
        )
    if dark.shape != white.shape:
        raise ValueError(
            f"runtime calibration reference shape mismatch: dark={dark.shape!r}, white={white.shape!r}"
        )

    params = _extract_calibration_params(manifest.training_metadata)
    return RuntimeCalibrationContext(
        input_kind=input_kind,
        dark_reference=np.ascontiguousarray(dark),
        white_reference=np.ascontiguousarray(white),
        epsilon=float(params.get("epsilon", 1e-6)),
        clip_min=float(params.get("clip_min", 0.0)),
        clip_max=float(params.get("clip_max", 1.5)),
        invalid_fill=float(params.get("invalid_fill", 0.0)),
        absorbance_clip_max=float(params.get("absorbance_clip_max", 10.0)),
        reference_paths={
            "dark_mean": str(dark_path),
            "white_mean": str(white_path),
        },
    )


def apply_runtime_calibration(
    cube: np.ndarray,
    context: RuntimeCalibrationContext | None,
) -> RuntimeCalibrationResult:
    array = np.asarray(cube)
    if context is None:
        return RuntimeCalibrationResult(
            cube=array,
            summary={"input_kind": "raw", "applied": False, "reason": "no_context"},
        )
    input_kind = normalize_runtime_input_kind(context.input_kind)
    if input_kind == "raw":
        return RuntimeCalibrationResult(
            cube=array,
            summary={**context.to_summary(), "applied": False, "reason": "raw_model_input"},
        )
    if context.dark_reference is None or context.white_reference is None:
        raise ValueError(f"{input_kind} runtime input requires dark and white references.")

    reflectance = compute_reflectance_with_diagnostics(
        raw_cube=array,
        dark_reference=context.dark_reference,
        white_reference=context.white_reference,
        epsilon=float(context.epsilon),
        clip_min=float(context.clip_min),
        clip_max=float(context.clip_max),
        invalid_fill=float(context.invalid_fill),
    )
    if input_kind == "reflectance":
        output = reflectance.cube
    else:
        output = reflectance_to_absorbance(
            reflectance.cube,
            epsilon=float(context.epsilon),
            clip_max=float(context.absorbance_clip_max),
        )
    return RuntimeCalibrationResult(
        cube=output,
        summary={
            **context.to_summary(),
            "applied": True,
            "diagnostics": reflectance.diagnostics.to_dict(),
            "output": _summarize_cube(output),
        },
    )


def summarize_calibration_windows(results: list[dict[str, object]]) -> dict[str, object]:
    if not results:
        return {"applied": False, "window_count": 0}
    applied = [item for item in results if bool(item.get("applied"))]
    if not applied:
        first = dict(results[0])
        first["window_count"] = len(results)
        return first
    diagnostics = [
        item.get("diagnostics")
        for item in applied
        if isinstance(item.get("diagnostics"), dict)
    ]
    summary: dict[str, object] = {
        "applied": True,
        "window_count": len(results),
        "input_kind": applied[0].get("input_kind", "raw"),
    }
    if diagnostics:
        for key in (
            "invalid_denominator_ratio",
            "negative_denominator_ratio",
            "non_finite_ratio",
            "clip_low_ratio",
            "clip_high_ratio",
        ):
            values = [float(item.get(key, 0.0)) for item in diagnostics]
            summary[f"{key}_max"] = float(np.max(values))
            summary[f"{key}_mean"] = float(np.mean(values))
    return summary


def _extract_calibration_params(training_metadata: dict[str, object]) -> dict[str, Any]:
    payload = training_metadata.get("calibration_params", {})
    return dict(payload) if isinstance(payload, dict) else {}


def _summarize_cube(cube: np.ndarray) -> dict[str, float]:
    data = np.asarray(cube, dtype=np.float32)
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        finite = np.asarray([0.0], dtype=np.float32)
    return {
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "p01": float(np.percentile(finite, 1.0)),
        "p50": float(np.percentile(finite, 50.0)),
        "p99": float(np.percentile(finite, 99.0)),
    }
