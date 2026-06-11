from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from common.paths import ensure_directory


@dataclass(slots=True)
class ReferenceBundle:
    kind: str
    mean: np.ndarray
    std: np.ndarray
    frame_count: int
    band_count: int
    spatial_width: int


def build_reference_bundle(cube: np.ndarray, kind: str) -> ReferenceBundle:
    normalized_kind = normalize_reference_kind(kind)
    validate_cube(cube)

    # 수정
    # mean = cube.astype(np.float32).mean(axis=0)
    # std = cube.astype(np.float32).std(axis=0)
    float_cube = cube.astype(np.float32)
    mean = np.mean(float_cube, axis=0)
    std = np.std(float_cube, axis=0)
    
    return ReferenceBundle(
        kind=normalized_kind,
        mean=np.ascontiguousarray(mean),
        std=np.ascontiguousarray(std),
        frame_count=int(cube.shape[0]),
        band_count=int(cube.shape[1]),
        spatial_width=int(cube.shape[2]),
    )


def save_reference_bundle(
    output_dir: Path,
    bundle: ReferenceBundle,
    *,
    camera_info: Mapping[str, Any],
    settings: Mapping[str, Any],
    requested_settings: Mapping[str, Any] | None = None,
    source_provider: str,
    source_session: str | None,
    preview_filename: str | None = None,
    stream_stats: Mapping[str, Any] | None = None,
    qc: Mapping[str, Any] | None = None,
    extra_files: Mapping[str, str | None] | None = None,
) -> Path:
    ensure_directory(output_dir)

    np.save(output_dir / "mean.npy", bundle.mean, allow_pickle=False)
    np.save(output_dir / "std.npy", bundle.std, allow_pickle=False)

    files: dict[str, str | None] = {
        "mean": "mean.npy",
        "std": "std.npy",
        "preview": preview_filename,
    }
    if extra_files is not None:
        files.update(dict(extra_files))

    actual_settings = dict(settings)
    canonical_settings = dict(requested_settings) if requested_settings is not None else dict(settings)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "kind": bundle.kind,
        "frame_count": bundle.frame_count,
        "band_count": bundle.band_count,
        "spatial_width": bundle.spatial_width,
        "dtype": str(bundle.mean.dtype),
        "files": files,
        "source": {
            "provider": source_provider,
            "session": source_session,
        },
        "camera_info": dict(camera_info),
        "settings": canonical_settings,
        "requested_settings": dict(canonical_settings),
        "actual_settings": actual_settings,
        "stream_stats": dict(stream_stats or {}),
        "qc": dict(qc or {}),
    }

    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return manifest_path


def load_reference_bundle(reference_dir: Path) -> tuple[ReferenceBundle, dict[str, Any]]:
    manifest_path = reference_dir / "manifest.json"
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError(f"Invalid manifest payload in {manifest_path}")

    files = manifest.get("files", {})
    if not isinstance(files, dict):
        raise ValueError(f"Invalid files mapping in {manifest_path}")
    mean_path = reference_dir / str(files.get("mean", "mean.npy"))
    std_path = reference_dir / str(files.get("std", "std.npy"))

    mean = np.load(mean_path, allow_pickle=False)
    std = np.load(std_path, allow_pickle=False)
    validate_reference_plane(mean, "mean")
    validate_reference_plane(std, "std")

    bundle = ReferenceBundle(
        kind=normalize_reference_kind(str(manifest.get("kind", ""))),
        mean=np.ascontiguousarray(mean.astype(np.float32, copy=False)),
        std=np.ascontiguousarray(std.astype(np.float32, copy=False)),
        frame_count=int(manifest.get("frame_count", 0)),
        band_count=int(manifest.get("band_count", mean.shape[0])),
        spatial_width=int(manifest.get("spatial_width", mean.shape[1])),
    )
    return bundle, manifest


def make_reference_dir(output_root: Path, *, kind: str, provider: str) -> Path:
    ensure_directory(output_root)
    normalized_kind = normalize_reference_kind(kind)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reference_dir = output_root / f"{timestamp}-{normalized_kind}-{provider}"
    suffix = 1
    while reference_dir.exists():
        reference_dir = output_root / f"{timestamp}-{normalized_kind}-{provider}-{suffix:02d}"
        suffix += 1
    reference_dir.mkdir(parents=True, exist_ok=False)
    return reference_dir


def normalize_reference_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized not in {"dark", "white"}:
        raise ValueError("Reference kind must be 'dark' or 'white'.")
    return normalized


def validate_cube(cube: np.ndarray) -> None:
    if cube.ndim != 3:
        raise ValueError("Expected cube with shape (frame_count, band_count, spatial_width).")
    if cube.shape[0] <= 0 or cube.shape[1] <= 0 or cube.shape[2] <= 0:
        raise ValueError(f"Cube dimensions must be positive, got shape={cube.shape!r}.")


def validate_reference_plane(reference_plane: np.ndarray, name: str) -> None:
    if reference_plane.ndim != 2:
        raise ValueError(f"{name} reference must be 2D (band_count, spatial_width).")
    if reference_plane.shape[0] <= 0 or reference_plane.shape[1] <= 0:
        raise ValueError(f"{name} reference must have positive dimensions.")


def reference_bundle_to_dict(bundle: ReferenceBundle) -> dict[str, Any]:
    payload = asdict(bundle)
    payload["mean"] = bundle.mean.tolist()
    payload["std"] = bundle.std.tolist()
    return payload
