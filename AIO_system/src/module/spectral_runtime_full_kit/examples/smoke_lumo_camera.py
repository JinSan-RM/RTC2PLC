from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


KIT_ROOT = Path(__file__).resolve().parents[1]
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from camera.cube_assembler import LineCubeAssembler
from camera.lumo_provider import list_native_lumo_devices
from camera.stream_worker import StreamWorker
from capture.writer import write_capture_session
from common.config import load_yaml
from common.paths import make_session_dir
from features.bands import build_pseudo_rgb_preview, save_preview_png
from runtime_module import LumoLiveConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke-test a real Specim/Lumo camera without running inference.")
    parser.add_argument("--camera-config", type=Path, default=KIT_ROOT / "configs" / "camera.fx17e.example.yaml")
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--output-root", type=Path, default=KIT_ROOT / "reports" / "camera-smoke")
    parser.add_argument("--no-save", action="store_true", help="capture into memory only")
    parser.add_argument("--list-devices", action="store_true", help="scan native Lumo devices and exit")
    parser.add_argument("--band-count", type=int)
    parser.add_argument("--spatial-width", type=int)
    parser.add_argument("--integration-time-us", type=int)
    parser.add_argument("--line-rate-hz", type=float)
    parser.add_argument("--lumo-serial", type=str)
    parser.add_argument("--lumo-mac", type=str)
    parser.add_argument("--lumo-ip", type=str)
    parser.add_argument("--lumo-interface", type=str)
    parser.add_argument("--lumo-device-index", type=int)
    parser.add_argument("--lumo-timeout-ms", type=int)
    scan_group = parser.add_mutually_exclusive_group()
    scan_group.add_argument("--lumo-skip-scan", action="store_true", help="force direct-open by configured device index")
    scan_group.add_argument("--no-lumo-skip-scan", action="store_true", help="force native device scan before opening")
    parser.add_argument("--queue-size", type=int, default=64)
    parser.add_argument("--frame-timeout-seconds", type=float, default=0.5)
    parser.add_argument("--max-idle-seconds", type=float, default=30.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_devices:
        devices = list_native_lumo_devices()
        print("devices=" + json.dumps(devices, ensure_ascii=False))
        return 0

    camera_config = load_yaml(args.camera_config) if args.camera_config and args.camera_config.exists() else {}
    lumo_config = _apply_lumo_overrides(LumoLiveConfig.from_mapping(camera_config), args)
    settings = lumo_config.build_settings(max_frames=int(args.frames))
    provider = lumo_config.build_provider()

    source = provider.open(settings)
    try:
        print("camera_info=" + json.dumps(source.camera_info.to_dict(), ensure_ascii=False))
        status = _read_status(source)
        if status:
            print("open_status=" + json.dumps(status, ensure_ascii=False))

        worker = StreamWorker(source, queue_maxsize=max(1, int(args.queue_size)), close_source_on_stop=False)
        assembler = LineCubeAssembler()
        worker.start(max_frames=int(args.frames))
        for frame in worker.iter_frames(
            timeout_s=float(args.frame_timeout_seconds),
            max_idle_seconds=float(args.max_idle_seconds),
        ):
            assembler.append(frame)
        worker.wait()
        if worker.stats.error:
            raise RuntimeError(worker.stats.error)
        cube = assembler.build()

        final_status = _read_status(source)
        summary = {
            "frame_count": int(cube.frame_count),
            "band_count": int(cube.band_count),
            "spatial_width": int(cube.spatial_width),
            "settings": source.settings.to_dict(),
            "stream_stats": worker.stats.to_dict(),
            "status": final_status,
        }
        print("capture=" + json.dumps(summary, ensure_ascii=False))

        if args.no_save:
            return 0

        session_dir = make_session_dir(Path(args.output_root), "lumo-camera-smoke")
        preview_path = session_dir / "preview.png"
        preview = build_pseudo_rgb_preview(cube.cube, source.settings.rgb_bands)
        save_preview_png(preview, preview_path)
        manifest_path = write_capture_session(
            session_dir=session_dir,
            assembled_cube=cube,
            camera_info=source.camera_info,
            settings=source.settings,
            requested_settings=settings,
            preview_filename=preview_path.name,
            stream_stats=worker.stats.to_dict(),
            capture_metadata={"project_id": "portable-full-kit", "source": "smoke_lumo_camera.py"},
        )
        print(f"session_dir={session_dir}")
        print(f"manifest={manifest_path}")
        print(f"preview={preview_path}")
        return 0
    finally:
        source.close()


def _apply_lumo_overrides(config: LumoLiveConfig, args: argparse.Namespace) -> LumoLiveConfig:
    updates: dict[str, object] = {}
    mapping = {
        "band_count": "band_count",
        "spatial_width": "spatial_width",
        "integration_time_us": "integration_time_us",
        "line_rate_hz": "line_rate_hz",
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
    if args.no_lumo_skip_scan:
        updates["skip_scan"] = False
    return config.with_updates(**updates) if updates else config


def _read_status(source: object) -> dict[str, object]:
    getter = getattr(source, "get_status", None)
    if not callable(getter):
        return {}
    payload = getter()
    return dict(payload) if isinstance(payload, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
