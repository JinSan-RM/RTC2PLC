from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from camera.base import LineFrame


@dataclass(slots=True)
class AssembledCube:
    cube: np.ndarray
    timestamps_s: np.ndarray
    frame_count: int
    band_count: int
    spatial_width: int


class LineCubeAssembler:
    def __init__(self) -> None:
        self._lines: list[np.ndarray] = []
        self._timestamps_s: list[float] = []

    @property
    def frame_count(self) -> int:
        return len(self._lines)

    def append(self, frame: LineFrame) -> None:
        self._lines.append(frame.data.copy())
        self._timestamps_s.append(frame.timestamp_monotonic_s)

    def build(self) -> AssembledCube:
        if not self._lines:
            raise ValueError("No frames have been appended.")

        cube = np.stack(self._lines, axis=0)
        timestamps_s = np.asarray(self._timestamps_s, dtype=np.float64)
        return AssembledCube(
            cube=cube,
            timestamps_s=timestamps_s,
            frame_count=cube.shape[0],
            band_count=cube.shape[1],
            spatial_width=cube.shape[2],
        )
