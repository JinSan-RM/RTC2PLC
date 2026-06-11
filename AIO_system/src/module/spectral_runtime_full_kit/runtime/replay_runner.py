from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from capture.replay import load_manifest
from common.paths import ensure_directory, make_session_dir, project_root
from models.infer import load_model
from runtime.alarm_profiles import load_operational_targets, resolve_alarm_thresholds
from runtime.dashboard import (
    DashboardThresholds,
    build_runtime_dashboard_payload,
    write_runtime_dashboard_html,
)
from runtime.calibration import RuntimeCalibrationContext, apply_runtime_calibration
from runtime.line_visualization import resolve_project_class_schema_path, write_line_inference_artifacts
from runtime.pixel_inference import infer_pixel_map
from runtime.positioning import RuntimePositionConfig
from runtime.replay_runtime import (
    RuntimeWindowResult,
    parse_session_created_at,
    run_replay_runtime,
    summarize_runtime_results,
)
from runtime.stream_adapter import stream_json_messages


@dataclass(slots=True)
class ReplayRuntimeExecutionConfig:
    app_config: dict[str, object]
    session_dir: Path
    model_path: Path
    output_root: Path | None = None
    window_size: int = 32
    stride: int = 32
    threshold: float = 0.5
    min_area: int = 25
    connectivity: int = 8
    opening_size: int = 0
    closing_size: int = 0
    valid_x_min: int | None = None
    valid_x_max: int | None = None
    min_bbox_width: int = 1
    min_bbox_height: int = 1
    max_bbox_aspect_ratio: float | None = None
    min_class_fraction: float = 0.0
    object_confidence_threshold: float = 0.0
    suppress_iou_threshold: float | None = None
    suppress_containment_threshold: float | None = None
    suppress_across_classes: bool = False
    position_config: RuntimePositionConfig | None = None
    line_id: str | None = None
    alarm_profile: str | None = None
    alarm_max_unknown_ratio: float | None = None
    alarm_max_dropped_small_components: int | None = None
    alarm_min_objects_per_window: int | None = None
    no_dashboard: bool = False
    disable_ack_api: bool = False
    ack_api_token: str | None = None
    stream_endpoint: str | None = None
    stream_timeout_seconds: float = 3.0
    stream_retries: int = 3
    stream_retry_backoff_ms: int = 250
    enforce_operational_targets: bool = False
    max_frames: int | None = None
    output_label_prefix: str = "replay-runtime"
    preflight: dict[str, object] | None = None
    calibration_context: RuntimeCalibrationContext | None = None


@dataclass(slots=True)
class ReplayRuntimeExecutionResult:
    return_code: int
    output_dir: Path
    events_path: Path
    summary_path: Path
    dashboard_path: Path | None
    ack_log_path: Path
    runtime_summary: dict[str, object]
    summary_payload: dict[str, object]
    stream_messages_sent: int
    stream_attempts: int
    stream_failed: bool
    stream_last_error: str | None
    resolved_alarm_profile: str | None
    resolved_dashboard_thresholds: DashboardThresholds
    operational_gate: dict[str, object]


