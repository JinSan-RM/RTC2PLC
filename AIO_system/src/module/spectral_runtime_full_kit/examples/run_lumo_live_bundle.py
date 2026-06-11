from __future__ import annotations

import argparse
import sys
from pathlib import Path


KIT_ROOT = Path(__file__).resolve().parents[1]
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from common.config import load_yaml
from runtime_module import InferenceRuntimeParams, LumoLiveConfig, SpectralRuntimeModule


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Lumo live inference from a model bundle.")
    parser.add_argument("--bundle", type=Path, required=True, help="model bundle directory")
    parser.add_argument("--camera-config", type=Path, default=KIT_ROOT / "configs" / "camera.fx17e.example.yaml")
    parser.add_argument("--app-config", type=Path, default=KIT_ROOT / "configs" / "app.example.yaml")
    parser.add_argument("--output-root", type=Path, help="runtime output directory")
    parser.add_argument("--session-id", type=str, default="lumo-live")
    parser.add_argument("--skip-bundle-verify", action="store_true")
    parser.add_argument("--band-count", type=int)
    parser.add_argument("--spatial-width", type=int)
    parser.add_argument("--integration-time-us", type=int)
    parser.add_argument("--line-rate-hz", type=float)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--lumo-serial", type=str)
    parser.add_argument("--lumo-mac", type=str)
    parser.add_argument("--lumo-ip", type=str)
    parser.add_argument("--lumo-interface", type=str)
    parser.add_argument("--lumo-device-index", type=int)
    parser.add_argument("--lumo-timeout-ms", type=int)
    parser.add_argument("--lumo-skip-scan", action="store_true")
    parser.add_argument("--queue-size", type=int, default=64)
    parser.add_argument("--frame-timeout-seconds", type=float, default=0.5)
    parser.add_argument("--max-idle-seconds", type=float, default=30.0)
    parser.add_argument("--window-size", type=int)
    parser.add_argument("--stride", type=int)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--min-area", type=int)
    parser.add_argument("--no-dashboard", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app_config = load_yaml(args.app_config) if args.app_config and args.app_config.exists() else {}
    camera_config = load_yaml(args.camera_config) if args.camera_config and args.camera_config.exists() else {}
    module = SpectralRuntimeModule.from_bundle(
        args.bundle,
        app_config=app_config,
        output_root=args.output_root,
        verify_bundle=not bool(args.skip_bundle_verify),
    )
    lumo_config = _apply_lumo_overrides(LumoLiveConfig.from_mapping(camera_config), args)
    params = _apply_runtime_overrides(module.default_params(), args)
    result = module.run_lumo_live(
        lumo_config=lumo_config,
        params=params,
        session_id=args.session_id,
        queue_size=args.queue_size,
        frame_timeout_seconds=args.frame_timeout_seconds,
        max_idle_seconds=args.max_idle_seconds,
    )
    _print_result(result)
    return result.return_code


def _apply_runtime_overrides(params: InferenceRuntimeParams, args: argparse.Namespace) -> InferenceRuntimeParams:
    updates: dict[str, object] = {}
    for name in ("window_size", "stride", "threshold", "min_area", "max_frames"):
        value = getattr(args, name)
        if value is not None:
            updates[name] = value
    if args.no_dashboard:
        updates["dashboard"] = False
    return params.with_updates(**updates) if updates else params


def _apply_lumo_overrides(config: LumoLiveConfig, args: argparse.Namespace) -> LumoLiveConfig:
    updates: dict[str, object] = {}
    mapping = {
        "band_count": "band_count",
        "spatial_width": "spatial_width",
        "integration_time_us": "integration_time_us",
        "line_rate_hz": "line_rate_hz",
        "max_frames": "max_frames",
        "lumo_serial": "serial_number",
        "lumo_mac": "mac_address",
        "lumo_ip": "ip_address",
        "lumo_interface": "interface_name",
        "lumo_device_index": "device_index",
        "lumo_timeout_ms": "timeout_ms",
    }
    for arg_name, field_name in mapping.items():
        value = getattr(args, arg_name)
        if value is not None:
            updates[field_name] = value
    if args.lumo_skip_scan:
        updates["skip_scan"] = True
    return config.with_updates(**updates) if updates else config


def _print_result(result: object) -> None:
    print(f"ok={result.ok}")
    print(f"return_code={result.return_code}")
    print(f"output_dir={result.output_dir}")
    print(f"events={result.events_path}")
    print(f"summary={result.summary_path}")
    if result.dashboard_path is not None:
        print(f"dashboard={result.dashboard_path}")
    if result.live_status is not None:
        print(f"connected={bool(result.live_status.get('connected', False))}")
        print(f"streaming={bool(result.live_status.get('streaming', False))}")
        print(f"frame_counter={int(result.live_status.get('frame_counter', 0))}")
        print(f"last_error={result.live_status.get('last_error') or ''}")


if __name__ == "__main__":
    raise SystemExit(main())
