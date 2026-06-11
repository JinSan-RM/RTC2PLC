from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from calibration.qc import (
    ReferenceQcThresholds,
    build_reference_pair_qc_payload,
    evaluate_reference_pair_qc,
    evaluate_reference_qc,
    judge_reference_pair_qc,
)
from capture.replay import load_manifest
from models.bundle import (
    ModelBundleManifest,
    load_bundle_manifest,
    validate_bundle,
)


@dataclass(slots=True)
class RuntimeSourceDescriptor:
    source: str
    band_count: int
    spatial_width: int
    frame_count: int | None = None
    source_path: str | None = None
    created_at_utc: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RuntimePreflightReport:
    ok: bool
    errors: list[str]
    warnings: list[str]
    bundle: dict[str, object]
    source: dict[str, object]
    compatibility: dict[str, object]
    calibration_qc: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": bool(self.ok),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "bundle": dict(self.bundle),
            "source": dict(self.source),
            "compatibility": dict(self.compatibility),
            "calibration_qc": dict(self.calibration_qc),
        }


def build_replay_source_descriptor(session_dir: Path) -> RuntimeSourceDescriptor:
    session = Path(session_dir).resolve()
    manifest = load_manifest(session)
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("session manifest must include a 'files' mapping.")

    lines_path = session / str(files.get("lines", "lines.npy"))
    timestamps_path = session / str(files.get("timestamps", "timestamps.npy"))
    cube = np.load(lines_path, mmap_mode="r", allow_pickle=False)
    timestamps = np.load(timestamps_path, mmap_mode="r", allow_pickle=False)

    if cube.ndim != 3:
        raise ValueError("replay lines array must be 3D (frame_count, band_count, spatial_width).")
    if timestamps.ndim != 1:
        raise ValueError("replay timestamps array must be 1D.")
    if int(timestamps.shape[0]) != int(cube.shape[0]):
        raise ValueError(
            "replay lines/timestamps frame mismatch: "
            f"frames={int(cube.shape[0])}, timestamps={int(timestamps.shape[0])}"
        )

    return RuntimeSourceDescriptor(
        source="replay",
        frame_count=int(cube.shape[0]),
        band_count=int(cube.shape[1]),
        spatial_width=int(cube.shape[2]),
        source_path=str(session),
        created_at_utc=str(manifest.get("created_at_utc", "")) or None,
    )


def build_lumo_source_descriptor(
    *,
    band_count: int,
    spatial_width: int,
    source_path: str | None = None,
) -> RuntimeSourceDescriptor:
    return RuntimeSourceDescriptor(
        source="lumo",
        frame_count=None,
        band_count=int(band_count),
        spatial_width=int(spatial_width),
        source_path=source_path,
    )


def run_runtime_preflight(
    *,
    bundle_dir: Path,
    source: RuntimeSourceDescriptor,
    verify_bundle_hashes: bool = True,
    min_dynamic_range: float = 1000.0,
    max_low_dynamic_ratio: float = 0.20,
) -> RuntimePreflightReport:
    errors: list[str] = []
    warnings: list[str] = []
    bundle_root = Path(bundle_dir).resolve()

    try:
        manifest = load_bundle_manifest(bundle_root)
    except Exception as exc:  # noqa: BLE001
        return RuntimePreflightReport(
            ok=False,
            errors=[f"bundle manifest load failed: {exc}"],
            warnings=[],
            bundle={"bundle_dir": str(bundle_root)},
            source=source.to_dict(),
            compatibility={},
            calibration_qc={},
        )

    validation = validate_bundle(
        bundle_dir=bundle_root,
        manifest=manifest,
        verify_hashes=verify_bundle_hashes,
    )
    errors.extend(validation.errors)
    warnings.extend(validation.warnings)

    compatibility = _validate_source_compatibility(
        bundle_root=bundle_root,
        manifest=manifest,
        source=source,
        errors=errors,
    )
    calibration_qc = _evaluate_calibration_qc(
        bundle_root=bundle_root,
        manifest=manifest,
        min_dynamic_range=min_dynamic_range,
        max_low_dynamic_ratio=max_low_dynamic_ratio,
        errors=errors,
        warnings=warnings,
    )

    report = RuntimePreflightReport(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        bundle={
            "bundle_dir": str(bundle_root),
            "bundle_id": manifest.bundle_id,
            "schema_version": manifest.schema_version,
            "model_path": str(bundle_root / manifest.model.path),
            "validation": {
                "ok": validation.ok,
                "errors": validation.errors,
                "warnings": validation.warnings,
                "verify_hashes": bool(verify_bundle_hashes),
            },
        },
        source=source.to_dict(),
        compatibility=compatibility,
        calibration_qc=calibration_qc,
    )
    return report