def execute_replay_runtime(config: ReplayRuntimeExecutionConfig) -> ReplayRuntimeExecutionResult:
    session_dir = Path(config.session_dir).resolve()
    model_path = Path(config.model_path).resolve()
    app_config = dict(config.app_config)

    output_root = resolve_output_root(config.output_root, app_config)
    manifest = load_manifest(session_dir)
    model = load_model(model_path)

    lines_path = session_dir / str(manifest.get("files", {}).get("lines", "lines.npy"))
    timestamps_path = session_dir / str(manifest.get("files", {}).get("timestamps", "timestamps.npy"))
    cube = np.load(lines_path, allow_pickle=False)
    timestamps_s = np.load(timestamps_path, allow_pickle=False).astype(np.float64, copy=False)

    if config.max_frames is not None:
        max_frames = max(1, int(config.max_frames))
        cube = cube[:max_frames]
        timestamps_s = timestamps_s[:max_frames]

    calibration_result = apply_runtime_calibration(cube, config.calibration_context)
    inference_cube = calibration_result.cube

    session_created_at = parse_session_created_at(manifest.get("created_at_utc"))  # type: ignore[arg-type]
    results = run_replay_runtime(
        cube=inference_cube,
        timestamps_s=timestamps_s,
        model=model,
        window_size=max(1, int(config.window_size)),
        stride=max(1, int(config.stride)),
        confidence_threshold=float(config.threshold),
        min_area=max(1, int(config.min_area)),
        connectivity=int(config.connectivity),
        opening_size=max(0, int(config.opening_size)),
        closing_size=max(0, int(config.closing_size)),
        valid_x_min=config.valid_x_min,
        valid_x_max=config.valid_x_max,
        min_bbox_width=max(1, int(config.min_bbox_width)),
        min_bbox_height=max(1, int(config.min_bbox_height)),
        max_bbox_aspect_ratio=config.max_bbox_aspect_ratio,
        min_class_fraction=float(config.min_class_fraction),
        object_confidence_threshold=float(config.object_confidence_threshold),
        suppress_iou_threshold=config.suppress_iou_threshold,
        suppress_containment_threshold=config.suppress_containment_threshold,
        suppress_across_classes=bool(config.suppress_across_classes),
        position_config=config.position_config,
        session_created_at_utc=session_created_at,
    )
    runtime_summary = summarize_runtime_results(results)

    output_dir = make_session_dir(output_root, f"{config.output_label_prefix}-{session_dir.name}")
    events_path = output_dir / "events.jsonl"
    summary_path = output_dir / "summary.json"
    ack_log_path = output_dir / "ack-log.jsonl"
    dashboard_path: Path | None = None
    write_events_jsonl(events_path, [item.event for item in results])
    ensure_ack_log_file(ack_log_path)
    line_pixel_result = infer_pixel_map(
        model=model,
        cube=inference_cube,
        confidence_threshold=float(config.threshold),
        valid_x_min=config.valid_x_min,
        valid_x_max=config.valid_x_max,
    )
    line_artifacts = write_line_inference_artifacts(
        output_dir=output_dir,
        cube=inference_cube,
        pixel_result=line_pixel_result,
        object_events=[item.event for item in results],
        class_schema_path=resolve_project_class_schema_path(
            session_dir=session_dir,
            output_root=output_root,
        ),
    )

    dashboard_payload: dict[str, object] | None = None
    resolved_alarm_profile: str | None = None
    resolved_dashboard_thresholds = DashboardThresholds().normalized()
    needs_dashboard_payload = (not config.no_dashboard) or bool(config.stream_endpoint)
    if needs_dashboard_payload:
        resolved_dashboard_thresholds, resolved_alarm_profile = resolve_alarm_thresholds(
            app_config=app_config,
            profile_name=config.alarm_profile,
            line_id=config.line_id,
            override_max_unknown_ratio=config.alarm_max_unknown_ratio,
            override_max_dropped_small_components=config.alarm_max_dropped_small_components,
            override_min_objects_per_window=config.alarm_min_objects_per_window,
        )
        dashboard_payload = build_runtime_dashboard_payload(
            results=results,
            runtime_summary=runtime_summary,
            thresholds=resolved_dashboard_thresholds,
        )
        dashboard_payload["ack_export"] = {
            "session_id": session_dir.name,
            "default_filename": f"{session_dir.name}-ack-log.jsonl",
            "runtime_ack_log_path": str(ack_log_path),
        }
        dashboard_payload["ack_api"] = {
            "enabled": not bool(config.disable_ack_api),
            "session_id": session_dir.name,
            "list_url": "/api/ack",
            "post_url": "/api/ack",
            "history_url": "/api/ack/history",
            "token": str(config.ack_api_token) if config.ack_api_token else "",
        }
        if not config.no_dashboard:
            dashboard_path = write_runtime_dashboard_html(output_dir / "dashboard.html", dashboard_payload)

    stream_messages_sent = 0
    stream_attempts = 0
    stream_failed = False
    stream_last_error: str | None = None
    if config.stream_endpoint:
        if dashboard_payload is None:
            raise ValueError("dashboard payload was not generated for stream adapter.")
        stream_payloads = build_stream_payloads(
            results=results,
            dashboard_payload=dashboard_payload,
            session_dir_name=session_dir.name,
            summary_path=summary_path,
            alarm_profile=resolved_alarm_profile,
            line_id=str(config.line_id) if config.line_id else None,
            threshold_payload={
                "max_unknown_ratio": float(resolved_dashboard_thresholds.max_unknown_ratio),
                "max_dropped_small_components": int(resolved_dashboard_thresholds.max_dropped_small_components),
                "min_objects_per_window": int(resolved_dashboard_thresholds.min_objects_per_window),
            },
            runtime_summary=runtime_summary,
            emitted_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        stream_messages_sent, stream_attempts, stream_last_error = send_stream_with_retry(
            endpoint=str(config.stream_endpoint),
            messages=stream_payloads,
            connect_timeout_s=float(config.stream_timeout_seconds),
            retries=max(0, int(config.stream_retries)),
            retry_backoff_ms=max(0, int(config.stream_retry_backoff_ms)),
        )
        stream_failed = stream_last_error is not None

    operational_targets = load_operational_targets(app_config=app_config, line_id=config.line_id)
    operational_gate = evaluate_operational_gate(
        dashboard_payload=dashboard_payload,
        runtime_summary=runtime_summary,
        targets=operational_targets,
        line_id=config.line_id,
        alarm_profile=resolved_alarm_profile,
    )

    summary_payload: dict[str, object] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "session_dir": str(session_dir),
        "model_path": str(model_path),
        "paths": {
            "session_lines_path": str(lines_path),
            "session_timestamps_path": str(timestamps_path),
            "events_jsonl": str(events_path),
            "ack_log_jsonl": str(ack_log_path),
            "dashboard_html": str(dashboard_path) if dashboard_path is not None else None,
            **line_artifacts.to_summary_paths(),
        },
        "params": {
            "window_size": max(1, int(config.window_size)),
            "stride": max(1, int(config.stride)),
            "threshold": float(config.threshold),
            "min_area": max(1, int(config.min_area)),
            "connectivity": int(config.connectivity),
            "opening_size": max(0, int(config.opening_size)),
            "closing_size": max(0, int(config.closing_size)),
            "valid_x_min": int(config.valid_x_min) if config.valid_x_min is not None else None,
            "valid_x_max": int(config.valid_x_max) if config.valid_x_max is not None else None,
            "min_bbox_width": max(1, int(config.min_bbox_width)),
            "min_bbox_height": max(1, int(config.min_bbox_height)),
            "max_bbox_aspect_ratio": (
                float(config.max_bbox_aspect_ratio) if config.max_bbox_aspect_ratio is not None else None
            ),
            "min_class_fraction": float(config.min_class_fraction),
            "object_confidence_threshold": float(config.object_confidence_threshold),
            "suppress_iou_threshold": (
                float(config.suppress_iou_threshold) if config.suppress_iou_threshold is not None else None
            ),
            "suppress_containment_threshold": (
                float(config.suppress_containment_threshold)
                if config.suppress_containment_threshold is not None
                else None
            ),
            "suppress_across_classes": bool(config.suppress_across_classes),
            "position_mapping": config.position_config.to_dict() if config.position_config is not None else None,
            "alarm_profile": resolved_alarm_profile,
            "line_id": str(config.line_id) if config.line_id else None,
            "alarm_max_unknown_ratio": float(resolved_dashboard_thresholds.max_unknown_ratio),
            "alarm_max_dropped_small_components": int(resolved_dashboard_thresholds.max_dropped_small_components),
            "alarm_min_objects_per_window": int(resolved_dashboard_thresholds.min_objects_per_window),
            "dashboard_enabled": not bool(config.no_dashboard),
            "ack_api_enabled": not bool(config.disable_ack_api),
            "ack_api_token_configured": bool(config.ack_api_token),
            "stream_endpoint": str(config.stream_endpoint) if config.stream_endpoint else None,
            "stream_timeout_seconds": float(config.stream_timeout_seconds),
            "stream_retries": max(0, int(config.stream_retries)),
            "stream_retry_backoff_ms": max(0, int(config.stream_retry_backoff_ms)),
            "stream_enabled": bool(config.stream_endpoint),
            "stream_messages_sent": int(stream_messages_sent),
            "stream_attempts": int(stream_attempts),
            "stream_failed": bool(stream_failed),
            "stream_last_error": stream_last_error,
            "enforce_operational_targets": bool(config.enforce_operational_targets),
            "max_frames": int(config.max_frames) if config.max_frames is not None else None,
        },
        "calibration": calibration_result.summary,
        "runtime_summary": runtime_summary,
        "dashboard_summary": (
            {
                "window_count": int(dashboard_payload.get("window_count", 0)),
                "status_counts": dashboard_payload.get("status_counts", {}),
                "max_unknown_ratio": float(dashboard_payload.get("max_unknown_ratio", 0.0)),
                "max_alarm_unknown_ratio": float(dashboard_payload.get("max_alarm_unknown_ratio", 0.0)),
                "max_dropped_small_components": int(dashboard_payload.get("max_dropped_small_components", 0)),
                "alarm_profile": resolved_alarm_profile,
            }
            if dashboard_payload is not None
            else None
        ),
        "operational_gate": operational_gate,
        "stream_summary": {
            "enabled": bool(config.stream_endpoint),
            "endpoint": str(config.stream_endpoint) if config.stream_endpoint else None,
            "messages_sent": int(stream_messages_sent),
            "attempts": int(stream_attempts),
            "failed": bool(stream_failed),
            "last_error": stream_last_error,
        },
    }
    if config.preflight is not None:
        summary_payload["preflight"] = config.preflight

    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, indent=2)

    return_code = 0
    if config.enforce_operational_targets and not bool(operational_gate.get("passed", True)):
        return_code = 2

    return ReplayRuntimeExecutionResult(
        return_code=return_code,
        output_dir=output_dir,
        events_path=events_path,
        summary_path=summary_path,
        dashboard_path=dashboard_path,
        ack_log_path=ack_log_path,
        runtime_summary=runtime_summary,
        summary_payload=summary_payload,
        stream_messages_sent=int(stream_messages_sent),
        stream_attempts=int(stream_attempts),
        stream_failed=bool(stream_failed),
        stream_last_error=stream_last_error,
        resolved_alarm_profile=resolved_alarm_profile,
        resolved_dashboard_thresholds=resolved_dashboard_thresholds,
        operational_gate=operational_gate,
    )


