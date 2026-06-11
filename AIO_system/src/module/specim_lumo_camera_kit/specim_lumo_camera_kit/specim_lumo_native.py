"""ctypes bridge for Lumo FX17e native integration.

This module keeps the Python-facing contract used by `camera.lumo_provider`
(`lumo_scan_devices`, `lumo_open`, `lumo_get_frame`, ...). It tries to load a
dedicated wrapper first and then falls back to Specim SI_* API symbols when
available in the loaded DLL.
"""

from __future__ import annotations

import ctypes
import glob
import json
import os
import re
import time
import threading
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

try:
    from .lumo_sdk_catalog import feature_names as _catalog_feature_names
except Exception:  # pragma: no cover - keeps the native bridge usable standalone.
    def _catalog_feature_names() -> list[str]:
        return [
            "ExposureTime",
            "AcquisitionLineRate",
            "Camera.Trigger.Mode",
            "Camera.Binning.Spectral",
            "Camera.Binning.Spatial",
            "Camera.Gain.Analog",
            "Camera.Gain.Digital",
            "Camera.MROI.Enable",
            "Camera.MROI.MultibandString",
            "Acquisition.DroppedFrames",
            "Acquisition.RingBuffer.Lag",
            "Acquisition.Error",
            "Camera.Temperature",
            "Camera.WavelengthTable",
        ]

# 예외 클래스, 바인딩은 있는데 호출 실패
class LumoNativeBindingError(RuntimeError):
    """Raised when native binding exists but a call failed."""

# 심볼/라이브러리 자체가 없음(미지원 / 미설치)
class LumoNativeBindingUnavailable(LumoNativeBindingError):
    """Raised when optional native binding is intentionally unavailable."""


_SI_HANDLE = ctypes.c_void_p
_SI_INT64 = ctypes.c_longlong
_SI_SYSTEM_HANDLE = _SI_HANDLE(0)

_DEFAULT_DLL_NAMES = (
    "specim_lumo_native",
    "LumoNative",
    "LumoNative.dll",
    "lumo_native",
    "specim_lumo_native.dll",
    "lumo_native.dll",
    "SpecSensor",
    "SpecSensor.dll",
)
_SDK_ENV_KEYS = (
    "LUMO_NATIVE_DLL",
    "LUMO_NATIVE_LIBRARY",
    "LUMO_NATIVE_PATH",
    "LUMO_SDK_BIN",
    "LUMO_SDK_ROOT",
)
_SPECIM_ROOTS = (
    Path(r"C:\Program Files\Specim\SDKs\Lumo_Sensor_SDK"),
    Path(r"C:\Program Files (x86)\Specim\SDKs\Lumo_Sensor_SDK"),
)
_SPECIM_PUBLIC_PROFILES = Path(r"C:\Users\Public\Documents\Specim")
_SPECIM_BIN_CANDIDATES = ("bin", "bin\\x64", "bin\\x86", "lib")

_LIB_LOCK = threading.RLock()
_SI_LOCK = threading.Lock()
_LOADED_LIBRARY: ctypes.CDLL | None = None
_LOADED_LIBRARY_PATH: str | None = None
_SI_RUNTIME_LOADED = False
_SI_FRAME_CONTEXTS: dict[int, dict[str, Any]] = {}
_SI_OPEN_SETTINGS: dict[int, dict[str, Any]] = {}
_SI_PROFILE_HINTS: dict[int, dict[str, Any]] = {}
_RUNTIME_PATHS_PREPARED = False


def _to_int(value: Any, fallback: int = 0) -> int:
    if value is None:
        return fallback
    try:
        return int(value)
    except Exception:
        return fallback

# 프레임/핸들 정규화
def _coerce_handle(raw: Any) -> int:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, ctypes.c_void_p):
        return int(raw.value or 0)
    if isinstance(raw, ctypes.c_long):
        return int(raw.value)
    if isinstance(raw, np.integer):
        return int(raw)
    return _to_int(raw)


def _normalize_json_or_default(payload: Any, default: Any) -> Any:
    if payload is None:
        return default
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, bytes):
        raw = payload
    elif isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            return {"raw": payload}
    elif isinstance(payload, (ctypes.Array, ctypes.Structure, ctypes.POINTER)):
        try:
            raw = bytes(payload)  # type: ignore[arg-type]
        except Exception:
            return default
    else:
        raw = str(payload).encode("utf-8", errors="replace")

    if not isinstance(raw, (bytes, bytearray, memoryview)):
        return default
    if not raw:
        return default
    try:
        return json.loads(bytes(raw).decode("utf-8"))
    except Exception:
        return {"raw": bytes(raw).decode("utf-8", errors="replace")}

# 프레임/핸들 정규화
def _coerce_frame_payload(raw: Any) -> dict[str, Any]:
    if raw is None:
        raise LumoNativeBindingError("native frame call returned None")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, tuple):
        if len(raw) == 0:
            raise LumoNativeBindingError("native frame tuple is empty")
        payload = {"payload": raw[0]}
        if len(raw) > 1 and isinstance(raw[1], dict):
            payload.update(raw[1])
        return payload
    if isinstance(raw, bytes):
        return {"payload": np.frombuffer(raw, dtype=np.uint16), "raw_format": "u16"}
    if isinstance(raw, bytearray):
        return {"payload": np.frombuffer(bytes(raw), dtype=np.uint16), "raw_format": "u16"}
    if isinstance(raw, np.ndarray):
        return {"payload": raw}
    if isinstance(raw, int):
        raise LumoNativeBindingError("native frame returned integer; no Python frame buffer was provided")
    return {"payload": raw, "raw_format": "unknown"}


@dataclass(slots=True)
class NativeDevice:
    index: int
    serial: str = ""
    model: str = ""
    transport: str = ""
    device_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "serial": self.serial,
            "model": self.model,
            "transport": self.transport,
            "device_id": self.device_id,
        }


def _first_ipv4_from_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "")
        for match in re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", text):
            parts = match.split(".")
            if all(0 <= int(part) <= 255 for part in parts):
                return match
    return None

# DLL 경로 탐색 / 로딩
def _candidate_library_paths() -> list[str]:
    paths: list[str] = []
    known_dlls = ("SpecSensor.dll", "specim_lumo_native.dll", "lumo_native.dll")

    def _normalize_env_candidate(value: str) -> str:
        text = value.strip().strip('"')
        if not text:
            return ""
        text = text.replace("\\ ", " ")
        if text.startswith("/") and len(text) >= 3 and text[1].isalpha() and text[2] == "/":
            drive = text[1].upper()
            tail = text[3:].replace("/", "\\")
            return f"{drive}:\\{tail}"
        return text

    for item in [os.environ.get(key) for key in _SDK_ENV_KEYS]:
        if not item:
            continue
        for value in str(item).split(os.pathsep):
            value = _normalize_env_candidate(value)
            if not value:
                continue
            candidate = Path(value)
            if candidate.exists():
                if candidate.is_file():
                    paths.append(str(candidate))
                elif candidate.is_dir():
                    for dll_name in known_dlls:
                        paths.append(str(candidate / dll_name))
                    for bin_name in _SPECIM_BIN_CANDIDATES:
                        for dll_name in known_dlls:
                            paths.append(str(candidate / bin_name / dll_name))

    roots: list[Path] = []
    for root in _SPECIM_ROOTS:
        base = Path(root)
        roots.append(base)
        if base.exists():
            for child in base.iterdir():
                if child.is_dir():
                    roots.append(child)

    for root in roots:
        if not root.exists():
            continue
        for bin_name in _SPECIM_BIN_CANDIDATES:
            for dll_name in known_dlls:
                candidate = root / bin_name / dll_name
                if candidate.exists():
                    paths.append(str(candidate))

    paths.extend(
        [
            str(path)
            for path in [
                Path.cwd() / "bin" / "lumo_native.dll",
                Path.cwd() / "bin" / "specim_lumo_native.dll",
                Path.cwd() / "lib" / "lumo_native.dll",
                Path.cwd() / "lib" / "specim_lumo_native.dll",
                Path.cwd() / "SpecSensor.dll",
            ]
        ]
    )

    dedup: list[str] = []
    for path in paths:
        if not path:
            continue
        if path not in dedup:
            dedup.append(path)
    return dedup


def _safe_add_dll_directory(path: str) -> None:
    if not path:
        return
    try:
        resolved = Path(path)
        if resolved.is_file():
            resolved = resolved.parent
        if not resolved.exists() or not resolved.is_dir():
            return
        if os.name != "nt":
            return
        candidate = str(resolved)
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        if candidate not in path_entries:
            os.environ["PATH"] = os.pathsep.join([candidate] + [p for p in path_entries if p])
        try:
            os.add_dll_directory(candidate)
        except Exception:
            pass
    except Exception:
        pass


@contextmanager
def _temporary_working_directory(path: Path | None):
    if path is None or not path.exists() or not path.is_dir():
        yield
        return
    original_cwd = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        try:
            os.chdir(original_cwd)
        except Exception:
            pass


def _runtime_working_directory() -> Path | None:
    env_bin = os.environ.get("LUMO_SDK_BIN")
    if env_bin:
        candidate = Path(env_bin)
        if candidate.exists() and candidate.is_dir():
            return candidate

    if _LOADED_LIBRARY_PATH:
        try:
            candidate = Path(_LOADED_LIBRARY_PATH).parent
            if candidate.exists() and candidate.is_dir():
                return candidate
        except Exception:
            pass

    for root in _SPECIM_ROOTS:
        for bin_dir in _SPECIM_BIN_CANDIDATES:
            candidate = Path(root) / bin_dir
            if candidate.exists() and candidate.is_dir():
                return candidate
    return None


def _resolve_license_path() -> str:
    env_value = os.environ.get("LUMO_LICENSE_PATH")
    if env_value and env_value.strip():
        return env_value.strip()

    candidates: list[Path] = [Path(r"C:\Users\Public\Documents\Specim\SpecSensor.lic")]
    for root in _SPECIM_ROOTS:
        candidates.append(root / "SpecSensor.lic")
        candidates.append(root / "profiles" / "SpecSensor.lic")
        if root.exists():
            try:
                for child in sorted(root.iterdir(), reverse=True):
                    if not child.is_dir():
                        continue
                    candidates.append(child / "SpecSensor.lic")
                    candidates.append(child / "profiles" / "SpecSensor.lic")
            except Exception:
                pass

    dedup: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(candidate)

    for candidate in dedup:
        if candidate.exists():
            return str(candidate)
    return ""


def _build_si_load_hint(*, load_arg: str, exc: Exception) -> str:
    text = str(exc)
    normalized = text.lower()
    runtime_dir = _runtime_working_directory()
    details: list[str] = []
    details.append(f"SI_Load argument: {load_arg!r}")
    if load_arg:
        load_path = Path(load_arg)
        details.append(f"SI_Load argument exists={load_path.exists()}")
        details.append(f"SI_Load argument suffix={load_path.suffix.lower() or '<none>'}")
    details.append(f"runtime_working_directory={runtime_dir or 'n/a'}")
    details.append(f"loaded_library={_LOADED_LIBRARY_PATH or 'n/a'}")
    if "stack overflow" in normalized:
        details.append(
            "Detected native stack overflow while calling SI_Load. "
            "This usually indicates a broken Specim runtime setup on this machine."
        )
    details.append(
        "Check: example2-x64.exe in the same SDK bin directory, "
        "Pleora/eBUS dependency alignment, and installed SSP/profile files."
    )
    return " | ".join(details)

