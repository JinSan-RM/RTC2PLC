from typing import Tuple, Dict
import cv2
import numpy as np
import time
from collections import defaultdict

class LineCounter:
    """
    컨베이어 벨트 스타일 카운팅 라인
    
    객체가 라인을 통과할 때 카운트
    
    현재는 박스안에 들어오면 부는 형태로 바꿀 예정이라서 필요 없음
    """
    
    def __init__(self, line_start: Tuple[int, int], line_end: Tuple[int, int], 
                 thickness: int = 3, buffer_zone: int = 50):
        self.line_start = line_start
        self.line_end = line_end
        self.thickness = thickness
        self.buffer_zone = buffer_zone
        self.tracked_objects = {}
        self.crossed_objects = set()
        
        self.class_counts = {
            'PET': 0, 'PE': 0, 'PP': 0, 'PS': 0
        }
        self.detailed_stats = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        
    def is_line_crossed(self, obj_id: int, center: Tuple[int, int]) -> bool:
        x, y = center
        dx = self.line_end[0] - self.line_start[0]
        dy = self.line_end[1] - self.line_start[1]
        
        if dx == 0 and dy == 0:
            distance = np.sqrt((x - self.line_start[0])**2 + (y - self.line_start[1])**2)
        else:
            distance = abs(dy * x - dx * y + self.line_end[0] * self.line_start[1] - 
                          self.line_end[1] * self.line_start[0]) / np.sqrt(dx**2 + dy**2)
        
        current_side = self._get_side_of_line(center)
        
        if obj_id in self.tracked_objects:
            previous_side = self.tracked_objects[obj_id]['side']
            if (previous_side != current_side and 
                distance < self.buffer_zone and 
                obj_id not in self.crossed_objects):
                self.crossed_objects.add(obj_id)
                return True
        
        self.tracked_objects[obj_id] = {
            'side': current_side,
            'center': center,
            'last_seen': time.time()
        }
        return False
    
    def _get_side_of_line(self, point: Tuple[int, int]) -> int:
        x, y = point
        return np.sign((self.line_end[0] - self.line_start[0]) * (y - self.line_start[1]) - 
                      (self.line_end[1] - self.line_start[1]) * (x - self.line_start[0]))
    
    def update_stats(self, class_name: str, metainfo: Dict = None):
        if class_name in self.class_counts:
            self.class_counts[class_name] += 1
            if metainfo:
                self.detailed_stats[class_name]['transparency'][metainfo.get('transparency', '불투명')] += 1
                self.detailed_stats[class_name]['shape'][metainfo.get('shape', '기타')] += 1
    
    def cleanup_old_tracks(self, timeout: int = 5):
        current_time = time.time()
        to_remove = [obj_id for obj_id, data in self.tracked_objects.items() 
                     if current_time - data['last_seen'] > timeout]
        for obj_id in to_remove:
            del self.tracked_objects[obj_id]
            self.crossed_objects.discard(obj_id)
    
    def draw_line(self, frame: np.ndarray) -> np.ndarray:
        cv2.line(frame, self.line_start, self.line_end, (0, 255, 0), self.thickness)
        mid_point = ((self.line_start[0] + self.line_end[0]) // 2,
                     (self.line_start[1] + self.line_end[1]) // 2)
        cv2.putText(frame, "CONVEYOR COUNTING LINE", (mid_point[0] - 80, mid_point[1] - 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        return frame
