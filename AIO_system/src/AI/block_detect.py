from src.AI.tracking.detection_box import ConveyorBoxZone, ConveyorBoxManager
from src.utils.logger import log
from src.utils.config_util import CAMERA_CONFIGS
from datetime import datetime


class BlockDetector:
    """feeder 막힘 감지"""
    
    def __init__(self, box_manager: ConveyorBoxManager, camera_index: int = 0, block_threshold: float = 3.0,
                 position_threshold: int = 100):
        """
        feeder 막힘 감지 초기화
        """
        self.camera_index = camera_index 
        camera_config = CAMERA_CONFIGS.get(camera_index, {}) # 카메라 설정에서 박스 정보 가져오기, 없으면 기본값으로 빈 딕셔너리
        self.box_manager = box_manager
        boxes_config = camera_config.get('boxes', [])  # 박스 정보 가져오기, 없으면 빈 리스트
        
        # 카메라 1의 첫번째 box를 feeder box로 정의
        if boxes_config:
            self.feeder_box_id = boxes_config[0]['box_id']
            log(f"Feeder Box ID set to: {self.feeder_box_id}")
        else:
            self.feeder_box_id = 1  # fallback
            log("No boxes found in config, using default feeder_box_id: 1")
            
        #수정
        self.feeder_box = self._find_feeder_box()
        
        self.block_threshold = block_threshold # 막힘 감지 초 임계값, 수정해서 사용
        self.position_threshold = position_threshold # 막힘 감지 위치 변화 임계값, 수정해서 사용
        self.block_triggered = False # 막힘 감지 시 한 번만 로그 출력하기 위한 플래그
        
        #Ver 2
        self.triggered_object_ids = set()  # block_threshold 초 이상 체류한 객체 ID 저장 (알람 중복 방지)

    def _find_feeder_box(self):
        for box in self.box_manager.boxes:
            if box.box_id == self.feeder_box_id:
                return box
        return None
    
    def is_blocked(self) -> bool:
        """
        feeder 막힘 감지
        
        Returns:
            True: feeder 막혔음 (airknife 발동)
            False: 정상
        """
        #수정
        if not self.feeder_box:
            return False
        
        return self._check_stay_duration(self.feeder_box)
    
    def _check_stay_duration(self, box: ConveyorBoxZone) -> bool:
        """
        객체가 block_threshold 초 이상 박스에 있는가?
        
        Args:
            box: ConveyorBoxZone 객체
        
        Returns:
            True: block_threshold 초 이상 체류 (막혔음)
            False: block_threshold 초 미만
        """
        
        # 박스에 객체가 없으면 OK
        if not box.tracked_objects_info:
            self.block_triggered = False  # 알람 초기화
            self.triggered_object_ids.clear()  # 알람 중복 방지용 ID 초기화
            return False
        
        
        current_time = datetime.now()
        
        #스냅샷 만들기(반복 중 수정 방지)
        tracked_objects_snapshot = dict(box.tracked_objects_info)
        object_data_snapshot = dict(box.object_data)

        
        # Ver 2
        
        should_trigger = False
        
        for obj_id, obj in tracked_objects_snapshot.items():
            if obj_id in object_data_snapshot:
                accumulated_time = object_data_snapshot[obj_id]['accumulated_time']
                entry_pos = object_data_snapshot[obj_id]['entry_pos']
                last_pos = object_data_snapshot[obj_id]['last_pos']
                
                distance_from_entry = box.calculate_distance(entry_pos, last_pos) if entry_pos and last_pos else 0
            
                # log(f"[DEBUG-4] 체류 시간={accumulated_time:.2f}s, "
                #     f"진입 위치로부터 거리={distance_from_entry:.1f}px")
            
                if accumulated_time >= self.block_threshold and distance_from_entry <= self.position_threshold:
                    if obj_id not in self.triggered_object_ids:
                        # log(f"🚨 [Feeder Block Detected] Box {self.feeder_box_id}: "
                        #     f"Object {obj_id} stayed for {accumulated_time:.1f}s")
                        self.triggered_object_ids.add(obj_id)
                        should_trigger = True
                        
        for obj_id in list(self.triggered_object_ids):
            if obj_id not in box.tracked_objects_info:
                self.triggered_object_ids.discard(obj_id)

        if should_trigger:
            self.block_triggered = True
            return True
                
        self.block_triggered = False
        return False