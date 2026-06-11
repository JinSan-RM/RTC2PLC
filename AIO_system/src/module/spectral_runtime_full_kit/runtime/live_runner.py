from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from camera.base import CameraInfo, CameraProvider, CameraSettings, FrameSource
from camera.stream_worker import StreamWorker
from common.paths import make_session_dir
from models.infer import load_model
from runtime.alarm_profiles import load_operational_targets, resolve_alarm_thresholds
from runtime.dashboard import (
    DashboardThresholds,
    build_runtime_dashboard_payload,
    write_runtime_dashboard_html,
)
from runtime.calibration import (
    RuntimeCalibrationContext,
    apply_runtime_calibration,
    summarize_calibration_windows,
)
from runtime.objectizer import objectize_class_map
from runtime.pixel_inference import infer_pixel_map, summarize_pixel_map
from runtime.positioning import RuntimePositionConfig
from runtime.replay_runner import (
    build_stream_payloads,
    ensure_ack_log_file,
    evaluate_operational_gate,
    resolve_output_root,
    send_stream_with_retry,
    write_events_jsonl,
)
from runtime.replay_runtime import RuntimeWindowResult, build_runtime_event, summarize_runtime_results


@dataclass(slots=True)
class LiveRuntimeExecutionConfig:
    app_config: dict[str, object]
    provider: CameraProvider
    settings: CameraSettings
    model_path: Path
    output_root: Path | None = None
    source_name: str = "lumo"
    session_id: str = "live"
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
    queue_size: int = 64
    frame_timeout_seconds: float = 0.5
    max_idle_seconds: float | None = 30.0
    output_label_prefix: str = "runtime-engine-lumo"
    preflight: dict[str, object] | None = None
    calibration_context: RuntimeCalibrationContext | None = None


@dataclass(slots=True)
class LiveRuntimeExecutionResult:
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
    live_status: dict[str, object]


