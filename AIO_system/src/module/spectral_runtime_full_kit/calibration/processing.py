from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from calibration.qc import (
    ReferencePairQcReport,
    ReferenceQcThresholds,
    build_reference_pair_qc_payload,
    evaluate_reference_pair_qc,
    judge_reference_pair_qc,
)
from calibration.references import load_reference_bundle
from calibration.reflectance import compute_reflectance_with_diagnostics, reflectance_to_absorbance
from capture.replay import load_manifest
from common.paths import ensure_directory, make_session_dir
from features.bands import build_pseudo_rgb_preview, resolve_rgb_bands, save_preview_png


@dataclass(slots=True)
class CalibrationParameters:
    mode: str = "both"
    epsilon: float = 1e-6
    clip_min: float = 0.0
    clip_max: float = 1.5
    invalid_fill: float = 0.0
    absorbance_clip_max: float = 10.0

    def normalized_mode(self) -> str:
        mode = self.mode.strip().lower()
        if mode not in {"both", "reflectance", "absorbance"}:
            raise ValueError("mode must be one of: both, reflectance, absorbance.")
        return mode

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.normalized_mode()
        return payload


@dataclass(slots=True)
class CalibrationRunResult:
    output_dir: Path
    manifest_path: Path
    preview_path: Path
    frame_count: int
    has_reflectance: bool
    has_absorbance: bool


def run_session_calibration(
    *,
    session_dir: Path,
    dark_reference_dir: Path,
    white_reference_dir: Path,
    output_root: Path,
    parameters: CalibrationParameters,
    rgb_bands: Iterable[int] | None = None,
) -> CalibrationRunResult:
    mode = parameters.normalized_mode()

    session_manifest = load_manifest(session_dir)
    raw_cube, timestamps_s = load_capture_arrays(session_dir, session_manifest)
    dark_bundle, dark_manifest = load_reference_bundle(dark_reference_dir)
    white_bundle, white_manifest = load_reference_bundle(white_reference_dir)
    validate_reference_shapes(raw_cube, dark_bundle.mean, white_bundle.mean)

    reflectance_result = compute_reflectance_with_diagnostics(
        raw_cube=raw_cube,
        dark_reference=dark_bundle.mean,
        white_reference=white_bundle.mean,
        epsilon=parameters.epsilon,
        clip_min=parameters.clip_min,
        clip_max=parameters.clip_max,
        invalid_fill=parameters.invalid_fill,
    )
    reflectance_cube = reflectance_result.cube
    absorbance_cube = reflectance_to_absorbance(
        reflectance_cube,
        epsilon=parameters.epsilon,
        clip_max=parameters.absorbance_clip_max,
    )

    output_dir = make_session_dir(output_root, f"calibrated-{mode}")
    ensure_directory(output_dir)

    np.save(output_dir / "timestamps.npy", timestamps_s, allow_pickle=False)

    reflectance_path: Path | None = None
    absorbance_path: Path | None = None
    if mode in {"both", "reflectance"}:
        reflectance_path = output_dir / "reflectance.npy"
        np.save(reflectance_path, reflectance_cube, allow_pickle=False)
    if mode in {"both", "absorbance"}:
        absorbance_path = output_dir / "absorbance.npy"
        np.save(absorbance_path, absorbance_cube, allow_pickle=False)

    settings = session_manifest.get("settings", {})
    selected_rgb_bands = resolve_rgb_bands(raw_cube.shape[1], rgb_bands or settings.get("rgb_bands"))
    preview_source = reflectance_cube if reflectance_path is not None else absorbance_cube
    preview = build_pseudo_rgb_preview(preview_source, selected_rgb_bands)
    preview_path = save_preview_png(preview, output_dir / "preview.png")

    qc_thresholds = ReferenceQcThresholds()
    pair_qc = evaluate_reference_pair_qc(
        dark_bundle.mean,
        white_bundle.mean,
        min_dynamic_range=qc_thresholds.pair_min_dynamic_range,
    )
    warnings = build_calibration_warnings(pair_qc, thresholds=qc_thresholds)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "frame_count": int(raw_cube.shape[0]),
        "band_count": int(raw_cube.shape[1]),
        "spatial_width": int(raw_cube.shape[2]),
        "rgb_bands": list(selected_rgb_bands),
        "files": {
            "reflectance": reflectance_path.name if reflectance_path is not None else None,
            "absorbance": absorbance_path.name if absorbance_path is not None else None,
            "timestamps": "timestamps.npy",
            "preview": preview_path.name,
        },
        "source_session": str(session_dir),
        "reference_dirs": {
            "dark": str(dark_reference_dir),
            "white": str(white_reference_dir),
        },
        "camera_info": session_manifest.get("camera_info", {}),
        "settings": settings,
        "calibration_params": parameters.to_dict(),
        "warnings": warnings,
        "qc": {
            "reference_pair": build_reference_pair_qc_payload(pair_qc, thresholds=qc_thresholds),
            "reflectance": summarize_cube(reflectance_cube),
            "reflectance_diagnostics": reflectance_result.diagnostics.to_dict(),
            "absorbance": summarize_cube(absorbance_cube),
            "dark_reference": dark_manifest.get("qc", {}),
            "white_reference": white_manifest.get("qc", {}),
        },
    }

    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    return CalibrationRunResult(
        output_dir=output_dir,
        manifest_path=manifest_path,
        preview_path=preview_path,
        frame_count=int(raw_cube.shape[0]),
        has_reflectance=reflectance_path is not None,
        has_absorbance=absorbance_path is not None,
    )


