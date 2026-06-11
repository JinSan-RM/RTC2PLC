"""Lumo native camera provider for FX17e acquisition."""

from __future__ import annotations

import importlib
import json
import re
import time
import threading
from dataclasses import replace
from typing import Any

import numpy as np

from camera.base import CameraInfo, CameraProvider, CameraSettings, FrameSource, LineFrame
from common.logging import get_logger
from common.local_network import (
    find_lumo_neighbor_by_mac,
    list_local_network_adapters,
    list_lumo_remote_neighbors,
    normalize_mac_address,
)

LOGGER = get_logger(__name__)
_NATIVE_OPEN_TIMEOUT_SECONDS = 20.0

_NATIVE_MODULE_CANDIDATES = (
    "specim_lumo_native",
    "spectral_runtime_lumo_native",
    "lumo_native",
)
_SHAPE_COMPAT_LOGGED: set[tuple[tuple[int, ...], int, int, str]] = set()
_OPTIONAL_STATUS_ERROR_PREFIXES = (
    "Acquisition.DroppedFrames:",
    "Acquisition.RingBuffer.Lag:",
    "Acquisition.RingBuffer.Size:",
)
_MISSING_FEATURE_MARKERS = (
    "feature cannot be found",
    "not found",
    "not implemented",
)


# 카메라 C++ 기반 연결 로직
# 문제가 생기면 즉시 RuntimeError로 감싸서 반환한다.
class NativeLumoProviderError(RuntimeError):
    pass


