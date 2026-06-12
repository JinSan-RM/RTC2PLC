from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from camera.base import CameraProvider, CameraSettings
from camera.lumo_provider import LumoCameraProvider
from features.bands import resolve_rgb_bands
from common.local_network import merge_lumo_network_auto_settings
from models.bundle import ModelBundleManifest, load_bundle_manifest, validate_bundle
from runtime.calibration import RuntimeCalibrationContext, build_runtime_calibration_context
from runtime.live_runner import LiveRuntimeExecutionConfig, execute_live_runtime
from runtime.positioning import RuntimePositionConfig
from runtime.replay_runner import ReplayRuntimeExecutionConfig, execute_replay_runtime


@dataclass(slots=True)
class InferenceRuntimeParams:
    """Shared pixel inference, objectization, dashboard, and output parameters."""

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
    dashboard: bool = True
    ack_api: bool = True
    ack_api_token: str | None = None
    stream_endpoint: str | None = None
    stream_timeout_seconds: float = 3.0
    stream_retries: int = 3
    stream_retry_backoff_ms: int = 250
    enforce_operational_targets: bool = False
    max_frames: int | None = None
    calibration_context: RuntimeCalibrationContext | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object] | None,
        *,
        base: "InferenceRuntimeParams | None" = None,
    ) -> "InferenceRuntimeParams":
        result = replace(base) if base is not None else cls()
        data = dict(payload or {})
        result.window_size = _resolve_int(data.get("window_size"), result.window_size, minimum=1)
        result.stride = _resolve_int(data.get("stride"), result.stride, minimum=1)
        result.threshold = _resolve_unit_float(data.get("threshold"), result.threshold)
        result.min_area = _resolve_int(data.get("min_area"), result.min_area, minimum=1)
        result.connectivity = _resolve_connectivity(data.get("connectivity"), result.connectivity)
        result.opening_size = _resolve_int(data.get("opening_size"), result.opening_size, minimum=0)
        result.closing_size = _resolve_int(data.get("closing_size"), result.closing_size, minimum=0)
        result.valid_x_min = _resolve_optional_int(data.get("valid_x_min"), result.valid_x_min, minimum=0)
        result.valid_x_max = _resolve_optional_int(data.get("valid_x_max"), result.valid_x_max, minimum=0)
        result.min_bbox_width = _resolve_int(data.get("min_bbox_width"), result.min_bbox_width, minimum=1)
        result.min_bbox_height = _resolve_int(data.get("min_bbox_height"), result.min_bbox_height, minimum=1)
        result.max_bbox_aspect_ratio = _resolve_optional_float(
            data.get("max_bbox_aspect_ratio"),
            result.max_bbox_aspect_ratio,
            minimum=1.0,
        )
        result.min_class_fraction = _resolve_unit_float(data.get("min_class_fraction"), result.min_class_fraction)
        result.object_confidence_threshold = _resolve_unit_float(
            data.get("object_confidence_threshold"),
            result.object_confidence_threshold,
        )
        result.suppress_iou_threshold = _resolve_optional_float(
            data.get("suppress_iou_threshold"),
            result.suppress_iou_threshold,
            minimum=0.0,
        )
        result.suppress_containment_threshold = _resolve_optional_float(
            data.get("suppress_containment_threshold"),
            result.suppress_containment_threshold,
            minimum=0.0,
        )
        if "suppress_across_classes" in data:
            result.suppress_across_classes = bool(data.get("suppress_across_classes"))
        position_config = build_position_config_from_mapping(data)
        if position_config is not None:
            result.position_config = position_config
        return result

    def with_updates(self, **updates: object) -> "InferenceRuntimeParams":
        allowed = set(self.__dataclass_fields__)  # type: ignore[attr-defined]
        unknown = sorted(set(updates) - allowed)
        if unknown:
            raise ValueError(f"unknown runtime parameter(s): {', '.join(unknown)}")
        return replace(self, **updates)