# DLL 경로 탐색 / 로딩
def _prepare_runtime_search_paths() -> None:
    global _RUNTIME_PATHS_PREPARED
    if _RUNTIME_PATHS_PREPARED:
        return

    with _LIB_LOCK:
        if _RUNTIME_PATHS_PREPARED:
            return

        paths: list[str] = [
            os.environ.get("LUMO_SDK_BIN"),
            os.environ.get("LUMO_SDK_ROOT"),
            os.environ.get("LUMO_NATIVE_PATH"),
            os.environ.get("LUMO_NATIVE_DLL"),
            os.environ.get("LUMO_NATIVE_LIBRARY"),
            os.environ.get("GENICAM_GENTL64_PATH"),
            os.environ.get("PV_GENICAM_GENTL64_DIR"),
            r"C:\Windows\System32",
            r"C:\Windows\System32\Specim",
        ]

        for candidate in _candidate_library_paths():
            if candidate.lower().endswith(".dll"):
                try:
                    paths.append(str(Path(candidate).parent))
                except Exception:
                    pass

        cti_dirs: list[str] = []
        for root in _SPECIM_ROOTS:
            for bin_dir in _SPECIM_BIN_CANDIDATES:
                candidate = Path(root) / bin_dir
                if candidate.exists():
                    paths.append(str(candidate))
                    for cti in candidate.glob("*.cti"):
                        if cti.is_file():
                            parent = str(cti.parent)
                            if parent not in paths:
                                paths.append(parent)
                            if parent not in cti_dirs:
                                cti_dirs.append(parent)
            if root.exists():
                for cti in Path(root).glob("*.cti"):
                    if cti.is_file():
                        parent = str(cti.parent)
                        if parent not in paths:
                            paths.append(parent)
                        if parent not in cti_dirs:
                            cti_dirs.append(parent)

        if cti_dirs and not os.environ.get("GENICAM_GENTL64_PATH"):
            os.environ["GENICAM_GENTL64_PATH"] = ";".join(cti_dirs)

        deduped: list[str] = []
        for path in paths:
            if not path:
                continue
            if path not in deduped:
                deduped.append(path)

        for path in deduped:
            _safe_add_dll_directory(path)

        _RUNTIME_PATHS_PREPARED = True


def _discover_specim_roots() -> list[Path]:
    roots: list[Path] = []
    for root in _SPECIM_ROOTS:
        if not root.exists():
            continue
        roots.extend([match.parent.parent for match in root.glob("**/bin/") if match.is_dir()])
    if not roots:
        return []
    return roots

# DLL 경로 탐색 / 로딩
def _load_library() -> ctypes.CDLL:
    global _LOADED_LIBRARY, _LOADED_LIBRARY_PATH
    if _LOADED_LIBRARY is not None:
        return _LOADED_LIBRARY

    with _LIB_LOCK:
        if _LOADED_LIBRARY is not None:
            return _LOADED_LIBRARY

        _prepare_runtime_search_paths()

        errors: list[str] = []
        for path in _candidate_library_paths():
            if not path:
                continue
            p = Path(path)
            if not p.exists():
                continue
            try:
                # Specim SI API functions are exported with C linkage and default calling convention
                # (cdecl). On Windows, prefer CDLL over WinDLL to avoid stdcall/cdecl mismatch.
                loaded = ctypes.CDLL(str(p))
                _LOADED_LIBRARY = loaded
                _LOADED_LIBRARY_PATH = str(p)
                return loaded
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        raise LumoNativeBindingUnavailable("Native DLL not found. " + "; ".join(errors))


def _set_signature(symbol: Callable[..., Any], argtypes: Sequence[Any] | None, restype: Any | None) -> None:
    if argtypes is not None:
        try:
            symbol.argtypes = list(argtypes)
        except Exception:
            pass
    if restype is not None:
        try:
            symbol.restype = restype
        except Exception:
            pass

# 심볼 로딩/호출
def _load_symbol(lib: ctypes.CDLL, names: Sequence[str]) -> Callable[..., Any] | None:
    lower = {name.lower(): name for name in dir(lib)}
    for candidate in names:
        try:
            return getattr(lib, candidate)
        except Exception:
            pass
        candidate_lower = candidate.lower()
        if candidate_lower in lower:
            try:
                return getattr(lib, lower[candidate_lower])
            except Exception:
                pass
    return None

# 심볼 로딩/호출
def _call_symbol(lib: ctypes.CDLL, names: Sequence[str], args: tuple[Any, ...]) -> Any:
    fn = _load_symbol(lib, names)
    if fn is None:
        raise LumoNativeBindingUnavailable(f"missing symbol: {names}")
    return fn(*args)


def _normalize_identifier(raw: str) -> str:
    return "".join(ch.lower() for ch in (raw or "").strip() if ch.isalnum())


def _has_si_api(lib: ctypes.CDLL) -> bool:
    return (
        _load_symbol(lib, ("SI_Load",)) is not None
        and _load_symbol(lib, ("SI_Open",)) is not None
        and _load_symbol(lib, ("SI_Close",)) is not None
    )


def _configure_si_signatures(lib: ctypes.CDLL) -> None:
    _set_signature(_load_symbol(lib, ("SI_Load",)) or (lambda *_args: 0), (ctypes.c_wchar_p,), ctypes.c_int)
    _set_signature(_load_symbol(lib, ("SI_Unload",)) or (lambda *_args: 0), (), ctypes.c_int)
    _set_signature(_load_symbol(lib, ("SI_Open",)) or (lambda *_args: 0), (ctypes.c_int, ctypes.POINTER(_SI_HANDLE)), ctypes.c_int)
    _set_signature(_load_symbol(lib, ("SI_Close",)) or (lambda *_args: 0), (_SI_HANDLE,), ctypes.c_int)
    _set_signature(
        _load_symbol(lib, ("SI_IsImplemented",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_bool)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_IsReadable",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_bool)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_IsWritable",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_bool)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetInt",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(_SI_INT64)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_SetInt",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, _SI_INT64),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_SetIntFeature",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, _SI_INT64),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetIntMax",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(_SI_INT64)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetIntMin",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(_SI_INT64)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetFloat",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_double)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_SetFloat",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.c_double),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetFloatMax",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_double)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetFloatMin",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_double)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetBool",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_bool)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_SetBool",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.c_bool),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetString",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_Command",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetEnumStringByIndex",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetEnumCount",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(_SI_INT64)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_SetString",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.c_wchar_p),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetStringMaxLength",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetFeatureType",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_IsReadOnly",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_bool)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_GetEnumIndex",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_SetEnumIndex",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.c_int),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_SetEnumIndexByString",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.c_wchar_p),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_SetEnumString",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_wchar_p, ctypes.c_wchar_p),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_Wait",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_void_p, ctypes.POINTER(_SI_INT64), ctypes.POINTER(_SI_INT64), _SI_INT64),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_CreateBuffer",)) or (lambda *_args: 0),
        (_SI_HANDLE, _SI_INT64, ctypes.POINTER(ctypes.c_void_p)),
        ctypes.c_int,
    )
    _set_signature(
        _load_symbol(lib, ("SI_DisposeBuffer",)) or (lambda *_args: 0),
        (_SI_HANDLE, ctypes.c_void_p),
        ctypes.c_int,
    )
    _set_signature(_load_symbol(lib, ("SI_GetErrorString",)) or (lambda *_args: ""), (ctypes.c_int,), ctypes.c_wchar_p)


def _si_error_text(lib: ctypes.CDLL, error_code: int) -> str:
    fn = _load_symbol(lib, ("SI_GetErrorString",))
    if fn is None:
        return str(error_code)
    try:
        text = fn(_to_int(error_code))
        if text:
            return str(text)
    except Exception:
        pass
    return str(error_code)


def _si_command(handle: int, command: str) -> int:
    lib = _load_library()
    _ensure_si_runtime(lib)
    command_fn = _load_symbol(lib, ("SI_Command",))
    if command_fn is None:
        return 0
    try:
        with _temporary_working_directory(_runtime_working_directory()):
            rc = command_fn(_SI_HANDLE(handle), command)
        return _to_int(rc, 0)
    except TypeError:
        try:
            with _temporary_working_directory(_runtime_working_directory()):
                rc = command_fn(_SI_HANDLE(handle), ctypes.c_wchar_p(command))
            return _to_int(rc, 0)
        except Exception:
            return 0
    except Exception:
        return 0


def _si_get_bool(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str) -> tuple[bool | None, int | None]:
    getter = _load_symbol(lib, ("SI_GetBool",))
    if getter is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        value = ctypes.c_bool(False)
        rc = _to_int(getter(handle_, key, ctypes.byref(value)))
        if rc < 0:
            return None, rc
        return bool(value.value), rc
    except Exception:
        return None, None


def _si_feature_bool_query(
    lib: ctypes.CDLL,
    handle: int | _SI_HANDLE,
    key: str,
    symbol_name: str,
) -> tuple[bool | None, int | None]:
    query = _load_symbol(lib, (symbol_name,))
    if query is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        value = ctypes.c_bool(False)
        rc = _to_int(query(handle_, key, ctypes.byref(value)))
        if rc < 0:
            return None, rc
        return bool(value.value), rc
    except Exception:
        return None, None


def _si_get_frame_size_bytes(handle: int) -> int | None:
    lib = _load_library()
    _ensure_si_runtime(lib)
    for key in (
        "Camera.Image.SizeBytes",
        "Image.SizeBytes",
        "SizeBytes",
        "PayloadSize",
    ):
        value, rc = _si_get_int(lib, handle, key)
        if value is not None and value > 0 and (rc is None or rc >= 0):
            return value
    return None


def _si_get_frame_shape(handle: int) -> tuple[int | None, int | None]:
    lib = _load_library()
    _ensure_si_runtime(lib)
    band_count, rc = _si_get_int(lib, handle, "Camera.Image.Bands")
    if band_count is None or band_count <= 0:
        band_count, rc = _si_get_int(lib, handle, "Height")
        if rc is not None and rc < 0:
            band_count = None
    width, rc = _si_get_int(lib, handle, "Width")
    if width is None or width <= 0:
        width, rc = _si_get_int(lib, handle, "Camera.Image.Width")
        if rc is not None and rc < 0:
            width = None
    return band_count, width


def _si_get_frame_context(handle: int) -> dict[str, Any]:
    if handle in _SI_FRAME_CONTEXTS:
        return _SI_FRAME_CONTEXTS[handle]
    context: dict[str, Any] = {"running": False}
    _SI_FRAME_CONTEXTS[handle] = context
    return context


