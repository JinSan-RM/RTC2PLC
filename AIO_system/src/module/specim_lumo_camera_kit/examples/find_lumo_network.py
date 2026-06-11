from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


KIT_ROOT = Path(__file__).resolve().parents[1]
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from specim_lumo_camera_kit import (  # noqa: E402
    find_lumo_neighbor_by_mac,
    list_local_network_adapters,
    list_lumo_remote_neighbors,
    normalize_mac_address,
)
from specim_lumo_camera_kit.config_example import CAMERA_CONFIG  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find the current Specim Lumo camera IP from Windows neighbors")
    parser.add_argument("--mac-address", type=str, help="target camera MAC address")
    parser.add_argument("--interface-name", type=str, help="Windows network interface alias")
    parser.add_argument("--list-candidates", action="store_true", help="print all valid remote candidates")
    return parser


def _lumo_config() -> dict[str, object]:
    lumo = CAMERA_CONFIG.get("lumo", {})
    return dict(lumo) if isinstance(lumo, dict) else {}


def main() -> int:
    args = build_parser().parse_args()
    lumo = _lumo_config()
    mac = str(args.mac_address or lumo.get("mac_address") or lumo.get("target_mac_address") or "").strip()
    interface = str(args.interface_name or lumo.get("interface_name") or "").strip() or None
    adapters = list_local_network_adapters(timeout_seconds=5.0)
    local_ips = [
        ip
        for adapter in adapters
        for ip in adapter.ipv4_addresses
        if adapter.media_connected and ip
    ]

    payload: dict[str, object] = {
        "target_mac": normalize_mac_address(mac) if mac else "",
        "interface_name": interface or "",
        "local_ipv4_addresses": local_ips,
    }

    if mac:
        neighbor = find_lumo_neighbor_by_mac(
            mac_address=mac,
            interface_name=interface,
            local_ipv4_addresses=local_ips,
            timeout_seconds=5.0,
        )
        payload["match"] = neighbor.to_dict() if neighbor is not None else None
    else:
        payload["match"] = None

    if args.list_candidates:
        candidates = list_lumo_remote_neighbors(
            interface_name=interface,
            local_ipv4_addresses=local_ips,
            timeout_seconds=5.0,
        )
        payload["candidates"] = [candidate.to_dict() for candidate in candidates]

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("match") else 1


if __name__ == "__main__":
    raise SystemExit(main())
