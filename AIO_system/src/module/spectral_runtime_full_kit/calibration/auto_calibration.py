from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from calibration.processing import CalibrationParameters, run_session_calibration
from calibration.qc import ReferenceQcThresholds, evaluate_reference_pair_qc, judge_reference_pair_qc
from calibration.references import load_reference_bundle


@dataclass(slots=True)
class CalibratedCubeResolution:
    cube_path: Path
    output_dir: Path
    dark_reference_dir: Path
    white_reference_dir: Path
    created: bool


def ensure_session_calibrated(
    *,
    session_dir: Path,
    input_kind: str,
    processed_root: Path,
    reference_root: Path | None = None,
    dark_reference_dir: Path | None = None,
    white_reference_dir: Path | None = None,
    parameters: CalibrationParameters | None = None,
    allow_quality_warn: bool = True,
) -> CalibratedCubeResolution:
    normalized_input = str(input_kind or "").strip().lower()
    if normalized_input not in {"reflectance", "absorbance"}:
        raise ValueError("auto calibration is only supported for reflectance or absorbance input.")

    dark_dir, white_dir = resolve_reference_pair(
        reference_root=reference_root,
        dark_reference_dir=dark_reference_dir,
        white_reference_dir=white_reference_dir,
        allow_quality_warn=allow_quality_warn,
    )
    run_parameters = parameters or CalibrationParameters(mode=normalized_input)
    result = run_session_calibration(
        session_dir=Path(session_dir),
        dark_reference_dir=dark_dir,
        white_reference_dir=white_dir,
        output_root=Path(processed_root),
        parameters=run_parameters,
    )
    cube_path = result.output_dir / f"{normalized_input}.npy"
    if not cube_path.exists():
        raise FileNotFoundError(f"calibration completed but {cube_path.name} was not written: {cube_path}")
    return CalibratedCubeResolution(
        cube_path=cube_path,
        output_dir=result.output_dir,
        dark_reference_dir=dark_dir,
        white_reference_dir=white_dir,
        created=True,
    )


def resolve_reference_pair(
    *,
    reference_root: Path | None = None,
    dark_reference_dir: Path | None = None,
    white_reference_dir: Path | None = None,
    allow_quality_warn: bool = False,
) -> tuple[Path, Path]:
    dark_dir = Path(dark_reference_dir) if dark_reference_dir is not None else None
    white_dir = Path(white_reference_dir) if white_reference_dir is not None else None

    if dark_dir is not None and white_dir is not None:
        validate_reference_pair_compatibility(
            dark_dir,
            white_dir,
            allow_quality_warn=allow_quality_warn,
        )
        return dark_dir, white_dir

    if reference_root is None:
        raise FileNotFoundError("reference_root is required when explicit dark/white references are not provided.")

    root = Path(reference_root)
    dark_candidates = [dark_dir] if dark_dir is not None else find_reference_dirs(root, kind="dark")
    white_candidates = [white_dir] if white_dir is not None else find_reference_dirs(root, kind="white")
    dark_candidates = [candidate for candidate in dark_candidates if candidate is not None]
    white_candidates = [candidate for candidate in white_candidates if candidate is not None]
    if not dark_candidates:
        raise FileNotFoundError(f"No dark reference found under {root}.")
    if not white_candidates:
        raise FileNotFoundError(f"No white reference found under {root}.")

    pair_errors: list[str] = []
    for candidate_dark in dark_candidates:
        for candidate_white in white_candidates:
            try:
                validate_reference_pair_compatibility(
                    candidate_dark,
                    candidate_white,
                    allow_quality_warn=allow_quality_warn,
                )
            except ValueError as exc:
                pair_errors.append(str(exc))
                continue
            return candidate_dark, candidate_white

    details = "; ".join(pair_errors[:3])
    raise ValueError(f"No compatible dark/white reference pair found under {root}. {details}")


def find_latest_reference_dir(reference_root: Path, *, kind: str) -> Path | None:
    candidates = find_reference_dirs(reference_root, kind=kind)
    return candidates[0] if candidates else None


def find_reference_dirs(reference_root: Path, *, kind: str) -> list[Path]:
    root = Path(reference_root)
    if not root.exists():
        return []

    candidates: list[tuple[float, Path]] = []
    for manifest_path in root.glob("*/manifest.json"):
        reference_dir = manifest_path.parent
        try:
            bundle, _manifest = load_reference_bundle(reference_dir)
        except Exception:
            continue
        if bundle.kind != kind:
            continue
        try:
            timestamp = float(manifest_path.stat().st_mtime)
        except OSError:
            timestamp = 0.0
        candidates.append((timestamp, reference_dir))

    if not candidates:
        return []
    candidates.sort(key=lambda row: row[0], reverse=True)
    return [path for _timestamp, path in candidates]