def resolve_output_root(output_root: Path | None, app_config: dict[str, object]) -> Path:
    if output_root is not None:
        return ensure_directory(Path(output_root))

    paths_section = app_config.get("paths", {})
    reports_output_root = "data/reports"
    if isinstance(paths_section, dict):
        reports_output_root = str(paths_section.get("reports_output_root", reports_output_root))

    resolved = Path(reports_output_root)
    if not resolved.is_absolute():
        resolved = project_root() / resolved
    return ensure_directory(resolved)


def write_events_jsonl(path: Path, events: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event))
            handle.write("\n")
    return path


def ensure_ack_log_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def send_stream_with_retry(
    *,
    endpoint: str,
    messages: list[dict[str, object]],
    connect_timeout_s: float,
    retries: int,
    retry_backoff_ms: int,
) -> tuple[int, int, str | None]:
    attempts = 0
    last_error: str | None = None
    for attempt in range(retries + 1):
        attempts = attempt + 1
        try:
            sent = stream_json_messages(
                endpoint=endpoint,
                messages=messages,
                connect_timeout_s=connect_timeout_s,
            )
            return sent, attempts, None
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt >= retries:
                break
            sleep_s = max(0.0, float(retry_backoff_ms) / 1000.0) * (2**attempt)
            time.sleep(sleep_s)
    return 0, attempts, last_error