def _to_int(value: Any, fallback: int | None = None) -> int | None:
    if value is None:
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_float(value: Any, fallback: float | None = None) -> float | None:
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _format_native_device_payload(item: dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return "unknown"
    model = item.get("model") or item.get("model_name") or "unknown"
    serial = item.get("serial") or item.get("serial_number") or "unknown"
    transport = item.get("transport") or item.get("device_class") or "unknown"
    identifier = item.get("id") or item.get("device_id") or item.get("handle", "unknown")
    return f"model={model} serial={serial} transport={transport} id={identifier}"


def _native_load_error(err: Exception, context: str) -> str:
    message = f"native lumo binding failed ({context}): {err}"
    if isinstance(err, ImportError):
        return message + " install native binding module first."
    return message


def _native_open_error_hint(
    error: Exception,
    serial_number: str | None,
    device_index: int,
    ip_address: str | None = None,
    interface_name: str | None = None,
) -> str:
    message = str(error)
    normalized = message.lower()
    selectors = [
        f"serial={serial_number}" if serial_number else "serial=<none>",
        f"ip={ip_address}" if ip_address else "ip=<none>",
        f"interface={interface_name}" if interface_name else "interface=<none>",
        f"device_index={device_index}",
    ]
    selector_text = ", ".join(selectors)

    if "-604" in normalized or "loading the module failed" in normalized:
        return (
            f"Lumo native open failed with a transport-module load issue (commonly code -604). "
            f"Current target: {selector_text}. "
            "This usually means a Pleora transport DLL/CTI path mismatch. "
            "Recommended checks: confirm SDK runtime dependency folders (Specim Lumo SDK bin + Pleora runtime deps), "
            "confirm camera index resolves to the non-mock FX17e entry, and retry after fixing native runtime dependencies."
        )

    return f"{message} (target: {selector_text})"

# 실제 Lumo SDK로 데이터를 받는 네이티브 바인딩 모듈을 import한다.
# 기본 후보는 `specim_lumo_native`이며, 실패 시 다른 후보를 순차 시도한다.
def _import_native_module() -> Any:
    last_error: Exception | None = None
    for module_name in _NATIVE_MODULE_CANDIDATES:
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            last_error = exc
            LOGGER.debug("Failed loading native module %s: %s", module_name, exc)
            continue
    raise NativeLumoProviderError(_native_load_error(last_error or RuntimeError("unknown"), "import"))


def _coerce_native_status(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"raw": raw}
    if isinstance(raw, (bytes, bytearray, memoryview)):
        try:
            return json.loads(bytes(raw).decode("utf-8"))
        except Exception:
            return {"raw": raw}
    if isinstance(raw, (tuple, list)) and raw:
        for item in raw:
            if isinstance(item, dict):
                return item
    return {"raw": str(raw)}


def _is_optional_status_feature_error(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    normalized = text.lower()
    return any(text.startswith(prefix) for prefix in _OPTIONAL_STATUS_ERROR_PREFIXES) and any(
        marker in normalized for marker in _MISSING_FEATURE_MARKERS
    )


def _to_string(value: Any, fallback: str | None) -> str:
    if value is None:
        return fallback or ""
    text = str(value).strip()
    return text or (fallback or "")


def _extract_ipv4_text(value: Any) -> str | None:
    text = str(value or "")
    for match in re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", text):
        parts = match.split(".")
        if all(0 <= int(part) <= 255 for part in parts):
            return match
    return None


def _device_ip_address(device: dict[str, Any]) -> str | None:
    for key in ("ip", "ip_address", "device_ip", "address", "ipv4"):
        value = _extract_ipv4_text(device.get(key))
        if value:
            return value
    for value in device.values():
        candidate = _extract_ipv4_text(value)
        if candidate:
            return candidate
    return None


def _network_device_from_interface(
    interface_name: str | None,
    device_index: int,
    *,
    mac_address: str | None = None,
) -> dict[str, Any] | None:
    if not interface_name and not mac_address:
        return None
    try:
        adapters = list_local_network_adapters(timeout_seconds=5.0)
        local_ips = [
            value
            for adapter in adapters
            for value in adapter.ipv4_addresses
        ]
        if mac_address:
            neighbor = find_lumo_neighbor_by_mac(
                mac_address=mac_address,
                interface_name=interface_name,
                local_ipv4_addresses=local_ips,
                timeout_seconds=5.0,
            )
            neighbors = [neighbor] if neighbor is not None else []
        else:
            neighbors = list_lumo_remote_neighbors(
                interface_name=interface_name,
                local_ipv4_addresses=local_ips,
                timeout_seconds=5.0,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("Lumo network neighbor discovery failed: %s", exc)
        return None
    if not neighbors:
        return None
    neighbor = neighbors[0]
    return {
        "index": int(device_index),
        "id": str(int(device_index)),
        "device_id": str(int(device_index)),
        "model": "network-discovered",
        "serial": "",
        "transport": "windows-neighbor",
        "ip_address": neighbor.ip_address,
        "mac_address": normalize_mac_address(neighbor.link_layer_address),
        "link_layer_address": neighbor.link_layer_address,
        "target_mac_address": normalize_mac_address(mac_address) if mac_address else "",
        "neighbor_state": neighbor.state,
        "interface_name": neighbor.interface_alias or interface_name,
        "network_discovery_source": "windows_neighbor",
    }


def _select_native_device(
    devices: list[dict[str, Any]],
    serial_number: str | None,
    ip_address: str | None,
    interface_name: str | None,
    device_index: int,
) -> dict[str, Any] | None:
    if not devices:
        return None

    def is_low_quality_candidate(device: dict[str, Any]) -> bool:
        values = [
            _to_string(device.get("model"), ""),
            _to_string(device.get("name"), ""),
            _to_string(device.get("transport"), ""),
            _to_string(device.get("device_class"), ""),
            _to_string(device.get("description"), ""),
        ]
        normalized = " ".join(values).lower()
        bad_keywords = ("filereader", "mock", "with pleora", "pleora")
        return any(keyword in normalized for keyword in bad_keywords)

    def matches_filters(device: dict[str, Any]) -> bool:
        if serial_number:
            target = _normalize_identifier(serial_number)
            candidates: set[str] = set()
            for key in ("serial", "serial_number", "device_id", "id", "model", "name"):
                candidates.update(_expand_identifier_candidates(_to_string(device.get(key), "")))
            if target not in candidates:
                return False

        if ip_address:
            target_ip = ip_address.strip().lower()
            detected_ip = _device_ip_address(device)
            if target_ip != str(detected_ip or "").lower():
                return False

        if interface_name:
            target_if = interface_name.strip().lower()
            if_keys = ("interface", "interface_name", "adapter", "nic")
            interface_candidates = {_to_string(device.get(key), "").lower() for key in if_keys}
            interface_candidates = {value for value in interface_candidates if value}
            if interface_candidates and not any(target_if in value for value in interface_candidates):
                return False

        return True

    has_explicit_filter = bool(serial_number or ip_address or interface_name)

    if 0 <= device_index < len(devices):
        candidate = devices[device_index]
        if matches_filters(candidate) and (has_explicit_filter or not is_low_quality_candidate(candidate)):
            return candidate

    if has_explicit_filter:
        for device in devices:
            if matches_filters(device) and not is_low_quality_candidate(device):
                return device
        for device in devices:
            if matches_filters(device):
                return device
        return None

    if not serial_number and not ip_address and not interface_name:
        for device in devices:
            if not is_low_quality_candidate(device):
                return device
        return devices[0]
    return None


def _coerce_native_frame(raw: Any) -> tuple[np.ndarray, dict[str, Any]]:
    if isinstance(raw, dict):
        payload = raw.get("data")
        if payload is None:
            payload = raw.get("payload")
        if payload is None:
            payload = raw.get("buffer")
        metadata = dict(raw)
        metadata.pop("data", None)
        metadata.pop("payload", None)
        metadata.pop("buffer", None)
        if payload is None:
            raise NativeLumoProviderError("native frame result has no payload")
        data = np.asarray(payload)
        return data, metadata

    if isinstance(raw, (tuple, list)):
        payload = raw[0] if raw else None
        metadata: dict[str, Any] = {}
        if len(raw) > 1 and isinstance(raw[1], dict):
            metadata = dict(raw[1])
        if payload is None:
            raise NativeLumoProviderError("native frame result tuple is empty")
        return np.asarray(payload), metadata

    if isinstance(raw, (bytes, bytearray, memoryview)):
        return np.frombuffer(raw, dtype=np.uint16), {}

    if isinstance(raw, np.ndarray):
        return raw, {}

    raise NativeLumoProviderError(f"unsupported native frame payload type: {type(raw)!r}")


def _log_shape_compat_once(
    raw_shape: tuple[int, ...],
    expected_band_count: int,
    expected_spatial_width: int,
    action: str,
) -> None:
    key = (raw_shape, expected_band_count, expected_spatial_width, action)
    if key in _SHAPE_COMPAT_LOGGED:
        return
    _SHAPE_COMPAT_LOGGED.add(key)
    LOGGER.warning(
        "Lumo grab shape compatibility applied: shape=%s expected=(bands=%s, width=%s), %s",
        raw_shape,
        expected_band_count,
        expected_spatial_width,
        action,
    )


def _normalize_native_frame_data(
    raw_array: np.ndarray,
    metadata: dict[str, Any],
    expected_band_count: int,
    expected_spatial_width: int,
) -> np.ndarray:
    if raw_array.ndim == 0:
        raise NativeLumoProviderError("native frame payload is scalar")

    if raw_array.ndim == 1:
        length = raw_array.size
        if length == 0:
            raise NativeLumoProviderError("native frame payload is empty")

        candidate_shapes: list[tuple[int, int]] = []

        if expected_band_count > 0 and expected_spatial_width > 0:
            expected_total = expected_band_count * expected_spatial_width
            if length == expected_total:
                candidate_shapes.append((expected_band_count, expected_spatial_width))

        metadata_band_count = (
            _to_int(metadata.get("band_count"), None)
            or _to_int(metadata.get("bands"), None)
            or _to_int(metadata.get("height"), None)
        )
        metadata_width = (
            _to_int(metadata.get("spatial_width"), None)
            or _to_int(metadata.get("width"), None)
            or _to_int(metadata.get("line_width"), None)
        )
        if metadata_band_count is not None and metadata_width is not None:
            if metadata_band_count > 0 and metadata_width > 0 and metadata_band_count * metadata_width == length:
                candidate_shapes.append((metadata_band_count, metadata_width))

        if not candidate_shapes:
            if metadata_band_count is not None and metadata_band_count > 0 and length % metadata_band_count == 0:
                candidate_shapes.append((metadata_band_count, length // metadata_band_count))
            if metadata_width is not None and metadata_width > 0 and length % metadata_width == 0:
                candidate_shapes.append((length // metadata_width, metadata_width))
            if expected_band_count > 0 and length % expected_band_count == 0:
                candidate_shapes.append((expected_band_count, length // expected_band_count))
            if expected_spatial_width > 0 and length % expected_spatial_width == 0:
                candidate_shapes.append((length // expected_spatial_width, expected_spatial_width))

        if not candidate_shapes:
            raise NativeLumoProviderError(
                "native frame payload length does not match any inferred 2D shape "
                f"length={length} expected_band_count={expected_band_count} expected_spatial_width={expected_spatial_width}"
            )

        last_error: Exception | None = None
        for rows, cols in dict.fromkeys(candidate_shapes):
            try:
                return raw_array.reshape((rows, cols))
            except Exception as exc:
                last_error = exc
        raise NativeLumoProviderError(
            f"cannot reshape native frame to 2D. candidates={candidate_shapes}. reason={last_error}"
        )

    if raw_array.ndim == 2:
        return raw_array

    raise NativeLumoProviderError(
        f"native frame payload has unsupported dimension={raw_array.ndim}"
    )


def _is_recoverable_native_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(token in message for token in ("timeout", "timed out", "grab timeout", "no frame"))


def _extract_handle(raw: Any) -> Any:
    if isinstance(raw, dict):
        for key in ("handle", "device_handle", "native_handle", "context"):
            if key in raw and raw[key] is not None:
                return raw[key]
        if "error_code" in raw and raw.get("error_code", 0):
            raise NativeLumoProviderError(f"native open error: {raw.get('error_code')}")
        if "handle" in raw:
            return raw["handle"]
        raise NativeLumoProviderError("native open returned an empty response")
    if isinstance(raw, (tuple, list)) and raw:
        if _to_int(raw[0], None) is not None and raw[0] < 0:
            raise NativeLumoProviderError(f"native open failed with code: {raw[0]}")
        if _to_int(raw[0], None) is not None and raw[0] >= 0 and len(raw) > 1:
            return raw[0]
        if _to_int(raw[0], None) is not None:
            return raw[0]
        if raw[0] is not None:
            return raw[0]
    return raw


def _call_native_function(func: Any, *args: Any, context: str) -> Any:
    if not callable(func):
        raise NativeLumoProviderError(f"native binding missing required function: {context}")
    try:
        return func(*args)
    except Exception as exc:
        raise NativeLumoProviderError(_native_load_error(exc, context)) from exc


def list_native_lumo_devices() -> list[dict[str, Any]]:
    """Return discoverable native devices when native module is present."""
    module = _import_native_module()
    scan = _call_native_function(getattr(module, "lumo_scan_devices", None), context="scan_devices")
    if scan is None:
        return []

    if isinstance(scan, bytes):
        scan = bytes(scan).decode("utf-8")
    if isinstance(scan, str):
        try:
            parsed = json.loads(scan)
            if isinstance(parsed, list):
                return [dict(item) for item in parsed if isinstance(item, dict)]
        except json.JSONDecodeError:
            return []
    if isinstance(scan, list):
        return [dict(item) for item in scan if isinstance(item, dict)]
    return []


def format_native_lumo_device_report() -> str:
    devices = list_native_lumo_devices()
    if not devices:
        return "No native Lumo device found."
    lines = [f"native Lumo device count: {len(devices)}"]
    for index, device in enumerate(devices):
        line = _format_native_device_payload(device)
        lines.append(f"[{index}] {line}")
    return "\n".join(lines)


"""
실제로 Lumo SDK를 통해 데이터가 들어오는 객체.
카메라 연결 전체 흐름(중요):

1. native 모듈 import
2. 카메라 설정값 구성 (band, width, exposure 등)
3. 장치 선택
   - skip_scan=True: device_index 기반 direct open
   - skip_scan=False: scan -> filter -> select
4. lumo_open 호출 (DLL 내부 SI_Open)
5. handle 획득 (카메라 세션 핸들)
6. lumo_start 호출 (Acquisition 시작)
7. 이후 frames()에서 line 데이터 수신

즉, 이 클래스 생성 시점에 "카메라 연결 + 스트리밍 시작"까지 완료된다.
"""
class NativeLumoFrameSource(FrameSource):
    _START_TIMEOUT_SECONDS = 20.0  # 스트리밍 시작 후 첫 프레임 대기 시간 제한

    def __init__(
        self,
        settings: CameraSettings,
        serial_number: str | None = None,
        ip_address: str | None = None,
        interface_name: str | None = None,
        mac_address: str | None = None,
        device_index: int = 0,
        timeout_ms: int = 5000,
        skip_scan: bool = False,
    ) -> None:
        LOGGER.info("Native open step1: import native module")
        self._module = _import_native_module()  # native 바인딩 모듈 로드
        self._timeout_ms = timeout_ms         
        self._closed = False                  
        self._handle = None
        self._frame_counter = 0
        self._dropped_frames = 0
        self._timeout_frames = 0
        self._stream_errors = 0
        self._last_status_error: str | None = None
        self._needs_runtime_reset = False
        self._status_cache: dict[str, Any] = {}
        self._selected_device: dict[str, Any] = {}
        self._open_native_settings: dict[str, Any] = {}
        self._first_frame_monotonic: float | None = None
        self._last_frame_monotonic: float | None = None

        native_settings = {
            "band_count": settings.band_count,
            "spatial_width": settings.spatial_width,
            "integration_time_us": settings.integration_time_us,
            "exposure_time_us": settings.exposure_time_us,
            "line_rate_hz": settings.line_rate_hz,
            "rgb_bands": settings.rgb_bands,
        }
        target_mac_address = normalize_mac_address(mac_address) if mac_address else None
        if ip_address:
            native_settings["ip_address"] = ip_address
        if interface_name:
            native_settings["interface_name"] = interface_name
        if target_mac_address:
            native_settings["mac_address"] = target_mac_address

        selected: dict[str, Any] | None = None
        network_device = (
            _network_device_from_interface(
                interface_name,
                device_index,
                mac_address=target_mac_address,
            )
            if not ip_address
            else None
        )
        if target_mac_address and not ip_address and network_device is None:
            raise NativeLumoProviderError(
                f"No valid network neighbor matched configured Lumo MAC {target_mac_address!r} "
                f"on interface {interface_name!r}."
            )
        if skip_scan:
            LOGGER.info("Native open step2: skip scan enabled, using direct selector")
            selected = {
                "index": device_index,
                "serial": serial_number or "",
                "ip_address": ip_address or "",
                "interface_name": interface_name or "",
                "device_id": str(device_index),
                "id": str(device_index),
                "model": "unknown",
                "transport": "native",
            }
            if network_device:
                LOGGER.info(
                    "Native open step2b: using network neighbor IP %s for direct selector",
                    network_device.get("ip_address"),
                )
                selected.update(network_device)
            native_settings["device_index"] = device_index
        else:
            LOGGER.info("Native open step2: enumerate native devices")
            devices = list_native_lumo_devices()
            if not devices:
                if network_device:
                    LOGGER.info(
                        "Native open step2b: SDK scan returned no devices; using network neighbor IP %s",
                        network_device.get("ip_address"),
                    )
                    devices = [network_device]
                else:
                    raise NativeLumoProviderError(
                        "No native Lumo device was enumerated and no valid network neighbor camera was found. "
                        "Confirm SpecSensor runtime, FX17e transport, and Ethernet interface are available before opening."
                    )

            LOGGER.info(
                "Native open step3: select device (serial=%s, ip=%s, interface=%s, index=%s, count=%s)",
                serial_number or "<none>",
                ip_address or "<none>",
                interface_name or "<none>",
                device_index,
                len(devices),
            )
            selected = _select_native_device(
                devices=devices,
                serial_number=serial_number,
                ip_address=ip_address,
                interface_name=interface_name,
                device_index=device_index,
            )
            if selected is None and network_device:
                selected = network_device
            if selected is not None and network_device and target_mac_address:
                selected.update(network_device)
            if selected is None:
                available = ", ".join(_format_native_device_payload(item) for item in devices)
                raise NativeLumoProviderError(
                    f"Native device selection failed for serial='{serial_number}', ip='{ip_address}', "
                    f"interface='{interface_name}', index={device_index}. "
                    f"Enumerated devices: {available}"
                )

        detected_ip = _device_ip_address(selected)
        if detected_ip and not ip_address:
            LOGGER.info("Native open step3b: using discovered device IP %s", detected_ip)
            native_settings["ip_address"] = detected_ip
        if detected_ip:
            selected.setdefault("ip_address", detected_ip)

        device_selector: Any = device_index if skip_scan else None
        if device_selector is None:
            device_selector = (
                selected.get("id")
                or selected.get("serial")
                or selected.get("serial_number")
                or selected.get("device_id")
                or selected
            )
        native_settings["device"] = selected.get("id") or selected
        LOGGER.info("Native open step4: open selected device")
        open_result = _call_native_function(
            getattr(self._module, "lumo_open", None),
            device_selector,
            json.dumps(native_settings),
            context="lumo_open",
        )
        self._handle = _extract_handle(open_result)
        if self._handle is None:
            raise NativeLumoProviderError("native open returned no handle")

        self._selected_device = dict(selected)
        self._open_native_settings = dict(native_settings)
        self._settings = self._resolve_runtime_settings(self._module, self._handle, settings)
        self._camera_info = self._build_camera_info(selected, self._module, self._handle)

        try:
            LOGGER.info("Native open step5: start stream")
            _call_native_function(
                getattr(self._module, "lumo_start", None),
                self._handle,
                context="lumo_start",
            )
            LOGGER.info("Native open step6: native open/start completed")
        except NativeLumoProviderError:
            self._needs_runtime_reset = True
            self.close()
            raise

    @property
    def camera_info(self) -> CameraInfo:
        return self._camera_info

    @property
    def settings(self) -> CameraSettings:
        return self._settings

    def _require_handle(self) -> Any:
        if self._handle is None or self._closed:
            raise NativeLumoProviderError("native camera source is not open")
        return self._handle

    def command(self, command: str) -> int:
        result = _call_native_function(
            getattr(self._module, "lumo_command", None),
            self._require_handle(),
            command,
            context=f"lumo_command:{command}",
        )
        return int(result or 0)

    def apply_acquisition_settings(self, settings: CameraSettings) -> dict[str, Any]:
        payload = {
            "integration_time_us": int(settings.integration_time_us),
            "exposure_time_us": int(settings.exposure_time_us),
            "line_rate_hz": float(settings.line_rate_hz),
        }
        result = _call_native_function(
            getattr(self._module, "lumo_apply_acquisition_settings", None),
            self._require_handle(),
            json.dumps(payload),
            context="lumo_apply_acquisition_settings",
        )
        status = _coerce_native_status(result)
        exposure = _to_int(status.get("exposure_time_us"), settings.integration_time_us)
        line_rate = _coerce_float(status.get("acquisition_line_rate"), settings.line_rate_hz)
        self._settings = replace(
            self._settings,
            integration_time_us=exposure or int(settings.integration_time_us),
            line_rate_hz=line_rate or float(settings.line_rate_hz),
            rgb_bands=settings.rgb_bands,
        )
        return status

    def open_shutter(self) -> int:
        result = _call_native_function(
            getattr(self._module, "lumo_shutter_open", None),
            self._require_handle(),
            context="lumo_shutter_open",
        )
        return int(result or 0)

    def close_shutter(self) -> int:
        result = _call_native_function(
            getattr(self._module, "lumo_shutter_close", None),
            self._require_handle(),
            context="lumo_shutter_close",
        )
        return int(result or 0)

    def is_shutter_open(self) -> bool | None:
        result = _call_native_function(
            getattr(self._module, "lumo_is_shutter_open", None),
            self._require_handle(),
            context="lumo_is_shutter_open",
        )
        return None if result is None else bool(result)

    def is_feature_implemented(self, feature: str) -> bool | None:
        result = _call_native_function(
            getattr(self._module, "lumo_is_feature_implemented", None),
            self._require_handle(),
            feature,
            context=f"lumo_is_feature_implemented:{feature}",
        )
        return None if result is None else bool(result)

    def frames(self, max_frames: int | None = None):
        requested_frames = max_frames if max_frames is not None else self._settings.max_frames
        if requested_frames is not None and requested_frames <= 0:
            return

        start_mono = time.monotonic()
        no_frame_deadline = start_mono + self._START_TIMEOUT_SECONDS
        frame_index = 0
        while not self._closed:
            if requested_frames is not None and frame_index >= requested_frames:
                return

            try:
                raw_frame = _call_native_function(
                    getattr(self._module, "lumo_get_frame", None),
                    self._handle,
                    self._timeout_ms,
                    context="lumo_get_frame",
                )
                if raw_frame is None:
                    raise NativeLumoProviderError("native frame call returned null")

                parsed = _coerce_native_frame(raw_frame)
                frame_data, metadata = parsed
                self._apply_native_metadata(metrics=metadata)

                frame_data = _normalize_native_frame_data(
                    np.asarray(frame_data),
                    metadata=metadata,
                    expected_band_count=self._settings.band_count,
                    expected_spatial_width=self._settings.spatial_width,
                )
                self._frame_counter += 1
                now_monotonic = time.monotonic()
                if self._first_frame_monotonic is None:
                    self._first_frame_monotonic = now_monotonic
                self._last_frame_monotonic = now_monotonic
                line = normalize_grab_array(
                    frame_data,
                    expected_band_count=self._settings.band_count,
                    expected_spatial_width=self._settings.spatial_width,
                    allow_actual_shape=True,
                )
                self._sync_settings_to_line_shape(line.shape)
                line_timestamp = time.monotonic() - start_mono

                yield LineFrame(
                    index=frame_index,
                    timestamp_monotonic_s=line_timestamp,
                    data=line,
                )
                frame_index += 1
                no_frame_deadline = time.monotonic() + self._START_TIMEOUT_SECONDS
            except NativeLumoProviderError as exc:
                self._stream_errors += 1
                self._last_status_error = str(exc)
                if _is_recoverable_native_error(exc):
                    self._timeout_frames += 1
                    if time.monotonic() > no_frame_deadline:
                        self._needs_runtime_reset = True
                        raise NativeLumoProviderError(
                            "native camera stream stalled due to repeated timeouts. "
                            "Check transport driver, power/network, and camera trigger mode."
                        )
                    continue
                self._needs_runtime_reset = True
                raise

    def _sync_settings_to_line_shape(self, line_shape: tuple[int, ...]) -> None:
        if len(line_shape) != 2:
            return
        band_count, spatial_width = int(line_shape[0]), int(line_shape[1])
        if band_count == int(self._settings.band_count) and spatial_width == int(self._settings.spatial_width):
            return
        LOGGER.warning(
            "Lumo runtime frame shape resolved from grab: configured=(bands=%s, width=%s) "
            "actual=(bands=%s, width=%s). Using actual frame shape for this source.",
            self._settings.band_count,
            self._settings.spatial_width,
            band_count,
            spatial_width,
        )
        max_band_index = max(0, band_count - 1)
        rgb_bands = tuple(min(max(0, int(band)), max_band_index) for band in self._settings.rgb_bands)
        self._settings = replace(
            self._settings,
            band_count=band_count,
            spatial_width=spatial_width,
            rgb_bands=rgb_bands,
        )
        self._status_cache["bands"] = band_count
        self._status_cache["height"] = band_count
        self._status_cache["width"] = spatial_width

    def _apply_native_metadata(self, metrics: dict[str, Any] | None = None) -> None:
        if not metrics:
            return
        self._status_cache.update(metrics)

        frame_counter = _to_int(metrics.get("frame_counter"), None)
        if frame_counter is not None:
            self._frame_counter = max(self._frame_counter, frame_counter)

        dropped_frames = _to_int(metrics.get("dropped_frames"), None)
        if dropped_frames is None:
            dropped_frames = _to_int(metrics.get("dropped"), None)
        if dropped_frames is not None:
            self._dropped_frames = max(self._dropped_frames, dropped_frames)

        timeout_frames = _to_int(metrics.get("timeout_frames"), None)
        if timeout_frames is not None:
            self._timeout_frames = max(self._timeout_frames, timeout_frames)

        error_code = _to_int(metrics.get("error_code"), None)
        if error_code is not None and error_code != 0:
            self._last_status_error = str(metrics.get("error", error_code))

    def get_status(self) -> dict[str, Any]:
        if self._handle is None:
            return {
                "connected": False,
                "streaming": False,
                "frame_counter": self._frame_counter,
                "dropped_frames": 0,
                "error_code": 0,
                "error": None,
                "timeout_frames": self._timeout_frames,
                "stream_errors": self._stream_errors,
                "provider_mode": "native",
                "last_error": self._last_status_error,
            }

        payload = _coerce_native_status(
            _call_native_function(
                getattr(self._module, "lumo_get_status", None),
                self._handle,
                context="lumo_get_status",
            )
        )
        if self._status_cache:
            merged = dict(self._status_cache)
            merged.update(payload)
            payload = merged
        native_last_error = payload.get("last_error")
        if _is_optional_status_feature_error(native_last_error):
            existing_warnings = payload.get("status_warnings")
            if isinstance(existing_warnings, list):
                warnings = [str(item) for item in existing_warnings if str(item)]
            elif existing_warnings:
                warnings = [str(existing_warnings)]
            else:
                warnings = []
            warning_text = str(native_last_error)
            if warning_text not in warnings:
                warnings.append(warning_text)
            payload["status_warnings"] = warnings
            payload["last_error"] = self._last_status_error
        payload.setdefault("frame_counter", self._frame_counter)
        payload.setdefault("dropped_frames", self._dropped_frames + self._timeout_frames)
        native_dropped = _to_int(payload.get("acquisition_dropped_frames"), None)
        if native_dropped is not None:
            payload["dropped_frames"] = max(_to_int(payload.get("dropped_frames"), 0) or 0, native_dropped)
        payload.setdefault("timeout_frames", self._timeout_frames)
        payload.setdefault("stream_errors", self._stream_errors)
        payload.setdefault("provider_mode", "native")
        payload.setdefault("last_error", self._last_status_error)
        payload.setdefault("connected", True)
        payload.setdefault("streaming", self._handle is not None and not self._closed)
        if self._open_native_settings.get("ip_address"):
            payload.setdefault("ip_address", self._open_native_settings.get("ip_address"))
        if self._open_native_settings.get("interface_name"):
            payload.setdefault("interface_name", self._open_native_settings.get("interface_name"))
        if self._selected_device.get("mac_address") or self._selected_device.get("link_layer_address"):
            payload.setdefault(
                "mac_address",
                self._selected_device.get("mac_address") or self._selected_device.get("link_layer_address"),
            )
        if self._selected_device.get("network_discovery_source"):
            payload.setdefault("network_discovery_source", self._selected_device.get("network_discovery_source"))
        if self._selected_device.get("target_mac_address") or self._open_native_settings.get("mac_address"):
            payload.setdefault(
                "target_mac_address",
                self._selected_device.get("target_mac_address") or self._open_native_settings.get("mac_address"),
            )
        payload.setdefault("device_index", self._selected_device.get("index"))
        payload.setdefault("bands", int(self._settings.band_count))
        payload.setdefault("height", int(self._settings.band_count))
        payload.setdefault("width", int(self._settings.spatial_width))
        payload.setdefault("configured_integration_time_us", int(self._settings.integration_time_us))
        payload.setdefault("configured_exposure_time_us", int(self._settings.exposure_time_us))
        payload.setdefault("configured_line_rate_hz", float(self._settings.line_rate_hz))
        payload.setdefault("exposure_time_us", int(self._settings.exposure_time_us))
        payload.setdefault(
            "actual_line_rate_hz",
            _coerce_float(payload.get("acquisition_line_rate"), float(self._settings.line_rate_hz)),
        )
        if self._first_frame_monotonic is not None and self._last_frame_monotonic is not None:
            elapsed = self._last_frame_monotonic - self._first_frame_monotonic
            if elapsed > 0 and self._frame_counter > 1:
                payload["measured_line_rate_hz"] = float((self._frame_counter - 1) / elapsed)
        if "shutter_is_open" not in payload:
            try:
                payload["shutter_is_open"] = self.is_shutter_open()
            except NativeLumoProviderError as exc:
                payload["shutter_status_error"] = str(exc)
        return payload

    def close(self) -> None:
        self._closed = True
        handle = self._handle
        self._handle = None
        should_reset_runtime = bool(self._needs_runtime_reset)

        if handle is not None:
            try:
                _call_native_function(
                    getattr(self._module, "lumo_stop", None),
                    handle,
                    context="lumo_stop",
                )
            except NativeLumoProviderError:
                pass
            try:
                _call_native_function(
                    getattr(self._module, "lumo_close", None),
                    handle,
                    context="lumo_close",
                )
            except NativeLumoProviderError:
                pass

        if should_reset_runtime:
            try:
                _call_native_function(
                    getattr(self._module, "lumo_reset_runtime", None),
                    True,
                    context="lumo_reset_runtime",
                )
            except NativeLumoProviderError:
                pass
            finally:
                self._needs_runtime_reset = False

    def _resolve_runtime_settings(
        self,
        module: Any,
        handle: Any,
        configured: CameraSettings,
    ) -> CameraSettings:
        status = {}
        status_fetcher = getattr(module, "lumo_get_status", None)
        if callable(status_fetcher):
            try:
                status = _coerce_native_status(status_fetcher(handle))
            except Exception:
                status = {}

        band_count = _to_int(status.get("bands"), None)
        if band_count is None:
            band_count = _to_int(status.get("height"), None)
        if band_count is None:
            band_count = configured.band_count
        spatial_width = _to_int(status.get("width"), configured.spatial_width)
        line_rate_hz = _coerce_float(
            status.get("acquisition_line_rate") if isinstance(status, dict) else None,
            configured.line_rate_hz,
        )
        exposure = _to_int(status.get("exposure_time_us"), configured.integration_time_us)
        return replace(
            configured,
            band_count=band_count or configured.band_count,
            spatial_width=spatial_width or configured.spatial_width,
            integration_time_us=exposure or configured.integration_time_us,
            line_rate_hz=line_rate_hz or configured.line_rate_hz,
        )

    def _build_camera_info(self, selected_device: dict[str, Any], module: Any, handle: Any) -> CameraInfo:
        firmware = None
        status_fetcher = getattr(module, "lumo_get_status", None)
        if callable(status_fetcher):
            try:
                status = _coerce_native_status(status_fetcher(handle))
            except Exception:
                status = {}
        if isinstance(status, dict):
            firmware = _to_string(status.get("firmware_version"), None)
        return CameraInfo(
            provider="lumo_native",
            model=_to_string(selected_device.get("model"), "unknown"),
            serial_number=_to_string(
                selected_device.get("serial"),
                _to_string(selected_device.get("serial_number"), "unknown"),
            ),
            transport=_to_string(selected_device.get("transport"), "unknown"),
            firmware_version=firmware,
        )

# Python entry point for Lumo provider selection.
class LumoCameraProvider(CameraProvider):
    """FX17e provider using Lumo native binding only."""

    def __init__(
        self,
        provider_mode: str = "native",
        serial_number: str | None = None,
        ip_address: str | None = None,
        interface_name: str | None = None,
        mac_address: str | None = None,
        device_index: int = 0,
        timeout_ms: int = 5000,
        skip_scan: bool = False,
    ) -> None:
        normalized_mode = str(provider_mode).lower()
        # 현재 구현은 native 모드만 지원한다.
        if normalized_mode != "native":
            raise ValueError("provider_mode must be 'native'.")
        self._serial_number = serial_number
        self._ip_address = ip_address
        self._interface_name = interface_name
        self._mac_address = normalize_mac_address(mac_address) if mac_address else None
        self._device_index = device_index
        self._timeout_ms = timeout_ms
        self._skip_scan = skip_scan
        self._provider_mode = normalized_mode
        self._native_import_error: str | None = None  # native import/open 실패 메시지 저장용

    # 카메라 연결이 오래 걸리는 경우를 대비한 강제 timeout 처리
    def _with_timeout(self, callback, timeout_seconds: float, label: str):
        result = {}
        done = threading.Event()

        def _runner() -> None:
            try:
                result["value"] = callback()
            except Exception as exc:  # noqa: BLE001
                result["error"] = exc
            finally:
                done.set()

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        if not done.wait(timeout_seconds):
            raise TimeoutError(f"{label} timed out after {timeout_seconds:.1f}s")
        if "error" in result:
            raise result["error"]
        return result.get("value")

    # NativeLumoFrameSource 객체를 생성한다.
    # CameraSettings 값에 따라 FrameSource를 구성해 반환한다.
    # 실제 open/start는 NativeLumoFrameSource 생성 과정에서 실행된다.
    
    def _open_native(self, settings: CameraSettings) -> FrameSource:
        self._native_import_error = None
        return NativeLumoFrameSource(
            settings=settings,
            serial_number=self._serial_number,
            ip_address=self._ip_address,
            interface_name=self._interface_name,
            mac_address=self._mac_address,
            device_index=self._device_index,
            timeout_ms=self._timeout_ms,
            skip_scan=self._skip_scan,
        )

    # 기본 CameraSettings를 사용해 네이티브 카메라 open을 수행한다.
    # skip_scan=True면 장치 탐색을 건너뛰고 바로 native open 경로로 진입한다.
    # 실제 현장에서는 장치 탐색보다 고정 selector가 더 안정적일 수 있다.
    def open(self, settings: CameraSettings | None = None) -> FrameSource:
        resolved_settings = settings or CameraSettings()
        if self._skip_scan:
            return self._open_native(resolved_settings)
        try:
            return self._with_timeout(
                lambda: self._open_native(resolved_settings),
                timeout_seconds=_NATIVE_OPEN_TIMEOUT_SECONDS,
                label="Native Lumo open",
            )
        except Exception as exc:
            # selector 정보를 포함한 힌트 메시지로 변환한다.
            self._native_import_error = _native_open_error_hint(
                exc,
                serial_number=self._serial_number,
                device_index=self._device_index,
                ip_address=self._ip_address,
                interface_name=self._interface_name,
            )
            raise RuntimeError(self._native_import_error) from exc


def normalize_grab_array(
    raw_array: np.ndarray,
    expected_band_count: int,
    expected_spatial_width: int,
    *,
    allow_actual_shape: bool = False,
) -> np.ndarray:
    if raw_array.ndim != 2:
        raise ValueError(f"Expected a 2D grab result, got shape={raw_array.shape!r}.")

    line = raw_array
    if raw_array.shape == (expected_band_count, expected_spatial_width):
        pass
    elif raw_array.shape == (expected_spatial_width, expected_band_count):
        line = raw_array.T
    elif raw_array.shape[0] == expected_band_count:
        line = raw_array
    elif raw_array.shape[1] == expected_band_count:
        line = raw_array.T
    elif (
        expected_band_count > 0
        and expected_spatial_width > 0
        and raw_array.shape[0] > expected_band_count
        and raw_array.shape[1] == expected_spatial_width
    ):
        extra_rows = raw_array.shape[0] - expected_band_count
        start = extra_rows // 2
        end = start + expected_band_count
        _log_shape_compat_once(
            raw_array.shape,
            expected_band_count,
            expected_spatial_width,
            f"cropped spectral rows [{start}:{end}]",
        )
        line = raw_array[start:end, :]
    elif (
        expected_band_count > 0
        and expected_spatial_width > 0
        and raw_array.shape[0] == expected_spatial_width
        and raw_array.shape[1] > expected_band_count
    ):
        extra_cols = raw_array.shape[1] - expected_band_count
        start = extra_cols // 2
        end = start + expected_band_count
        _log_shape_compat_once(
            raw_array.shape,
            expected_band_count,
            expected_spatial_width,
            f"cropped spectral columns [{start}:{end}] and transposed",
        )
        line = raw_array[:, start:end].T
    elif allow_actual_shape and raw_array.shape[0] > 0 and raw_array.shape[1] > 0:
        _log_shape_compat_once(
            raw_array.shape,
            expected_band_count,
            expected_spatial_width,
            "using actual frame shape from native grab",
        )
        line = raw_array
    else:
        hint = ""
        if raw_array.shape[1] == expected_spatial_width and raw_array.shape[0] < expected_band_count:
            hint = (
                " Got fewer spectral rows than expected; check the Lumo device selector/profile "
                "and frame payload size. FX17e raw capture should be 224 x 640."
            )
        raise ValueError(
            "Grab result shape does not match configured bands. "
            f"shape={raw_array.shape!r}, expected_band_count={expected_band_count}, "
            f"expected_spatial_width={expected_spatial_width}.{hint}"
        )

    if line.dtype == np.uint16:
        return np.ascontiguousarray(line)

    if np.issubdtype(line.dtype, np.integer):
        return np.ascontiguousarray(line.astype(np.uint16, copy=False))

    if np.issubdtype(line.dtype, np.floating):
        clipped = np.clip(line, 0.0, 65535.0)
        return np.ascontiguousarray(np.rint(clipped).astype(np.uint16))

    raise ValueError(f"Unsupported grab dtype: {line.dtype}")


def _normalize_identifier(raw: str) -> str:
    """Normalize serial-like identifiers for tolerant matching."""
    return re.sub(r"[\W_]", "", (raw or "").strip().lower())


def _expand_identifier_candidates(raw: str) -> list[str]:
    if not raw:
        return []

    values = {raw.strip()}
    for part in re.split(r"[\s,:;/|]+", raw):
        part = part.strip()
        if not part:
            continue
        values.add(part)

    expanded: list[str] = []
    for value in values:
        if not value:
            continue
        expanded.append(_normalize_identifier(value))
        expanded.append(_normalize_identifier(value.replace("-", "")))
        expanded.append(_normalize_identifier(value.replace(" ", "")))

    deduped = []
    for value in expanded:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
