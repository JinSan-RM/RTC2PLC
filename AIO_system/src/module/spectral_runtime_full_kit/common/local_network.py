from __future__ import annotations

import json
from dataclasses import dataclass
import ipaddress
import re
import subprocess
from typing import Mapping


AUTO_VALUE_TOKENS = {"auto", "local", "local-ip", "local_ipv4", "local-ipv4", "auto-local-ip"}


@dataclass(frozen=True, slots=True)
class LocalNetworkAdapter:
    name: str
    description: str | None
    ipv4_addresses: tuple[str, ...]
    media_connected: bool
    is_wireless: bool
    raw_header: str

    def preferred_ipv4(self, *, prefer_link_local: bool = True) -> str | None:
        if not self.ipv4_addresses:
            return None
        if prefer_link_local:
            for value in self.ipv4_addresses:
                if is_link_local_ipv4(value):
                    return value
        return self.ipv4_addresses[0]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "ipv4_addresses": list(self.ipv4_addresses),
            "media_connected": self.media_connected,
            "is_wireless": self.is_wireless,
            "raw_header": self.raw_header,
        }


@dataclass(frozen=True, slots=True)
class LocalNetworkNeighbor:
    ip_address: str
    link_layer_address: str
    state: str
    interface_alias: str

    @property
    def is_valid_remote(self) -> bool:
        return (
            _is_unicast_ipv4(self.ip_address)
            and _has_resolved_link_layer_address(self.link_layer_address)
            and _has_usable_neighbor_state(self.state)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ip_address": self.ip_address,
            "link_layer_address": self.link_layer_address,
            "state": self.state,
            "interface_alias": self.interface_alias,
            "is_valid_remote": self.is_valid_remote,
        }


def normalize_mac_address(value: object) -> str:
    compact = "".join(ch for ch in str(value or "") if ch.isalnum()).lower()
    if len(compact) != 12:
        return compact
    return "-".join(compact[index : index + 2] for index in range(0, 12, 2)).upper()


def list_local_network_adapters(*, timeout_seconds: float = 10.0) -> list[LocalNetworkAdapter]:
    output = subprocess.check_output(
        ["ipconfig", "/all"],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=float(timeout_seconds),
    )
    return parse_ipconfig_all(output)


def list_ipv4_neighbors(
    *,
    interface_name: str | None = None,
    timeout_seconds: float = 5.0,
) -> list[LocalNetworkNeighbor]:
    command = "Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue"
    if interface_name:
        command += f" -InterfaceAlias {_powershell_quote(interface_name)}"
    command += " | Select-Object IPAddress,LinkLayerAddress,State,InterfaceAlias | ConvertTo-Json -Compress"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", _powershell_utf8_command(command)],
        stdout=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        stderr=subprocess.STDOUT,
        timeout=float(timeout_seconds),
        check=False,
    )
    if result.returncode != 0:
        return []
    return parse_net_neighbor_json(result.stdout)


def _powershell_utf8_command(command: str) -> str:
    return (
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        "$OutputEncoding = [Console]::OutputEncoding; "
        + command
    )


def parse_net_neighbor_json(output: str) -> list[LocalNetworkNeighbor]:
    raw = str(output or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, Mapping):
        items = [payload]
    elif isinstance(payload, list):
        items = [item for item in payload if isinstance(item, Mapping)]
    else:
        return []

    neighbors: list[LocalNetworkNeighbor] = []
    for item in items:
        ip_address = str(item.get("IPAddress") or "").strip()
        if not ip_address:
            continue
        try:
            ipaddress.IPv4Address(ip_address)
        except ipaddress.AddressValueError:
            continue
        neighbors.append(
            LocalNetworkNeighbor(
                ip_address=ip_address,
                link_layer_address=str(item.get("LinkLayerAddress") or "").strip(),
                state=str(item.get("State") or "").strip(),
                interface_alias=str(item.get("InterfaceAlias") or "").strip(),
            )
        )
    return neighbors


def list_lumo_remote_neighbors(
    *,
    interface_name: str | None,
    local_ipv4_addresses: list[str] | tuple[str, ...] = (),
    timeout_seconds: float = 5.0,
) -> list[LocalNetworkNeighbor]:
    neighbors = list_ipv4_neighbors(interface_name=interface_name, timeout_seconds=timeout_seconds)
    local_ips = {str(value).strip() for value in local_ipv4_addresses if str(value).strip()}
    candidates = [
        neighbor
        for neighbor in neighbors
        if neighbor.is_valid_remote and neighbor.ip_address not in local_ips
    ]
    return sorted(candidates, key=_lumo_neighbor_sort_key)