def execute_live_runtime(config: LiveRuntimeExecutionConfig) -> LiveRuntimeExecutionResult:
    app_config = dict(config.app_config)
    model_path = Path(config.model_path).resolve()
    model = load_model(model_path)

    output_root = resolve_output_root(config.output_root, app_config)
    session_started_at_utc = datetime.now(timezone.utc)
    runtime_session_id = str(config.session_id).strip() or "live"

    source: FrameSource | None = None
    worker: StreamWorker | None = None
    line_buffer: list[np.ndarray] = []
    timestamp_buffer: list[float] = []
    results: list[RuntimeWindowResult] = []
    frame_counter = 0
    buffer_start_index = 0
    next_window_start = 0
    local_timeout_frames = 0
    connected = False
    streaming = False
    last_error: str | None = None
    last_frame_received_at = time.monotonic()
    source_status: dict[str, object] = {}
    calibration_windows: list[dict[str, object]] = []

    try:
        source = config.provider.open(config.settings)
        connected = True
        mismatch_error = _resolve_source_settings_mismatch(
            expected_settings=config.settings,
            resolved_settings=source.settings,
        )
        if mismatch_error is not None:
            last_error = mismatch_error
        else:
            worker = StreamWorker(source, queue_maxsize=max(1, int(config.queue_size)))
            worker.start(max_frames=int(config.max_frames) if config.max_frames is not None else None)

            while True:
                frame = worker.pop_frame(timeout_s=float(config.frame_timeout_seconds))
                if frame is None:
                    if worker.stats.finished:
                        break
                    local_timeout_frames += 1
                    if config.max_idle_seconds is not None:
                        idle_seconds = time.monotonic() - last_frame_received_at
                        if idle_seconds > float(config.max_idle_seconds):
                            last_error = (
                                "live stream idle timeout exceeded: "
                                f"idle={idle_seconds:.3f}s, max_idle={float(config.max_idle_seconds):.3f}s"
                            )
                            break
                    continue

                frame_counter += 1
                streaming = True
                last_frame_received_at = time.monotonic()
                line_buffer.append(np.asarray(frame.data))
                timestamp_buffer.append(float(frame.timestamp_monotonic_s))

                while (next_window_start + max(1, int(config.window_size))) <= frame_counter:
                    start_offset = next_window_start - buffer_start_index
                    end_offset = start_offset + max(1, int(config.window_size))
                    window_result, calibration_summary = _build_runtime_window(
                        line_chunk=line_buffer[start_offset:end_offset],
                        timestamp_chunk=timestamp_buffer[start_offset:end_offset],
                        model=model,
                        calibration_context=config.calibration_context,
                        window_index=len(results),
                        frame_start=next_window_start,
                        threshold=float(config.threshold),
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
                        session_started_at_utc=session_started_at_utc,
                    )
                    results.append(window_result)
                    calibration_windows.append(calibration_summary)
                    next_window_start += max(1, int(config.stride))
                    line_buffer, timestamp_buffer, buffer_start_index = _prune_window_buffers(
                        line_buffer=line_buffer,
                        timestamp_buffer=timestamp_buffer,
                        frame_counter=frame_counter,
                        buffer_start_index=buffer_start_index,
                        next_window_start=next_window_start,
                    )

            while next_window_start < frame_counter:
                start_offset = next_window_start - buffer_start_index
                if start_offset < 0 or start_offset >= len(line_buffer):
                    break
                window_result, calibration_summary = _build_runtime_window(
                    line_chunk=line_buffer[start_offset:],
                    timestamp_chunk=timestamp_buffer[start_offset:],
                    model=model,
                    calibration_context=config.calibration_context,
                    window_index=len(results),
                    frame_start=next_window_start,
                    threshold=float(config.threshold),
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
                    session_started_at_utc=session_started_at_utc,
                )
                results.append(window_result)
                calibration_windows.append(calibration_summary)
                next_window_start += max(1, int(config.stride))
                line_buffer, timestamp_buffer, buffer_start_index = _prune_window_buffers(
                    line_buffer=line_buffer,
                    timestamp_buffer=timestamp_buffer,
                    frame_counter=frame_counter,
                    buffer_start_index=buffer_start_index,
                    next_window_start=next_window_start,
                )

            if worker.stats.error:
                last_error = worker.stats.error
    finally:
        source_status = _safe_get_source_status(source)
        if worker is not None:
            worker.stop()
        elif source is not None:
            source.close()

    live_status = _build_live_status(
        source_status=source_status,
        connected=connected,
        streaming=streaming,
        frame_counter=frame_counter,
        dropped_frames=int(worker.stats.dropped_frames) if worker is not None else 0,
        timeout_frames=local_timeout_frames,
        last_error=last_error,
    )

    runtime_summary = summarize_runtime_results(results)
    runtime_summary["live_status"] = dict(live_status)
    calibration_summary = summarize_calibration_windows(calibration_windows)

    output_dir = make_session_dir(output_root, f"{config.output_label_prefix}-{runtime_session_id}")
    events_path = output_dir / "events.jsonl"
    summary_path = output_dir / "summary.json"
    ack_log_path = output_dir / "ack-log.jsonl"
    dashboard_path: Path | None = None
    write_events_jsonl(events_path, [item.event for item in results])
    ensure_ack_log_file(ack_log_path)

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
            "session_id": runtime_session_id,
            "default_filename": f"{runtime_session_id}-ack-log.jsonl",
            "runtime_ack_log_path": str(ack_log_path),
        }
        dashboard_payload["ack_api"] = {
            "enabled": not bool(config.disable_ack_api),
            "session_id": runtime_session_id,
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
            session_dir_name=runtime_session_id,
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
        "source": {
            "name": str(config.source_name),
            "session_id": runtime_session_id,
            "camera_info": source.camera_info.to_dict() if source is not None else None,
            "settings": source.settings.to_dict() if source is not None else config.settings.to_dict(),
        },
        "model_path": str(model_path),
        "paths": {
            "events_jsonl": str(events_path),
            "ack_log_jsonl": str(ack_log_path),
            "dashboard_html": str(dashboard_path) if dashboard_path is not None else None,
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
            "queue_size": max(1, int(config.queue_size)),
            "frame_timeout_seconds": float(config.frame_timeout_seconds),
            "max_idle_seconds": float(config.max_idle_seconds) if config.max_idle_seconds is not None else None,
        },
        "calibration": calibration_summary,
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
        "live_status": dict(live_status),
    }
    if config.preflight is not None:
        summary_payload["preflight"] = config.preflight

    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, indent=2)

    return_code = 0
    if _is_live_runtime_unhealthy(
        live_status=live_status,
        frame_counter=frame_counter,
    ):
        return_code = 3
    elif config.enforce_operational_targets and not bool(operational_gate.get("passed", True)):
        return_code = 2

    return LiveRuntimeExecutionResult(
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
        live_status=live_status,
    )


