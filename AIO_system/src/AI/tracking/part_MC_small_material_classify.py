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
    """ 재질 정보 """
    classification: str # 재질 종류 (PP, HDPE, PS, PET 등)
    size: str
    timestamp: float


@dataclass
class DetectLineInfo:
    """ 감지 선 정보 """
    line_id: int
    x: int
    y: int
    width: int
    height: int


class MaterialEventBuffer:
    """ 재질 이벤트 버퍼 (선 통과를 기준으로) """

    def __init__(self):
        self.buffer = deque()

    def add(self, material: MaterialInfo):
        """재질 추가"""
        self.buffer.append(material)

    def pop(self) -> MaterialInfo | None:
        """선 통과 시 하나 꺼냄"""
        if self.buffer:
            return self.buffer.popleft()
        return None

    def remove_old(self, max_age_sec=2.0):
        """오래된 데이터 제거"""
        now = time.time()

        while self.buffer:
            if (now - self.buffer[0].timestamp) > max_age_sec:
                old = self.buffer.popleft()
                log(f"[BUFFER] drop old: {old.classification}")
            else:
                break

    def get_plc_value(self, material: MaterialInfo) -> int | None:
        """ 재질과 크기에 따른 PLC 값 반환 """
        if material.size == "small":
            return PLASTIC_VALUE_MAPPING_SMALL.get(material.classification)
        elif material.size == "large":
            return PLASTIC_VALUE_MAPPING_LARGE.get(material.classification)
        return None


class LineCrossZone:
    """기준 선 통과 감지 영역"""
    def __init__(self, line_id: int, x: int, y: int,
                 width: int, height: int,
                 on_cross_callback=None):

        self.line_id = line_id
        self.line_info = DetectLineInfo(
            line_id=line_id,
            x=x,
            y=y,
            width=width,
            height=height
        )

        self.prev_positions: dict[int, int] = {}
        self.tracked_objects = set()
        self.crossed_objects = set()
        self.tracked_objects_info: dict[int, DetectedObject] = {}

        self.on_cross_callback = on_cross_callback

        self.is_active = False

    def is_crossed(self, cur_x: int, prev_x: int) -> bool:
        return cur_x <= self.line_info.x and prev_x > self.line_info.x

    def update(self, obj: DetectedObject):
        """감지 업데이트"""
        obj_id = obj.id
        current_x = obj.center[0]
        prev_x = self.prev_positions.get(obj_id)

        # 이전 위치 저장
        self.prev_positions[obj_id] = current_x

        # 처음 들어온 객체는 비교 불가
        if prev_x is None:
            return False

        crossed = self.is_crossed(current_x, prev_x)

        if crossed and obj_id not in self.crossed_objects:
            self.crossed_objects.add(obj_id)

            log(f"[LINE] object {obj_id} crossed line")

            if self.on_cross_callback:
                self.on_cross_callback()

            return True

        return False
    
    def draw(self, frame: np.ndarray) -> np.ndarray:
        """선 그리기"""
        color = (0, 255, 0)
        cv2.line(
            frame,
            (self.line_info.x, self.line_info.y),
            (self.line_info.x, self.line_info.y + self.line_info.height),
            color,
            self.line_info.width
        )
        return frame

    def cleanup(self, active_ids: set):
        """프레임에서 사라진 객체 정리"""
        self.prev_positions = {
            obj_id: y for obj_id, y in self.prev_positions.items()
            if obj_id in active_ids
        }

        self.crossed_objects &= active_ids


class LineCrossManager:
    """선 통과 감지 관리"""
    def __init__(self, boxes: list[LineCrossZone]):
        self.boxes = boxes

    def update_detections(self, detected_objects: list[DetectedObject]):
        """모든 박스에 대해 감지 업데이트"""
        # 조기 리턴으로 불필요한 연산 제거
        if not detected_objects:
            for box in self.boxes:
                box.tracked_objects.clear()
                box.tracked_objects_info.clear()
            return

        current_ids = {obj.id for obj in detected_objects}

        # 새로운 객체들 업데이트
        for obj in detected_objects:
            for box in self.boxes:
                box.update(obj)

        # 각 박스에서 사라진 객체 제거
        for box in self.boxes:
            # 현재 프레임에 없는 ID는 tracked_objects에서 제거
            # box.tracked_objects = box.tracked_objects & current_ids
            box.tracked_objects &= current_ids
            box.tracked_objects_info = {
                k: v for k, v in box.tracked_objects_info.items()
                if k in current_ids
            }

    def draw_all(self, frame: np.ndarray) -> np.ndarray:
        """모든 박스 그리기"""
        for box in self.boxes:
            box.draw(frame)
        return frame


class LineTrigger:
    """선 통과 감지 시 버퍼에서 재질 정보 꺼내서 PLC 신호 전송"""
    def __init__(self, buffer: MaterialEventBuffer, plc_callback):
        self.buffer = buffer
        self.plc_callback = plc_callback

    def on_cross_line(self, obj):
        """ 선 통과 시 신호 처리 """

        self.buffer.remove_old()

        material = self.buffer.pop()

        if not material:
            log("매칭 재질 없음")
            return

        plc_value = self.buffer.get_plc_value(material)

        if plc_value is None:
            log("PLC 매핑 실패")
            return

        if self.plc_callback:   # PLC 신호 전송
            self.plc_callback(plc_value)

        log(f"AIR: {material.classification} (obj_id={obj.id})")