@dataclass(slots=True)
class LumoLiveConfig:
    """Lumo provider and CameraSettings values for live runtime execution."""

    band_count: int = 224
    spatial_width: int = 640
    integration_time_us: int = 4000
    line_rate_hz: float = 100.0
    rgb_bands: tuple[int, int, int] | None = None
    mirror_line: bool = False
    max_frames: int | None = None
    serial_number: str | None = None
    ip_address: str | None = None
    interface_name: str | None = None
    mac_address: str | None = None
    device_index: int = 0
    timeout_ms: int = 5000
    skip_scan: bool = False
    provider_mode: str = "native"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object] | None) -> "LumoLiveConfig":
        data = merge_lumo_network_auto_settings(dict(payload or {}))
        camera_section = data.get("camera", {})
        lumo_section = data.get("lumo", {})
        breeze_section = data.get("breeze_compat", {})
        camera = dict(camera_section) if isinstance(camera_section, Mapping) else {}
        lumo = dict(lumo_section) if isinstance(lumo_section, Mapping) else {}
        breeze = dict(breeze_section) if isinstance(breeze_section, Mapping) else {}

        raw_rgb = camera.get("rgb_bands")
        rgb_bands: tuple[int, int, int] | None = None
        if isinstance(raw_rgb, (list, tuple)) and len(raw_rgb) >= 3:
            rgb_bands = (int(raw_rgb[0]), int(raw_rgb[1]), int(raw_rgb[2]))

        return cls(
            band_count=_resolve_int(camera.get("band_count"), 224, minimum=1),
            spatial_width=_resolve_int(camera.get("spatial_width"), 640, minimum=1),
            integration_time_us=_resolve_int(
                camera.get("integration_time_us", camera.get("exposure_time_us")),
                4000,
                minimum=1,
            ),
            line_rate_hz=_resolve_float(camera.get("line_rate_hz"), 100.0, minimum=0.0),
            rgb_bands=rgb_bands,
            mirror_line=bool(breeze.get("mirror_line", False)),
            serial_number=_optional_text(lumo.get("serial_number")),
            ip_address=_optional_text(lumo.get("ip_address")),
            interface_name=_optional_text(lumo.get("interface_name")),
            mac_address=_optional_text(lumo.get("mac_address") or lumo.get("target_mac_address")),
            device_index=_resolve_int(lumo.get("device_index"), 0, minimum=0),
            timeout_ms=_resolve_int(lumo.get("grab_timeout_ms"), 5000, minimum=1),
            skip_scan=bool(lumo.get("skip_scan", False)),
            provider_mode=str(lumo.get("provider_mode", "native") or "native").lower(),
        )

    def build_settings(self, *, max_frames: int | None = None) -> CameraSettings:
        rgb = self.rgb_bands or resolve_rgb_bands(int(self.band_count))
        return CameraSettings(
            band_count=int(self.band_count),
            spatial_width=int(self.spatial_width),
            integration_time_us=int(self.integration_time_us),
            line_rate_hz=float(self.line_rate_hz),
            max_frames=max_frames if max_frames is not None else self.max_frames,
            rgb_bands=rgb,
            mirror_line=bool(self.mirror_line),
        )

    def build_provider(self) -> LumoCameraProvider:
        return LumoCameraProvider(
            provider_mode=str(self.provider_mode or "native"),
            serial_number=self.serial_number,
            ip_address=self.ip_address,
            interface_name=self.interface_name,
            mac_address=self.mac_address,
            device_index=int(self.device_index),
            timeout_ms=int(self.timeout_ms),
            skip_scan=bool(self.skip_scan),
        )

    def with_updates(self, **updates: object) -> "LumoLiveConfig":
        allowed = set(self.__dataclass_fields__)  # type: ignore[attr-defined]
        unknown = sorted(set(updates) - allowed)
        if unknown:
            raise ValueError(f"unknown lumo config parameter(s): {', '.join(unknown)}")
        return replace(self, **updates)


@dataclass(slots=True)
class RuntimeOutputResult:
    """Normalized result from replay or live inference."""

    source: str
    return_code: int
    output_dir: Path
    events_path: Path
    summary_path: Path
    dashboard_path: Path | None
    ack_log_path: Path
    runtime_summary: dict[str, object]
    summary_payload: dict[str, object]
    operational_gate: dict[str, object]
    stream_messages_sent: int
    stream_attempts: int
    stream_failed: bool
    stream_last_error: str | None
    live_status: dict[str, object] | None = None

    @property
    def ok(self) -> bool:
        return int(self.return_code) == 0 and not bool(self.stream_failed)

    def screen_outputs(self) -> dict[str, str]:
        paths = self.summary_payload.get("paths", {})
        if not isinstance(paths, dict):
            paths = {}
        outputs: dict[str, str] = {}
        if self.dashboard_path is not None:
            outputs["dashboard_html"] = str(self.dashboard_path)
        for key in ("line_preview_png", "line_overlay_png", "line_class_map_png"):
            value = paths.get(key)
            if value:
                outputs[key] = str(value)
        return outputs

    def data_outputs(self) -> dict[str, str]:
        outputs = {
            "events_jsonl": str(self.events_path),
            "summary_json": str(self.summary_path),
            "ack_log_jsonl": str(self.ack_log_path),
        }
        stream_summary = self.summary_payload.get("stream_summary", {})
        if isinstance(stream_summary, dict) and stream_summary.get("endpoint"):
            outputs["stream_endpoint"] = str(stream_summary["endpoint"])
        return outputs


