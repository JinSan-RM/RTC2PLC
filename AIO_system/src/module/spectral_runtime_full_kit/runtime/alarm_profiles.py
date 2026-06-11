from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.dashboard import DashboardThresholds


@dataclass(slots=True)
class AlarmProfile:
    name: str
    thresholds: DashboardThresholds


@dataclass(slots=True)
class OperationalTargets:
    max_alarm_window_ratio: float | None = None
    max_critical_window_ratio: float | None = None
    max_mean_unknown_ratio: float | None = None


def load_alarm_profiles_from_config(app_config: dict[str, object]) -> tuple[dict[str, DashboardThresholds], str | None]:
    runtime_dashboard = app_config.get("runtime_dashboard", {})
    if not isinstance(runtime_dashboard, dict):
        return {}, None

    default_profile = _normalize_optional_text(runtime_dashboard.get("default_alarm_profile"))
    profiles_payload = runtime_dashboard.get("alarm_profiles", {})
    if not isinstance(profiles_payload, dict):
        raise ValueError("runtime_dashboard.alarm_profiles must be a mapping.")

    profiles: dict[str, DashboardThresholds] = {}
    for raw_name, raw_payload in profiles_payload.items():
        profile_name = str(raw_name).strip()
        if not profile_name:
            continue
        if not isinstance(raw_payload, dict):
            raise ValueError(f"runtime_dashboard.alarm_profiles.{profile_name} must be a mapping.")
        profiles[profile_name] = _coerce_thresholds_from_payload(
            payload=raw_payload,
            fallback=DashboardThresholds().normalized(),
            field_prefix=f"runtime_dashboard.alarm_profiles.{profile_name}",
        )

    if default_profile is not None and default_profile not in profiles:
        available = ", ".join(sorted(profiles.keys())) or "<none>"
        raise ValueError(
            f"default_alarm_profile '{default_profile}' is not defined in runtime_dashboard.alarm_profiles. "
            f"Available profiles: {available}"
        )
    return profiles, default_profile


def resolve_alarm_thresholds(
    *,
    app_config: dict[str, object],
    profile_name: str | None,
    line_id: str | None = None,
    override_max_unknown_ratio: float | None,
    override_max_dropped_small_components: int | None,
    override_min_objects_per_window: int | None,
) -> tuple[DashboardThresholds, str | None]:
    profiles, default_profile = load_alarm_profiles_from_config(app_config)
    selected_profile = resolve_alarm_profile_name(
        app_config=app_config,
        explicit_profile_name=profile_name,
        line_id=line_id,
        default_profile=default_profile,
    )

    thresholds = DashboardThresholds().normalized()
    if selected_profile is not None:
        if selected_profile not in profiles:
            available = ", ".join(sorted(profiles.keys())) or "<none>"
            raise ValueError(f"Unknown alarm profile '{selected_profile}'. Available profiles: {available}")
        thresholds = profiles[selected_profile]

    if override_max_unknown_ratio is not None:
        thresholds = DashboardThresholds(
            max_unknown_ratio=float(override_max_unknown_ratio),
            max_dropped_small_components=thresholds.max_dropped_small_components,
            min_objects_per_window=thresholds.min_objects_per_window,
        )
    if override_max_dropped_small_components is not None:
        thresholds = DashboardThresholds(
            max_unknown_ratio=thresholds.max_unknown_ratio,
            max_dropped_small_components=int(override_max_dropped_small_components),
            min_objects_per_window=thresholds.min_objects_per_window,
        )
    if override_min_objects_per_window is not None:
        thresholds = DashboardThresholds(
            max_unknown_ratio=thresholds.max_unknown_ratio,
            max_dropped_small_components=thresholds.max_dropped_small_components,
            min_objects_per_window=int(override_min_objects_per_window),
        )
    return thresholds.normalized(), selected_profile


def resolve_alarm_profile_name(
    *,
    app_config: dict[str, object],
    explicit_profile_name: str | None,
    line_id: str | None,
    default_profile: str | None,
) -> str | None:
    explicit = _normalize_optional_text(explicit_profile_name)
    if explicit is not None:
        return explicit

    runtime_dashboard = app_config.get("runtime_dashboard", {})
    if not isinstance(runtime_dashboard, dict):
        return default_profile

    profile_map_payload = runtime_dashboard.get("line_profile_map", {})
    if not isinstance(profile_map_payload, dict):
        return default_profile

    normalized_map = {
        str(key).strip(): _normalize_optional_text(value)
        for key, value in profile_map_payload.items()
        if str(key).strip()
    }
    normalized_line = _normalize_optional_text(line_id)
    if normalized_line is not None and normalized_line in normalized_map:
        return normalized_map[normalized_line]
    if "default" in normalized_map and normalized_map["default"] is not None:
        return normalized_map["default"]
    return default_profile


