from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class ReferenceQcReport:
    min_value: float
    max_value: float
    mean_value: float
    std_value: float
    cv_value: float
    p01: float
    p50: float
    p99: float
    saturated_ratio: float
    near_zero_ratio: float
    non_finite_ratio: float = 0.0
    band_mean_min: float = 0.0
    band_mean_max: float = 0.0
    spatial_cv_p50: float = 0.0
    spatial_cv_p95: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReferencePairQcReport:
    dynamic_range_min: float
    dynamic_range_mean: float
    dynamic_range_p01: float
    dynamic_range_p99: float
    low_dynamic_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReferenceQcThresholds:
    sensor_max: float = 4095.0
    saturation_threshold_ratio: float = 0.99
    max_saturated_ratio: float = 0.001
    near_zero_threshold: float = 1.0
    max_near_zero_ratio: float = 0.01
    dark_warn_mean_ratio: float = 0.10
    dark_fail_mean_ratio: float = 0.50
    dark_warn_p99_ratio: float = 0.10
    dark_fail_p99_ratio: float = 0.50
    dark_max_cv_value: float = 1.00
    white_min_p50_ratio: float = 0.50
    white_target_low_ratio: float = 0.70
    white_target_high_ratio: float = 0.90
    white_fail_p99_ratio: float = 0.99
    white_max_spatial_cv_p95: float = 0.05
    pair_min_dynamic_range: float = 1000.0
    pair_warn_dynamic_range: float = 500.0
    pair_max_low_dynamic_ratio: float = 0.01
    pair_fail_low_dynamic_ratio: float = 0.20

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReferenceQcIssue:
    severity: str
    code: str
    message: str
    value: float | None = None
    limit: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReferenceQcDecision:
    kind: str
    verdict: str
    score: int
    issues: list[ReferenceQcIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "verdict": self.verdict,
            "score": int(self.score),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def evaluate_reference_qc(
    reference_plane: np.ndarray,
    *,
    sensor_max: float = 4095.0,
    saturation_threshold_ratio: float = 0.99,
    near_zero_threshold: float = 1.0,
    cv_epsilon: float = 1e-6,
) -> ReferenceQcReport:
    if reference_plane.ndim != 2:
        raise ValueError("reference_plane must be 2D (band_count, spatial_width).")
    if sensor_max <= 0:
        raise ValueError("sensor_max must be positive.")
    if not (0.0 < saturation_threshold_ratio <= 1.0):
        raise ValueError("saturation_threshold_ratio must be in (0, 1].")
    if cv_epsilon <= 0:
        raise ValueError("cv_epsilon must be positive.")

    plane = reference_plane.astype(np.float32, copy=False)
    finite_mask = np.isfinite(plane)
    if not np.any(finite_mask):
        raise ValueError("reference_plane must contain at least one finite value.")

    finite_values = plane[finite_mask]
    saturation_threshold = sensor_max * saturation_threshold_ratio
    saturated_ratio = float(np.mean(finite_values >= saturation_threshold))
    near_zero_ratio = float(np.mean(finite_values <= near_zero_threshold))
    mean_value = float(np.mean(finite_values))
    std_value = float(np.std(finite_values))
    cv_value = std_value / max(abs(mean_value), cv_epsilon)

    band_mean = np.nanmean(np.where(finite_mask, plane, np.nan), axis=1)
    band_std = np.nanstd(np.where(finite_mask, plane, np.nan), axis=1)
    spatial_cv = band_std / np.maximum(np.abs(band_mean), cv_epsilon)
    finite_spatial_cv = spatial_cv[np.isfinite(spatial_cv)]
    if finite_spatial_cv.size == 0:
        finite_spatial_cv = np.asarray([0.0], dtype=np.float32)

    return ReferenceQcReport(
        min_value=float(np.min(finite_values)),
        max_value=float(np.max(finite_values)),
        mean_value=mean_value,
        std_value=std_value,
        cv_value=float(cv_value),
        p01=float(np.percentile(finite_values, 1.0)),
        p50=float(np.percentile(finite_values, 50.0)),
        p99=float(np.percentile(finite_values, 99.0)),
        saturated_ratio=saturated_ratio,
        near_zero_ratio=near_zero_ratio,
        non_finite_ratio=float(1.0 - np.mean(finite_mask)),
        band_mean_min=float(np.nanmin(band_mean)),
        band_mean_max=float(np.nanmax(band_mean)),
        spatial_cv_p50=float(np.percentile(finite_spatial_cv, 50.0)),
        spatial_cv_p95=float(np.percentile(finite_spatial_cv, 95.0)),
    )


def evaluate_reference_pair_qc(
    dark_reference: np.ndarray,
    white_reference: np.ndarray,
    *,
    min_dynamic_range: float = 10.0,
) -> ReferencePairQcReport:
    if dark_reference.ndim != 2 or white_reference.ndim != 2:
        raise ValueError("Both dark_reference and white_reference must be 2D.")
    if dark_reference.shape != white_reference.shape:
        raise ValueError(
            f"Reference shapes must match, got {dark_reference.shape!r} vs {white_reference.shape!r}."
        )
    if min_dynamic_range < 0:
        raise ValueError("min_dynamic_range must be non-negative.")

    dark = dark_reference.astype(np.float32, copy=False)
    white = white_reference.astype(np.float32, copy=False)
    dynamic_range = white - dark
    finite = dynamic_range[np.isfinite(dynamic_range)]
    if finite.size == 0:
        raise ValueError("Reference dynamic range must contain at least one finite value.")

    return ReferencePairQcReport(
        dynamic_range_min=float(np.min(finite)),
        dynamic_range_mean=float(np.mean(finite)),
        dynamic_range_p01=float(np.percentile(finite, 1.0)),
        dynamic_range_p99=float(np.percentile(finite, 99.0)),
        low_dynamic_ratio=float(np.mean(finite < min_dynamic_range)),
    )


def judge_reference_qc(
    kind: str,
    report: ReferenceQcReport,
    *,
    thresholds: ReferenceQcThresholds | None = None,
) -> ReferenceQcDecision:
    normalized_kind = kind.strip().lower()
    if normalized_kind not in {"dark", "white"}:
        raise ValueError("Reference kind must be 'dark' or 'white'.")
    limits = thresholds or ReferenceQcThresholds()
    _validate_thresholds(limits)

    issues = _build_common_issues(report, limits)
    if normalized_kind == "dark":
        issues.extend(_build_dark_issues(report, limits))
    else:
        issues.extend(_build_white_issues(report, limits))
    return _decision_from_issues(normalized_kind, issues)


def judge_reference_pair_qc(
    report: ReferencePairQcReport,
    *,
    thresholds: ReferenceQcThresholds | None = None,
) -> ReferenceQcDecision:
    limits = thresholds or ReferenceQcThresholds()
    _validate_thresholds(limits)
    issues: list[ReferenceQcIssue] = []

    if report.dynamic_range_p01 <= 0.0:
        issues.append(
            _issue(
                "error",
                "PAIR_NEGATIVE_DENOMINATOR",
                "white-dark p01 must be positive.",
                report.dynamic_range_p01,
                0.0,
            )
        )
    if report.low_dynamic_ratio > limits.pair_fail_low_dynamic_ratio:
        issues.append(
            _issue(
                "error",
                "PAIR_TOO_MANY_LOW_DYNAMIC_PIXELS",
                "too many pixels have insufficient white-dark signal.",
                report.low_dynamic_ratio,
                limits.pair_fail_low_dynamic_ratio,
            )
        )
    elif report.low_dynamic_ratio > limits.pair_max_low_dynamic_ratio:
        issues.append(
            _issue(
                "warning",
                "PAIR_LOW_DYNAMIC_PIXELS",
                "some pixels have weak white-dark signal.",
                report.low_dynamic_ratio,
                limits.pair_max_low_dynamic_ratio,
            )
        )
    if report.dynamic_range_mean < limits.pair_warn_dynamic_range:
        issues.append(
            _issue(
                "warning",
                "PAIR_LOW_MEAN_DYNAMIC_RANGE",
                "mean white-dark signal is below the caution threshold.",
                report.dynamic_range_mean,
                limits.pair_warn_dynamic_range,
            )
        )
    if report.dynamic_range_p01 < limits.pair_min_dynamic_range:
        issues.append(
            _issue(
                "warning",
                "PAIR_P01_BELOW_PASS_THRESHOLD",
                "white-dark p01 is below the FX17e pass threshold.",
                report.dynamic_range_p01,
                limits.pair_min_dynamic_range,
            )
        )
    return _decision_from_issues("pair", issues)


def build_reference_qc_payload(
    kind: str,
    report: ReferenceQcReport,
    *,
    thresholds: ReferenceQcThresholds | None = None,
) -> dict[str, Any]:
    limits = thresholds or ReferenceQcThresholds()
    decision = judge_reference_qc(kind, report, thresholds=limits)
    payload = report.to_dict()
    payload["status"] = decision.verdict
    payload["warnings"] = [
        issue.message for issue in decision.issues if issue.severity in {"warning", "error"}
    ]
    payload["decision"] = decision.to_dict()
    payload["thresholds"] = limits.to_dict()
    return payload


def build_reference_pair_qc_payload(
    report: ReferencePairQcReport,
    *,
    thresholds: ReferenceQcThresholds | None = None,
) -> dict[str, Any]:
    limits = thresholds or ReferenceQcThresholds()
    decision = judge_reference_pair_qc(report, thresholds=limits)
    payload = report.to_dict()
    payload["status"] = decision.verdict
    payload["warnings"] = [
        issue.message for issue in decision.issues if issue.severity in {"warning", "error"}
    ]
    payload["decision"] = decision.to_dict()
    payload["thresholds"] = limits.to_dict()
    return payload


def assert_white_reference_qc_acceptable(
    report: ReferenceQcReport,
    *,
    sensor_max: float = 4095.0,
    max_saturated_ratio: float = 0.001,
    max_near_zero_ratio: float = 0.01,
    min_p50_ratio: float = 0.50,
    max_cv_value: float = 0.05,
) -> None:
    failures = build_white_reference_qc_warnings(
        report,
        sensor_max=sensor_max,
        max_saturated_ratio=max_saturated_ratio,
        max_near_zero_ratio=max_near_zero_ratio,
        min_p50_ratio=min_p50_ratio,
        max_cv_value=max_cv_value,
    )
    if failures:
        raise ValueError("Reference QC rejected: " + "; ".join(failures))


def assert_dark_reference_qc_acceptable(
    report: ReferenceQcReport,
    *,
    sensor_max: float = 4095.0,
    max_saturated_ratio: float = 0.001,
    max_p99_ratio: float = 0.10,
    max_cv_value: float = 1.00,
) -> None:
    failures = build_dark_reference_qc_warnings(
        report,
        sensor_max=sensor_max,
        max_saturated_ratio=max_saturated_ratio,
        max_p99_ratio=max_p99_ratio,
        max_cv_value=max_cv_value,
    )
    if failures:
        raise ValueError("Reference QC rejected: " + "; ".join(failures))


def build_white_reference_qc_warnings(
    report: ReferenceQcReport,
    *,
    sensor_max: float = 4095.0,
    max_saturated_ratio: float = 0.001,
    max_near_zero_ratio: float = 0.01,
    min_p50_ratio: float = 0.50,
    max_cv_value: float = 0.05,
) -> list[str]:
    thresholds = ReferenceQcThresholds(
        sensor_max=sensor_max,
        max_saturated_ratio=max_saturated_ratio,
        max_near_zero_ratio=max_near_zero_ratio,
        white_min_p50_ratio=min_p50_ratio,
        white_max_spatial_cv_p95=max_cv_value,
    )
    decision = judge_reference_qc("white", report, thresholds=thresholds)
    return [issue.message for issue in decision.issues]


def build_dark_reference_qc_warnings(
    report: ReferenceQcReport,
    *,
    sensor_max: float = 4095.0,
    max_saturated_ratio: float = 0.001,
    max_p99_ratio: float = 0.10,
    max_cv_value: float = 1.00,
) -> list[str]:
    thresholds = ReferenceQcThresholds(
        sensor_max=sensor_max,
        max_saturated_ratio=max_saturated_ratio,
        dark_warn_p99_ratio=max_p99_ratio,
        dark_max_cv_value=max_cv_value,
    )
    decision = judge_reference_qc("dark", report, thresholds=thresholds)
    return [issue.message for issue in decision.issues]


def _build_common_issues(
    report: ReferenceQcReport,
    thresholds: ReferenceQcThresholds,
) -> list[ReferenceQcIssue]:
    issues: list[ReferenceQcIssue] = []
    if report.non_finite_ratio > 0.0:
        issues.append(
            _issue(
                "error",
                "REFERENCE_NON_FINITE_VALUES",
                "reference contains non-finite values.",
                report.non_finite_ratio,
                0.0,
            )
        )
    if report.saturated_ratio > thresholds.max_saturated_ratio:
        issues.append(
            _issue(
                "error",
                "REFERENCE_SATURATED_PIXELS",
                "saturated pixel ratio exceeds the allowed limit.",
                report.saturated_ratio,
                thresholds.max_saturated_ratio,
            )
        )
    elif report.saturated_ratio > 0.0:
        issues.append(
            _issue(
                "warning",
                "REFERENCE_SATURATION_PRESENT",
                "reference contains pixels near the saturation limit.",
                report.saturated_ratio,
                0.0,
            )
        )
    return issues


def _build_dark_issues(
    report: ReferenceQcReport,
    thresholds: ReferenceQcThresholds,
) -> list[ReferenceQcIssue]:
    sensor_max = thresholds.sensor_max
    issues: list[ReferenceQcIssue] = []
    if report.mean_value > sensor_max * thresholds.dark_fail_mean_ratio:
        issues.append(
            _issue(
                "error",
                "DARK_MEAN_TOO_HIGH",
                "dark reference average signal is too high.",
                report.mean_value,
                sensor_max * thresholds.dark_fail_mean_ratio,
            )
        )
    elif report.mean_value > sensor_max * thresholds.dark_warn_mean_ratio:
        issues.append(
            _issue(
                "warning",
                "DARK_MEAN_ELEVATED",
                "dark reference average signal is elevated.",
                report.mean_value,
                sensor_max * thresholds.dark_warn_mean_ratio,
            )
        )
    if report.p99 > sensor_max * thresholds.dark_fail_p99_ratio:
        issues.append(
            _issue(
                "error",
                "DARK_P99_TOO_HIGH",
                "dark reference p99 signal is too high.",
                report.p99,
                sensor_max * thresholds.dark_fail_p99_ratio,
            )
        )
    elif report.p99 > sensor_max * thresholds.dark_warn_p99_ratio:
        issues.append(
            _issue(
                "warning",
                "DARK_P99_ELEVATED",
                "dark reference p99 signal is elevated.",
                report.p99,
                sensor_max * thresholds.dark_warn_p99_ratio,
            )
        )
    if report.cv_value > thresholds.dark_max_cv_value:
        issues.append(
            _issue(
                "warning",
                "DARK_VARIATION_HIGH",
                "dark reference variation is high.",
                report.cv_value,
                thresholds.dark_max_cv_value,
            )
        )
    return issues


def _build_white_issues(
    report: ReferenceQcReport,
    thresholds: ReferenceQcThresholds,
) -> list[ReferenceQcIssue]:
    sensor_max = thresholds.sensor_max
    issues: list[ReferenceQcIssue] = []
    if report.near_zero_ratio > thresholds.max_near_zero_ratio:
        issues.append(
            _issue(
                "error",
                "WHITE_NEAR_ZERO_PIXELS",
                "white reference has too many near-zero pixels.",
                report.near_zero_ratio,
                thresholds.max_near_zero_ratio,
            )
        )
    if report.p50 < sensor_max * thresholds.white_min_p50_ratio:
        issues.append(
            _issue(
                "error",
                "WHITE_SIGNAL_TOO_LOW",
                "white reference median signal is too low.",
                report.p50,
                sensor_max * thresholds.white_min_p50_ratio,
            )
        )
    elif report.p50 < sensor_max * thresholds.white_target_low_ratio:
        issues.append(
            _issue(
                "warning",
                "WHITE_SIGNAL_BELOW_TARGET",
                "white reference median signal is below the FX17e target zone.",
                report.p50,
                sensor_max * thresholds.white_target_low_ratio,
            )
        )
    if report.p99 >= sensor_max * thresholds.white_fail_p99_ratio or report.max_value >= sensor_max:
        issues.append(
            _issue(
                "error",
                "WHITE_SIGNAL_SATURATED",
                "white reference is at or above the saturation guard band.",
                max(report.p99, report.max_value),
                sensor_max * thresholds.white_fail_p99_ratio,
            )
        )
    elif report.p99 > sensor_max * thresholds.white_target_high_ratio:
        issues.append(
            _issue(
                "warning",
                "WHITE_SIGNAL_NEAR_SATURATION",
                "white reference p99 is above the target zone.",
                report.p99,
                sensor_max * thresholds.white_target_high_ratio,
            )
        )
    if report.spatial_cv_p95 > thresholds.white_max_spatial_cv_p95:
        issues.append(
            _issue(
                "warning",
                "WHITE_SPATIAL_UNIFORMITY_HIGH",
                "white reference spatial variation is above the uniformity target.",
                report.spatial_cv_p95,
                thresholds.white_max_spatial_cv_p95,
            )
        )
    return issues


def _decision_from_issues(kind: str, issues: list[ReferenceQcIssue]) -> ReferenceQcDecision:
    has_error = any(issue.severity == "error" for issue in issues)
    has_warning = any(issue.severity == "warning" for issue in issues)
    if has_error:
        verdict = "fail"
    elif has_warning:
        verdict = "warn"
    else:
        verdict = "pass"
    score = max(
        0,
        100
        - sum(35 for issue in issues if issue.severity == "error")
        - sum(12 for issue in issues if issue.severity == "warning"),
    )
    return ReferenceQcDecision(kind=kind, verdict=verdict, score=score, issues=issues)


def _issue(
    severity: str,
    code: str,
    message: str,
    value: float | None = None,
    limit: float | None = None,
) -> ReferenceQcIssue:
    return ReferenceQcIssue(
        severity=severity,
        code=code,
        message=message,
        value=None if value is None else float(value),
        limit=None if limit is None else float(limit),
    )


def _validate_thresholds(thresholds: ReferenceQcThresholds) -> None:
    if thresholds.sensor_max <= 0:
        raise ValueError("sensor_max must be positive.")
    if not (0.0 < thresholds.saturation_threshold_ratio <= 1.0):
        raise ValueError("saturation_threshold_ratio must be in (0, 1].")
    if thresholds.max_saturated_ratio < 0:
        raise ValueError("max_saturated_ratio must be non-negative.")
    if thresholds.near_zero_threshold < 0:
        raise ValueError("near_zero_threshold must be non-negative.")
    if thresholds.pair_min_dynamic_range < 0 or thresholds.pair_warn_dynamic_range < 0:
        raise ValueError("pair dynamic range thresholds must be non-negative.")