class SpectralRuntimeModule:
    """Copy-folder runtime facade for replay and Lumo live inference."""

    def __init__(
        self,
        *,
        model_path: Path,
        app_config: Mapping[str, object] | None = None,
        output_root: Path | None = None,
        default_params: InferenceRuntimeParams | None = None,
        calibration_context: RuntimeCalibrationContext | None = None,
        bundle_dir: Path | None = None,
        bundle_manifest: ModelBundleManifest | None = None,
    ) -> None:
        self.model_path = Path(model_path).resolve()
        self.app_config = dict(app_config or {})
        self.output_root = Path(output_root).resolve() if output_root is not None else None
        self.bundle_dir = Path(bundle_dir).resolve() if bundle_dir is not None else None
        self.bundle_manifest = bundle_manifest
        base_params = default_params or InferenceRuntimeParams()
        if calibration_context is not None and base_params.calibration_context is None:
            base_params = replace(base_params, calibration_context=calibration_context)
        self._default_params = base_params

    @classmethod
    def from_model(
        cls,
        model_path: Path,
        *,
        app_config: Mapping[str, object] | None = None,
        output_root: Path | None = None,
        default_params: InferenceRuntimeParams | None = None,
        calibration_context: RuntimeCalibrationContext | None = None,
    ) -> "SpectralRuntimeModule":
        return cls(
            model_path=Path(model_path),
            app_config=app_config,
            output_root=output_root,
            default_params=default_params,
            calibration_context=calibration_context,
        )

    @classmethod
    def from_bundle(
        cls,
        bundle_dir: Path,
        *,
        app_config: Mapping[str, object] | None = None,
        output_root: Path | None = None,
        verify_bundle: bool = True,
    ) -> "SpectralRuntimeModule":
        root = Path(bundle_dir).resolve()
        manifest = load_bundle_manifest(root)
        if verify_bundle:
            report = validate_bundle(bundle_dir=root, manifest=manifest, verify_hashes=True)
            if not report.ok:
                errors = "; ".join(report.errors)
                raise ValueError(f"model bundle validation failed: {errors}")
        calibration_context = build_runtime_calibration_context(bundle_dir=root, manifest=manifest)
        params = InferenceRuntimeParams.from_mapping(manifest.runtime_params)
        return cls(
            model_path=(root / manifest.model.path).resolve(),
            app_config=app_config,
            output_root=output_root,
            default_params=params,
            calibration_context=calibration_context,
            bundle_dir=root,
            bundle_manifest=manifest,
        )

    def default_params(self) -> InferenceRuntimeParams:
        return replace(self._default_params)

    def run_replay(
        self,
        *,
        session_dir: Path,
        params: InferenceRuntimeParams | None = None,
        output_label_prefix: str = "portable-replay-runtime",
    ) -> RuntimeOutputResult:
        runtime_params = self._resolve_params(params)
        config = ReplayRuntimeExecutionConfig(
            app_config=self.app_config,
            session_dir=Path(session_dir),
            model_path=self.model_path,
            output_root=self.output_root,
            window_size=int(runtime_params.window_size),
            stride=int(runtime_params.stride),
            threshold=float(runtime_params.threshold),
            min_area=int(runtime_params.min_area),
            connectivity=int(runtime_params.connectivity),
            opening_size=int(runtime_params.opening_size),
            closing_size=int(runtime_params.closing_size),
            valid_x_min=runtime_params.valid_x_min,
            valid_x_max=runtime_params.valid_x_max,
            min_bbox_width=int(runtime_params.min_bbox_width),
            min_bbox_height=int(runtime_params.min_bbox_height),
            max_bbox_aspect_ratio=runtime_params.max_bbox_aspect_ratio,
            min_class_fraction=float(runtime_params.min_class_fraction),
            object_confidence_threshold=float(runtime_params.object_confidence_threshold),
            suppress_iou_threshold=runtime_params.suppress_iou_threshold,
            suppress_containment_threshold=runtime_params.suppress_containment_threshold,
            suppress_across_classes=bool(runtime_params.suppress_across_classes),
            position_config=runtime_params.position_config,
            line_id=runtime_params.line_id,
            alarm_profile=runtime_params.alarm_profile,
            alarm_max_unknown_ratio=runtime_params.alarm_max_unknown_ratio,
            alarm_max_dropped_small_components=runtime_params.alarm_max_dropped_small_components,
            alarm_min_objects_per_window=runtime_params.alarm_min_objects_per_window,
            no_dashboard=not bool(runtime_params.dashboard),
            disable_ack_api=not bool(runtime_params.ack_api),
            ack_api_token=runtime_params.ack_api_token,
            stream_endpoint=runtime_params.stream_endpoint,
            stream_timeout_seconds=float(runtime_params.stream_timeout_seconds),
            stream_retries=int(runtime_params.stream_retries),
            stream_retry_backoff_ms=int(runtime_params.stream_retry_backoff_ms),
            enforce_operational_targets=bool(runtime_params.enforce_operational_targets),
            max_frames=runtime_params.max_frames,
            output_label_prefix=output_label_prefix,
            calibration_context=runtime_params.calibration_context,
        )
        return _normalize_result("replay", execute_replay_runtime(config))

    def run_live(
        self,
        *,
        provider: CameraProvider,
        settings: CameraSettings,
        params: InferenceRuntimeParams | None = None,
        source_name: str = "live",
        session_id: str = "live",
        queue_size: int = 64,
        frame_timeout_seconds: float = 0.5,
        max_idle_seconds: float | None = 30.0,
        output_label_prefix: str = "portable-live-runtime",
    ) -> RuntimeOutputResult:
        runtime_params = self._resolve_params(params)
        config = LiveRuntimeExecutionConfig(
            app_config=self.app_config,
            provider=provider,
            settings=settings,
            model_path=self.model_path,
            output_root=self.output_root,
            source_name=source_name,
            session_id=session_id,
            window_size=int(runtime_params.window_size),
            stride=int(runtime_params.stride),
            threshold=float(runtime_params.threshold),
            min_area=int(runtime_params.min_area),
            connectivity=int(runtime_params.connectivity),
            opening_size=int(runtime_params.opening_size),
            closing_size=int(runtime_params.closing_size),
            valid_x_min=runtime_params.valid_x_min,
            valid_x_max=runtime_params.valid_x_max,
            min_bbox_width=int(runtime_params.min_bbox_width),
            min_bbox_height=int(runtime_params.min_bbox_height),
            max_bbox_aspect_ratio=runtime_params.max_bbox_aspect_ratio,
            min_class_fraction=float(runtime_params.min_class_fraction),
            object_confidence_threshold=float(runtime_params.object_confidence_threshold),
            suppress_iou_threshold=runtime_params.suppress_iou_threshold,
            suppress_containment_threshold=runtime_params.suppress_containment_threshold,
            suppress_across_classes=bool(runtime_params.suppress_across_classes),
            position_config=runtime_params.position_config,
            line_id=runtime_params.line_id,
            alarm_profile=runtime_params.alarm_profile,
            alarm_max_unknown_ratio=runtime_params.alarm_max_unknown_ratio,
            alarm_max_dropped_small_components=runtime_params.alarm_max_dropped_small_components,
            alarm_min_objects_per_window=runtime_params.alarm_min_objects_per_window,
            no_dashboard=not bool(runtime_params.dashboard),
            disable_ack_api=not bool(runtime_params.ack_api),
            ack_api_token=runtime_params.ack_api_token,
            stream_endpoint=runtime_params.stream_endpoint,
            stream_timeout_seconds=float(runtime_params.stream_timeout_seconds),
            stream_retries=int(runtime_params.stream_retries),
            stream_retry_backoff_ms=int(runtime_params.stream_retry_backoff_ms),
            enforce_operational_targets=bool(runtime_params.enforce_operational_targets),
            max_frames=runtime_params.max_frames,
            queue_size=int(queue_size),
            frame_timeout_seconds=float(frame_timeout_seconds),
            max_idle_seconds=max_idle_seconds,
            output_label_prefix=output_label_prefix,
            calibration_context=runtime_params.calibration_context,
        )
        return _normalize_result(source_name, execute_live_runtime(config))

    def run_lumo_live(
        self,
        *,
        lumo_config: LumoLiveConfig,
        params: InferenceRuntimeParams | None = None,
        session_id: str = "lumo-live",
        queue_size: int = 64,
        frame_timeout_seconds: float = 0.5,
        max_idle_seconds: float | None = 30.0,
    ) -> RuntimeOutputResult:
        runtime_params = self._resolve_params(params)
        if runtime_params.max_frames is None and lumo_config.max_frames is not None:
            runtime_params = replace(runtime_params, max_frames=int(lumo_config.max_frames))
        return self.run_live(
            provider=lumo_config.build_provider(),
            settings=lumo_config.build_settings(max_frames=runtime_params.max_frames),
            params=runtime_params,
            source_name="lumo",
            session_id=session_id,
            queue_size=queue_size,
            frame_timeout_seconds=frame_timeout_seconds,
            max_idle_seconds=max_idle_seconds,
            output_label_prefix="portable-lumo-live-runtime",
        )

    def _resolve_params(self, params: InferenceRuntimeParams | None) -> InferenceRuntimeParams:
        return replace(params) if params is not None else self.default_params()