def _si_prepare_frame_context(handle: int) -> dict[str, Any]:
    context = _si_get_frame_context(handle)
    if context.get("buffer_handle"):
        return context

    lib = _load_library()
    _ensure_si_runtime(lib)
    cached = _SI_OPEN_SETTINGS.get(handle, {})
    cached_band_count = _to_int(
        cached.get("band_count") or cached.get("bands") or cached.get("height"),
        0,
    )
    cached_width = _to_int(
        cached.get("spatial_width") or cached.get("width") or cached.get("line_width"),
        0,
    )
    band_count: int | None = int(cached_band_count) if cached_band_count > 0 else None
    width: int | None = int(cached_width) if cached_width > 0 else None
    size_bytes = _si_get_frame_size_bytes(handle)
    if size_bytes is None or size_bytes <= 0:
        if band_count and width and band_count > 0 and width > 0:
            size_bytes = int(band_count) * int(width) * 2
        else:
            band_count, width = _si_get_frame_shape(handle)
            if band_count and width and band_count > 0 and width > 0:
                size_bytes = int(band_count) * int(width) * 2
    if size_bytes is None or size_bytes <= 0:
        if cached_band_count > 0 and cached_width > 0:
            size_bytes = int(cached_band_count) * int(cached_width) * 2
            band_count = int(cached_band_count)
            width = int(cached_width)
    if size_bytes is None or size_bytes <= 0:
        cached = _SI_OPEN_SETTINGS.get(handle, {})
        raise LumoNativeBindingError(
            "Unable to resolve frame buffer size. No size feature available and no valid open settings fallback. "
            f"cached_settings_keys={sorted(cached.keys()) if isinstance(cached, dict) else []}"
        )

    context["frame_size_bytes"] = int(size_bytes)
    context["frame_size_value"] = _SI_INT64(int(size_bytes))
    context["frame_number_value"] = _SI_INT64(0)
    if band_count and band_count > 0:
        context["band_count"] = int(band_count)
    if width and width > 0:
        context["spatial_width"] = int(width)

    create_buffer_fn = _load_symbol(lib, ("SI_CreateBuffer",))
    if create_buffer_fn is not None:
        buffer_handle = ctypes.c_void_p()
        rc = create_buffer_fn(_SI_HANDLE(handle), context["frame_size_bytes"], ctypes.byref(buffer_handle))
        rc_int = _to_int(rc, 0)
        if rc_int < 0:
            raise LumoNativeBindingError(
                f"SI_CreateBuffer failed (code={rc_int}): {_si_error_text(lib, rc_int)}"
            )
        context["buffer_handle"] = int(buffer_handle.value or 0)
        context["owns_buffer"] = True
        context["buffer"] = None
        return context

    fallback = (ctypes.c_ubyte * context["frame_size_bytes"])()
    context["buffer"] = fallback
    context["buffer_handle"] = ctypes.cast(fallback, ctypes.c_void_p).value
    context["owns_buffer"] = False
    return context


def _si_clear_frame_context(handle: int) -> None:
    context = _SI_FRAME_CONTEXTS.get(handle)
    if not context:
        return

    lib = _load_library()
    dispose_fn = _load_symbol(lib, ("SI_DisposeBuffer",))
    if (
        context.get("owns_buffer")
        and dispose_fn is not None
        and context.get("buffer_handle")
    ):
        try:
            dispose_fn(_SI_HANDLE(handle), ctypes.c_void_p(int(context["buffer_handle"])))
        except Exception:
            pass

    context.clear()

# SI fallback 런타임
def _ensure_si_runtime(lib: ctypes.CDLL) -> None:
    global _SI_RUNTIME_LOADED
    if _SI_RUNTIME_LOADED:
        return

    with _SI_LOCK:
        if _SI_RUNTIME_LOADED:
            return

        set_profiles = _load_symbol(lib, ("SI_SetString",))
        profile_dir = _default_profiles_directory()
        _configure_si_signatures(lib)
        si_load = _load_symbol(lib, ("SI_Load",))
        if si_load is None:
            raise LumoNativeBindingUnavailable("SI_Load symbol not found")

        # Match known-good startup sequence: set profiles directory before SI_Load.
        if set_profiles is not None and profile_dir:
            try:
                set_profiles(_SI_SYSTEM_HANDLE, "ProfilesDirectory", profile_dir)
            except Exception:
                pass

        # Keep runtime behavior compatible with pre-3ee9b65 flow:
        # attempt SI_Load first and let SDK-level diagnostics decide failures.
        load_arg = _resolve_license_path()
        try:
            with _temporary_working_directory(_runtime_working_directory()):
                rc = si_load(load_arg)
        except Exception as exc:  # noqa: BLE001
            hint = _build_si_load_hint(load_arg=load_arg, exc=exc)
            raise LumoNativeBindingError(f"SI_Load invocation failed: {hint}") from exc
        if _to_int(rc) < 0:
            raise LumoNativeBindingError(f"SI_Load failed: {_si_error_text(lib, _to_int(rc))}")

        # Re-apply after load for runtimes that only persist post-load values.
        if set_profiles is not None and profile_dir:
            try:
                set_profiles(_SI_SYSTEM_HANDLE, "ProfilesDirectory", profile_dir)
            except Exception:
                pass

        _SI_RUNTIME_LOADED = True


def _si_get_string(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str, default: str | None = None) -> str | None:
    value, rc = _si_get_string_with_rc(lib, handle, key)
    if rc is not None and rc < 0:
        return default
    return value if value not in (None, "") else default


def _si_get_string_with_rc(
    lib: ctypes.CDLL,
    handle: int | _SI_HANDLE,
    key: str,
) -> tuple[str | None, int | None]:
    getter = _load_symbol(lib, ("SI_GetString",))
    if getter is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        buffer = ctypes.create_unicode_buffer(4096)
        rc = _to_int(getter(handle_, key, buffer, 4096), -1)
        if _to_int(rc) < 0:
            return None, rc
        value = str(buffer.value or "").strip()
        return value or None, rc
    except Exception:
        return None, None


def _si_get_string_max_length(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str) -> tuple[int | None, int | None]:
    getter = _load_symbol(lib, ("SI_GetStringMaxLength",))
    if getter is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        value = ctypes.c_int(0)
        rc = _to_int(getter(handle_, key, ctypes.byref(value)), -1)
        if rc < 0:
            return None, rc
        return int(value.value), rc
    except Exception:
        return None, None


def _si_get_feature_type(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str) -> tuple[str | None, int | None]:
    getter = _load_symbol(lib, ("SI_GetFeatureType",))
    if getter is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        buffer = ctypes.create_unicode_buffer(128)
        rc = _to_int(getter(handle_, key, buffer, 128), -1)
        if rc < 0:
            return None, rc
        value = str(buffer.value or "").strip()
        return value or None, rc
    except Exception:
        return None, None


def _si_get_float(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str) -> tuple[float | None, int | None]:
    getter = _load_symbol(lib, ("SI_GetFloat",))
    if getter is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        value = ctypes.c_double(0.0)
        rc = _to_int(getter(handle_, key, ctypes.byref(value)), -1)
        if rc < 0:
            return None, rc
        return float(value.value), rc
    except Exception:
        return None, None


def _si_get_int_limit(
    lib: ctypes.CDLL,
    handle: int | _SI_HANDLE,
    key: str,
    symbol_name: str,
) -> tuple[int | None, int | None]:
    getter = _load_symbol(lib, (symbol_name,))
    if getter is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        value = _SI_INT64(0)
        rc = _to_int(getter(handle_, key, ctypes.byref(value)), -1)
        if rc < 0:
            return None, rc
        return int(value.value), rc
    except Exception:
        return None, None


def _si_get_float_limit(
    lib: ctypes.CDLL,
    handle: int | _SI_HANDLE,
    key: str,
    symbol_name: str,
) -> tuple[float | None, int | None]:
    getter = _load_symbol(lib, (symbol_name,))
    if getter is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        value = ctypes.c_double(0.0)
        rc = _to_int(getter(handle_, key, ctypes.byref(value)), -1)
        if rc < 0:
            return None, rc
        return float(value.value), rc
    except Exception:
        return None, None


def _si_get_enum_index(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str) -> tuple[int | None, int | None]:
    getter = _load_symbol(lib, ("SI_GetEnumIndex",))
    if getter is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        value = ctypes.c_int(0)
        rc = _to_int(getter(handle_, key, ctypes.byref(value)), -1)
        if rc < 0:
            return None, rc
        return int(value.value), rc
    except Exception:
        return None, None


def _si_set_string(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str, value: str) -> int:
    setter = _load_symbol(lib, ("SI_SetString",))
    if setter is None:
        return -1
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        return _to_int(setter(handle_, key, value), -1)
    except Exception:
        return -1


def _si_set_int(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str, value: int) -> int:
    handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
    last_rc = -1
    for names in (("SI_SetInt",), ("SI_SetIntFeature",)):
        setter = _load_symbol(lib, names)
        if setter is None:
            continue
        try:
            rc = _to_int(setter(handle_, key, _SI_INT64(int(value))), -1)
            if rc >= 0:
                return rc
            last_rc = rc
        except TypeError:
            try:
                rc = _to_int(setter(handle_, ctypes.c_wchar_p(key), _SI_INT64(int(value))), -1)
                if rc >= 0:
                    return rc
                last_rc = rc
            except Exception:
                continue
        except Exception:
            continue
    return last_rc


def _si_set_float(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str, value: float) -> int:
    setter = _load_symbol(lib, ("SI_SetFloat",))
    if setter is None:
        return -1
    handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
    try:
        return _to_int(setter(handle_, key, ctypes.c_double(float(value))), -1)
    except TypeError:
        try:
            return _to_int(setter(handle_, ctypes.c_wchar_p(key), ctypes.c_double(float(value))), -1)
        except Exception:
            return -1
    except Exception:
        return -1


def _default_profiles_directory() -> str | None:
    profile_dir = os.environ.get("LUMO_PROFILES_DIRECTORY")
    if profile_dir and profile_dir.strip():
        return profile_dir.strip()
    for candidate in _candidate_profiles_directories():
        return str(candidate)
    return None


def _candidate_profiles_directories() -> list[Path]:
    candidates: list[Path] = []

    def add(path: Path | str | None) -> None:
        if path is None:
            return
        try:
            candidate = Path(str(path).strip().strip('"'))
        except Exception:
            return
        if not candidate:
            return
        if candidate.name.lower() != "profiles" and (candidate / "profiles").exists():
            candidate = candidate / "profiles"
        if candidate.exists() and candidate.is_dir() and any(candidate.glob("*.ssp")):
            resolved = candidate.resolve()
            if resolved not in candidates:
                candidates.append(resolved)

    add(os.environ.get("LUMO_SDK_ROOT"))
    bin_dir = os.environ.get("LUMO_SDK_BIN")
    if bin_dir:
        try:
            bin_path = Path(bin_dir.strip().strip('"'))
            add(bin_path.parent.parent)
        except Exception:
            pass
    add(_SPECIM_PUBLIC_PROFILES)
    for root in _SPECIM_ROOTS:
        add(root)
        if root.exists():
            for child in root.iterdir():
                if child.is_dir():
                    add(child)
    return candidates