def find_lumo_neighbor_by_mac(
    *,
    mac_address: str,
    interface_name: str | None = None,
    local_ipv4_addresses: list[str] | tuple[str, ...] = (),
    timeout_seconds: float = 5.0,
) -> LocalNetworkNeighbor | None:
    target = normalize_mac_address(mac_address)
    if not target:
        return None
    neighbors = list_lumo_remote_neighbors(
        interface_name=interface_name,
        local_ipv4_addresses=local_ipv4_addresses,
        timeout_seconds=timeout_seconds,
    )
    for neighbor in neighbors:
        if normalize_mac_address(neighbor.link_layer_address) == target:
            return neighbor
    return None


def parse_ipconfig_all(output: str) -> list[LocalNetworkAdapter]:
    sections: list[tuple[str, list[str]]] = []
    current_header: str | None = None
    current_lines: list[str] = []
    for raw_line in str(output or "").splitlines():
        line = raw_line.rstrip()
        if _is_adapter_header(line):
            if current_header is not None:
                sections.append((current_header, current_lines))
            current_header = line.strip()
            current_lines = []
            continue
        if current_header is not None:
            current_lines.append(line)
    if current_header is not None:
        sections.append((current_header, current_lines))

    adapters: list[LocalNetworkAdapter] = []
    for header, lines in sections:
        name = _adapter_name_from_header(header)
        if not name:
            continue
        is_wireless = _is_wireless_header(header)
        disconnected = any(_is_disconnected_line(line) for line in lines)
        description = _extract_description(lines)
        ipv4_addresses = tuple(_extract_ipv4_addresses(lines))
        media_connected = bool(ipv4_addresses) and not disconnected
        adapters.append(
            LocalNetworkAdapter(
                name=name,
                description=description,
                ipv4_addresses=ipv4_addresses,
                media_connected=media_connected,
                is_wireless=is_wireless,
                raw_header=header.strip().rstrip(":"),
            )
        )
    return adapters


