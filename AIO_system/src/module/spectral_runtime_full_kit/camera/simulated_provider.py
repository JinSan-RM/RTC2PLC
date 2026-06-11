from __future__ import annotations

import math

import numpy as np

from camera.base import CameraInfo, CameraProvider, CameraSettings, FrameSource, LineFrame


class SimulatedFrameSource(FrameSource):
    def __init__(self, settings: CameraSettings, seed: int, scene: str = "normal") -> None:
        if scene not in {"normal", "dark", "white"}:
            raise ValueError(f"Unsupported simulated scene: {scene}")
        self._settings = settings
        self._scene = scene
        self._camera_info = CameraInfo(
            provider="simulate",
            model="FX17e-sim",
            serial_number=f"SIM-{seed:04d}",
            transport="in-process",
            firmware_version=f"week1-{scene}",
        )
        self._closed = False
        self._rng = np.random.default_rng(seed)
        self._spectral_axis = np.linspace(0.0, 1.0, settings.band_count, dtype=np.float32)[:, None]
        self._spatial_axis = np.linspace(-1.0, 1.0, settings.spatial_width, dtype=np.float32)[None, :]

    @property
    def camera_info(self) -> CameraInfo:
        return self._camera_info

    @property
    def settings(self) -> CameraSettings:
        return self._settings

    def frames(self, max_frames: int | None = None):
        total_frames = max_frames or self._settings.max_frames or 100
        for index in range(total_frames):
            if self._closed:
                break

            yield LineFrame(
                index=index,
                timestamp_monotonic_s=index / self._settings.line_rate_hz,
                data=self._make_line(index),
            )

    def close(self) -> None:
        self._closed = True

    def _make_line(self, index: int) -> np.ndarray:
        line = self._base_signal(index)
        for spectral_peak, amplitude, sigma_band, sigma_x, phase in (
            (0.22, 0.60, 0.06, 0.12, 0.0),
            (0.57, 0.85, 0.08, 0.10, 1.7),
            (0.81, 0.40, 0.05, 0.18, 3.4),
        ):
            center_x = 0.65 * math.sin((index / 18.0) + phase)
            spatial_profile = np.exp(-0.5 * ((self._spatial_axis - center_x) / sigma_x) ** 2)
            spectral_profile = np.exp(-0.5 * ((self._spectral_axis - spectral_peak) / sigma_band) ** 2)
            line += amplitude * spectral_profile * spatial_profile

        noise = self._rng.normal(loc=0.0, scale=0.01, size=line.shape)
        line = np.clip(line + noise, 0.0, 1.0)
        line = self._apply_scene_profile(line)
        return np.round(line * 4095.0).astype(np.uint16)

    def _base_signal(self, index: int) -> np.ndarray:
        spectral = 0.08 + 0.04 * np.sin((self._spectral_axis * math.pi * 6.0) + (index / 20.0))
        spatial = 0.02 * np.cos((self._spatial_axis * math.pi * 3.0) - (index / 25.0))
        return spectral + spatial + 0.08

    def _apply_scene_profile(self, line: np.ndarray) -> np.ndarray:
        if self._scene == "dark":
            return np.clip(line * 0.15, 0.0, 1.0)
        if self._scene == "white":
            return np.clip((line * 0.70) + 0.25, 0.0, 1.0)
        return line


class SimulatedCameraProvider(CameraProvider):
    def __init__(self, seed: int = 7, scene: str = "normal") -> None:
        if scene not in {"normal", "dark", "white"}:
            raise ValueError(f"Unsupported simulated scene: {scene}")
        self._seed = seed
        self._scene = scene

    def open(self, settings: CameraSettings | None = None) -> FrameSource:
        return SimulatedFrameSource(settings or CameraSettings(), seed=self._seed, scene=self._scene)