def build_stream_payloads(
    *,
    results: list[RuntimeWindowResult],
    dashboard_payload: dict[str, object],
    session_dir_name: str,
    summary_path: Path,
    alarm_profile: str | None,
    line_id: str | None,
    threshold_payload: dict[str, object],
    runtime_summary: dict[str, object],
    emitted_at_utc: str,
) -> list[dict[str, object]]:
    dashboard_windows = dashboard_payload.get("windows", [])
    status_by_window_index: dict[int, dict[str, object]] = {}
    if isinstance(dashboard_windows, list):
        for row in dashboard_windows:
            if not isinstance(row, dict):
                continue
            status_by_window_index[int(row.get("window_index", -1))] = row

    messages: list[dict[str, object]] = []
    sequence = 1
    for item in results:
        event = item.event if isinstance(item.event, dict) else {}
        status_payload = status_by_window_index.get(int(item.window_index), {})
        stream_objects = build_stream_objects(event=event)
        message: dict[str, object] = {
            "stream_version": "runtime-stream.v2",
            "kind": "runtime_window",
            "message_id": make_message_id(
                kind="runtime_window",
                session_id=session_dir_name,
                window_index=int(item.window_index),
                timestamp_ms=int(event.get("timestamp", 0)),
            ),
            "sequence": sequence,
            "emitted_at_utc": emitted_at_utc,
            "session_id": session_dir_name,
            "window_index": int(item.window_index),
            "timestamp": int(event.get("timestamp", 0)),
            "timestamp_iso": str(event.get("timestamp_iso", "")),
            "timestamp_monotonic_s": float(event.get("timestamp_monotonic_s", 0.0)),
            "frame_range": [int(item.frame_start), int(item.frame_end)],
            "status": str(status_payload.get("status", "ok")),
            "alerts": status_payload.get("alerts", []),
            "object_count": int(status_payload.get("object_count", 0)),
            "objects": stream_objects,
            "metrics": {
                "unknown_ratio": float(status_payload.get("unknown_ratio", 0.0)),
                "alarm_unknown_ratio": float(
                    status_payload.get("alarm_unknown_ratio", status_payload.get("unknown_ratio", 0.0))
                ),
                "low_confidence_pixels": int(status_payload.get("low_confidence_pixels", 0)),
                "ignored_pixels": int(status_payload.get("ignored_pixels", 0)),
                "invalid_x_pixels": int(status_payload.get("invalid_x_pixels", 0)),
                "actionable_unknown_pixels": int(status_payload.get("actionable_unknown_pixels", 0)),
                "dropped_small_components": int(status_payload.get("dropped_small_components", 0)),
                "known_pixels": int(status_payload.get("known_pixels", 0)),
                "unknown_pixels": int(status_payload.get("unknown_pixels", 0)),
            },
            "thresholds": threshold_payload,
            "alarm_profile": alarm_profile,
            "line_id": line_id,
        }
        messages.append(message)
        sequence += 1

    messages.append(
        {
            "stream_version": "runtime-stream.v2",
            "kind": "runtime_summary",
            "message_id": make_message_id(
                kind="runtime_summary",
                session_id=session_dir_name,
                window_index=-1,
                timestamp_ms=0,
            ),
            "sequence": sequence,
            "emitted_at_utc": emitted_at_utc,
            "session_id": session_dir_name,
            "summary_path": str(summary_path),
            "alarm_profile": alarm_profile,
            "line_id": line_id,
            "thresholds": threshold_payload,
            "runtime_summary": runtime_summary,
            "dashboard_summary": {
                "status_counts": dashboard_payload.get("status_counts", {}),
                "max_unknown_ratio": float(dashboard_payload.get("max_unknown_ratio", 0.0)),
                "max_alarm_unknown_ratio": float(dashboard_payload.get("max_alarm_unknown_ratio", 0.0)),
                "max_dropped_small_components": int(dashboard_payload.get("max_dropped_small_components", 0)),
            },
        }
    )
    return messages