def merge_lumo_network_auto_settings(
    camera_config: Mapping[str, object],
    *,
    adapters: list[LocalNetworkAdapter] | None = None,
    ipconfig_output: str | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:

    """Resolve `lumo` auto network placeholders from local Windows adapters.

    This function is intentionally opt-in. It reads OS adapter values only when
    `lumo.auto_from_local_network` is true or `interface_name` /
    `local_ipv4_address` is set to an auto token. It never writes
    `lumo.ip_address`; the camera IP is discovered from the remote MAC address
    or supplied explicitly by CLI/UI override.
    """

    resolved: dict[str, object] = dict(camera_config or {})
    raw_lumo = resolved.get("lumo", {})
    lumo = dict(raw_lumo) if isinstance(raw_lumo, Mapping) else {}
    resolved["lumo"] = lumo
    if not _should_auto_resolve_lumo(lumo):
        return resolved

    try:
        local_adapters = adapters
        if local_adapters is None:
            local_adapters = parse_ipconfig_all(ipconfig_output) if ipconfig_output is not None else list_local_network_adapters(
                timeout_seconds=timeout_seconds
            )
    except Exception as exc:  # noqa: BLE001
        lumo["local_network_error"] = str(exc)
        return resolved

    preferred_interface = _preferred_interface_name(lumo)
    preferred_ip = _preferred_local_ip(lumo)
    selected = select_lumo_local_adapter(
        local_adapters,
        preferred_interface=preferred_interface,
        preferred_ip=preferred_ip,
        prefer_link_local=bool(lumo.get("prefer_link_local", True)),
    )
    if selected is None:
        lumo["local_network_error"] = "no suitable local adapter found"
        return resolved

    local_ip = selected.preferred_ipv4(prefer_link_local=bool(lumo.get("prefer_link_local", True)))
    if _is_missing_or_auto(lumo.get("interface_name")):
        lumo["interface_name"] = selected.name
    if local_ip and _is_missing_or_auto(lumo.get("local_ipv4_address")):
        lumo["local_ipv4_address"] = local_ip
    lumo["local_network_adapter"] = selected.to_dict()
    return resolved


def select_lumo_local_adapter(
    adapters: list[LocalNetworkAdapter],
    *,
    preferred_interface: str | None = None,
    preferred_ip: str | None = None,
    prefer_link_local: bool = True,
) -> LocalNetworkAdapter | None:

    candidates = [adapter for adapter in adapters if adapter.media_connected and adapter.ipv4_addresses]
    if not candidates:
        candidates = [adapter for adapter in adapters if adapter.ipv4_addresses]
    if not candidates:
        return None

    if preferred_ip:
        target_ip = preferred_ip.strip()
        for adapter in candidates:
            if target_ip in adapter.ipv4_addresses:
                return adapter
        if not preferred_interface:
            return None

    if preferred_interface:
        normalized = preferred_interface.strip().lower()
        for adapter in candidates:
            values = [adapter.name, adapter.description or "", adapter.raw_header]
            if any(normalized in value.lower() for value in values):
                return adapter
        return None

    wired_candidates = [adapter for adapter in candidates if not adapter.is_wireless] or candidates
    if prefer_link_local:
        for adapter in wired_candidates:
            if any(is_link_local_ipv4(value) for value in adapter.ipv4_addresses):
                return adapter
    return wired_candidates[0]


def is_link_local_ipv4(value: str) -> bool:
    try:
        return ipaddress.IPv4Address(str(value)).is_link_local
    except ipaddress.AddressValueError:
        return False


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _has_resolved_link_layer_address(value: object) -> bool:
    compact = "".join(ch for ch in str(value or "").strip() if ch.isalnum()).lower()
    if not compact:
        return False
    return compact not in {"0" * len(compact), "f" * len(compact)}


def _has_usable_neighbor_state(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    return text not in {"0", "1", "unreachable", "incomplete", "invalid"}


def _is_unicast_ipv4(value: object) -> bool:
    try:
        parsed = ipaddress.IPv4Address(str(value or "").strip())
    except ipaddress.AddressValueError:
        return False
    return not (
        parsed.is_multicast
        or parsed.is_loopback
        or parsed.is_unspecified
        or str(parsed) == "255.255.255.255"
    )


def _lumo_neighbor_sort_key(neighbor: LocalNetworkNeighbor) -> tuple[int, int, str]:
    try:
        parsed = ipaddress.IPv4Address(neighbor.ip_address)
    except ipaddress.AddressValueError:
        return (2, 9, neighbor.ip_address)
    link_local_rank = 0 if parsed.is_link_local else 1
    state_rank = 0 if str(neighbor.state).strip().lower() in {"5", "reachable"} else 1
    return (link_local_rank, state_rank, neighbor.ip_address)


def _should_auto_resolve_lumo(lumo: Mapping[str, object]) -> bool:
    if bool(lumo.get("auto_from_local_network", False)):
        return True
    return any(
        _is_auto_value(lumo.get(key))
        for key in ("interface_name", "local_ipv4_address")
    )


def _is_missing_or_auto(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.lower() in AUTO_VALUE_TOKENS


def _is_auto_value(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in AUTO_VALUE_TOKENS


def _preferred_interface_name(lumo: Mapping[str, object]) -> str | None:
    for key in ("preferred_interface_name", "preferred_interface", "interface_hint"):
        value = lumo.get(key)
        if value is not None and not _is_auto_value(value):
            text = str(value).strip()
            if text:
                return text
    value = lumo.get("interface_name")
    if value is not None and not _is_auto_value(value):
        text = str(value).strip()
        if text:
            return text
    return None


def _preferred_local_ip(lumo: Mapping[str, object]) -> str | None:
    for key in ("preferred_local_ipv4_address", "preferred_local_ip"):
        value = lumo.get(key)
        if value is not None and not _is_auto_value(value):
            text = str(value).strip()
            if text:
                return text
    return None


def _is_adapter_header(line: str) -> bool:
    text = line.strip()
    if not text or not text.endswith(":"):
        return False
    if line[:1].isspace():
        return False
    lowered = text.lower()
    return "adapter" in lowered or "어댑터" in text


def _adapter_name_from_header(header: str) -> str:
    text = header.strip().rstrip(":").strip()
    prefixes = (
        "Ethernet adapter ",
        "Wireless LAN adapter ",
        "Tunnel adapter ",
        "Unknown adapter ",
        "이더넷 어댑터 ",
        "무선 LAN 어댑터 ",
        "터널 어댑터 ",
    )
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):].strip() or text
    return text


def _is_wireless_header(header: str) -> bool:
    lowered = header.lower()
    return "wireless" in lowered or "wi-fi" in lowered or "wifi" in lowered or "무선" in header


def _is_disconnected_line(line: str) -> bool:
    lowered = line.lower()
    return "media disconnected" in lowered or "미디어 연결 끊김" in line or "연결 끊김" in line


def _extract_description(lines: list[str]) -> str | None:
    for line in lines:
        lowered = line.lower()
        if "description" not in lowered and "설명" not in line:
            continue
        value = _value_after_colon(line)
        if value:
            return value
    return None


def _extract_ipv4_addresses(lines: list[str]) -> list[str]:
    values: list[str] = []
    for line in lines:
        if "ipv4" not in line.lower():
            continue
        for match in re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", line):
            try:
                parsed = ipaddress.IPv4Address(match)
            except ipaddress.AddressValueError:
                continue
            if parsed.is_loopback or parsed.is_unspecified:
                continue
            text = str(parsed)
            if text not in values:
                values.append(text)
    return values


def _value_after_colon(line: str) -> str:
    if ":" not in line:
        return ""
    return line.split(":", 1)[1].strip()