def _validate_source_compatibility(
    *,
    bundle_root: Path,
    manifest: ModelBundleManifest,
    source: RuntimeSourceDescriptor,
    errors: list[str],
) -> dict[str, object]:
    training_band_count: int | None = _as_positive_int(manifest.training_metadata.get("input_band_count"))
    selected_band_count: int | None = _as_positive_int(manifest.training_metadata.get("selected_band_count"))
    reference_band_count, reference_spatial_width = _load_reference_shape(
        bundle_root=bundle_root,
        manifest=manifest,
        errors=errors,
    )
    if source.band_count <= 0:
        errors.append(f"source.band_count must be > 0, got {source.band_count}.")
    if source.spatial_width <= 0:
        errors.append(f"source.spatial_width must be > 0, got {source.spatial_width}.")
    if source.frame_count is not None and source.frame_count <= 0:
        errors.append(f"source.frame_count must be > 0 when provided, got {source.frame_count}.")

    if reference_band_count > 0 and source.band_count != reference_band_count:
        errors.append(
            "source/bundle band_count mismatch: "
            f"source={source.band_count}, reference={reference_band_count}"
        )
    if reference_spatial_width > 0 and source.spatial_width != reference_spatial_width:
        errors.append(
            "source/bundle spatial_width mismatch: "
            f"source={source.spatial_width}, reference={reference_spatial_width}"
        )
    if training_band_count is not None and source.band_count != training_band_count:
        errors.append(
            "source/training input_band_count mismatch: "
            f"source={source.band_count}, training={training_band_count}"
        )

    return {
        "source_band_count": int(source.band_count),
        "source_spatial_width": int(source.spatial_width),
        "source_frame_count": int(source.frame_count) if source.frame_count is not None else None,
        "reference_band_count": int(reference_band_count),
        "reference_spatial_width": int(reference_spatial_width),
        "training_input_band_count": int(training_band_count) if training_band_count is not None else None,
        "training_selected_band_count": int(selected_band_count) if selected_band_count is not None else None,
    }