def build_position_config_from_mapping(payload: Mapping[str, object]) -> RuntimePositionConfig | None:
    keys = (
        "x_mm_per_pixel",
        "y_mm_per_frame",
        "belt_speed_mm_s",
        "encoder_counts_per_mm",
        "encoder_origin_count",
        "nozzle_origin_x_mm",
        "nozzle_pitch_mm",
    )
    if not any(payload.get(key) is not None for key in keys):
        return None
    return RuntimePositionConfig(
        x_mm_per_pixel=_resolve_optional_float(payload.get("x_mm_per_pixel"), None, minimum=0.0),
        y_mm_per_frame=_resolve_optional_float(payload.get("y_mm_per_frame"), None, minimum=0.0),
        belt_speed_mm_s=_resolve_optional_float(payload.get("belt_speed_mm_s"), None, minimum=0.0),
        x_origin_mm=_resolve_float(payload.get("x_origin_mm"), 0.0),
        y_origin_mm=_resolve_float(payload.get("y_origin_mm"), 0.0),
        encoder_counts_per_mm=_resolve_optional_float(payload.get("encoder_counts_per_mm"), None, minimum=0.0),
        encoder_origin_count=_resolve_optional_float(payload.get("encoder_origin_count"), None, minimum=0.0),
        nozzle_origin_x_mm=_resolve_optional_float(payload.get("nozzle_origin_x_mm"), None, minimum=0.0),
        nozzle_pitch_mm=_resolve_optional_float(payload.get("nozzle_pitch_mm"), None, minimum=0.0),
    )


