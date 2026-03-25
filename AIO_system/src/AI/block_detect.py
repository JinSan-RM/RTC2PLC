from src.AI.tracking.detection_box import ConveyorBoxZone, ConveyorBoxManager
from src.utils.logger import log
from src.utils.config_util import CAMERA_CONFIGS
from datetime import datetime


class BlockDetector:
    """feeder 막힘 감지"""
    
    def __init__(self, box_manager: ConveyorBoxManager, camera_index: int = 0, block_threshold: float = 1.0):
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
        
        self.block_threshold = block_threshold # 막힘 감지 임계값, 수정해서 사용
        self.block_triggered = False # 막힘 감지 시 한 번만 로그 출력하기 위한 플래그

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
        log(f"[DEBUG-1] _check_stay_duration 시작")
        
        # 박스에 객체가 없으면 OK
        if not box.tracked_objects_info:
            #log(f"[DEBUG-2] tracked_objects_info 비어있음")  
            self.block_triggered = False  # 알람 초기화
            return False
        
        log(f"[DEBUG-3] tracked_objects_info 개수: {len(box.tracked_objects_info)}")  
        
        current_time = datetime.now()
        
        #스냅샷 만들기(반복 중 수정 방지)
        tracked_objects_snapshot = dict(box.tracked_objects_info)
        entry_times_snapshot = dict(box.object_entry_times)
        
        # ← 스냅샷으로 반복 (원본 딕셔너리 수정 안 됨)
        for obj_id, obj in tracked_objects_snapshot.items():
            if obj_id in entry_times_snapshot:
                entry_time = entry_times_snapshot[obj_id]
                stay_duration = (current_time - entry_time).total_seconds()
            
                #log(f"[DEBUG-4] 체류 시간={stay_duration:.2f}s")
            
                if stay_duration >= self.block_threshold:
                    if not self.block_triggered:
                        # log(f"🚨 [Feeder Block Detected] Box {self.feeder_box_id}: "
                        #     f"Object {obj_id} stayed for {stay_duration:.1f}s")
                        self.block_triggered = True
                
                    return True
        
        self.block_triggered = False
        return False