def _split_channel_values(raw: str | None) -> list[str]:
    if raw is None:
        return []
    values: list[str] = []
    for chunk in raw.replace("\n", ";").replace("|", ";").replace(",", ";").split(";"):
        text = chunk.strip()
        if text:
            values.append(text)
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _pick_channel_value(available: list[str], preferred: list[str]) -> str | None:
    if not available:
        return None
    normalized = {value.lower(): value for value in available}
    for target in preferred:
        if target.lower() in normalized:
            return normalized[target.lower()]
    for target in preferred:
        for value in available:
            if target.lower() in value.lower():
                return value
    return available[0] if available else None


def _is_file_reader_setup_path(path: str | Path | None) -> bool:
    if path is None:
        return False
    try:
        name = Path(str(path)).stem.lower().replace(" ", "")
    except Exception:
        name = str(path).lower().replace(" ", "")
    return "filereader" in name


def _si_apply_profile_settings(lib: ctypes.CDLL, handle: int, device_index: int | None = None) -> None:
    profile_dir = _default_profiles_directory()
    if profile_dir:
        _si_set_string(lib, _SI_SYSTEM_HANDLE, "ProfilesDirectory", profile_dir)

    open_settings = _SI_OPEN_SETTINGS.get(handle, {})
    if not isinstance(open_settings, dict):
        open_settings = {}
    has_network_selector = any(
        str(open_settings.get(key) or "").strip()
        for key in ("ip_address", "ip", "interface_name", "interface")
    )

    preferred_channel_values: list[str] = []
    env_camera_channel = os.environ.get("LUMO_CAMERA_CHANNEL")
    env_grabber_channel = os.environ.get("LUMO_GRABBER_CHANNEL")
    env_shutter_channel = os.environ.get("LUMO_SHUTTER_CHANNEL")

    for value in (env_camera_channel, env_grabber_channel, env_shutter_channel):
        if value:
            preferred_channel_values.append(value.strip())

    for feature_name in ("DeviceName", "Camera.Model"):
        value = _si_get_string(lib, handle, feature_name)
        if value:
            preferred_channel_values.append(value)

    if device_index is not None and device_index >= 0:
        for item in _si_device_list():
            if item.index == device_index:
                if item.model:
                    preferred_channel_values.append(item.model)
                break

    normalized_preferred: list[str] = []
    for value in preferred_channel_values:
        text = str(value).strip()
        if text and text not in normalized_preferred:
            normalized_preferred.append(text)

    setup_file_candidates: list[str] = []
    env_setup_file = os.environ.get("LUMO_SETUP_FILE_PATH")
    if env_setup_file:
        setup_file_candidates.append(env_setup_file)
    if profile_dir:
        profile_root = Path(profile_dir)
        if has_network_selector:
            setup_file_candidates.append(str(profile_root / "FX17e with Pleora.ssp"))
            setup_file_candidates.append(str(profile_root / "FX17e.ssp"))
            for name in normalized_preferred:
                setup_file_candidates.append(str(profile_root / f"{name}.ssp"))
        else:
            for name in normalized_preferred:
                setup_file_candidates.append(str(profile_root / f"{name}.ssp"))
            setup_file_candidates.append(str(profile_root / "FX17e.ssp"))
            setup_file_candidates.append(str(profile_root / "FX17e with Pleora.ssp"))

    chosen_setup_file: str | None = None
    for raw_path in setup_file_candidates:
        try:
            candidate = Path(raw_path.strip())
        except Exception:
            continue
        if has_network_selector and not env_setup_file and _is_file_reader_setup_path(candidate):
            continue
        if candidate.exists() and candidate.is_file():
            chosen_setup_file = str(candidate)
            break

    channel_env_overrides = {
        "Camera.Channel": env_camera_channel.strip() if env_camera_channel and env_camera_channel.strip() else None,
        "Grabber.Channel": env_grabber_channel.strip() if env_grabber_channel and env_grabber_channel.strip() else None,
        "Shutter.Channel": env_shutter_channel.strip() if env_shutter_channel and env_shutter_channel.strip() else None,
    }

    # When using GigE FX17e, some deployments use the camera IP as Grabber.Channel.
    # Keep this only as a fallback; SDK profile defaults such as Pleora "ui" are closer
    # to the vendor startup flow and should not be overwritten automatically.
    grabber_ip_fallback = str(open_settings.get("ip_address") or open_settings.get("ip") or "").strip()
    if grabber_ip_fallback:
        preferred_channel_values.append(grabber_ip_fallback)

    module_channels: dict[str, str] = {}
    ssp_channel_defaults: dict[str, str] = {}
    ssp_feature_names: set[str] = set()
    if chosen_setup_file:
        module_channels = _extract_module_channels_from_ssp(Path(chosen_setup_file))
        ssp_channel_defaults = _extract_channel_defaults_from_ssp(Path(chosen_setup_file))
        ssp_feature_names = _extract_feature_names_from_ssp(Path(chosen_setup_file))
        _SI_PROFILE_HINTS.setdefault(handle, {})
        _SI_PROFILE_HINTS[handle]["setup_file_path"] = chosen_setup_file
        _SI_PROFILE_HINTS[handle]["module_channels"] = dict(module_channels)
        _SI_PROFILE_HINTS[handle]["ssp_channel_defaults"] = dict(ssp_channel_defaults)
        _SI_PROFILE_HINTS[handle]["ssp_feature_names"] = set(ssp_feature_names)

        setup_feature_present = "Acquisition.SetupFilePath" in ssp_feature_names
        env_setup_file = os.environ.get("LUMO_SETUP_FILE_PATH")
        if setup_feature_present and (env_setup_file or chosen_setup_file):
            _si_set_string(lib, handle, "Acquisition.SetupFilePath", env_setup_file or chosen_setup_file)

    # Channels are mandatory inputs for Initialize.
    # Set explicit values first: env override > IP selector > SSP default.
    applied_channels: dict[str, str] = {}
    channel_errors: dict[str, str] = {}
    for feature_name in ("Camera.Channel", "Grabber.Channel", "Shutter.Channel"):
        if ssp_feature_names and feature_name not in ssp_feature_names:
            continue
        explicit_value = channel_env_overrides.get(feature_name)
        if not explicit_value and feature_name == "Grabber.Channel" and grabber_ip_fallback:
            explicit_value = grabber_ip_fallback
        if not explicit_value:
            explicit_value = ssp_channel_defaults.get(feature_name)
        if explicit_value:
            rc = _si_set_string(lib, handle, feature_name, explicit_value)
            if rc >= 0:
                applied_channels[feature_name] = explicit_value
            else:
                channel_errors[feature_name] = (
                    f"value={explicit_value!r}, rc={rc}, error={_si_error_text(lib, rc)}"
                )
    if applied_channels:
        _SI_PROFILE_HINTS.setdefault(handle, {})
        _SI_PROFILE_HINTS[handle]["applied_channels"] = dict(applied_channels)
    if channel_errors:
        _SI_PROFILE_HINTS.setdefault(handle, {})
        _SI_PROFILE_HINTS[handle]["channel_settings_errors"] = dict(channel_errors)
    else:
        _SI_PROFILE_HINTS.setdefault(handle, {}).pop("channel_settings_errors", None)

    # For profiles that only define a grabber module, Grabber.Channel may default to a module id
    # (e.g. grab016) instead of a usable runtime channel value. Try enum candidates first.
    if not channel_env_overrides.get("Grabber.Channel"):
        current_grabber = (_si_get_string(lib, handle, "Grabber.Channel", default="") or "").strip()
        module_grabber = str(module_channels.get("grabber", "")).strip() if isinstance(module_channels, dict) else ""
        if (
            (not current_grabber)
            or (module_grabber and current_grabber.lower() == module_grabber.lower())
        ):
            enum_values = _si_get_enum_values(lib, handle, "Grabber.Channels")
            if enum_values:
                _si_set_string(lib, handle, "Grabber.Channel", enum_values[0])