def _normalize_result(source: str, result: Any) -> RuntimeOutputResult:
    live_status = getattr(result, "live_status", None)
    return RuntimeOutputResult(
        source=str(source),
        return_code=int(result.return_code),
        output_dir=Path(result.output_dir),
        events_path=Path(result.events_path),
        summary_path=Path(result.summary_path),
        dashboard_path=Path(result.dashboard_path) if result.dashboard_path is not None else None,
        ack_log_path=Path(result.ack_log_path),
        runtime_summary=dict(result.runtime_summary),
        summary_payload=dict(result.summary_payload),
        operational_gate=dict(result.operational_gate),
        stream_messages_sent=int(result.stream_messages_sent),
        stream_attempts=int(result.stream_attempts),
        stream_failed=bool(result.stream_failed),
        stream_last_error=result.stream_last_error,
        live_status=dict(live_status) if isinstance(live_status, dict) else None,
    )


def _resolve_int(value: object, default: int, *, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(int(minimum), parsed)


def _resolve_optional_int(value: object, default: int | None, *, minimum: int) -> int | None:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    parsed = max(int(minimum), parsed)
    return parsed if parsed > 0 else None


def _resolve_float(value: object, default: float, *, minimum: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    if minimum is not None:
        parsed = max(float(minimum), parsed)
    return parsed


def _resolve_optional_float(value: object, default: float | None, *, minimum: float) -> float | None:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(float(minimum), parsed) if parsed > 0.0 else None


def _resolve_unit_float(value: object, default: float) -> float:
    return min(1.0, max(0.0, _resolve_float(value, default)))


def _resolve_connectivity(value: object, default: int) -> int:
    parsed = _resolve_int(value, default, minimum=4)
    return parsed if parsed in (4, 8) else int(default)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
