import time
from typing import Optional
from collections import deque
from dataclasses import dataclass

from typing import List, Dict
from src.AI.AI_manager import DetectedObject
from src.utils.config_util import (
    PLASTIC_VALUE_MAPPING_SMALL,
    PLASTIC_VALUE_MAPPING_LARGE,
    CLASS_MAPPING
)
from src.utils.logger import log


@dataclass
class MaterialInfo:
    """ 재질 정보 """
    classification: str # 재질 종류 (PP, HDPE, PS, PET 등)
    size: str
    timestamp: float


class MaterialEventBuffer:
    """ 재질 이벤트 버퍼 (선 통과를 기준으로) """

    def __init__(self):
        self.buffer = deque()

    def add(self, material: MaterialInfo):
        """재질 추가"""
        self.buffer.append(material)

    def pop(self) -> Optional[MaterialInfo]:
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

    def get_plc_value(self, material: MaterialInfo) -> Optional[int]:
        """ 재질과 크기에 따른 PLC 값 반환 """
        if material.size == "small":
            return PLASTIC_VALUE_MAPPING_SMALL.get(material.classification)
        elif material.size == "large":
            return PLASTIC_VALUE_MAPPING_LARGE.get(material.classification)
        return None


class LineCrossZone:
    """ 기준 선 통과 감지 영역(+ PLC 신호 트리거) """

    def __init__(self,
                 line_y: int,
                 target_classes: List[str],
                 on_cross_callback=None):

        self.line_y = line_y
        self.target_classes = set(target_classes or ["PLASTIC"])

        self.prev_positions: Dict[int, int] = {}
        self.crossed_objects = set() 

        self.on_cross_callback = on_cross_callback

    def update(self, obj: DetectedObject):
        """ 감지 업데이트 """

        if obj.class_name not in self.target_classes:
            return False

        obj_id = obj.id
        current_y = obj.center[1]

        prev_y = self.prev_positions.get(obj_id)

        # 이전 위치 저장
        self.prev_positions[obj_id] = current_y

        # 처음 들어온 객체는 비교 불가
        if prev_y is None:
            return False

        crossed = prev_y < self.line_y and current_y >= self.line_y

        if crossed and obj_id not in self.crossed_objects:
            self.crossed_objects.add(obj_id)

            log(f"[LINE] object {obj_id} crossed line")

            if self.on_cross_callback:
                self.on_cross_callback(obj)

            return True

        return False

    def cleanup(self, active_ids: set):
        """
        프레임에서 사라진 객체 정리
        """
        self.prev_positions = {
            obj_id: y for obj_id, y in self.prev_positions.items()
            if obj_id in active_ids
        }

        self.crossed_objects &= active_ids


class LineTrigger:
    """ 선 통과 감지 시 버퍼에서 재질 정보 꺼내서 PLC 신호 전송 """

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