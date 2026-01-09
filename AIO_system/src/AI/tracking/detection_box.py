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
    
    def __init__(self, box_id: int, x: int, y: int,
                width: int, height: int,
                target_classes: List[str] = ['PET', 'PE', 'PP', 'PS'],
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

        self.is_active = False  # 현재 물체가 있는지
        
        
    def is_inside(self, center: Tuple[int, int]) -> bool:
        """중심점이 박스 안에 있는지 확인"""
        x, y = center
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2
    
    def update(self, obj_id: int, center: Tuple[int, int], class_name: str) -> bool:
        inside = self.is_inside(center)
        is_target = class_name in self.target_classes
        
        if inside and is_target:
            if obj_id not in self.tracked_objects:
                self.tracked_objects.add(obj_id)
                self.class_counts[class_name] += 1  # 클래스별 카운트
                return True  # 액션 트리거
            else:
                self.tracked_objects.add(obj_id)
                self.is_active = True
        else:
            self.tracked_objects.discard(obj_id)
            
        self.is_active = len(self.tracked_objects) > 0
        return False
    
    def draw(self, frame: np.ndarray) -> np.ndarray:
        """박스 그리기 (물체 있으면 빨강, 없으면 초록)"""
        color = (0, 0, 255) if self.is_active else (0, 255, 0)
        cv2.rectangle(frame, (self.x1, self.y1), (self.x2, self.y2), color, 2)
        thickness = 2
        
        # Zone 별로 ID
        cv2.putText(frame, f"Zone {self.box_id}", (self.x1 + 5, self.y1 + 20),
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
        self.class_counts = {cls: 0 for cls in self.target_classes}
        self.is_active = False
        
        
class ConveyorBoxManager:
    """여러 개의 감지 박스 관리"""
    
    def __init__(self, boxes: List[ConveyorBoxZone]):
        self.boxes = boxes

    def update_detections(self, detected_objects: List[DetectedObject]) -> List[Tuple[int, str]]:
        """
        모든 박스에 대해 감지 업데이트
        Returns: [(box_id, class_name), ...] 새로 감지된 객체들
        """
        current_ids = {obj.id for obj in detected_objects}
    
        # 새로운 객체들 업데이트
        for obj in detected_objects:
            for box in self.boxes:
                box.update(obj.id, obj.center, obj.class_name)
                
        # 각 박스에서 사라진 객체 제거
        for box in self.boxes:
            # 현재 프레임에 없는 ID는 tracked_objects에서 제거
            box.tracked_objects = box.tracked_objects & current_ids
            # 박스 상태 업데이트
            box.is_active = len(box.tracked_objects) > 0
    
    def draw_all(self, frame: np.ndarray) -> np.ndarray:
        """모든 박스 그리기"""
        for box in self.boxes:
            frame = box.draw(frame)
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