def load_operational_targets(
    *,
    app_config: dict[str, object],
    line_id: str | None,
) -> OperationalTargets:
    runtime_dashboard = app_config.get("runtime_dashboard", {})
    if not isinstance(runtime_dashboard, dict):
        return OperationalTargets()

    base_targets_payload = runtime_dashboard.get("operational_targets", {})
    base_targets = _coerce_operational_targets(
        payload=base_targets_payload if isinstance(base_targets_payload, dict) else {},
        field_prefix="runtime_dashboard.operational_targets",
    )

    line_targets_payload = runtime_dashboard.get("operational_targets_by_line", {})
    if not isinstance(line_targets_payload, dict):
        return base_targets

    normalized_line = _normalize_optional_text(line_id)
    if normalized_line is None or normalized_line not in line_targets_payload:
        return base_targets
    maybe_line_payload = line_targets_payload.get(normalized_line)
    if not isinstance(maybe_line_payload, dict):
        raise ValueError(f"runtime_dashboard.operational_targets_by_line.{normalized_line} must be a mapping.")
    return _merge_operational_targets(
        base=base_targets,
        override=_coerce_operational_targets(
            payload=maybe_line_payload,
            field_prefix=f"runtime_dashboard.operational_targets_by_line.{normalized_line}",
        ),
    )


def resolve_profile_sequence(
    *,
    app_config: dict[str, object],
    requested_profiles: list[str] | None,
) -> list[AlarmProfile]:
    profiles, default_profile = load_alarm_profiles_from_config(app_config)
    if requested_profiles:
        normalized = [name.strip() for name in requested_profiles if str(name).strip()]
        missing = [name for name in normalized if name not in profiles]
        if missing:
            available = ", ".join(sorted(profiles.keys())) or "<none>"
            raise ValueError(f"Unknown alarm profile(s): {', '.join(missing)}. Available profiles: {available}")
        return [AlarmProfile(name=name, thresholds=profiles[name]) for name in normalized]

    if profiles:
        return [AlarmProfile(name=name, thresholds=profiles[name]) for name in sorted(profiles.keys())]

    fallback_name = default_profile or "default"
    return [AlarmProfile(name=fallback_name, thresholds=DashboardThresholds().normalized())]


def _coerce_thresholds_from_payload(
    *,
    payload: dict[str, Any],
    fallback: DashboardThresholds,
    field_prefix: str,
) -> DashboardThresholds:
    return DashboardThresholds(
        max_unknown_ratio=_coerce_float(
            payload.get("max_unknown_ratio", fallback.max_unknown_ratio),
            field_name=f"{field_prefix}.max_unknown_ratio",
        ),
        max_dropped_small_components=_coerce_int(
            payload.get("max_dropped_small_components", fallback.max_dropped_small_components),
            field_name=f"{field_prefix}.max_dropped_small_components",
        ),
        min_objects_per_window=_coerce_int(
            payload.get("min_objects_per_window", fallback.min_objects_per_window),
            field_name=f"{field_prefix}.min_objects_per_window",
        ),
    ).normalized()


def _coerce_operational_targets(*, payload: dict[str, Any], field_prefix: str) -> OperationalTargets:
    return OperationalTargets(
        max_alarm_window_ratio=_coerce_optional_float(
            payload.get("max_alarm_window_ratio"),
            field_name=f"{field_prefix}.max_alarm_window_ratio",
        ),
        max_critical_window_ratio=_coerce_optional_float(
            payload.get("max_critical_window_ratio"),
            field_name=f"{field_prefix}.max_critical_window_ratio",
        ),
        max_mean_unknown_ratio=_coerce_optional_float(
            payload.get("max_mean_unknown_ratio"),
            field_name=f"{field_prefix}.max_mean_unknown_ratio",
        ),
    )


def _merge_operational_targets(*, base: OperationalTargets, override: OperationalTargets) -> OperationalTargets:
    return OperationalTargets(
        max_alarm_window_ratio=(
            override.max_alarm_window_ratio
            if override.max_alarm_window_ratio is not None
            else base.max_alarm_window_ratio
        ),
        max_critical_window_ratio=(
            override.max_critical_window_ratio
            if override.max_critical_window_ratio is not None
            else base.max_critical_window_ratio
        ),
        max_mean_unknown_ratio=(
            override.max_mean_unknown_ratio
            if override.max_mean_unknown_ratio is not None
            else base.max_mean_unknown_ratio
        ),
    )


def _coerce_float(value: object, *, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number.") from exc


def _coerce_int(value: object, *, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc


def _coerce_optional_float(value: object, *, field_name: str) -> float | None:
    if value is None:
        return None
    return _coerce_float(value, field_name=field_name)


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
