from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .base import CameraInfo, CameraProvider, CameraSettings, FrameSource
from .cube_assembler import AssembledCube, LineCubeAssembler
from .lumo_provider import LumoCameraProvider, list_native_lumo_devices
from .stream_worker import StreamStats, StreamWorker
from .writer import write_capture_session
from .local_network import LocalNetworkAdapter, merge_lumo_network_auto_settings
from .paths import make_session_dir
from .bands import resolve_rgb_bands


@dataclass(slots=True)
class SpecimLumoModuleConfig:
    """Selector/runtime configuration for the native Specim Lumo camera path."""

    provider_mode: str = "native"
    serial_number: str | None = None
    ip_address: str | None = None
    interface_name: str | None = None
    mac_address: str | None = None
    device_index: int = 0
    timeout_ms: int = 5000
    skip_scan: bool = False
    open_timeout_s: float = 60.0

    def build_provider(self) -> LumoCameraProvider:
        return LumoCameraProvider(
            provider_mode=self.provider_mode,
            serial_number=self.serial_number,
            ip_address=self.ip_address,
            interface_name=self.interface_name,
            mac_address=self.mac_address,
            device_index=int(self.device_index),
            timeout_ms=int(self.timeout_ms),
            skip_scan=bool(self.skip_scan),
            open_timeout_s=float(self.open_timeout_s),
        )


@dataclass(slots=True)
class CameraCaptureResult:
    """In-memory result of a Lumo camera capture/smoke run."""

    assembled_cube: AssembledCube
    camera_info: CameraInfo
    settings: CameraSettings
    requested_settings: CameraSettings
    stream_stats: StreamStats
    status: dict[str, object]
    duration_s: float

    @property
    def frame_count(self) -> int:
        return int(self.assembled_cube.frame_count)

    def to_summary(self) -> dict[str, object]:
        return {
            "frame_count": self.frame_count,
            "band_count": int(self.assembled_cube.band_count),
            "spatial_width": int(self.assembled_cube.spatial_width),
            "camera_info": self.camera_info.to_dict(),
            "settings": self.settings.to_dict(),
            "requested_settings": self.requested_settings.to_dict(),
            "stream_stats": self.stream_stats.to_dict(),
            "status": dict(self.status),
            "duration_s": float(self.duration_s),
        }


@dataclass(slots=True)
class CameraSessionResult:
    """Persisted capture session created by the camera module."""

    session_dir: Path
    manifest_path: Path
    capture: CameraCaptureResult

    def to_summary(self) -> dict[str, object]:
        payload = self.capture.to_summary()
        payload["session_dir"] = str(self.session_dir)
        payload["manifest_path"] = str(self.manifest_path)
        return payload