def load_capture_arrays(session_dir: Path, session_manifest: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    files = session_manifest.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("session manifest must contain a 'files' mapping.")

    lines_path = session_dir / str(files.get("lines", "lines.npy"))
    timestamps_path = session_dir / str(files.get("timestamps", "timestamps.npy"))
    raw_cube = np.load(lines_path, allow_pickle=False)
    timestamps_s = np.load(timestamps_path, allow_pickle=False)
    if raw_cube.ndim != 3:
        raise ValueError("raw capture array must be 3D (frame_count, band_count, spatial_width).")
    if timestamps_s.ndim != 1:
        raise ValueError("timestamps array must be 1D.")
    if raw_cube.shape[0] != timestamps_s.shape[0]:
        raise ValueError("frame count mismatch between lines and timestamps.")
    return raw_cube.astype(np.float32, copy=False), timestamps_s.astype(np.float64, copy=False)


def validate_reference_shapes(
    raw_cube: np.ndarray,
    dark_reference: np.ndarray,
    white_reference: np.ndarray,
) -> None:
    expected_shape = raw_cube.shape[1:]
    if dark_reference.shape != expected_shape:
        raise ValueError(
            f"dark reference shape mismatch: expected {expected_shape!r}, got {dark_reference.shape!r}."
        )
    if white_reference.shape != expected_shape:
        raise ValueError(
            f"white reference shape mismatch: expected {expected_shape!r}, got {white_reference.shape!r}."
        )


def summarize_cube(cube: np.ndarray) -> dict[str, float]:
    data = cube.astype(np.float32, copy=False)
    return {
        "min": float(np.min(data)),
        "max": float(np.max(data)),
        "mean": float(np.mean(data)),
        "std": float(np.std(data)),
        "p01": float(np.percentile(data, 1.0)),
        "p50": float(np.percentile(data, 50.0)),
        "p99": float(np.percentile(data, 99.0)),
    }


def build_calibration_warnings(
    pair_qc: ReferencePairQcReport,
    *,
    thresholds: ReferenceQcThresholds | None = None,
) -> list[str]:
    warnings: list[str] = []
    decision = judge_reference_pair_qc(pair_qc, thresholds=thresholds)
    for issue in decision.issues:
        warnings.append(f"{issue.code}: {issue.message}")
    return warnings