def build_stream_objects(*, event: dict[str, object]) -> list[dict[str, object]]:
    payload = event.get("objects", [])
    if not isinstance(payload, list):
        return []
    timestamp_ms = int(event.get("timestamp", 0))
    timestamp_monotonic_s = _to_float_or_none(event.get("timestamp_monotonic_s"))
    rows: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["detection_timestamp_ms"] = resolve_stream_object_detection_timestamp_ms(
            event_timestamp_ms=timestamp_ms,
            event_timestamp_monotonic_s=timestamp_monotonic_s,
            obj=row,
        )
        rows.append(row)
    return rows


def resolve_stream_object_detection_timestamp_ms(
    *,
    event_timestamp_ms: int,
    event_timestamp_monotonic_s: float | None,
    obj: dict[str, object],
) -> int:
    if "detection_timestamp_ms" in obj:
        return int(obj.get("detection_timestamp_ms", event_timestamp_ms))
    if event_timestamp_monotonic_s is None:
        return int(event_timestamp_ms)
    timestamp_range_s = obj.get("timestamp_range_s")
    if not isinstance(timestamp_range_s, list) or len(timestamp_range_s) < 2:
        return int(event_timestamp_ms)
    object_end_s = _to_float_or_none(timestamp_range_s[1])
    if object_end_s is None:
        return int(event_timestamp_ms)
    delta_s = max(0.0, float(event_timestamp_monotonic_s) - object_end_s)
    return int(round(float(event_timestamp_ms) - (delta_s * 1000.0)))


