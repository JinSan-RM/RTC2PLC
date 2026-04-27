import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from src.AI.AI_manager import DetectedObject
from src.utils.config_util import (
    PLASTIC_VALUE_MAPPING_SMALL,
    PLASTIC_VALUE_MAPPING_LARGE,
)
from src.utils.logger import log


@dataclass
class MaterialInfo:
    classification: str
    size: str
    timestamp: float


@dataclass
class DetectLineInfo:
    line_id: int
    x: int
    y: int
    width: int
    height: int


@dataclass
class LocalTrack:
    track_id: int
    center_x: float
    center_y: float
    last_seen: float
    crossed: bool = False


class MaterialEventBuffer:
    """Material event buffer kept for time/position based matching."""

    def __init__(self):
        self.buffer = deque()

    def add(self, material: MaterialInfo, x: int):
        self.buffer.append({
            "material": material,
            "x": x,
            "timestamp": material.timestamp,
        })

    def pop_closest(self, line_x: int, max_age_sec=0.2, distance_threshold=80):
        now = time.time()

        candidates = [
            item for item in self.buffer
            if (now - item["timestamp"]) <= max_age_sec
        ]
        if not candidates:
            return None

        candidates = [
            item for item in candidates
            if abs(item["x"] - line_x) < distance_threshold
        ]
        if not candidates:
            return None

        closest = min(candidates, key=lambda item: abs(item["x"] - line_x))
        self.buffer.remove(closest)
        return closest["material"]

    def remove_old(self, max_age_sec=2.0):
        now = time.time()
        while self.buffer:
            oldest = self.buffer[0]
            if (now - oldest["timestamp"]) > max_age_sec:
                dropped = self.buffer.popleft()
                log(f"[BUFFER] drop old: {dropped['material'].classification}")
            else:
                break

    def get_plc_value(self, material: MaterialInfo) -> int | None:
        if material.size == "small":
            return PLASTIC_VALUE_MAPPING_SMALL.get(material.classification)
        if material.size == "large":
            return PLASTIC_VALUE_MAPPING_LARGE.get(material.classification)
        return None


class LineCrossZone:
    """Line crossing detector using local centroid matching."""

    def __init__(self, line_id: int, x: int, y: int,
                 width: int, height: int,
                 on_cross_callback=None):

        self.line_id = line_id
        self.line_info = DetectLineInfo(
            line_id=line_id,
            x=x,
            y=y,
            width=width,
            height=height,
        )

        self.local_tracks: dict[int, LocalTrack] = {}
        self.next_track_id = 0
        self.track_ttl = 0.35
        self.track_match_distance = 120.0
        self.track_x_margin = 260
        self.track_y_margin = 40
        self.cooldown_sec = 0.2
        self.last_trigger_time = 0.0

        self.on_cross_callback = on_cross_callback
        self.is_active = False

    def is_crossed(self, cur_x: int, prev_x: int) -> bool:
        return cur_x <= self.line_info.x and prev_x > self.line_info.x

    def _cleanup_stale_tracks(self, now: float):
        stale_ids = [
            track_id
            for track_id, track in self.local_tracks.items()
            if now - track.last_seen > self.track_ttl
        ]
        for track_id in stale_ids:
            del self.local_tracks[track_id]

    def _is_relevant(self, obj: DetectedObject) -> bool:
        center_x, center_y = obj.center
        within_x = abs(center_x - self.line_info.x) <= self.track_x_margin
        within_y = (
            self.line_info.y - self.track_y_margin
            <= center_y
            <= self.line_info.y + self.line_info.height + self.track_y_margin
        )
        return within_x and within_y

    def _distance(self, track: LocalTrack, obj: DetectedObject) -> float:
        cur_x, cur_y = obj.center
        return float(np.hypot(track.center_x - cur_x, track.center_y - cur_y))

    def _is_vertical_relevant(self, obj: DetectedObject) -> bool:
        _, center_y = obj.center
        return (
            self.line_info.y - self.track_y_margin
            <= center_y
            <= self.line_info.y + self.line_info.height + self.track_y_margin
        )

    def _is_left_trigger_candidate(self, obj: DetectedObject) -> bool:
        if not self._is_vertical_relevant(obj):
            return False

        center_x, _ = obj.center
        return center_x <= self.line_info.x

    def _create_track(self, obj: DetectedObject, now: float):
        cur_x, cur_y = obj.center
        self.local_tracks[self.next_track_id] = LocalTrack(
            track_id=self.next_track_id,
            center_x=cur_x,
            center_y=cur_y,
            last_seen=now,
        )
        self.next_track_id += 1

    def _update_track(self, track: LocalTrack, obj: DetectedObject, now: float):
        prev_x = track.center_x
        cur_x, cur_y = obj.center

        track.center_x = cur_x
        track.center_y = cur_y
        track.last_seen = now

        if not track.crossed and self.is_crossed(cur_x, prev_x):
            track.crossed = True
            if self.on_cross_callback:
                self.on_cross_callback()
            log(
                f"[LINE] crossed line_id={self.line_info.line_id}, "
                f"track_id={track.track_id}, obj_id={obj.id}, x={cur_x}"
            )

    def update_frame(self, detected_objects: list[DetectedObject]):
        now = time.time()
        # Line mode triggers the callback directly, so box-based airknife flow
        # should stay inactive to avoid duplicate callbacks with wrong args.
        self.is_active = False
        trigger_candidates = [
            obj for obj in detected_objects
            if self._is_left_trigger_candidate(obj)
        ]
        if not trigger_candidates:
            return

        if now - self.last_trigger_time < self.cooldown_sec:
            return

        self.last_trigger_time = now
        lead_object = min(trigger_candidates, key=lambda item: item.center[0])

        if self.on_cross_callback:
            self.on_cross_callback()

    def draw(self, frame: np.ndarray) -> np.ndarray:
        color = (0, 255, 0)
        cv2.line(
            frame,
            (self.line_info.x, self.line_info.y),
            (self.line_info.x, self.line_info.y + self.line_info.height),
            color,
            self.line_info.width,
        )
        return frame

    def cleanup(self, active_ids: set):
        _ = active_ids


class LineCrossManager:
    def __init__(self, boxes: list[LineCrossZone]):
        self.boxes = boxes

    def update_detections(self, detected_objects: list[DetectedObject]):
        for box in self.boxes:
            box.update_frame(detected_objects)

    def draw_all(self, frame: np.ndarray) -> np.ndarray:
        for box in self.boxes:
            box.draw(frame)
        return frame


class LineTrigger:
    """Legacy helper kept for compatibility."""

    def __init__(self, buffer, plc_callback, line_x):
        self.buffer = buffer
        self.plc_callback = plc_callback
        self.line_x = line_x

    def on_cross_line(self, obj):
        material = self.buffer.pop_closest(self.line_x)

        if not material:
            obj_id = getattr(obj, "id", "n/a")
            log(f"matching failed (obj_id={obj_id})")
            return

        plc_value = self.buffer.get_plc_value(material)
        if plc_value is None:
            log("PLC mapping failed")
            return

        if self.plc_callback:
            self.plc_callback(plc_value)

        obj_id = getattr(obj, "id", "n/a")
        log(f"AIR: {material.classification} (obj_id={obj_id})")