def _evaluate_calibration_qc(
    *,
    bundle_root: Path,
    manifest: ModelBundleManifest,
    min_dynamic_range: float,
    max_low_dynamic_ratio: float,
    errors: list[str],
    warnings: list[str],
) -> dict[str, object]:
    dark_path = (bundle_root / manifest.calibration.dark.mean.path).resolve()
    white_path = (bundle_root / manifest.calibration.white.mean.path).resolve()

    try:
        dark = np.load(dark_path, allow_pickle=False).astype(np.float32, copy=False)
        white = np.load(white_path, allow_pickle=False).astype(np.float32, copy=False)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"failed to load calibration means for QC: {exc}")
        return {}

    if dark.ndim != 2 or white.ndim != 2:
        errors.append(
            "calibration mean arrays must both be 2D: "
            f"dark.ndim={dark.ndim}, white.ndim={white.ndim}"
        )
        return {}
    if dark.shape != white.shape:
        errors.append(f"calibration mean shape mismatch: dark={dark.shape!r}, white={white.shape!r}")
        return {}

    if not np.isfinite(dark).all():
        errors.append("dark calibration mean contains non-finite values.")
    if not np.isfinite(white).all():
        errors.append("white calibration mean contains non-finite values.")

    sensor_max = max(4095.0, float(np.max(np.asarray([dark.max(), white.max()]))))
    dark_qc = evaluate_reference_qc(dark, sensor_max=sensor_max)
    white_qc = evaluate_reference_qc(white, sensor_max=sensor_max)
    pair_qc = evaluate_reference_pair_qc(dark, white, min_dynamic_range=min_dynamic_range)
    thresholds = ReferenceQcThresholds(
        sensor_max=sensor_max,
        pair_min_dynamic_range=float(min_dynamic_range),
        pair_warn_dynamic_range=min(ReferenceQcThresholds().pair_warn_dynamic_range, float(min_dynamic_range)),
        pair_fail_low_dynamic_ratio=float(max_low_dynamic_ratio),
    )
    pair_decision = judge_reference_pair_qc(pair_qc, thresholds=thresholds)

    if pair_qc.dynamic_range_p01 <= 0.0:
        errors.append(
            "calibration QC failed: dynamic_range_p01 must be > 0, "
            f"got {pair_qc.dynamic_range_p01:.6f}"
        )
    if pair_qc.dynamic_range_mean <= 0.0:
        errors.append(
            "calibration QC failed: dynamic_range_mean must be > 0, "
            f"got {pair_qc.dynamic_range_mean:.6f}"
        )
    if pair_qc.low_dynamic_ratio > max_low_dynamic_ratio:
        errors.append(
            "calibration QC failed: low_dynamic_ratio exceeds threshold "
            f"({pair_qc.low_dynamic_ratio:.6f} > {max_low_dynamic_ratio:.6f})"
        )
    for issue in pair_decision.issues:
        message = f"calibration QC {issue.severity}: {issue.code}: {issue.message}"
        if issue.severity == "error":
            if message not in errors:
                errors.append(message)
        else:
            warnings.append(message)
    if dark_qc.saturated_ratio > 0.95:
        warnings.append(
            "dark reference has very high saturation ratio; verify sensor exposure/reference capture."
        )
    if white_qc.near_zero_ratio > 0.50:
        warnings.append(
            "white reference has high near-zero ratio; illumination/reference may be invalid."
        )

    return {
        "dark": dark_qc.to_dict(),
        "white": white_qc.to_dict(),
        "pair": build_reference_pair_qc_payload(pair_qc, thresholds=thresholds),
        "thresholds": {
            "min_dynamic_range": float(min_dynamic_range),
            "max_low_dynamic_ratio": float(max_low_dynamic_ratio),
        },
        "reference_shape": [int(dark.shape[0]), int(dark.shape[1])],
    }


def _as_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _load_reference_shape(
    *,
    bundle_root: Path,
    manifest: ModelBundleManifest,
    errors: list[str],
) -> tuple[int, int]:
    dark_path = (bundle_root / manifest.calibration.dark.mean.path).resolve()
    white_path = (bundle_root / manifest.calibration.white.mean.path).resolve()
    try:
        dark = np.load(dark_path, allow_pickle=False, mmap_mode="r")
        white = np.load(white_path, allow_pickle=False, mmap_mode="r")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"failed to read reference shape from bundle: {exc}")
        return -1, -1
    if dark.ndim != 2 or white.ndim != 2:
        errors.append(
            f"reference arrays must be 2D for compatibility check: dark.ndim={dark.ndim}, white.ndim={white.ndim}"
        )
        return -1, -1
    if dark.shape != white.shape:
        errors.append(f"reference shape mismatch: dark={dark.shape!r}, white={white.shape!r}")
        return int(dark.shape[0]), int(dark.shape[1])
    return int(dark.shape[0]), int(dark.shape[1])
