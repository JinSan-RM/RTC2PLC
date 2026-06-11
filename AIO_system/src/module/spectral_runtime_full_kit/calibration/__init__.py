"""Calibration helpers for dark/white references and reflectance transforms."""

from calibration.qc import (
    ReferenceQcDecision,
    ReferenceQcThresholds,
    ReferencePairQcReport,
    ReferenceQcReport,
    build_reference_qc_payload,
    evaluate_reference_pair_qc,
    evaluate_reference_qc,
    judge_reference_pair_qc,
    judge_reference_qc,
)
from calibration.auto_calibration import (
    CalibratedCubeResolution,
    ensure_session_calibrated,
    find_latest_reference_dir,
    resolve_reference_pair,
    validate_reference_pair_compatibility,
    validate_reference_pair_quality,
)
from calibration.processing import CalibrationParameters, CalibrationRunResult, run_session_calibration
from calibration.references import (
    ReferenceBundle,
    build_reference_bundle,
    load_reference_bundle,
    save_reference_bundle,
)
from calibration.reflectance import compute_reflectance, reflectance_to_absorbance

__all__ = [
    "ReferenceBundle",
    "CalibratedCubeResolution",
    "CalibrationParameters",
    "CalibrationRunResult",
    "ReferencePairQcReport",
    "ReferenceQcDecision",
    "ReferenceQcReport",
    "ReferenceQcThresholds",
    "build_reference_qc_payload",
    "build_reference_bundle",
    "compute_reflectance",
    "ensure_session_calibrated",
    "evaluate_reference_pair_qc",
    "evaluate_reference_qc",
    "find_latest_reference_dir",
    "load_reference_bundle",
    "reflectance_to_absorbance",
    "resolve_reference_pair",
    "run_session_calibration",
    "save_reference_bundle",
    "validate_reference_pair_compatibility",
    "validate_reference_pair_quality",
    "judge_reference_pair_qc",
    "judge_reference_qc",
]