def validate_reference_pair_compatibility(
    dark_reference_dir: Path,
    white_reference_dir: Path,
    *,
    allow_quality_warn: bool = False,
) -> None:
    dark_bundle, dark_manifest = load_reference_bundle(Path(dark_reference_dir))
    white_bundle, white_manifest = load_reference_bundle(Path(white_reference_dir))
    if dark_bundle.kind != "dark":
        raise ValueError(f"Expected dark reference, got {dark_bundle.kind}: {dark_reference_dir}")
    if white_bundle.kind != "white":
        raise ValueError(f"Expected white reference, got {white_bundle.kind}: {white_reference_dir}")
    if dark_bundle.mean.shape != white_bundle.mean.shape:
        raise ValueError(
            "dark/white reference shape mismatch: "
            f"dark={dark_bundle.mean.shape!r}, white={white_bundle.mean.shape!r}"
        )
    if dark_bundle.band_count != white_bundle.band_count:
        raise ValueError(
            "dark/white reference band_count mismatch: "
            f"dark={dark_bundle.band_count}, white={white_bundle.band_count}"
        )
    if dark_bundle.spatial_width != white_bundle.spatial_width:
        raise ValueError(
            "dark/white reference spatial_width mismatch: "
            f"dark={dark_bundle.spatial_width}, white={white_bundle.spatial_width}"
        )

    mismatches = _reference_manifest_setting_mismatches(dark_manifest, white_manifest)
    if mismatches:
        raise ValueError(
            "dark/white reference settings are incompatible: " + "; ".join(mismatches)
        )
    validate_reference_pair_quality(
        dark_reference_dir,
        white_reference_dir,
        allow_warn=allow_quality_warn,
    )


def validate_reference_pair_quality(
    dark_reference_dir: Path,
    white_reference_dir: Path,
    *,
    allow_warn: bool = False,
    thresholds: ReferenceQcThresholds | None = None,
) -> None:
    dark_bundle, _dark_manifest = load_reference_bundle(Path(dark_reference_dir))
    white_bundle, _white_manifest = load_reference_bundle(Path(white_reference_dir))
    limits = thresholds or ReferenceQcThresholds()
    pair_qc = evaluate_reference_pair_qc(
        dark_bundle.mean,
        white_bundle.mean,
        min_dynamic_range=limits.pair_min_dynamic_range,
    )
    decision = judge_reference_pair_qc(pair_qc, thresholds=limits)
    if decision.verdict == "pass" or (allow_warn and decision.verdict == "warn"):
        return
    if decision.verdict != "pass":
        issue_text = "; ".join(
            f"{issue.code}(severity={issue.severity}, value={issue.value}, limit={issue.limit})"
            for issue in decision.issues
        )
        raise ValueError(
            "dark/white reference pair QC failed: "
            f"dynamic_range_mean={pair_qc.dynamic_range_mean:.3f}, "
            f"dynamic_range_p01={pair_qc.dynamic_range_p01:.3f}, "
            f"low_dynamic_ratio={pair_qc.low_dynamic_ratio:.6f}; "
            f"{issue_text}"
        )


def _assert_reference_kind(reference_dir: Path, expected_kind: str) -> None:
    bundle, _manifest = load_reference_bundle(reference_dir)
    if bundle.kind != expected_kind:
        raise ValueError(f"Expected {expected_kind} reference, got {bundle.kind}: {reference_dir}")


def _reference_manifest_setting_mismatches(
    dark_manifest: dict[str, Any],
    white_manifest: dict[str, Any],
) -> list[str]:
    mismatches: list[str] = []
    dark_settings = _as_mapping(dark_manifest.get("settings"))
    white_settings = _as_mapping(white_manifest.get("settings"))
    dark_camera = _as_mapping(dark_manifest.get("camera_info"))
    white_camera = _as_mapping(white_manifest.get("camera_info"))
    dark_source = _as_mapping(dark_manifest.get("source"))
    white_source = _as_mapping(white_manifest.get("source"))

    for key in ("band_count", "spatial_width", "integration_time_us", "exposure_time_us"):
        dark_value = _first_present(dark_settings, key)
        white_value = _first_present(white_settings, key)
        dark_number = _coerce_float(dark_value)
        white_number = _coerce_float(white_value)
        if dark_number is not None and white_number is not None and int(dark_number) != int(white_number):
            mismatches.append(f"{key}: dark={dark_value}, white={white_value}")

    dark_line_rate = _first_present(dark_settings, "line_rate_hz")
    white_line_rate = _first_present(white_settings, "line_rate_hz")
    dark_line_rate_number = _coerce_float(dark_line_rate)
    white_line_rate_number = _coerce_float(white_line_rate)
    if dark_line_rate_number is not None and white_line_rate_number is not None:
        if abs(dark_line_rate_number - white_line_rate_number) > 1e-6:
            mismatches.append(f"line_rate_hz: dark={dark_line_rate}, white={white_line_rate}")

    for key in ("provider", "model", "serial_number"):
        dark_value = str(_first_present(dark_camera, key) or "").strip()
        white_value = str(_first_present(white_camera, key) or "").strip()
        if dark_value and white_value and dark_value != white_value:
            mismatches.append(f"camera_info.{key}: dark={dark_value}, white={white_value}")

    dark_provider = str(_first_present(dark_source, "provider") or "").strip()
    white_provider = str(_first_present(white_source, "provider") or "").strip()
    if dark_provider and white_provider and dark_provider != white_provider:
        mismatches.append(f"source.provider: dark={dark_provider}, white={white_provider}")
    return mismatches


def _as_mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _first_present(mapping: dict[str, Any], key: str) -> Any | None:
    if key in mapping and mapping[key] is not None:
        return mapping[key]
    if key == "integration_time_us" and mapping.get("exposure_time_us") is not None:
        return mapping["exposure_time_us"]
    if key == "exposure_time_us" and mapping.get("integration_time_us") is not None:
        return mapping["integration_time_us"]
    return None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
