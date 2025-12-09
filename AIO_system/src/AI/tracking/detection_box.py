import cv2
import numpy as np
from typing import Tuple, List, Optional, Dict
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class DetectedObject:
    """감지된 폐플라스틱 객체 정보"""
    id: int
    class_name: str
    center: Tuple[int, int]
    bbox: Tuple[int, int, int, int]
    confidence: float
    metainfo: Optional[Dict] = None
    

class ConveyorBoxZone:
    """
    컨베이어 벨트 위의 감지 박스 영역
    
    객체의 중앙점이 박스안에 들어오면 AirKnife에 부는 형태로 카운팅
    """
    
    def __init__(self, box_id: int, x: int, y: int, width: int, height: int):
        self.box_id = box_id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.x1 = x
        self.y1 = y
        self.x2 = x + width
        self.y2 = y + height
        
        self.tracked_objects = set()  # 현재 박스 안에 있는 객체들
        self.detected_objects = set()  # 이미 카운트된 객체들
        
        self.class_counts = {
            'PET': 0, 'PE': 0, 'PP': 0, 'PS': 0
        }
        self.is_active = False  # 현재 물체가 있는지
        
    def is_inside(self, center: Tuple[int, int]) -> bool:
        """중심점이 박스 안에 있는지 확인"""
        x, y = center
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2
    
    def update_detection(self, obj_id: int, center: Tuple[int, int], class_name: str) -> bool:
        """
        객체 감지 업데이트
        Returns: True if 새로 감지된 경우 (카운트 필요)
        """
        if self.is_inside(center):
            self.is_active = True
            
            # 새로운 객체 발견
            if obj_id not in self.detected_objects:
                self.tracked_objects.add(obj_id)
                self.detected_objects.add(obj_id)
                self.class_counts[class_name] += 1
                return True
            else:
                self.tracked_objects.add(obj_id)
        else:
            # 박스 밖으로 나감
            self.tracked_objects.discard(obj_id)
        
        self.is_active = len(self.tracked_objects) > 0
        return False
    
    def draw(self, frame: np.ndarray) -> np.ndarray:
        """박스 그리기 (물체 있으면 빨강, 없으면 초록)"""
        color = (0, 0, 255) if self.is_active else (0, 255, 0)
        thickness = 3 if self.is_active else 2
        
        # 박스 그리기
        cv2.rectangle(frame, (self.x1, self.y1), (self.x2, self.y2), color, thickness)
        
        # 박스 ID 표시
        label = f"Zone {self.box_id}"
        cv2.putText(frame, label, (self.x1 + 5, self.y1 + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # 현재 카운트 표시 (작게)
        total = sum(self.class_counts.values())
        if total > 0:
            count_label = f"Count: {total}"
            cv2.putText(frame, count_label, (self.x1 + 5, self.y1 + 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        return frame
    
    def reset(self):
        """카운트 리셋"""
        self.tracked_objects.clear()
        self.detected_objects.clear()
        self.class_counts = {'PET': 0, 'PE': 0, 'PP': 0, 'PS': 0}
        self.is_active = False
        
        
class ConveyorBoxManager:
    """여러 개의 감지 박스 관리"""
    
    def __init__(self, boxes: List[ConveyorBoxZone]):
        self.boxes = boxes
        self.total_class_counts = {
            'PET': 0, 'PE': 0, 'PP': 0, 'PS': 0
        }
        self.detailed_stats = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    
    def update_detections(self, detected_objects: List[DetectedObject]) -> List[Tuple[int, str]]:
        """
        모든 박스에 대해 감지 업데이트
        Returns: [(box_id, class_name), ...] 새로 감지된 객체들
        """
        newly_detected = []
        
        for obj in detected_objects:
            for box in self.boxes:
                if box.update_detection(obj.id, obj.center, obj.class_name):
                    newly_detected.append((box.box_id, obj.class_name))
                    self.total_class_counts[obj.class_name] += 1
        
        return detected_objects, newly_detected
    
    def draw_all(self, frame: np.ndarray) -> np.ndarray:
        """모든 박스 그리기"""
        for box in self.boxes:
            frame = box.draw(frame)
        return frame
    
    def reset_all(self):
        """모든 박스 리셋"""
        for box in self.boxes:
            box.reset()
        self.total_class_counts = {'PET': 0, 'PE': 0, 'PP': 0, 'PS': 0}