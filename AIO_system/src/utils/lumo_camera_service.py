"""Shared helpers for Specim/Lumo camera diagnostics and test scans."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

from src.utils.config_util import DEFAULT_LUMO_MAC_ADDRESS


def ensure_lumo_module_path() -> None:
    module_root = Path(__file__).resolve().parents[1] / "module" / "specim_lumo_camera_kit"
    module_path = str(module_root)
    if module_root.exists() and module_path not in sys.path:
        sys.path.insert(0, module_path)


def lumo_camera_payload(app_config: dict[str, Any] | None) -> dict[str, Any]:
    camera_connection = (app_config or {}).get("camera_connection_config", {})
    hyper = camera_connection.get("hyperspectral", {}) if isinstance(camera_connection, dict) else {}
    if not isinstance(hyper, dict):
        hyper = {}

    camera = hyper.get("camera", {})
    lumo = hyper.get("lumo", {})
    breeze_compat = hyper.get("breeze_compat", {})

    payload = {
        "camera": dict(camera) if isinstance(camera, dict) else {},
        "lumo": dict(lumo) if isinstance(lumo, dict) else {},
        "breeze_compat": dict(breeze_compat) if isinstance(breeze_compat, dict) else {},
    }
    payload["lumo"]["mac_address"] = DEFAULT_LUMO_MAC_ADDRESS
    payload["lumo"]["interface_name"] = sanitize_lumo_interface_name(
        payload["lumo"].get("interface_name")
    ) or ""
    payload["lumo"].setdefault("provider_mode", "native")
    payload["lumo"].setdefault("grab_timeout_ms", 5000)
    payload["lumo"].setdefault("device_index", 0)
    return payload


def sanitize_lumo_interface_name(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or "\ufffd" in text or text.count("?") >= 2:
        return None
    return text


def list_lumo_devices() -> list[dict[str, Any]]:
    ensure_lumo_module_path()
    from specim_lumo_camera_kit import SpecimLumoCameraModule

    devices = SpecimLumoCameraModule.list_devices()
    return devices if isinstance(devices, list) else []


def find_lumo_network(interface_name: str | None = None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    ensure_lumo_module_path()
    from specim_lumo_camera_kit import (
        find_lumo_neighbor_by_mac,
        list_local_network_adapters,
        list_lumo_remote_neighbors,
        normalize_mac_address,
        select_lumo_local_adapter,
    )

    requested_interface = sanitize_lumo_interface_name(interface_name)
    adapters = list_local_network_adapters(timeout_seconds=5.0)
    selected_adapter = None
    if requested_interface:
        selected_adapter = select_lumo_local_adapter(adapters, preferred_interface=requested_interface)

    resolved_interface = selected_adapter.name if selected_adapter is not None else None
    local_ips = [
        ip
        for adapter in adapters
        for ip in adapter.ipv4_addresses
        if adapter.media_connected and ip
    ]

    candidates = list_lumo_remote_neighbors(
        interface_name=resolved_interface,
        local_ipv4_addresses=local_ips,
        timeout_seconds=5.0,
    )

    neighbor = find_lumo_neighbor_by_mac(
        mac_address=DEFAULT_LUMO_MAC_ADDRESS,
        interface_name=resolved_interface,
        local_ipv4_addresses=local_ips,
        timeout_seconds=5.0,
    )
    if neighbor is None and resolved_interface:
        neighbor = find_lumo_neighbor_by_mac(
            mac_address=DEFAULT_LUMO_MAC_ADDRESS,
            interface_name=None,
            local_ipv4_addresses=local_ips,
            timeout_seconds=5.0,
        )

    if neighbor is None:
        return None, [candidate.to_dict() for candidate in candidates]

    adapter = next((item for item in adapters if item.name == neighbor.interface_alias), None)
    network = {
        "ip_address": neighbor.ip_address,
        "interface_alias": neighbor.interface_alias,
        "mac_address": normalize_mac_address(neighbor.link_layer_address or DEFAULT_LUMO_MAC_ADDRESS),
        "neighbor_state": neighbor.state,
        "local_ipv4_addresses": list(adapter.ipv4_addresses) if adapter else local_ips,
    }
    return network, [candidate.to_dict() for candidate in candidates]


def find_lumo_device_index(
    devices: list[dict[str, Any]],
    *,
    mac_address: str = DEFAULT_LUMO_MAC_ADDRESS,
    ip_address: str = "",
) -> int | None:
    if not isinstance(devices, list):
        return None
    target_mac = _compact_mac(mac_address)
    target_ip = str(ip_address or "").strip()

    for fallback_index, device in enumerate(devices):
        if not isinstance(device, dict):
            continue
        device_macs = [
            device.get("mac_address"),
            device.get("target_mac_address"),
            device.get("link_layer_address"),
            device.get("mac"),
        ]
        if target_mac and any(_compact_mac(value) == target_mac for value in device_macs):
            return _device_index(device, fallback_index)

    for fallback_index, device in enumerate(devices):
        if not isinstance(device, dict):
            continue
        device_ips = [
            device.get("ip_address"),
            device.get("ip"),
            device.get("camera_ip"),
        ]
        if target_ip and any(str(value or "").strip() == target_ip for value in device_ips):
            return _device_index(device, fallback_index)

    if len(devices) == 1:
        return _device_index(devices[0], 0)

    best_devices = [
        (fallback_index, device)
        for fallback_index, device in enumerate(devices)
        if isinstance(device, dict) and not is_low_quality_lumo_device(device)
    ]
    if len(best_devices) == 1:
        fallback_index, device = best_devices[0]
        return _device_index(device, fallback_index)
    return None


def lumo_status_snapshot(app_config: dict[str, Any] | None) -> dict[str, Any]:
    payload = lumo_camera_payload(app_config)
    interface_name = sanitize_lumo_interface_name(payload.get("lumo", {}).get("interface_name"))
    network, candidates = find_lumo_network(interface_name=interface_name)
    devices = list_lumo_devices()
    device_index = find_lumo_device_index(
        devices,
        ip_address=str(network.get("ip_address", "")) if network else "",
    )
    return {
        "network": network,
        "network_candidates": candidates,
        "devices": devices,
        "device_index": device_index,
        "connected": bool(network) and device_index is not None,
    }


def lumo_line_to_rgb_bytes(frame_data: Any, rgb_bands: list[int] | tuple[int, int, int] | None = None) -> bytes:
    data = np.asarray(frame_data)
    rgb = tuple(int(item) for item in (rgb_bands or (32, 96, 160)))
    if data.ndim != 2:
        raise ValueError(f"Expected 2D Lumo frame data, got shape={data.shape!r}.")

    if data.shape[0] > max(rgb):
        channels = [data[band, :] for band in rgb]
    elif data.shape[1] > max(rgb):
        channels = [data[:, band] for band in rgb]
    else:
        channels = [data.mean(axis=0)]
        channels = channels * 3

    stacked = np.stack([_normalize_channel(channel) for channel in channels], axis=1)
    return stacked.astype(np.uint8).tobytes()


def is_low_quality_lumo_device(device: dict[str, Any]) -> bool:
    text = " ".join(
        str(device.get(key, ""))
        for key in ("model", "transport", "name", "device_id", "id")
    ).lower()
    return any(keyword in text for keyword in ("filereader", "mock", "with pleora", "pleora"))


def _normalize_channel(channel: Any) -> np.ndarray:
    values = np.asarray(channel, dtype=np.float32)
    if values.size == 0:
        return np.zeros((0,), dtype=np.uint8)
    low = float(np.percentile(values, 1))
    high = float(np.percentile(values, 99))
    if high <= low:
        high = float(values.max())
        low = float(values.min())
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8)
    return np.clip((values - low) * 255.0 / (high - low), 0, 255).astype(np.uint8)


def _compact_mac(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isalnum()).lower()


def _device_index(device: dict[str, Any], fallback_index: int) -> int:
    for key in ("device_index", "index", "id", "device_id"):
        value = device.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return int(fallback_index)