@dataclass(slots=True)
class SpecimLumoCameraModule:
    """High-level Specim FX17e/Lumo acquisition facade.

    The class keeps Lumo-specific concerns behind the existing `CameraProvider`
    abstraction. Tests can inject a provider; production code should use
    `SpecimLumoModuleConfig` so the native Lumo SDK binding stays isolated.
    """

    config: SpecimLumoModuleConfig = field(default_factory=SpecimLumoModuleConfig)
    settings: CameraSettings = field(default_factory=CameraSettings)
    provider: CameraProvider | None = None
    _source: FrameSource | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_config_payload(
        cls,
        camera_config: Mapping[str, Any],
        *,
        provider: CameraProvider | None = None,
    ) -> "SpecimLumoCameraModule":
        return cls(
            config=build_lumo_module_config(camera_config),
            settings=build_lumo_camera_settings(camera_config),
            provider=provider,
        )

    @staticmethod
    def list_devices() -> list[dict[str, Any]]:
        return list_native_lumo_devices()

    @property
    def is_connected(self) -> bool:
        return self._source is not None

    @property
    def source(self) -> FrameSource | None:
        return self._source

    def connect(self, settings: CameraSettings | None = None) -> dict[str, object]:
        if self._source is not None:
            return self.status()
        self.settings = settings or self.settings
        provider = self.provider or self.config.build_provider()
        self._source = provider.open(self.settings)
        return self.status()

    def disconnect(self) -> None:
        source = self._source
        self._source = None
        if source is not None:
            source.close()

    def status(self) -> dict[str, object]:
        source = self._source
        if source is None:
            return {"connected": False, "streaming": False}
        getter = getattr(source, "get_status", None)
        if callable(getter):
            payload = getter()
            if isinstance(payload, dict):
                return dict(payload)
        return {
            "connected": True,
            "streaming": True,
            "camera_info": source.camera_info.to_dict(),
            "settings": source.settings.to_dict(),
        }

    def smoke(
        self,
        *,
        frames: int = 100,
        queue_size: int = 64,
        frame_timeout_s: float = 0.5,
        max_idle_seconds: float | None = 30.0,
    ) -> CameraCaptureResult:
        return self.capture_lines(
            frames=frames,
            queue_size=queue_size,
            frame_timeout_s=frame_timeout_s,
            max_idle_seconds=max_idle_seconds,
            keep_connected=True,
        )

    def capture_lines(
        self,
        *,
        frames: int,
        queue_size: int = 64,
        frame_timeout_s: float = 0.5,
        max_idle_seconds: float | None = 30.0,
        keep_connected: bool = True,
        progress_callback: Callable[[int, FrameSource, StreamStats], None] | None = None,
    ) -> CameraCaptureResult:
        if int(frames) <= 0:
            raise ValueError("frames must be a positive integer.")

        requested_settings = self.settings
        source = self._source
        if source is None:
            self.connect(requested_settings)
            source = self._source
        if source is None:
            raise RuntimeError("Failed to open Lumo camera source.")

        start = time.monotonic()
        worker = StreamWorker(
            source,
            queue_maxsize=max(1, int(queue_size)),
            close_source_on_stop=False,
        )
        assembler = LineCubeAssembler()
        try:
            worker.start(max_frames=int(frames))
            for frame in worker.iter_frames(
                timeout_s=float(frame_timeout_s),
                max_idle_seconds=max_idle_seconds,
            ):
                assembler.append(frame)
                if progress_callback is not None:
                    progress_callback(assembler.frame_count, source, worker.stats)
            worker.wait()
            if worker.stats.error is not None:
                raise RuntimeError(worker.stats.error)
            if assembler.frame_count == 0:
                raise RuntimeError("No frames were captured from Lumo camera.")
            assembled = assembler.build()
            return CameraCaptureResult(
                assembled_cube=assembled,
                camera_info=source.camera_info,
                settings=source.settings,
                requested_settings=requested_settings,
                stream_stats=worker.stats,
                status=self.status(),
                duration_s=time.monotonic() - start,
            )
        finally:
            worker.stop(close_source=False)
            if not keep_connected:
                self.disconnect()

    def capture_session(
        self,
        *,
        output_root: Path,
        frames: int,
        label: str = "lumo",
        queue_size: int = 64,
        frame_timeout_s: float = 0.5,
        max_idle_seconds: float | None = 30.0,
        capture_metadata: dict[str, object] | None = None,
        keep_connected: bool = True,
    ) -> CameraSessionResult:
        capture = self.capture_lines(
            frames=frames,
            queue_size=queue_size,
            frame_timeout_s=frame_timeout_s,
            max_idle_seconds=max_idle_seconds,
            keep_connected=keep_connected,
        )
        session_dir = make_session_dir(Path(output_root), label)
        manifest_path = write_capture_session(
            session_dir=session_dir,
            assembled_cube=capture.assembled_cube,
            camera_info=capture.camera_info,
            settings=capture.settings,
            requested_settings=capture.requested_settings,
            stream_stats=capture.stream_stats.to_dict(),
            capture_metadata=capture_metadata or {},
        )
        return CameraSessionResult(
            session_dir=session_dir,
            manifest_path=manifest_path,
            capture=capture,
        )


def build_lumo_module_config(
    camera_config: Mapping[str, Any],
    *,
    local_network_adapters: list[LocalNetworkAdapter] | None = None,
) -> SpecimLumoModuleConfig:
    camera_config = merge_lumo_network_auto_settings(
        camera_config,
        adapters=local_network_adapters,
    )
    lumo_section = camera_config.get("lumo", {})
    if not isinstance(lumo_section, Mapping):
        lumo_section = {}
    return SpecimLumoModuleConfig(
        provider_mode=str(lumo_section.get("provider_mode", "native")).lower(),
        serial_number=_optional_text(lumo_section.get("serial_number")),
        ip_address=_optional_text(lumo_section.get("ip_address")),
        interface_name=_optional_text(lumo_section.get("interface_name")),
        mac_address=_optional_text(lumo_section.get("mac_address") or lumo_section.get("target_mac_address")),
        device_index=int(lumo_section.get("device_index", 0)),
        timeout_ms=int(lumo_section.get("grab_timeout_ms", 5000)),
        skip_scan=bool(lumo_section.get("skip_scan", False)),
        open_timeout_s=float(lumo_section.get("open_timeout_s", lumo_section.get("initialize_timeout_s", 60.0)) or 60.0),
    )


def build_lumo_camera_settings(camera_config: Mapping[str, Any]) -> CameraSettings:
    camera_section = camera_config.get("camera", {})
    if not isinstance(camera_section, Mapping):
        camera_section = {}
    breeze_compat_section = camera_config.get("breeze_compat", {})
    if not isinstance(breeze_compat_section, Mapping):
        breeze_compat_section = {}

    band_count = int(camera_section.get("band_count", 224))
    spatial_width = int(camera_section.get("spatial_width", 640))
    raw_integration = camera_section.get(
        "integration_time_us",
        camera_section.get("exposure_time_us", 4000),
    )
    integration_time_us = int(float(raw_integration))
    line_rate_hz = float(camera_section.get("line_rate_hz", 100.0))
    raw_rgb = camera_section.get("rgb_bands")
    rgb_bands = resolve_rgb_bands(
        band_count,
        raw_rgb if isinstance(raw_rgb, (list, tuple)) else None,
    )
    return CameraSettings(
        band_count=band_count,
        spatial_width=spatial_width,
        integration_time_us=integration_time_us,
        line_rate_hz=line_rate_hz,
        rgb_bands=rgb_bands,
        mirror_line=bool(breeze_compat_section.get("mirror_line", False)),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
