from __future__ import annotations

from dataclasses import asdict, dataclass, field

from camera.base import LineFrame
from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class FrameFilterStats:   # drop한 프레임 결과를 저장
    rejected_frames: int = 0
    shape_mismatch_frames: int = 0
    dark_frames: int = 0
    max_consecutive_rejected_frames: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(slots=True)
class BasicFrameFilter:
    expected_shape: tuple[int, int]
    dark_mean_threshold: float | None = None
    stats: FrameFilterStats = field(default_factory=FrameFilterStats)
    _consecutive_rejected_frames: int = field(default=0, init=False, repr=False)

    def _register_rejection(self) -> None:
        self.stats.rejected_frames += 1
        self._consecutive_rejected_frames += 1
        self.stats.max_consecutive_rejected_frames = max(
            self.stats.max_consecutive_rejected_frames,
            self._consecutive_rejected_frames,
        )

    def accept(self, frame: LineFrame) -> LineFrame | None:   # 실제 프레임 필터링 함수
        """Stage-2 filter: reject shape mismatch and overly dark frames."""
        if frame.data.shape != self.expected_shape:   # 기준 mismatch면 reject하고, 카운트 증가
            self._register_rejection()
            self.stats.shape_mismatch_frames += 1
            LOGGER.warning(
                "Dropped frame index=%s due to shape mismatch: got=%s expected=%s",
                frame.index,
                frame.data.shape,
                self.expected_shape,
            )
            return None

        if self.dark_mean_threshold is not None:
            mean_value = float(frame.data.mean())
            if mean_value < self.dark_mean_threshold:
                self._register_rejection()
                self.stats.dark_frames += 1
                LOGGER.warning(
                    "Dropped frame index=%s due to dark mean: mean=%.3f threshold=%.3f",
                    frame.index,
                    mean_value,
                    self.dark_mean_threshold,
                )
                return None

        self._consecutive_rejected_frames = 0
        return frame
