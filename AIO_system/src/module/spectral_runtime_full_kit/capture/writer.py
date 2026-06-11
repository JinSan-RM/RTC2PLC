from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import numpy as np

from camera.base import CameraInfo, CameraSettings
from camera.cube_assembler import AssembledCube
from common.paths import ensure_directory


def write_capture_session(
    session_dir: Path,
    assembled_cube: AssembledCube,
    camera_info: CameraInfo,
    settings: CameraSettings,
    requested_settings: CameraSettings | None = None,
    preview_filename: str | None = None,
    stream_stats: dict[str, object] | None = None,
    frame_filter_summary: dict[str, object] | None = None,
    capture_metadata: dict[str, object] | None = None,
    hsi_quality: dict[str, object] | None = None,
) -> Path:
    ensure_directory(session_dir)

    np.save(session_dir / "lines.npy", assembled_cube.cube, allow_pickle=False)
    np.save(session_dir / "timestamps.npy", assembled_cube.timestamps_s, allow_pickle=False)
    created_at_utc = datetime.now(timezone.utc).isoformat()

    actual_settings = _settings_payload_for_saved_cube(settings.to_dict(), assembled_cube)
    requested_payload = requested_settings.to_dict() if requested_settings is not None else settings.to_dict()
    runtime_settings = _settings_payload_for_saved_cube(requested_payload, assembled_cube)

    capture_metadata_payload = capture_metadata or {}
    stream_stats_payload = stream_stats or {}
    frame_filter_summary_payload = frame_filter_summary or {}
    hsi_quality_payload = hsi_quality or {}

    manifest = {
        "created_at_utc": created_at_utc,
        "frame_count": assembled_cube.frame_count,
        "band_count": assembled_cube.band_count,
        "spatial_width": assembled_cube.spatial_width,
        "dtype": str(assembled_cube.cube.dtype),
        "files": {
            "lines": "lines.npy",
            "timestamps": "timestamps.npy",
            "preview": preview_filename,
        },
        "camera_info": camera_info.to_dict(),
        "settings": runtime_settings,
        "requested_settings": dict(runtime_settings),
        "actual_settings": actual_settings,
        "stream_stats": stream_stats_payload,
        "frame_filter_summary": frame_filter_summary_payload,
        "capture_metadata": capture_metadata_payload,
        "hsi_quality": hsi_quality_payload,
        "metadata_schema_version": "capture-metadata.v1",
        "metadata": _build_metadata_summary(
            session_dir=session_dir,
            created_at_utc=created_at_utc,
            assembled_cube=assembled_cube,
            camera_info=camera_info,
            settings=requested_settings or settings,
            stream_stats=stream_stats_payload,
            capture_metadata=capture_metadata_payload,
            hsi_quality=hsi_quality_payload,
        ),
    }

    manifest_path = session_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return manifest_path


def _settings_payload_for_saved_cube(
    settings: Mapping[str, object],
    assembled_cube: AssembledCube,
) -> dict[str, object]:
    payload = dict(settings)
    payload["band_count"] = int(assembled_cube.band_count)
    payload["spatial_width"] = int(assembled_cube.spatial_width)
    payload["max_frames"] = int(assembled_cube.frame_count)
    return payload


def _build_metadata_summary(
    *,
    session_dir: Path,
    created_at_utc: str,
    assembled_cube: AssembledCube,
    camera_info: CameraInfo,
    settings: CameraSettings,
    stream_stats: Mapping[str, object],
    capture_metadata: Mapping[str, object],
    hsi_quality: Mapping[str, object],
) -> dict[str, object]:
    measurement_id = str(session_dir.name)
    files_size_bytes = _safe_file_size(session_dir / "lines.npy") + _safe_file_size(
        session_dir / "timestamps.npy"
    )
    sensor_max = _safe_nested_float(hsi_quality, ("sensor_range", "max"))
    return {
        "measurement": {
            "measurement_id": measurement_id,
            "converted_to": str(capture_metadata.get("converted_to", "Absorbance")),
            "created_by": str(capture_metadata.get("created_by", "Unknown")),
            "created_at_utc": created_at_utc,
            "modified_at_utc": created_at_utc,
            "file_size_bytes": files_size_bytes,
        },
        "dimension": {
            "frames": int(assembled_cube.frame_count),
            "pixels_per_line": int(assembled_cube.spatial_width),
            "spectral_bands": int(assembled_cube.band_count),
            "resolution_mm_per_pixel": _safe_float(capture_metadata.get("resolution_mm_per_pixel")),
            "length_mm": _safe_float(capture_metadata.get("length_mm")),
        },
        "camera": {
            "dropped_frames": int(_safe_float(stream_stats.get("dropped_frames")) or 0),
            "frame_rate_hz": float(settings.line_rate_hz),
            "integration_time_us": int(settings.integration_time_us),
            "exposure_time_us": int(settings.exposure_time_us),
            "max_signal": sensor_max,
            "serial_number": str(camera_info.serial_number),
            "type": str(camera_info.provider),
            "rgb_bands": [int(band) for band in settings.rgb_bands],
            "max_saturated_band_index": _safe_nested_float(
                hsi_quality, ("saturation", "max_saturated_band_index")
            ),
            "max_saturated_band_ratio": _safe_nested_float(
                hsi_quality, ("saturation", "max_saturated_band_ratio")
            ),
        },
        "references": {
            "white_reference": capture_metadata.get("white_reference", {}),
            "dark_reference": capture_metadata.get("dark_reference", {}),
        },
        "other": {
            "project_id": str(capture_metadata.get("project_id", "")),
            "project_name": str(capture_metadata.get("project_name", "")),
            "app_version": str(capture_metadata.get("app_version", "spectral-runtime-dev")),
        },
    }


def _safe_file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_nested_float(payload: Mapping[str, object], path: tuple[str, str]) -> float | None:
    first = payload.get(path[0])
    if not isinstance(first, Mapping):
        return None
    return _safe_float(first.get(path[1]))
