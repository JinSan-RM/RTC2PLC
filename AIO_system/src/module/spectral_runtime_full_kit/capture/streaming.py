from __future__ import annotations

import sys
import time
from dataclasses import dataclass, replace
from typing import Callable

from camera.base import CameraInfo, CameraProvider, CameraSettings, FrameSource
from camera.cube_assembler import AssembledCube, LineCubeAssembler
from camera.frame_filter import BasicFrameFilter, FrameFilterStats
from camera.stream_worker import StreamStats, StreamWorker
from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class StreamCaptureResult:
    assembled_cube: AssembledCube
    camera_info: CameraInfo
    settings: CameraSettings
    stream_stats: StreamStats
    frame_filter_stats: FrameFilterStats
    open_duration_s: float


def capture_stream_session(
    *,
    provider: CameraProvider,
    provider_name: str,
    settings: CameraSettings,
    frames: int,
    dark_mean_threshold: float | None = 1.0,
    queue_size: int = 64,
    progress_every: int = 25,
    progress_message: str = "captured %s frames",
    frame_timeout_s: float = 0.5,
    max_idle_seconds: float | None = None,
    source_configurer: Callable[[FrameSource], None] | None = None,
    source_finalizer: Callable[[FrameSource], None] | None = None,
    progress_callback: Callable[[int, FrameSource, StreamStats], None] | None = None,
    discard_initial_frames: int = 0,
) -> StreamCaptureResult:
    LOGGER.info("Camera lifecycle step1: open")
    open_start = time.monotonic()
    source = provider.open(None if provider_name == "replay" else settings)
    open_duration_s = time.monotonic() - open_start
    LOGGER.info("Camera lifecycle step2: open completed in %.2fs", open_duration_s)

    worker: StreamWorker | None = None
    assembler = LineCubeAssembler()
    capture_settings = source.settings
    frame_filter = BasicFrameFilter(
        expected_shape=(source.settings.band_count, source.settings.spatial_width),
        dark_mean_threshold=dark_mean_threshold,
    )
    try:
        if source_configurer is not None:
            source_configurer(source)
            capture_settings = source.settings
            frame_filter.expected_shape = (source.settings.band_count, source.settings.spatial_width)

        worker = StreamWorker(source, queue_maxsize=queue_size)
        LOGGER.info("Camera lifecycle step3: start")
        discard_remaining = max(0, int(discard_initial_frames))
        worker.start(max_frames=frames + discard_remaining)
        for frame in _iter_worker_frames(
            worker,
            timeout_s=frame_timeout_s,
            max_idle_seconds=max_idle_seconds,
        ):
            if discard_remaining > 0:
                discard_remaining -= 1
                continue
            if assembler.frame_count == 0:
                capture_settings = _sync_settings_to_frame_shape(
                    settings=capture_settings,
                    frame_shape=frame.data.shape,
                    frame_filter=frame_filter,
                    allow_full_shape_override=(provider_name == "lumo"),
                )
            filtered_frame = frame_filter.accept(frame)
            if filtered_frame is None:
                continue
            assembler.append(filtered_frame)
            if progress_every > 0 and assembler.frame_count % progress_every == 0:
                LOGGER.info(progress_message, assembler.frame_count)
                if progress_callback is not None:
                    try:
                        progress_callback(assembler.frame_count, source, worker.stats)
                    except Exception as exc:  # noqa: BLE001
                        LOGGER.warning("Progress callback failed: %s", exc)

        LOGGER.info("Camera lifecycle step4: stream completed")
        if (
            progress_callback is not None
            and assembler.frame_count > 0
            and (progress_every <= 0 or assembler.frame_count % progress_every != 0)
        ):
            try:
                progress_callback(assembler.frame_count, source, worker.stats)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Progress callback failed: %s", exc)
        worker.wait()
        if worker.stats.error is not None:
            raise RuntimeError(worker.stats.error)
        if assembler.frame_count == 0:
            raise RuntimeError("No frames were captured.")
        if frame_filter.stats.rejected_frames > 0:
            LOGGER.warning(
                "Frame filter rejected %s frame(s): %s",
                frame_filter.stats.rejected_frames,
                frame_filter.stats.to_dict(),
            )

        assembled_cube = assembler.build()
        return StreamCaptureResult(
            assembled_cube=assembled_cube,
            camera_info=source.camera_info,
            settings=capture_settings,
            stream_stats=worker.stats,
            frame_filter_stats=frame_filter.stats,
            open_duration_s=open_duration_s,
        )
    finally:
        LOGGER.info("Camera lifecycle step5: stop/close")
        finalizer_error: Exception | None = None
        if source_finalizer is not None:
            try:
                source_finalizer(source)
            except Exception as exc:  # noqa: BLE001
                finalizer_error = exc
                LOGGER.warning("Source finalizer failed: %s", exc)
        if worker is not None:
            worker.stop()
        else:
            source.close()
        if finalizer_error is not None and sys.exc_info()[0] is None:
            raise finalizer_error


def _iter_worker_frames(
    worker: StreamWorker,
    *,
    timeout_s: float,
    max_idle_seconds: float | None,
):
    if max_idle_seconds is None:
        yield from worker.iter_frames(timeout_s=timeout_s)
        return

    try:
        yield from worker.iter_frames(timeout_s=timeout_s, max_idle_seconds=max_idle_seconds)
        return
    except TypeError as exc:
        if "max_idle_seconds" not in str(exc):
            raise

    yield from worker.iter_frames(timeout_s=timeout_s)


def _sync_settings_to_frame_shape(
    *,
    settings: CameraSettings,
    frame_shape: tuple[int, ...],
    frame_filter: BasicFrameFilter,
    allow_full_shape_override: bool = False,
) -> CameraSettings:
    if len(frame_shape) != 2:
        return settings

    band_count, spatial_width = int(frame_shape[0]), int(frame_shape[1])
    if allow_full_shape_override and (
        band_count != int(settings.band_count) or spatial_width != int(settings.spatial_width)
    ):
        LOGGER.warning(
            "Camera frame shape resolved from first frame: configured=(bands=%s, width=%s) "
            "actual=(bands=%s, width=%s). Using actual frame shape for this capture session.",
            settings.band_count,
            settings.spatial_width,
            band_count,
            spatial_width,
        )
        max_band_index = max(0, band_count - 1)
        rgb_bands = tuple(min(max(0, int(band)), max_band_index) for band in settings.rgb_bands)
        resolved = replace(
            settings,
            band_count=band_count,
            spatial_width=spatial_width,
            rgb_bands=rgb_bands,
        )
        frame_filter.expected_shape = (resolved.band_count, resolved.spatial_width)
        return resolved

    if band_count != int(settings.band_count):
        return settings
    if spatial_width == int(settings.spatial_width):
        return settings
    if spatial_width < int(settings.spatial_width):
        return settings

    LOGGER.warning(
        "Camera spatial width resolved from first frame: configured=%s actual=%s. "
        "Using actual frame width for this capture session.",
        settings.spatial_width,
        spatial_width,
    )
    resolved = replace(settings, spatial_width=spatial_width)
    frame_filter.expected_shape = (resolved.band_count, resolved.spatial_width)
    return resolved
