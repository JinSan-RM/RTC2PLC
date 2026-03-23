"""
Author : Jeong Min Seon
Date : 2026-03-17
Description : PLC Machine Entrance Traffic Detect
After Action PLC Send Signal to RTC Algorithm

"""
import time
import cv2
import numpy as np
from typing import Tuple, List, Optional, Dict
from collections import defaultdict
from dataclasses import dataclass
from src.AI.AI_manager import DetectedObject


class EntranceBoxZone:
    """
    피더 입구에서 막힘을 감지 박스 영역
    
    객체의 중앙점이 박스안에 들어오면 AirKnife에 부는 형태로 카운팅
    """
    
    def __init__(self, box_id: int, x: int, y: int,
                width: int, height: int,
                target_classes: List[str] = ['PLASTIC'],
                airknife_callback = None,
                block_detection_time = 5
                ):
        
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

        self.last_obj_id = 0
        self.last_in_time = 0

        self.is_active = False  # 현재 물체가 있는지

        self.airknife_callback = airknife_callback
        self.block_detection_time = block_detection_time
        
        
    def is_inside(self, center: Tuple[int, int]) -> bool:
        """중심점이 박스 안에 있는지 확인"""
        x, y = center
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2



    def update(self, obj: DetectedObject) -> bool:  
        inside = self.is_inside(obj.center) # 물체의 중심점이 박스 안에 있는지
        is_target = obj.class_name in self.target_classes   # 감지할 대상인지 확인

        current_time = time.time()  # 현재 시간(얼마나 오래 머물렀는지 알기 위해서)
        if inside and is_target:    # 감지 박스 안에 있고 감지할 대상이라면
            if obj.id not in self.tracked_objects:  # obj.id가 새롭게 들어온 경우(새로운 물체)
                # print("new object detected in box")
                self.tracked_objects.add(obj.id) # tracked_objects에 새롭게 들어온 객체 ID 추가
                # self.class_counts[obj.class_name] += 1  # 클래스별 카운트
                
                self.tracked_objects_info[obj.id] = obj

                self.last_in_time = current_time
                self.last_obj_id = obj.id
                
            else:
                # 이미 박스 안에 있는 물체가 일정 시간 이상 나가지 않고 머물러 있다면? -> 뭔가 막혔다! (조건문을 어떤식으로 작성할건지) -> airknife_callback() 호출 -> True 반환
                if obj.id == self.last_obj_id:  # 마지막으로 들어온 객체가 여전히 박스 안에 있는 경우
                    if current_time - self.last_in_time > self.block_detection_time:  # 막힘 감지 시간 이상 같은 객체가 있으면 막힘으로 간주
                        self.last_in_time = current_time  # 시간 갱신

                        # if self.airknife_callback:
                        #     self.airknife_callback()   # 에어 분사 부분

                        return True  # 막힘 신호 트리거  
                
        else:
            # 박스 밖으로 나간 객체는 tracked_objects에서 제거
            self.tracked_objects.discard(obj.id)
            self.tracked_objects_info.pop(obj.id, None)
            
        self.is_active = len(self.tracked_objects) > 0
        return False
    
    
    
    def draw(self, frame: np.ndarray) -> np.ndarray:
        """박스 그리기 (물체 있으면 빨강, 없으면 초록)"""
        color = (0, 0, 255) if self.is_active else (255, 0, 255)
        cv2.rectangle(frame, (self.x1, self.y1), (self.x2, self.y2), color, 2)
        
        # Zone 별로 ID
        cv2.putText(frame, f"EntranceZone {self.box_id}", (self.x1 + 5, self.y1 + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # class별로 카운트 표시
        y_offset = 40
        for cls, count in self.class_counts.items():
            count_label = f"{cls}: {count}"
            cv2.putText(frame, f"{cls}:{count}", (self.x1 + 5, self.y1 + y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            y_offset += 15
        
        return frame
    
    def reset(self):
        """카운트 리셋"""
        self.tracked_objects.clear()
        self.detected_objects.clear()
        self.tracked_objects_info.clear()
        self.class_counts = {cls: 0 for cls in self.target_classes}
        self.is_active = False
        
        
        
class EntranceBoxManager:
    """여러 개의 감지 박스 관리"""
    
    def __init__(self, boxes: List[EntranceBoxZone]):
        self.boxes = boxes

    def update_detections(self, detected_objects: List[DetectedObject]):
        """
        모든 박스에 대해 감지 업데이트
        """
        # 조기 리턴으로 불필요한 연산 제거
        if not detected_objects:
            for box in self.boxes:
                box.tracked_objects.clear()
                box.tracked_objects_info.clear()
                box.is_active = False
            return
        
        current_ids = {obj.id for obj in detected_objects}
    
        # 새로운 객체들 업데이트
        for obj in detected_objects:
            for box in self.boxes:
                triggered = box.update(obj)

                if triggered: # 신호 처리 부분
                    print(f"[block detected] Box {box.box_id}")

                
        # 각 박스에서 사라진 객체 제거
        for box in self.boxes:
            # 현재 프레임에 없는 ID는 tracked_objects에서 제거
            # box.tracked_objects = box.tracked_objects & current_ids
            box.tracked_objects &= current_ids
            box.tracked_objects_info = {
                k: v for k, v in box.tracked_objects_info.items() 
                if k in current_ids
            }
            # 박스 상태 업데이트
            box.is_active = bool(box.tracked_objects)
    
    def draw_all(self, frame: np.ndarray) -> np.ndarray:
        """모든 박스 그리기"""
        # for box in self.boxes:
        #     frame = box.draw(frame)
        # return frame
        for box in self.boxes:
            box.draw(frame)
        return frame
    
    def get_total_counts(self) -> Dict[str, int]:
        total = defaultdict(int)
        for box in self.boxes:
            for cls, cnt in box.class_counts.items():
                total[cls] += cnt
        return dict(total)
    
    def reset_all(self):
        """모든 박스 리셋"""
        for box in self.boxes:
            box.reset()