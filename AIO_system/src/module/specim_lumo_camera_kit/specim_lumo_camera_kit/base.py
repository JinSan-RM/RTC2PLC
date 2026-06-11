from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Iterator, Mapping

import numpy as np


@dataclass(slots=True)
class CameraSettings:
    band_count: int = 224
    spatial_width: int = 640
    integration_time_us: int = 4000
    line_rate_hz: float = 100.0
    max_frames: int | None = None
    rgb_bands: tuple[int, int, int] = (32, 96, 160)
    mirror_line: bool = False

    def __post_init__(self) -> None:
        self.rgb_bands = tuple(int(band) for band in self.rgb_bands)
        if len(self.rgb_bands) != 3:
            raise ValueError("rgb_bands must contain exactly three band indices")

    @property
    def exposure_time_us(self) -> int:
        return int(self.integration_time_us)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rgb_bands"] = list(self.rgb_bands)
        payload["exposure_time_us"] = int(self.integration_time_us)
        return payload


@dataclass(slots=True)
class CameraInfo:
    provider: str
    model: str
    serial_number: str
    transport: str
    firmware_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LineFrame:
    index: int
    timestamp_monotonic_s: float
    data: np.ndarray

    def copy(self) -> "LineFrame":
        return LineFrame(
            index=self.index,
            timestamp_monotonic_s=self.timestamp_monotonic_s,
            data=self.data.copy(),
        )


class FrameSource(ABC):
    @property
    @abstractmethod
    def camera_info(self) -> CameraInfo:
        raise NotImplementedError

    @property
    @abstractmethod
    def settings(self) -> CameraSettings:
        raise NotImplementedError

    @abstractmethod
    def frames(self, max_frames: int | None = None) -> Iterator[LineFrame]:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class CameraProvider(ABC):
    @abstractmethod
    def open(self, settings: CameraSettings | None = None) -> FrameSource:
        raise NotImplementedError


def camera_settings_from_mapping(data: Mapping[str, Any]) -> CameraSettings:
    payload = dict(data)
    if "integration_time_us" not in payload and "exposure_time_us" in payload:
        payload["integration_time_us"] = payload["exposure_time_us"]
    payload.pop("exposure_time_us", None)
    if "rgb_bands" in payload:
        payload["rgb_bands"] = tuple(int(band) for band in payload["rgb_bands"])
    return CameraSettings(**payload)


def camera_info_from_mapping(data: Mapping[str, Any]) -> CameraInfo:
    return CameraInfo(**dict(data))
