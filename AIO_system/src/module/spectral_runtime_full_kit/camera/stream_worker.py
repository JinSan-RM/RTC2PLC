from __future__ import annotations

import queue
import threading
import time
from dataclasses import asdict, dataclass

from camera.base import FrameSource, LineFrame

@dataclass(slots=True)
class StreamStats:
    produced_frames: int = 0
    dropped_frames: int = 0
    finished: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class StreamWorker:
    def __init__(
        self,
        source: FrameSource,
        queue_maxsize: int = 64,
        *,
        close_source_on_stop: bool = True,
    ) -> None:
        self._source = source
        self._queue: queue.Queue[LineFrame] = queue.Queue(maxsize=queue_maxsize)
        self._stats = StreamStats()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._close_source_on_stop = bool(close_source_on_stop)

    @property
    def stats(self) -> StreamStats:
        return self._stats

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, max_frames: int | None = None) -> None:
        if self._thread is not None:
            raise RuntimeError("StreamWorker.start() can only be called once.")

        self._thread = threading.Thread(
            target=self._run,
            kwargs={"max_frames": max_frames},
            name="stream-worker",
            daemon=True,
        )
        self._thread.start()

    def iter_frames(self, timeout_s: float = 0.5, max_idle_seconds: float | None = None):
        frame_deadline = time.monotonic() + max_idle_seconds if max_idle_seconds else None

        while True:
            try:
                item = self._queue.get(timeout=timeout_s)
            except queue.Empty:
                if self._stats.finished:
                    break
                if frame_deadline is not None and time.monotonic() > frame_deadline:
                    raise TimeoutError("No frames have arrived within the configured idle timeout.")
                continue

            if frame_deadline is not None:
                frame_deadline = time.monotonic() + max_idle_seconds
            yield item

    def pop_frame(self, timeout_s: float = 0.5) -> LineFrame | None:
        try:
            return self._queue.get(timeout=timeout_s)
        except queue.Empty:
            return None

    def wait(self, timeout_s: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)

    def stop(self, timeout_s: float | None = None, *, close_source: bool | None = None) -> None:
        self._stop_event.set()
        should_close_source = self._close_source_on_stop if close_source is None else bool(close_source)
        if should_close_source:
            self._source.close()
        self.wait(timeout_s)

    def _run(self, max_frames: int | None) -> None:
        try:
            for frame in self._source.frames(max_frames=max_frames):
                if self._stop_event.is_set():
                    break

                if getattr(self._source.settings, "mirror_line", False):
                    frame = LineFrame(
                        index=frame.index,
                        timestamp_monotonic_s=frame.timestamp_monotonic_s,
                        data=frame.data[:, ::-1].copy(),
                    )

                try:
                    self._queue.put(frame, timeout=0.1)
                except queue.Full:
                    self._stats.dropped_frames += 1
                    continue

                self._stats.produced_frames += 1
        except Exception as exc:
            self._stats.error = f"{exc.__class__.__name__}: {exc}"
        finally:
            self._stats.finished = True
