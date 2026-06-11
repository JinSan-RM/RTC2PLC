from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


KIT_ROOT = Path(__file__).resolve().parents[1]
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from specim_lumo_camera_kit import SpecimLumoCameraModule  # noqa: E402
from specim_lumo_camera_kit.config_example import CAMERA_CONFIG  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Specim Lumo camera kit smoke capture")
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--no-save", action="store_true", help="capture into memory only")
    parser.add_argument("--mac-address", type=str, help="target Lumo camera MAC address for IP discovery")
    parser.add_argument("--ip-address", type=str, help="manual Lumo camera IP override for diagnostics")
    parser.add_argument("--interface-name", type=str, help="override network interface name")
    parser.add_argument("--device-index", type=int, help="override native device index")
    parser.add_argument("--no-skip-scan", action="store_true", help="enumerate devices before open")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = dict(CAMERA_CONFIG)
    config["lumo"] = dict(CAMERA_CONFIG["lumo"])
    if args.mac_address:
        config["lumo"]["mac_address"] = args.mac_address
    if args.interface_name:
        config["lumo"]["interface_name"] = args.interface_name
    if args.device_index is not None:
        config["lumo"]["device_index"] = int(args.device_index)
    if args.no_skip_scan:
        config["lumo"]["skip_scan"] = False

    camera = SpecimLumoCameraModule.from_config_payload(config)
    if args.ip_address:
        camera.config.ip_address = args.ip_address
    try:
        print("connect_status=" + json.dumps(camera.connect(), ensure_ascii=False))
        if args.no_save:
            result = camera.smoke(frames=int(args.frames))
            print("capture=" + json.dumps(result.to_summary(), ensure_ascii=False))
        else:
            result = camera.capture_session(
                output_root=args.output_root,
                frames=int(args.frames),
                label="lumo-smoke",
                capture_metadata={"project_id": "portable-kit"},
            )
            print("capture=" + json.dumps(result.to_summary(), ensure_ascii=False))
            print(f"session_dir={result.session_dir}")
            print(f"manifest={result.manifest_path}")
    finally:
        camera.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
