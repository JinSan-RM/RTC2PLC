from __future__ import annotations

import argparse
import sys
from pathlib import Path


KIT_ROOT = Path(__file__).resolve().parents[1]
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from common.config import load_yaml
from runtime_module import InferenceRuntimeParams, SpectralRuntimeModule


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run replay inference from a model bundle.")
    parser.add_argument("--bundle", type=Path, required=True, help="model bundle directory")
    parser.add_argument("--session", type=Path, required=True, help="capture/replay session directory")
    parser.add_argument("--app-config", type=Path, default=KIT_ROOT / "configs" / "app.example.yaml")
    parser.add_argument("--output-root", type=Path, help="runtime output directory")
    parser.add_argument("--skip-bundle-verify", action="store_true")
    parser.add_argument("--window-size", type=int)
    parser.add_argument("--stride", type=int)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--min-area", type=int)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--no-dashboard", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app_config = load_yaml(args.app_config) if args.app_config and args.app_config.exists() else {}
    module = SpectralRuntimeModule.from_bundle(
        args.bundle,
        app_config=app_config,
        output_root=args.output_root,
        verify_bundle=not bool(args.skip_bundle_verify),
    )
    params = _apply_common_overrides(module.default_params(), args)
    result = module.run_replay(session_dir=args.session, params=params)
    _print_result(result)
    return result.return_code


def _apply_common_overrides(params: InferenceRuntimeParams, args: argparse.Namespace) -> InferenceRuntimeParams:
    updates: dict[str, object] = {}
    for name in ("window_size", "stride", "threshold", "min_area", "max_frames"):
        value = getattr(args, name)
        if value is not None:
            updates[name] = value
    if args.no_dashboard:
        updates["dashboard"] = False
    return params.with_updates(**updates) if updates else params


def _print_result(result: object) -> None:
    print(f"ok={result.ok}")
    print(f"return_code={result.return_code}")
    print(f"output_dir={result.output_dir}")
    print(f"events={result.events_path}")
    print(f"summary={result.summary_path}")
    if result.dashboard_path is not None:
        print(f"dashboard={result.dashboard_path}")
    print(f"windows={result.runtime_summary.get('window_count', 0)}")
    print(f"objects={result.runtime_summary.get('total_objects', 0)}")


if __name__ == "__main__":
    raise SystemExit(main())
