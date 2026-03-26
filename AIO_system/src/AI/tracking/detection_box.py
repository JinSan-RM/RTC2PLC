"""
src/AI/tracking/detection_box.py
"""
from typing import Tuple, List, Dict
from collections import defaultdict
# from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np

from src.AI.AI_manager import DetectedObject

class ConveyorBoxZone:
    """
    컨베이어 벨트 위의 감지 박스 영역
    
    객체의 중앙점이 박스안에 들어오면 AirKnife에 부는 형태로 카운팅
    """

    def __init__(self, box_id: int, x: int, y: int,
                width: int, height: int,
                # target_classes: List[str] = ['PET', 'PE', 'PP', 'PS'],
                # TensorRT 변경 부분 =========
                target_classes: List[str] = None,
                ):

        if target_classes is None:
            target_classes = ['PLASTIC']

        self.box_id = box_id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.x1 = x
        self.y1 = y
        self.x2 = x + width
        self.y2 = y + height
        self.target_classes = set(target_classes)

        self.tracked_objects = set()  # 현재 박스 안에 있는 객체들
        self.class_counts = {cls: 0 for cls in target_classes}
        self.detected_objects = set()  # 이미 카운트된 객체들
        self.tracked_objects_info: Dict[int, DetectedObject] = {}

        self.object_data: Dict[int, Dict] = {}  # 객체 ID별로 진입 시간, 마지막 본 시간, 누적 체류 시간, 진입 위치, 마지막 위치 등을 저장하는 딕셔너리
        self.grace_period = 1.0  # 유예 시간 (초)
        self.distinguish_position_threshold = 200  # 개별 객체라고 판단하는 위치 임계값 (픽셀)
        self.is_active = False  # 현재 물체가 있는지

    def is_inside(self, center: Tuple[int, int]) -> bool:
        """중심점이 박스 안에 있는지 확인"""
        x, y = center
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def update(self, obj: DetectedObject) -> bool:
        """감지 박스 업데이트"""
        inside = self.is_inside(obj.center)
        is_target = obj.class_name in self.target_classes
        current_time = datetime.now()

        # Ver 2
        if inside and is_target:
            if obj.id not in self.tracked_objects:
                # 이전에 본 객체인지 확인 (유예 시간 내)
                if obj.id in self.object_data:
                    time_since_last_seen = (current_time - self.object_data[obj.id]['last_seen_time']).total_seconds()
                    # 유예 시간 내에 다시 나타났나?
                    if time_since_last_seen <= self.grace_period:
                        #위치 추적해서 같은 객체인지 확인
                        last_pos = self.object_data[obj.id].get('last_pos')
                        current_pos = obj.center
                        distance = self.calculate_distance(last_pos, current_pos) if last_pos else 0

                        # 유예 시간 내에 나타났고 위치도 가까우면 같은 객체로 간주
                        if distance <= self.distinguish_position_threshold:
                        # 진입 시간 유지
                            # print(f"[DEBUG-UPDATE-5] 🔄 재인식! obj.id={obj.id}, "
                            #     f"time_since_last_seen={time_since_last_seen:.2f}s")
                            self.tracked_objects.add(obj.id)
                            self.tracked_objects_info[obj.id] = obj
                            self.object_data[obj.id]['last_seen_time'] = current_time

                            #self.object_data[obj.id]['entry_pos'] = current_pos # 현재 위치를 진입 위치로 업데이트 -> 재인식 될 때 진입 위치도 업데이트한다면, 주석 풀어서 사용
                            self.object_data[obj.id]['last_pos'] = current_pos # 위치 업데이트

                            self.is_active = True
                            return False  # 진입 시간을 초기화하지 않음
                        else:
                            # print(f"[DEBUG-UPDATE-6] 🔴 다른 객체 재할당! obj.id={obj.id}, "
                            #        f"distance={distance:.1f}px (임계값: {self.distinguish_position_threshold}px)")
                            pass

                # 새로운 객체로 취급
                self.tracked_objects.add(obj.id)
                self.class_counts[obj.class_name] += 1  # 클래스별 카운트
                self.tracked_objects_info[obj.id] = obj

                self.object_data[obj.id] = {
                    'entry_time' : current_time,
                    'last_seen_time' : current_time,
                    'accumulated_time' : 0.0,
                    'entry_pos' : obj.center,
                    'last_pos' : obj.center
                }

                # print(f"[DEBUG-UPDATE-4] ✅ 박스 안으로 진입! obj.id={obj.id}")
                return True  # 액션 트리거
            else:
                # 이미 추적 중인 객체
                self.tracked_objects.add(obj.id)
                self.tracked_objects_info[obj.id] = obj
                self.object_data[obj.id]['last_seen_time'] = current_time
                self.object_data[obj.id]['last_pos'] = obj.center
                self.is_active = True

        else:
            # 박스 밖이거나 target이 아닌 경우
            # tracked_objects에서는 아직 제거하지 않음 (update_detections에서 처리)
            pass


        self.is_active = len(self.tracked_objects) > 0
        return False

    def calculate_distance(self, pos1, pos2):
        """거리 계산"""
        return np.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)

    def draw(self, frame: np.ndarray) -> np.ndarray:
        """박스 그리기 (물체 있으면 빨강, 없으면 초록)"""
        color = (255, 0, 0) if self.is_active else (0, 255, 0)
        cv2.rectangle(frame, (self.x1, self.y1), (self.x2, self.y2), color, 2)

        # Zone 별로 ID
        cv2.putText(frame, f"Zone {self.box_id}", (self.x1 + 5, self.y1 + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # class별로 카운트 표시
        y_offset = 40
        for cls, count in self.class_counts.items():
            # count_label = f"{cls}: {count}"
            cv2.putText(frame, f"{cls}:{count}", (self.x1 + 5, self.y1 + y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            y_offset += 15

        return frame

    def reset(self):
        """카운트 리셋"""
        self.tracked_objects.clear()
        self.detected_objects.clear()
        self.tracked_objects_info.clear()
        self.object_data.clear() # Ver 2
        self.class_counts = {cls: 0 for cls in self.target_classes}
        self.is_active = False

class ConveyorBoxManager:
    """여러 개의 감지 박스 관리"""

    def __init__(self, boxes: List[ConveyorBoxZone]):
        self.boxes = boxes

    def update_detections(self, detected_objects: List[DetectedObject]):
        """
        모든 박스에 대해 감지 업데이트
        """

        # Ver 2
        # 조기 리턴하기 전에 누적 시간 업데이트
        current_time = datetime.now()

        if not detected_objects:
            for box in self.boxes:
                # 유예 시간 내의 객체들은 누적 시간 업데이트
                for obj_id in box.tracked_objects:
                    if obj_id in box.object_data:
                        stay_duration = (current_time - box.object_data[obj_id]['entry_time']).total_seconds()
                        box.object_data[obj_id]['accumulated_time'] = stay_duration
                # 박스에서 객체 제거
                box.tracked_objects.clear()
                box.tracked_objects_info.clear()
                box.is_active = False
            return

        current_ids = {obj.id for obj in detected_objects}

        # 새로운 객체들 업데이트
        for obj in detected_objects:
            for box in self.boxes:
                box.update(obj)

        # Ver 2
        # 각 박스에서 사라진 객체 처리
        for box in self.boxes:            
            # 유예 시간이 지난 객체만 제거
            expired_ids = set()
            for obj_id in box.tracked_objects:
                if obj_id not in current_ids:
                    if obj_id in box.object_data:
                        time_since_last_seen = (current_time - box.object_data[obj_id]['last_seen_time']).total_seconds()
                        if time_since_last_seen > box.grace_period: # 유예 시간 지난 경우 제거
                            expired_ids.add(obj_id)
                    # else:
                    #     expired_ids.add(obj_id)

            # 만료된 객체 제거
            for obj_id in expired_ids:
                box.tracked_objects.discard(obj_id)
                box.tracked_objects_info.pop(obj_id, None)
                box.object_data.pop(obj_id, None)

            # 박스 상태 업데이트
            box.is_active = bool(box.tracked_objects)

        # 현재 추적 중인 객체들의 누적 시간 업데이트
        for box in self.boxes:
            for obj_id in box.tracked_objects:
                if obj_id in box.object_data:
                    # 진입 시간부터 현재까지의 시간 계산 (누적 체류 시간)
                    stay_duration = (current_time - box.object_data[obj_id]['entry_time']).total_seconds()
                    box.object_data[obj_id]['accumulated_time'] = stay_duration

        # 디버깅 출력문
        # for box in self.boxes:
        #     tracked_info = []
        #     for obj_id in box.tracked_objects:
        #         if obj_id in box.tracked_objects_info and obj_id in box.object_data:
        #             obj = box.tracked_objects_info[obj_id]
        #             if obj:
        #                 accumulated_time = box.object_data[obj_id].get('accumulated_time', 0.0)
        #                 tracked_info.append((f"{obj_id}", f"{obj.class_name}", f"{accumulated_time:.2f}s"))

        #     if tracked_info:
        #         print(f"{tracked_info}")

    def draw_all(self, frame: np.ndarray) -> np.ndarray:
        """모든 박스 그리기"""
        # for box in self.boxes:
        #     frame = box.draw(frame)
        # return frame
        for box in self.boxes:
            box.draw(frame)
        return frame

    def get_total_counts(self) -> Dict[str, int]:
        """재질별 전체 카운트 집계"""
        total = defaultdict(int)
        for box in self.boxes:
            for cls, cnt in box.class_counts.items():
                total[cls] += cnt
        return dict(total)

    def reset_all(self):
        """모든 박스 리셋"""
        for box in self.boxes:
            box.reset()