def _to_float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def make_message_id(*, kind: str, session_id: str, window_index: int, timestamp_ms: int) -> str:
    raw = f"{kind}|{session_id}|{window_index}|{timestamp_ms}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # noqa: S324
    return f"msg-{digest[:16]}"


def evaluate_operational_gate(
    *,
    dashboard_payload: dict[str, object] | None,
    runtime_summary: dict[str, object],
    targets: object,
    line_id: str | None,
    alarm_profile: str | None,
) -> dict[str, object]:
    max_alarm_window_ratio = getattr(targets, "max_alarm_window_ratio", None)
    max_critical_window_ratio = getattr(targets, "max_critical_window_ratio", None)
    max_mean_unknown_ratio = getattr(targets, "max_mean_unknown_ratio", None)

    windows = []
    if dashboard_payload is not None:
        maybe_windows = dashboard_payload.get("windows", [])
        if isinstance(maybe_windows, list):
            windows = [row for row in maybe_windows if isinstance(row, dict)]
    window_count = int(runtime_summary.get("window_count", len(windows)))
    if window_count <= 0:
        window_count = len(windows)
    status_counts = {}
    if dashboard_payload is not None:
        maybe_status_counts = dashboard_payload.get("status_counts", {})
        if isinstance(maybe_status_counts, dict):
            status_counts = maybe_status_counts

    critical_windows = int(status_counts.get("critical", 0))
    warning_windows = int(status_counts.get("warning", 0))
    alarm_windows = critical_windows + warning_windows
    mean_unknown_ratio = (
        float(sum(float(row.get("unknown_ratio", 0.0)) for row in windows)) / float(window_count)
        if window_count > 0
        else 0.0
    )
    mean_alarm_unknown_ratio = (
        float(
            sum(float(row.get("alarm_unknown_ratio", row.get("unknown_ratio", 0.0))) for row in windows)
        )
        / float(window_count)
        if window_count > 0
        else 0.0
    )
    alarm_window_ratio = float(alarm_windows) / float(window_count) if window_count > 0 else 0.0
    critical_window_ratio = float(critical_windows) / float(window_count) if window_count > 0 else 0.0

    violations: list[dict[str, object]] = []
    if max_alarm_window_ratio is not None and alarm_window_ratio > float(max_alarm_window_ratio):
        violations.append(
            {
                "metric": "alarm_window_ratio",
                "actual": alarm_window_ratio,
                "limit": float(max_alarm_window_ratio),
            }
        )
    if max_critical_window_ratio is not None and critical_window_ratio > float(max_critical_window_ratio):
        violations.append(
            {
                "metric": "critical_window_ratio",
                "actual": critical_window_ratio,
                "limit": float(max_critical_window_ratio),
            }
        )
    if max_mean_unknown_ratio is not None and mean_alarm_unknown_ratio > float(max_mean_unknown_ratio):
        violations.append(
            {
                "metric": "mean_alarm_unknown_ratio",
                "actual": mean_alarm_unknown_ratio,
                "limit": float(max_mean_unknown_ratio),
            }
        )

    return {
        "line_id": str(line_id) if line_id else None,
        "alarm_profile": alarm_profile,
        "targets": {
            "max_alarm_window_ratio": max_alarm_window_ratio,
            "max_critical_window_ratio": max_critical_window_ratio,
            "max_mean_unknown_ratio": max_mean_unknown_ratio,
        },
        "actual": {
            "window_count": window_count,
            "alarm_window_ratio": alarm_window_ratio,
            "critical_window_ratio": critical_window_ratio,
            "mean_unknown_ratio": mean_unknown_ratio,
            "mean_alarm_unknown_ratio": mean_alarm_unknown_ratio,
            "critical_windows": critical_windows,
            "warning_windows": warning_windows,
        },
        "passed": len(violations) == 0,
        "violations": violations,
    }