def _build_runtime_window(
    *,
    line_chunk: list[np.ndarray],
    timestamp_chunk: list[float],
    model: Any,
    calibration_context: RuntimeCalibrationContext | None,
    window_index: int,
    frame_start: int,
    threshold: float,
    min_area: int,
    connectivity: int,
    opening_size: int,
    closing_size: int,
    valid_x_min: int | None,
    valid_x_max: int | None,
    min_bbox_width: int,
    min_bbox_height: int,
    max_bbox_aspect_ratio: float | None,
    min_class_fraction: float,
    object_confidence_threshold: float,
    suppress_iou_threshold: float | None,
    suppress_containment_threshold: float | None,
    suppress_across_classes: bool,
    position_config: RuntimePositionConfig | None,
    session_started_at_utc: datetime,
) -> tuple[RuntimeWindowResult, dict[str, object]]:
    cube_window = np.stack([np.asarray(line) for line in line_chunk], axis=0)
    calibration_result = apply_runtime_calibration(cube_window, calibration_context)
    inference_cube = calibration_result.cube
    timestamps_window = np.asarray(timestamp_chunk, dtype=np.float64)
    pixel_result = infer_pixel_map(
        model=model,
        cube=inference_cube,
        confidence_threshold=threshold,
        valid_x_min=valid_x_min,
        valid_x_max=valid_x_max,
    )
    object_result = objectize_class_map(
        class_map=pixel_result.class_map,
        confidence_map=pixel_result.confidence_map,
        class_names=pixel_result.class_names,
        min_area=min_area,
        connectivity=connectivity,
        opening_size=opening_size,
        closing_size=closing_size,
        min_bbox_width=min_bbox_width,
        min_bbox_height=min_bbox_height,
        max_bbox_aspect_ratio=max_bbox_aspect_ratio,
        min_class_fraction=min_class_fraction,
        object_confidence_threshold=object_confidence_threshold,
        suppress_iou_threshold=suppress_iou_threshold,
        suppress_containment_threshold=suppress_containment_threshold,
        suppress_across_classes=suppress_across_classes,
        timestamps_s=timestamps_window,
    )
    frame_end = frame_start + int(inference_cube.shape[0]) - 1
    event = build_runtime_event(
        object_result=object_result,
        class_names=pixel_result.class_names,
        window_index=window_index,
        frame_start=frame_start,
        frame_end=frame_end,
        timestamp_monotonic_s=float(timestamps_window[-1]),
        session_created_at_utc=session_started_at_utc,
        position_config=position_config,
    )
    return (
        RuntimeWindowResult(
            window_index=int(window_index),
            frame_start=int(frame_start),
            frame_end=int(frame_end),
            event=event,
            pixel_summary=summarize_pixel_map(pixel_result),
            object_summary=object_result.to_dict(),
        ),
        calibration_result.summary,
    )


def _prune_window_buffers(
    *,
    line_buffer: list[np.ndarray],
    timestamp_buffer: list[float],
    frame_counter: int,
    buffer_start_index: int,
    next_window_start: int,
) -> tuple[list[np.ndarray], list[float], int]:
    prune_until = min(int(frame_counter), int(next_window_start))
    drop_count = prune_until - int(buffer_start_index)
    if drop_count <= 0:
        return line_buffer, timestamp_buffer, int(buffer_start_index)
    del line_buffer[:drop_count]
    del timestamp_buffer[:drop_count]
    return line_buffer, timestamp_buffer, int(prune_until)


def _safe_get_source_status(source: FrameSource | None) -> dict[str, object]:
    if source is None:
        return {}
    getter = getattr(source, "get_status", None)
    if not callable(getter):
        return {}
    try:
        payload = getter()
    except Exception:  # noqa: BLE001
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _build_live_status(
    *,
    source_status: dict[str, object],
    connected: bool,
    streaming: bool,
    frame_counter: int,
    dropped_frames: int,
    timeout_frames: int,
    last_error: str | None,
) -> dict[str, object]:
    merged_last_error = (
        _coerce_optional_text(source_status.get("last_error"))
        or _coerce_optional_text(source_status.get("error"))
        or _coerce_optional_text(last_error)
    )
    return {
        "connected": bool(source_status.get("connected", connected)),
        "streaming": bool(source_status.get("streaming", streaming)),
        "frame_counter": max(int(frame_counter), _coerce_int(source_status.get("frame_counter"), 0)),
        "dropped_frames": max(int(dropped_frames), _coerce_int(source_status.get("dropped_frames"), 0)),
        "timeout_frames": max(int(timeout_frames), _coerce_int(source_status.get("timeout_frames"), 0)),
        "last_error": merged_last_error,
    }


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _coerce_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _resolve_source_settings_mismatch(
    *,
    expected_settings: CameraSettings,
    resolved_settings: CameraSettings,
) -> str | None:
    expected_band_count = int(expected_settings.band_count)
    expected_spatial_width = int(expected_settings.spatial_width)
    resolved_band_count = int(resolved_settings.band_count)
    resolved_spatial_width = int(resolved_settings.spatial_width)
    if expected_band_count != resolved_band_count or expected_spatial_width != resolved_spatial_width:
        return (
            "live source settings mismatch after open: "
            f"expected band_count={expected_band_count}, spatial_width={expected_spatial_width}; "
            f"resolved band_count={resolved_band_count}, spatial_width={resolved_spatial_width}"
        )
    return None


def _is_live_runtime_unhealthy(*, live_status: dict[str, object], frame_counter: int) -> bool:
    last_error = _coerce_optional_text(live_status.get("last_error"))
    if last_error is not None:
        return True
    if int(frame_counter) <= 0:
        return True
    return False