def _si_apply_acquisition_settings(lib: ctypes.CDLL, handle: int) -> None:
    open_settings = _SI_OPEN_SETTINGS.get(handle, {})
    if not isinstance(open_settings, dict):
        return

    profile_hints = _SI_PROFILE_HINTS.setdefault(handle, {})
    applied = dict(profile_hints.get("applied_acquisition_settings", {}))
    errors = dict(profile_hints.get("acquisition_settings_errors", {}))

    def pick_positive_float(*keys: str) -> float | None:
        for key in keys:
            if key not in open_settings:
                continue
            raw_value = open_settings.get(key)
            try:
                value = float(raw_value)
            except Exception:
                coerced = _to_int(raw_value, 0)
                value = float(coerced or 0)
            if value > 0:
                return value
        return None

    def try_apply(label: str, candidates: Sequence[tuple[str, float | None, str]]) -> None:
        applied_errors: dict[str, str] = {}
        for feature_name, value, _unit in candidates:
            if value is None:
                continue
            if _try_apply_feature(label, feature_name, value, _unit, applied_errors):
                return
        errors.update(applied_errors)

    def _try_apply_feature(
        label: str,
        feature_name: str,
        value: float,
        unit: str,
        applied_errors: dict[str, str],
    ) -> bool:
        if value is None:
            return False
        writable, rc = _si_feature_bool_query(lib, handle, feature_name, "SI_IsWritable")
        if writable is False:
            applied_errors[feature_name] = "not writable"
            return False
        feature_type, _type_rc = _si_get_feature_type(lib, handle, feature_name)
        normalized_type = str(feature_type or "").strip().lower()
        attempts: list[tuple[str, Callable[[float], int]]] = []
        if any(token in normalized_type for token in ("float", "double")):
            attempts.append(("float", lambda raw: _si_set_float(lib, handle, feature_name, raw)))
            attempts.append(("int", lambda raw: _si_set_int(lib, handle, feature_name, int(round(raw)))))
        else:
            attempts.append(("int", lambda raw: _si_set_int(lib, handle, feature_name, int(round(raw)))))
            attempts.append(("float", lambda raw: _si_set_float(lib, handle, feature_name, raw)))

        last_rc = -1
        last_type = ""
        for value_type, setter in attempts:
            set_rc = setter(float(value))
            if set_rc >= 0:
                stored_value: float | int = float(value)
                if value_type == "int" and abs(float(value) - round(float(value))) < 1e-9:
                    stored_value = int(round(float(value)))
                applied[label] = {
                    "feature": feature_name,
                    "value": stored_value,
                    "unit": unit,
                    "value_type": value_type,
                }
                errors.pop(feature_name, None)
                errors.pop(f"{feature_name}.writable", None)
                applied_errors.pop(feature_name, None)
                applied_errors.pop(f"{feature_name}.writable", None)
                return True
            last_rc = set_rc
            last_type = value_type
        applied_errors[feature_name] = f"{last_type}: {_si_error_text(lib, last_rc)}"
        if rc is not None and rc < 0:
            applied_errors[f"{feature_name}.writable"] = _si_error_text(lib, rc)
        return False

    exposure_time_us = pick_positive_float("integration_time_us", "exposure_time_us")
    line_rate_hz = pick_positive_float("line_rate_hz", "acquisition_line_rate")
    try_apply(
        "exposure_time_us",
        (
            ("Camera.ExposureTime", None if exposure_time_us is None else exposure_time_us / 1000.0, "ms"),
            ("ExposureTime", exposure_time_us, "us"),
            ("Acquisition.ExposureTime", exposure_time_us, "us"),
        ),
    )
    try_apply(
        "line_rate_hz",
        (
            ("Camera.FrameRate", line_rate_hz, "Hz"),
            ("AcquisitionLineRate", line_rate_hz, "Hz"),
            ("Acquisition.LineRate", line_rate_hz, "Hz"),
            ("Camera.AcquisitionLineRate", line_rate_hz, "Hz"),
        ),
    )

    profile_hints["applied_acquisition_settings"] = applied
    if errors:
        profile_hints["acquisition_settings_errors"] = errors
    else:
        profile_hints.pop("acquisition_settings_errors", None)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _extract_module_channels_from_ssp(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception:
        return {}

    modules_element: ET.Element | None = None
    for element in root.iter():
        if _xml_local_name(element.tag) == "modules":
            modules_element = element
            break
    if modules_element is None:
        return {}

    result: dict[str, str] = {}
    for module in list(modules_element):
        if _xml_local_name(module.tag) != "module":
            continue
        module_type = (module.get("type") or "").strip().lower()
        value = (module.text or "").strip()
        if not module_type or not value:
            continue
        result[module_type] = value
    return result


def _xml_local_name(tag: Any) -> str:
    text = str(tag or "")
    if "}" in text:
        return text.split("}", 1)[1].strip().lower()
    return text.strip().lower()


def _extract_channel_defaults_from_ssp(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception:
        return {}

    supported = {"camera.channel", "grabber.channel", "shutter.channel"}
    normalized_to_canonical = {
        "camera.channel": "Camera.Channel",
        "grabber.channel": "Grabber.Channel",
        "shutter.channel": "Shutter.Channel",
    }
    result: dict[str, str] = {}

    for feature in root.iter():
        if _xml_local_name(feature.tag) != "feature":
            continue
        feature_name: str | None = None
        feature_value: str | None = None
        for child in list(feature):
            local_name = _xml_local_name(child.tag)
            text = (child.text or "").strip()
            if not text:
                continue
            if local_name == "name":
                feature_name = text
            elif local_name == "value":
                feature_value = text
        if not feature_name or not feature_value:
            continue
        normalized_name = feature_name.strip().lower()
        if normalized_name not in supported:
            continue
        canonical = normalized_to_canonical[normalized_name]
        result[canonical] = feature_value.strip()
    return result


def _extract_feature_names_from_ssp(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception:
        return set()

    names: set[str] = set()
    for feature in root.iter():
        if _xml_local_name(feature.tag) != "feature":
            continue
        for child in list(feature):
            if _xml_local_name(child.tag) != "name":
                continue
            text = (child.text or "").strip()
            if text:
                names.add(text)
            break
    return names


def _si_discover_command_candidates(
    lib: ctypes.CDLL,
    handle: int,
    *,
    suffixes: tuple[str, ...],
) -> list[str]:
    feature_list = _si_get_string(lib, handle, "FeatureList", default="")
    if not feature_list:
        return []
    suffix_set = tuple(suffix.lower() for suffix in suffixes)
    tokens = re.findall(r"[A-Za-z0-9_.]+", feature_list)
    discovered: list[str] = []
    for token in tokens:
        lowered = token.lower()
        if any(lowered == suffix for suffix in suffix_set):
            discovered.append(token)
            continue
        if any(lowered.endswith(f".{suffix}") for suffix in suffix_set):
            discovered.append(token)
    return _dedupe_preserve_order(discovered)


def _si_filter_command_candidates(
    lib: ctypes.CDLL,
    handle: int,
    candidates: list[str],
    *,
    always_keep: set[str] | None = None,
) -> list[str]:
    always = always_keep or set()
    feature_list = _si_get_string(lib, handle, "FeatureList", default="") or ""
    if not feature_list:
        return _dedupe_preserve_order(candidates)
    known = set(re.findall(r"[A-Za-z0-9_.]+", feature_list))
    filtered: list[str] = []
    for command in candidates:
        if command in always or command in known:
            filtered.append(command)
    return _dedupe_preserve_order(filtered)


def _si_try_command_list(handle: int, commands: list[str]) -> tuple[str | None, int | None, dict[str, int]]:
    results: dict[str, int] = {}
    for command in commands:
        rc = _si_command(handle, command)
        results[command] = rc
        if rc >= 0:
            return command, rc, results
    return None, None, results


def _si_get_enum_string(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str, index: int) -> str | None:
    getter = _load_symbol(lib, ("SI_GetEnumStringByIndex",))
    if getter is None:
        return None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        buffer = ctypes.create_unicode_buffer(4096)
        rc = getter(handle_, key, index, buffer, 4096)
        if _to_int(rc) < 0:
            return None
        value = str(buffer.value or "").strip()
        return value or None
    except Exception:
        return None


def _si_get_int(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str) -> tuple[int | None, int | None]:
    getter = _load_symbol(lib, ("SI_GetInt",))
    if getter is None:
        return None, None
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        value = _SI_INT64(0)
        rc = getter(handle_, key, ctypes.byref(value))
        rc_int = _to_int(rc)
        if rc_int < 0:
            return None, rc_int
        return int(value.value or 0), rc_int
    except Exception:
        return None, None


def _si_get_enum_values(lib: ctypes.CDLL, handle: int | _SI_HANDLE, key: str) -> list[str]:
    count_fn = _load_symbol(lib, ("SI_GetEnumCount",))
    item_fn = _load_symbol(lib, ("SI_GetEnumStringByIndex",))
    if count_fn is None or item_fn is None:
        return []
    try:
        handle_ = handle if isinstance(handle, _SI_HANDLE) else _SI_HANDLE(handle)
        count_value = _SI_INT64(0)
        rc = _to_int(count_fn(handle_, key, ctypes.byref(count_value)), -1)
        if rc < 0:
            return []
        count = int(count_value.value or 0)
        values: list[str] = []
        for idx in range(max(0, count)):
            buffer = ctypes.create_unicode_buffer(4096)
            irc = _to_int(item_fn(handle_, key, idx, buffer, 4096), -1)
            if irc < 0:
                continue
            text = str(buffer.value or "").strip()
            if text and text not in values:
                values.append(text)
        return values
    except Exception:
        return []

# SI fallback 런타임
def _si_describe_feature(lib: ctypes.CDLL, handle: int | _SI_HANDLE, feature: str) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"name": feature}
    errors: dict[str, str] = {}

    for label, symbol in (
        ("implemented", "SI_IsImplemented"),
        ("readable", "SI_IsReadable"),
        ("writable", "SI_IsWritable"),
        ("read_only", "SI_IsReadOnly"),
    ):
        value, rc = _si_feature_bool_query(lib, handle, feature, symbol)
        if value is not None:
            snapshot[label] = value
        if rc is not None and rc < 0:
            errors[label] = _si_error_text(lib, rc)

    feature_type, rc = _si_get_feature_type(lib, handle, feature)
    if feature_type:
        snapshot["feature_type"] = feature_type
    if rc is not None and rc < 0:
        errors["feature_type"] = _si_error_text(lib, rc)

    enum_values = _si_get_enum_values(lib, handle, feature)
    if enum_values:
        snapshot["enum_values"] = enum_values
        enum_index, enum_rc = _si_get_enum_index(lib, handle, feature)
        if enum_index is not None:
            snapshot["enum_index"] = enum_index
            if 0 <= enum_index < len(enum_values):
                snapshot["value"] = enum_values[enum_index]
                snapshot["value_type"] = "enum"
        if enum_rc is not None and enum_rc < 0:
            errors["enum_index"] = _si_error_text(lib, enum_rc)

    int_value, int_rc = _si_get_int(lib, handle, feature)
    if int_value is not None:
        snapshot.setdefault("value", int_value)
        snapshot.setdefault("value_type", "int")
        min_value, min_rc = _si_get_int_limit(lib, handle, feature, "SI_GetIntMin")
        max_value, max_rc = _si_get_int_limit(lib, handle, feature, "SI_GetIntMax")
        if min_value is not None:
            snapshot["min"] = min_value
        if max_value is not None:
            snapshot["max"] = max_value
        if min_rc is not None and min_rc < 0:
            errors["int_min"] = _si_error_text(lib, min_rc)
        if max_rc is not None and max_rc < 0:
            errors["int_max"] = _si_error_text(lib, max_rc)
    elif int_rc is not None and int_rc < 0:
        errors["int"] = _si_error_text(lib, int_rc)

    float_value, float_rc = _si_get_float(lib, handle, feature)
    if float_value is not None:
        snapshot.setdefault("value", float_value)
        snapshot.setdefault("value_type", "float")
        min_value, min_rc = _si_get_float_limit(lib, handle, feature, "SI_GetFloatMin")
        max_value, max_rc = _si_get_float_limit(lib, handle, feature, "SI_GetFloatMax")
        if min_value is not None:
            snapshot.setdefault("min", min_value)
        if max_value is not None:
            snapshot.setdefault("max", max_value)
        if min_rc is not None and min_rc < 0:
            errors["float_min"] = _si_error_text(lib, min_rc)
        if max_rc is not None and max_rc < 0:
            errors["float_max"] = _si_error_text(lib, max_rc)
    elif float_rc is not None and float_rc < 0:
        errors["float"] = _si_error_text(lib, float_rc)

    bool_value, bool_rc = _si_get_bool(lib, handle, feature)
    if bool_value is not None:
        snapshot.setdefault("value", bool_value)
        snapshot.setdefault("value_type", "bool")
    elif bool_rc is not None and bool_rc < 0:
        errors["bool"] = _si_error_text(lib, bool_rc)

    string_value, string_rc = _si_get_string_with_rc(lib, handle, feature)
    if string_value is not None:
        snapshot.setdefault("value", string_value)
        snapshot.setdefault("value_type", "string")
        max_length, max_length_rc = _si_get_string_max_length(lib, handle, feature)
        if max_length is not None:
            snapshot["string_max_length"] = max_length
        if max_length_rc is not None and max_length_rc < 0:
            errors["string_max_length"] = _si_error_text(lib, max_length_rc)
    elif string_rc is not None and string_rc < 0:
        errors["string"] = _si_error_text(lib, string_rc)

    if errors:
        snapshot["read_errors"] = errors
    return snapshot


def _si_scan_devices() -> str:
    lib = _load_library()
    if not _has_si_api(lib):
        return json.dumps([], ensure_ascii=False)

    _ensure_si_runtime(lib)
    get_int = _load_symbol(lib, ("SI_GetInt",))
    if get_int is None:
        return json.dumps([], ensure_ascii=False)

    count_ptr = _SI_INT64(0)
    rc = get_int(_SI_SYSTEM_HANDLE, "DeviceCount", ctypes.byref(count_ptr))
    rc_int = _to_int(rc)
    if rc_int < 0:
        raise LumoNativeBindingError(f"SI_GetInt(DeviceCount) failed: {_si_error_text(lib, rc_int)}")

    count = int(count_ptr.value or 0)
    devices: list[dict[str, Any]] = []
    detailed_scan = os.environ.get("LUMO_SI_SCAN_DETAIL", "").strip().lower() in {"1", "true", "yes", "on"}
    for index in range(count):
        model = _si_get_enum_string(lib, _SI_SYSTEM_HANDLE, "DeviceName", index) or f"device-{index}"
        desc = _si_get_enum_string(lib, _SI_SYSTEM_HANDLE, "DeviceDescription", index) or ""
        serial = str(index)
        if detailed_scan:
            serial = (
                _si_get_string(lib, _SI_SYSTEM_HANDLE, "Sensor.SerialNumber")
                or _si_get_string(lib, _SI_SYSTEM_HANDLE, "SensorSerialNumber")
                or _si_get_string(lib, _SI_SYSTEM_HANDLE, "Camera.SerialNumber")
                or _si_get_string(lib, _SI_SYSTEM_HANDLE, "DeviceSerialNumber")
                or _si_get_string(lib, _SI_SYSTEM_HANDLE, "SerialNumber")
                or str(index)
            )
        item = {
            "index": index,
            "serial": serial,
            "model": model,
            "transport": desc or "native",
            "device_id": str(index),
        }
        ip_address = _first_ipv4_from_text(model, desc)
        if ip_address:
            item["ip_address"] = ip_address
        devices.append(item)
    return json.dumps(devices, ensure_ascii=False)


def _si_device_list() -> list[NativeDevice]:
    payload = _normalize_json_or_default(_si_scan_devices(), [])
    if not isinstance(payload, list):
        return []
    devices: list[NativeDevice] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        devices.append(
            NativeDevice(
                index=_to_int(item.get("index"), 0),
                serial=str(item.get("serial", "")),
                model=str(item.get("model", "")),
                transport=str(item.get("transport", "")),
                device_id=str(item.get("device_id", "")),
            )
        )
    return devices


def _si_resolve_device_index(device: Any) -> int:
    if device is None:
        return 0
    if isinstance(device, int):
        return device
    if isinstance(device, str):
        text = device.strip()
        if text.isdigit():
            return int(text)
        normalized = _normalize_identifier(text)
        for entry in _si_device_list():
            if normalized in (_normalize_identifier(entry.serial), _normalize_identifier(entry.device_id), _normalize_identifier(entry.model)):
                return entry.index
        return -1
    if isinstance(device, dict):
        for key in ("index", "id", "serial", "serial_number", "device_id"):
            value = device.get(key)
            if value is None:
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
            if isinstance(value, str):
                normalized = _normalize_identifier(value)
                for entry in _si_device_list():
                    if normalized in (
                        _normalize_identifier(entry.serial),
                        _normalize_identifier(entry.device_id),
                        _normalize_identifier(entry.model),
                    ):
                        return entry.index
    return -1

# SI fallback 런타임
def _si_open(device: Any) -> int:
    lib = _load_library()
    if not _has_si_api(lib):
        raise LumoNativeBindingUnavailable("SI API unavailable")
    _ensure_si_runtime(lib)

    index = _si_resolve_device_index(device)
    if index < 0:
        raise LumoNativeBindingError(f"invalid SI device index: {index}")

    device_count, rc = _si_get_int(lib, _SI_SYSTEM_HANDLE, "DeviceCount")
    if rc is not None and rc < 0:
        raise LumoNativeBindingError(
            f"SI_GetInt(DeviceCount) failed (code={rc}): {_si_error_text(lib, rc)}"
        )
    if device_count is not None:
        try:
            count = int(device_count)
        except Exception:
            count = 0
        if count <= 0:
            raise LumoNativeBindingError("SI_GetInt(DeviceCount) returned 0 devices")
        if index >= count:
            raise LumoNativeBindingError(f"SI_Open target index {index} out of range (count={count})")

    opener = _load_symbol(lib, ("SI_Open",))
    if opener is None:
        raise LumoNativeBindingUnavailable("SI_Open symbol missing")
    handle_ptr = _SI_HANDLE()
    with _temporary_working_directory(_runtime_working_directory()):
        rc = opener(index, ctypes.byref(handle_ptr))
    rc_int = _to_int(rc)
    if rc_int < 0:
        raise LumoNativeBindingError(
            f"SI_Open failed (code={rc_int}): {_si_error_text(lib, rc_int)}"
        )
    handle = _coerce_handle(handle_ptr)
    _si_apply_profile_settings(lib, handle, device_index=index)
    # initialize per-handle metadata cache for SI_Wait mode.
    _SI_FRAME_CONTEXTS.pop(handle, None)
    return handle


def _si_status(handle: int) -> dict[str, Any]:
    lib = _load_library()
    if not _has_si_api(lib):
        return {"connected": False, "handle": handle, "streaming": False}

    _ensure_si_runtime(lib)
    status: dict[str, Any] = {"connected": True, "handle": handle, "streaming": True}
    feature_keys = {
        "Height": "height",
        "Width": "width",
        "Camera.Image.Bands": "bands",
        "Camera.Image.Width": "camera_image_width",
        "Camera.Image.SizeBytes": "camera_image_size_bytes",
        "Image.SizeBytes": "image_size_bytes",
        "PayloadSize": "payload_size",
        "ExposureTime": "exposure_time_us",
        "AcquisitionLineRate": "acquisition_line_rate",
        "Acquisition.DroppedFrames": "acquisition_dropped_frames",
        "Acquisition.RingBuffer.Lag": "ring_buffer_lag",
        "Acquisition.RingBuffer.Size": "ring_buffer_size",
    }
    for key, output_key in feature_keys.items():
        value, rc = _si_get_int(lib, handle, key)
        if value is not None:
            status[output_key] = value
        if rc is not None and rc < 0:
            status["last_error"] = f"{key}: {_si_error_text(lib, rc)}"
    camera_exposure_ms, rc = _si_get_float(lib, handle, "Camera.ExposureTime")
    if camera_exposure_ms is not None:
        status["camera_exposure_time_ms"] = float(camera_exposure_ms)
        status["exposure_time_us"] = float(camera_exposure_ms) * 1000.0
    if rc is not None and rc < 0:
        status["last_error"] = f"Camera.ExposureTime: {_si_error_text(lib, rc)}"
    camera_frame_rate_hz, rc = _si_get_float(lib, handle, "Camera.FrameRate")
    if camera_frame_rate_hz is not None:
        status["camera_frame_rate_hz"] = float(camera_frame_rate_hz)
        status["acquisition_line_rate"] = float(camera_frame_rate_hz)
    if rc is not None and rc < 0:
        status["last_error"] = f"Camera.FrameRate: {_si_error_text(lib, rc)}"
    shutter_open, rc = _si_get_bool(lib, handle, "Camera.Shutter.IsOpen")
    if shutter_open is not None:
        status["shutter_is_open"] = shutter_open
    if rc is not None and rc < 0:
        status["last_error"] = f"Camera.Shutter.IsOpen: {_si_error_text(lib, rc)}"
    profile_hints = _SI_PROFILE_HINTS.get(handle, {})
    if isinstance(profile_hints, dict):
        setup_file = profile_hints.get("setup_file_path")
        applied_channels = profile_hints.get("applied_channels")
        module_channels = profile_hints.get("module_channels")
        profile_status: dict[str, Any] = {}
        if setup_file:
            profile_status["setup_file"] = str(setup_file)
        if isinstance(applied_channels, dict) and applied_channels:
            profile_status["applied_channels"] = dict(applied_channels)
        if isinstance(module_channels, dict) and module_channels:
            profile_status["module_channels"] = dict(module_channels)
        channel_errors = profile_hints.get("channel_settings_errors")
        if isinstance(channel_errors, dict) and channel_errors:
            profile_status["channel_settings_errors"] = dict(channel_errors)
        if profile_status:
            status["profile"] = profile_status
        applied = profile_hints.get("applied_acquisition_settings")
        if isinstance(applied, dict) and applied:
            status["applied_acquisition_settings"] = applied
        errors = profile_hints.get("acquisition_settings_errors")
        if isinstance(errors, dict) and errors:
            status["acquisition_settings_errors"] = errors
    return status

# SI fallback 런타임
def _si_close(handle: int) -> int:
    lib = _load_library()
    if not _has_si_api(lib):
        return 0
    close_fn = _load_symbol(lib, ("SI_Close",))
    if close_fn is None:
        return 0
    rc = close_fn(_SI_HANDLE(handle))
    _SI_OPEN_SETTINGS.pop(handle, None)
    _SI_PROFILE_HINTS.pop(handle, None)
    return _to_int(rc, 0)

# SI fallback 런타임
def _si_start(handle: int) -> int:
    with _SI_LOCK:
        lib = _load_library()
        _ensure_si_runtime(lib)
        _si_apply_profile_settings(lib, handle)
        _si_apply_acquisition_settings(lib, handle)
        profile_hints = _SI_PROFILE_HINTS.get(handle, {})
        module_channels = profile_hints.get("module_channels", {})
        prefixed_initialize_candidates: list[str] = []
        prefixed_start_candidates: list[str] = []
        if isinstance(module_channels, dict):
            for raw_channel in module_channels.values():
                channel = str(raw_channel).strip()
                if not channel:
                    continue
                prefixed_initialize_candidates.extend(
                    [
                        f"{channel}.Initialize",
                        f"{channel}.Acquisition.Initialize",
                    ]
                )
                prefixed_start_candidates.extend(
                    [
                        f"{channel}.Acquisition.Start",
                        f"{channel}.Start",
                    ]
                )

        context = _si_get_frame_context(handle)
        initialize_candidates = _dedupe_preserve_order(
            [
                "Initialize",
                "Acquisition.Initialize",
                *prefixed_initialize_candidates,
                *_si_discover_command_candidates(lib, handle, suffixes=("initialize",)),
            ]
        )
        initialize_candidates = _si_filter_command_candidates(
            lib,
            handle,
            initialize_candidates,
            always_keep={"Initialize"},
        )
        init_command, init_rc, init_results = _si_try_command_list(handle, initialize_candidates)
        if init_command is None or init_rc is None:
            channel_state = {
                "Camera.Channel": _si_get_string(lib, handle, "Camera.Channel"),
                "Grabber.Channel": _si_get_string(lib, handle, "Grabber.Channel"),
                "Shutter.Channel": _si_get_string(lib, handle, "Shutter.Channel"),
            }
            if init_command is None or init_rc is None:
                _si_clear_frame_context(handle)
                init_error_code = list(init_results.values())[-1] if init_results else -1
                raise LumoNativeBindingError(
                    "SI initialize failed "
                    f"(init_results={init_results}, init_error={_si_error_text(lib, init_error_code)}); "
                    f"channel_state={channel_state}"
                )
        _si_apply_acquisition_settings(lib, handle)

        start_candidates = _dedupe_preserve_order(
            [
                "Acquisition.Start",
                "Start",
                *prefixed_start_candidates,
                *_si_discover_command_candidates(lib, handle, suffixes=("start",)),
            ]
        )
        start_candidates = _si_filter_command_candidates(
            lib,
            handle,
            start_candidates,
            always_keep={"Acquisition.Start", "Start"},
        )
        start_command, start_rc, start_results = _si_try_command_list(handle, start_candidates)
        if start_command is None or start_rc is None:
            channel_state = {
                "Camera.Channel": _si_get_string(lib, handle, "Camera.Channel"),
                "Grabber.Channel": _si_get_string(lib, handle, "Grabber.Channel"),
                "Shutter.Channel": _si_get_string(lib, handle, "Shutter.Channel"),
            }
            _si_clear_frame_context(handle)
            init_error_code = list(init_results.values())[-1] if init_results else -1
            start_error_code = list(start_results.values())[-1] if start_results else -1
            raise LumoNativeBindingError(
                "SI start failed "
                f"(init_results={init_results}, start_results={start_results}): "
                f"init_error={_si_error_text(lib, init_error_code)}, "
                f"start_error={_si_error_text(lib, start_error_code)}; "
                f"channel_state={channel_state}"
            )

        context["running"] = True
        context["last_started_ms"] = int(time.time() * 1000)
        context["start_command"] = start_command
        context["initialize_command"] = init_command
        context["initialize_rc"] = init_rc
        return start_rc

# SI fallback 런타임
def _si_stop(handle: int) -> int:
    with _SI_LOCK:
        lib = _load_library()
        _ensure_si_runtime(lib)
        context = _SI_FRAME_CONTEXTS.get(handle)
        if context:
            context["running"] = False
        profile_hints = _SI_PROFILE_HINTS.get(handle, {})
        module_channels = profile_hints.get("module_channels", {})
        prefixed_stop_candidates: list[str] = []
        if isinstance(module_channels, dict):
            for raw_channel in module_channels.values():
                channel = str(raw_channel).strip()
                if not channel:
                    continue
                prefixed_stop_candidates.extend(
                    [
                        f"{channel}.Acquisition.Stop",
                        f"{channel}.Stop",
                    ]
                )
        stop_candidates = _dedupe_preserve_order(
            [
                "Acquisition.Stop",
                "Stop",
                *prefixed_stop_candidates,
                *_si_discover_command_candidates(lib, handle, suffixes=("stop",)),
            ]
        )
        stop_candidates = _si_filter_command_candidates(
            lib,
            handle,
            stop_candidates,
            always_keep={"Acquisition.Stop", "Stop"},
        )
        _, stop_rc, _ = _si_try_command_list(handle, stop_candidates)
        if stop_rc is None:
            return -1
        return stop_rc

# SI fallback 런타임
def _si_get_frame(handle: int, timeout_ms: int) -> dict[str, Any]:
    lib = _load_library()
    _ensure_si_runtime(lib)
    with _SI_LOCK:
        wait_fn = _load_symbol(lib, ("SI_Wait",))
        if wait_fn is None:
            raise LumoNativeBindingUnavailable("SI frame function not available")

        context = _si_prepare_frame_context(handle)
        if not context.get("buffer_handle"):
            raise LumoNativeBindingUnavailable("SI frame buffer missing")

        frame_size = context.setdefault("frame_size_value", _SI_INT64(0))
        frame_number = context.setdefault("frame_number_value", _SI_INT64(0))
        frame_size.value = context["frame_size_bytes"]

        rc = wait_fn(
            _SI_HANDLE(handle),
            ctypes.c_void_p(int(context["buffer_handle"])),
            ctypes.byref(frame_size),
            ctypes.byref(frame_number),
            _SI_INT64(int(timeout_ms)),
        )
        rc_int = _to_int(rc)
        if rc_int == -706:
            _si_apply_profile_settings(lib, handle)
            profile_hints = _SI_PROFILE_HINTS.get(handle, {})
            module_channels = profile_hints.get("module_channels", {})
            prefixed_initialize_candidates: list[str] = []
            prefixed_start_candidates: list[str] = []
            if isinstance(module_channels, dict):
                for raw_channel in module_channels.values():
                    channel = str(raw_channel).strip()
                    if not channel:
                        continue
                    prefixed_initialize_candidates.extend(
                        [
                            f"{channel}.Initialize",
                            f"{channel}.Acquisition.Initialize",
                        ]
                    )
                    prefixed_start_candidates.extend(
                        [
                            f"{channel}.Acquisition.Start",
                            f"{channel}.Start",
                        ]
                    )

            initialize_candidates = _dedupe_preserve_order(
                [
                    "Initialize",
                    "Acquisition.Initialize",
                    *prefixed_initialize_candidates,
                    *_si_discover_command_candidates(lib, handle, suffixes=("initialize",)),
                ]
            )
            initialize_candidates = _si_filter_command_candidates(
                lib,
                handle,
                initialize_candidates,
                always_keep={"Initialize"},
            )
            _, _, init_results = _si_try_command_list(handle, initialize_candidates)
            start_candidates = _dedupe_preserve_order(
                [
                    "Acquisition.Start",
                    "Start",
                    *prefixed_start_candidates,
                    *_si_discover_command_candidates(lib, handle, suffixes=("start",)),
                ]
            )
            start_candidates = _si_filter_command_candidates(
                lib,
                handle,
                start_candidates,
                always_keep={"Acquisition.Start", "Start"},
            )
            recovered_start_command, recovered_start_rc, start_results = _si_try_command_list(handle, start_candidates)
            if recovered_start_command is not None and recovered_start_rc is not None and recovered_start_rc >= 0:
                context["running"] = True
                context["recovered_start_command"] = recovered_start_command
                context["recovered_start_rc"] = recovered_start_rc
                frame_size.value = context["frame_size_bytes"]
                rc = wait_fn(
                    _SI_HANDLE(handle),
                    ctypes.c_void_p(int(context["buffer_handle"])),
                    ctypes.byref(frame_size),
                    ctypes.byref(frame_number),
                    _SI_INT64(int(timeout_ms)),
                )
                rc_int = _to_int(rc)
            if rc_int < 0:
                raise LumoNativeBindingError(
                    "SI_Wait failed after recovery "
                    f"(code={rc_int}, init_results={init_results}, start_results={start_results}): "
                    f"{_si_error_text(lib, rc_int)}"
                )

        if rc_int < 0:
            raise LumoNativeBindingError(
                f"SI_Wait failed (code={rc_int}): {_si_error_text(lib, rc_int)}"
            )

        n_bytes = _to_int(frame_size.value, 0)
        if n_bytes <= 0:
            raise LumoNativeBindingError("SI_Wait returned no bytes")

        payload = np.frombuffer(
            ctypes.string_at(ctypes.c_void_p(int(context["buffer_handle"])), n_bytes),
            dtype=np.uint16,
        )
        band_count = _to_int(context.get("band_count"), None)
        width = _to_int(context.get("spatial_width"), None)
        return {
            "payload": np.copy(payload),
            "frame_number": int(frame_number.value or 0),
            "bytes_read": n_bytes,
            "frame_size_bytes": int(context["frame_size_bytes"]),
            "band_count": int(band_count) if band_count else None,
            "spatial_width": int(width) if width else None,
            "timestamp_ns": time.time_ns(),
        }


def _si_has_frame_api() -> bool:
    lib = _load_library()
    if not _has_si_api(lib):
        return False
    return _load_symbol(lib, ("SI_Wait",)) is not None

# device Scan용 함수, limo_scan_devices 심볼이 있으면 그걸 쓰고, 없으면 SI API로 fallback
def lumo_scan_devices() -> str:
    lib = _load_library()
    lumo_fn = _load_symbol(lib, ("lumo_scan_devices", "LumoScanDevices"))
    if lumo_fn is not None:
        payload = _call_symbol(lib, ("lumo_scan_devices", "LumoScanDevices"), ())
        return json.dumps(_normalize_json_or_default(payload, []), ensure_ascii=False)

    if _has_si_api(lib):
        return _si_scan_devices()
    raise LumoNativeBindingUnavailable("missing scan function symbol")

# 카메라 Open. 전용 open 심볼 우선, 실패/부재 시 SI_Open 경로로 open.
def lumo_open(device: Any, settings_json: str) -> int:
    lib = _load_library()
    lumo_open_fn = _load_symbol(lib, ("lumo_open", "LumoOpen", "si_open", "SI_Open"))
    if lumo_open_fn is not None and lumo_open_fn.__name__.lower() != "si_open":
        if isinstance(device, dict):
            device_id = (
                device.get("serial")
                or device.get("id")
                or device.get("device_id")
                or ""
            )
        elif device is None:
            device_id = ""
        else:
            device_id = str(device)

        if not isinstance(settings_json, (str, bytes)):
            settings_json = json.dumps(settings_json)
        settings_bytes = settings_json.encode("utf-8") if isinstance(settings_json, str) else settings_json

        for names in (("lumo_open", "LumoOpen"), ("si_open", "SI_Open")):
            if names[1] == "SI_Open":
                continue
            try:
                raw = _call_symbol(
                    lib,
                    names,
                    (ctypes.c_char_p(device_id.encode("utf-8")), ctypes.c_char_p(settings_bytes)),
                )
                handle = _coerce_handle(raw)
                if handle < 0:
                    raise LumoNativeBindingError(f"open returned error code {handle}")
                return handle
            except LumoNativeBindingUnavailable:
                raise
            except Exception:
                pass

    if _has_si_api(lib):
        if not _si_has_frame_api():
            raise LumoNativeBindingUnavailable("SI API frame retrieval function is not exposed (SI_Wait not found)")
        parsed_settings = _normalize_json_or_default(settings_json, {})
        if not isinstance(parsed_settings, dict):
            parsed_settings = {}
        handle = _si_open(device)
        _SI_OPEN_SETTINGS[handle] = dict(parsed_settings)
        return handle

    raise LumoNativeBindingUnavailable("unsupported native open signature")


# streaming 시작 
def lumo_start(handle: int) -> int:
    lib = _load_library()
    for names in (("lumo_start", "LumoStart"),):
        fn = _load_symbol(lib, names)
        if fn is None:
            continue
        try:
            result = fn(handle)
            if result is None:
                return 0
            return int(result)
        except Exception as exc:
            raise LumoNativeBindingError(f"lumo_start call failed: {exc}") from exc

    if _has_si_api(lib):
        result = _si_start(handle)
        if result < 0:
            raise LumoNativeBindingError(f"SI start failed (code={result}): {_si_error_text(lib, result)}")
        return result if result >= 0 else 0

    raise LumoNativeBindingUnavailable(f"missing start symbol: {('lumo_start', 'LumoStart')}")


def lumo_apply_acquisition_settings(handle: int, settings_json: Any) -> str:
    lib = _load_library()
    parsed_settings = _normalize_json_or_default(settings_json, {})
    if not isinstance(parsed_settings, dict):
        parsed_settings = {}

    for names in (("lumo_apply_acquisition_settings", "LumoApplyAcquisitionSettings"),):
        fn = _load_symbol(lib, names)
        if fn is None:
            continue
        try:
            payload = json.dumps(parsed_settings).encode("utf-8")
            result = fn(handle, ctypes.c_char_p(payload))
            return json.dumps(_normalize_json_or_default(result, {"connected": True}), ensure_ascii=False)
        except Exception as exc:
            raise LumoNativeBindingError(f"lumo_apply_acquisition_settings call failed: {exc}") from exc

    if _has_si_api(lib):
        existing = _SI_OPEN_SETTINGS.get(handle, {})
        if not isinstance(existing, dict):
            existing = {}
        merged = dict(existing)
        merged.update(parsed_settings)
        _SI_OPEN_SETTINGS[handle] = merged
        _si_apply_acquisition_settings(lib, handle)
        return json.dumps(_si_status(handle), ensure_ascii=False)

    raise LumoNativeBindingUnavailable("missing apply acquisition settings support")

# Generic feature command helpers used by reference capture and diagnostics.
def lumo_command(handle: int, command: str) -> int:
    lib = _load_library()
    for names in (("lumo_command", "LumoCommand"),):
        fn = _load_symbol(lib, names)
        if fn is None:
            continue
        try:
            result = fn(handle, command)
            rc = 0 if result is None else int(result)
        except Exception as exc:
            raise LumoNativeBindingError(f"lumo_command({command!r}) failed: {exc}") from exc
        if rc < 0:
            raise LumoNativeBindingError(f"lumo_command({command!r}) failed (code={rc})")
        return rc

    if _has_si_api(lib):
        rc = _si_command(handle, command)
        if rc < 0:
            raise LumoNativeBindingError(
                f"SI_Command({command!r}) failed (code={rc}): {_si_error_text(lib, rc)}"
            )
        return rc

    raise LumoNativeBindingUnavailable("missing command function symbol")


def lumo_get_bool(handle: int, feature: str) -> bool | None:
    lib = _load_library()
    if _has_si_api(lib):
        value, rc = _si_get_bool(lib, handle, feature)
        if rc is not None and rc < 0:
            raise LumoNativeBindingError(
                f"SI_GetBool({feature!r}) failed (code={rc}): {_si_error_text(lib, rc)}"
            )
        return value
    raise LumoNativeBindingUnavailable("missing boolean feature read symbol")


def lumo_is_feature_implemented(handle: int, feature: str) -> bool | None:
    lib = _load_library()
    if _has_si_api(lib):
        value, rc = _si_feature_bool_query(lib, handle, feature, "SI_IsImplemented")
        if rc is not None and rc < 0:
            raise LumoNativeBindingError(
                f"SI_IsImplemented({feature!r}) failed (code={rc}): {_si_error_text(lib, rc)}"
            )
        return value
    raise LumoNativeBindingUnavailable("missing feature query symbol")


def lumo_is_feature_readable(handle: int, feature: str) -> bool | None:
    lib = _load_library()
    if _has_si_api(lib):
        value, rc = _si_feature_bool_query(lib, handle, feature, "SI_IsReadable")
        if rc is not None and rc < 0:
            raise LumoNativeBindingError(
                f"SI_IsReadable({feature!r}) failed (code={rc}): {_si_error_text(lib, rc)}"
            )
        return value
    raise LumoNativeBindingUnavailable("missing feature query symbol")


def lumo_is_feature_writable(handle: int, feature: str) -> bool | None:
    lib = _load_library()
    if _has_si_api(lib):
        value, rc = _si_feature_bool_query(lib, handle, feature, "SI_IsWritable")
        if rc is not None and rc < 0:
            raise LumoNativeBindingError(
                f"SI_IsWritable({feature!r}) failed (code={rc}): {_si_error_text(lib, rc)}"
            )
        return value
    raise LumoNativeBindingUnavailable("missing feature query symbol")


def lumo_shutter_open(handle: int) -> int:
    return lumo_command(handle, "Camera.OpenShutter")


def lumo_shutter_close(handle: int) -> int:
    return lumo_command(handle, "Camera.CloseShutter")


def lumo_is_shutter_open(handle: int) -> bool | None:
    return lumo_get_bool(handle, "Camera.Shutter.IsOpen")


# Receive one frame. Use SI_Wait based acquisition when a dedicated frame helper is absent.
def lumo_get_frame(handle: int, timeout_ms: int) -> Any:
    lib = _load_library()
    for names in (("lumo_get_frame", "LumoGetFrame"),):
        fn = _load_symbol(lib, names)
        if fn is None:
            continue
        try:
            payload = fn(handle, int(timeout_ms))
            frame = _coerce_frame_payload(payload)
            if "payload" not in frame:
                frame["payload"] = []
            return frame
        except Exception:
            continue

    if _has_si_api(lib):
        frame = _si_get_frame(handle, timeout_ms)
        if "payload" not in frame:
            frame["payload"] = []
        return frame

    raise LumoNativeBindingUnavailable(f"missing frame symbol: {('lumo_get_frame', 'LumoGetFrame')}")

# 상태 json 반환.
def _parse_feature_names_payload(features_json: Any) -> list[str]:
    if features_json is None:
        return _catalog_feature_names()
    payload = _normalize_json_or_default(features_json, None)
    if isinstance(payload, dict):
        raw_values = payload.get("features") or payload.get("names") or []
    else:
        raw_values = payload
    if isinstance(raw_values, str):
        values = re.split(r"[\n,;|]+", raw_values)
    elif isinstance(raw_values, Sequence):
        values = [str(item) for item in raw_values]
    else:
        values = []
    names: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in names:
            names.append(text)
    return names or _catalog_feature_names()


def lumo_get_feature_snapshot(handle: int, features_json: Any = None) -> str:
    """Return a read-only JSON description of Lumo SDK feature capabilities."""
    lib = _load_library()
    if not _has_si_api(lib):
        raise LumoNativeBindingUnavailable("missing SI feature API")
    _ensure_si_runtime(lib)
    _configure_si_signatures(lib)

    requested_features = _parse_feature_names_payload(features_json)
    feature_list = _si_get_string(lib, handle, "FeatureList", default="") or ""
    discovered_features = _dedupe_preserve_order(re.findall(r"[A-Za-z0-9_.]+", feature_list))
    for feature in discovered_features:
        if feature not in requested_features:
            requested_features.append(feature)

    snapshot = {
        "handle": int(handle),
        "library_path": _LOADED_LIBRARY_PATH,
        "feature_count": len(requested_features),
        "features": [_si_describe_feature(lib, handle, feature) for feature in requested_features],
    }
    if discovered_features:
        snapshot["discovered_feature_count"] = len(discovered_features)
    return json.dumps(snapshot, ensure_ascii=False)


def lumo_get_status(handle: int) -> str:
    lib = _load_library()
    for names in (("lumo_get_status", "LumoGetStatus"),):
        try:
            payload = _call_symbol(lib, names, (handle,))
            status = _normalize_json_or_default(payload, {"connected": True})
            if isinstance(status, dict):
                status.setdefault("connected", True)
                status.setdefault("handle", handle)
                status.setdefault("streaming", True)
            return json.dumps(status, ensure_ascii=False) if not isinstance(status, str) else status
        except Exception:
            pass

    status = _si_status(handle)
    status.setdefault("provider_mode", "native")
    return json.dumps(status, ensure_ascii=False)

# stream 정지 / 핸들 종료
def lumo_stop(handle: int) -> int:
    lib = _load_library()
    for names in (("lumo_stop", "LumoStop"),):
        fn = _load_symbol(lib, names)
        if fn is None:
            continue
        try:
            result = fn(handle)
            return 0 if result is None else int(result)
        except Exception as exc:
            raise LumoNativeBindingError(f"lumo_stop call failed: {exc}") from exc

    if _has_si_api(lib):
        return _si_stop(handle)
    return 0

# stream 정지 / 핸들 종료
def lumo_close(handle: int) -> int:
    lib = _load_library()
    for names in (("lumo_close", "LumoClose"),):
        fn = _load_symbol(lib, names)
        if fn is None:
            continue
        try:
            result = fn(handle)
            return 0 if result is None else int(result)
        except Exception as exc:
            raise LumoNativeBindingError(f"lumo_close call failed: {exc}") from exc

    if _has_si_api(lib):
        rc = _si_close(handle)
        _si_clear_frame_context(handle)
        return rc

    return 0

# 전용 바인딩이 지원하면 release 호출, SI 경로에선 no-op
def lumo_release_frame(handle: int, frame_handle: Any) -> int:
    lib = _load_library()
    for names in (("lumo_release_frame", "LumoReleaseFrame"),):
        fn = _load_symbol(lib, names)
        if fn is None:
            continue
        try:
            result = fn(handle, frame_handle)
            return 0 if result is None else int(result)
        except Exception:
            continue

    # Optional, no-op for SI API-only paths.
    if _has_si_api(lib):
        return 0
    return 0


def lumo_reset_runtime(force_close_handles: bool = True) -> int:
    """Best-effort SI runtime reset for recovery after stream/control failures."""
    global _SI_RUNTIME_LOADED
    lib = _load_library()
    if not _has_si_api(lib):
        return 0

    with _SI_LOCK:
        known_handles: set[int] = set()
        for mapping in (_SI_OPEN_SETTINGS, _SI_PROFILE_HINTS, _SI_FRAME_CONTEXTS):
            for raw_handle in list(mapping.keys()):
                try:
                    known_handles.add(int(raw_handle))
                except Exception:
                    continue

        close_fn = _load_symbol(lib, ("SI_Close",))
        if force_close_handles and close_fn is not None:
            for handle in sorted(known_handles):
                try:
                    close_fn(_SI_HANDLE(handle))
                except Exception:
                    pass

        for handle in sorted(known_handles):
            _si_clear_frame_context(handle)

        _SI_OPEN_SETTINGS.clear()
        _SI_PROFILE_HINTS.clear()
        _SI_FRAME_CONTEXTS.clear()

        unload_rc = 0
        unload_fn = _load_symbol(lib, ("SI_Unload",))
        if _SI_RUNTIME_LOADED and unload_fn is not None:
            try:
                unload_rc = _to_int(unload_fn(), 0)
            except Exception:
                unload_rc = -1

        _SI_RUNTIME_LOADED = False
        return unload_rc


def __getattr__(name: str) -> Any:
    if name in {"LumoNativeBindingError", "LumoNativeBindingUnavailable"}:
        return globals()[name]
    raise AttributeError(name)
