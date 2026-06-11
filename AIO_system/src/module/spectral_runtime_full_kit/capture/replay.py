from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import numpy as np

from camera.base import (
    CameraInfo,
    CameraProvider,
    CameraSettings,
    FrameSource,
    LineFrame,
    camera_info_from_mapping,
    camera_settings_from_mapping,
)


class ReplayFrameSource(FrameSource):
    def __init__(self, session_dir: Path) -> None:
        self._session_dir = session_dir
        self._manifest = load_manifest(session_dir)
        lines_path = session_dir / self._manifest["files"]["lines"]
        timestamps_path = session_dir / self._manifest["files"]["timestamps"]
        self._cube = np.load(lines_path, allow_pickle=False)
        self._timestamps_s = np.load(timestamps_path, allow_pickle=False)
        self._settings = _resolve_replay_settings(self._manifest, self._cube)
        self._camera_info = camera_info_from_mapping(self._manifest["camera_info"])
        self._closed = False

    @property
    def camera_info(self) -> CameraInfo:
        return self._camera_info

    @property
    def settings(self) -> CameraSettings:
        return self._settings

    def frames(self, max_frames: int | None = None):
        total_frames = self._cube.shape[0]
        if max_frames is not None:
            total_frames = min(total_frames, max_frames)

        for index in range(total_frames):
            if self._closed:
                break
            yield LineFrame(
                index=index,
                timestamp_monotonic_s=float(self._timestamps_s[index]),
                data=self._cube[index],
            )

    def close(self) -> None:
        self._closed = True


class ReplayCameraProvider(CameraProvider):
    def __init__(self, session_dir: Path) -> None:
        self._session_dir = session_dir

    def open(self, settings: CameraSettings | None = None) -> FrameSource:
        return ReplayFrameSource(self._session_dir)


def load_manifest(session_dir: Path) -> dict[str, Any]:
    manifest_path = session_dir / "manifest.json"
    with manifest_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid manifest payload in {manifest_path}")
    return payload


def _resolve_replay_settings(manifest: dict[str, Any], cube: np.ndarray) -> CameraSettings:
    raw_settings = manifest.get("settings", {})
    if not isinstance(raw_settings, dict):
        raw_settings = {}

    settings = camera_settings_from_mapping(raw_settings)
    if cube.ndim != 3:
        return settings

    frame_count, band_count, spatial_width = cube.shape
    if settings.band_count == band_count and settings.spatial_width == spatial_width:
        return settings

    # manifest 설정이 낡은 경우를 위해 실제 저장 cube shape로 보정하게 함.
    return replace(
        settings,
        band_count=int(band_count),
        spatial_width=int(spatial_width),
        max_frames=int(frame_count),
    )
