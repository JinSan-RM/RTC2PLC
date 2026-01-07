"""
서보 위치 기반 에어나이프 제어 알고리즘
temp_algorithm.py

서보의 position index에 따라 어느 박스(zone)에서 감지되었을 때 
airknife를 동작시킬지 결정하는 로직
"""

from typing import Dict, List, Optional
from src.utils.logger import log


class ServoPositionBasedAirControl:
    # ========== 설정 영역 ==========
    
    # True: 서보 위치 기반 제어 사용
    # False: 기존 방식 사용 (클래스 기반)
    USE_SERVO_POSITION_CONTROL = False  # ← 여기를 True/False로 변경
    
    # 에어나이프별 활성 위치 매핑
    AIRKNIFE_POSITION_MAP = {
        1: [1, 3, 5],  # 에어나이프 #1은 위치 1, 3, 5에서만 동작
        2: [2, 4],     # 에어나이프 #2는 위치 2, 4에서만 동작
        3: [1, 2, 3, 4, 5],  # 에어나이프 #3은 모든 위치에서 동작
    }
    
    # 서보 위치 허용 오차 (mm)
    POSITION_TOLERANCE = 5.0
    

class ServoPositionBasedAirControl:
    """
    서보 위치 기반 에어나이프 제어 클래스
    
    서보의 현재 위치 인덱스에 따라 특정 박스(zone)에서만 airknife를 동작시킴
    """
    
    def __init__(self, app):
        """
        초기화
        
        Args:
            app: 메인 애플리케이션 인스턴스
        """
        self.app = app
        self.servo_positions = {}  # {servo_id: current_position_index}
        
        # 서보 위치 인덱스 정의 (1~5)
        # 실제 서보 위치값을 인덱스로 매핑
        self.position_mapping = {
            0: self._get_servo_position_value(0, 1),  # 위치 1
            1: self._get_servo_position_value(0, 2),  # 위치 2
            2: self._get_servo_position_value(0, 3),  # 위치 3
            3: self._get_servo_position_value(0, 4),  # 위치 4
            4: self._get_servo_position_value(0, 5),  # 위치 5
        }
        
        log("[INFO] 서보 위치 기반 에어나이프 제어 시스템 초기화")
    
    def _get_servo_position_value(self, servo_id: int, position_idx: int) -> float:
        """
        서보 설정에서 특정 위치 인덱스의 실제 위치값 가져오기
        
        Args:
            servo_id: 서보 ID (0: 폭 제어, 1: 높이 제어)
            position_idx: 위치 인덱스 (1~5)
            
        Returns:
            실제 서보 위치값 (mm)
        """
        servo_key = f"servo_{servo_id}"
        if servo_key in self.app.config.get("servo_config", {}):
            pos_key = f"pos_{position_idx}"
            return self.app.config["servo_config"][servo_key].get(pos_key, 0.0)
        return 0.0
    
    def update_servo_position(self, servo_id: int, current_pos: float):
        """
        서보의 현재 위치를 업데이트하고 가장 가까운 위치 인덱스 계산
        
        Args:
            servo_id: 서보 ID
            current_pos: 현재 서보 위치 (mm)
        """
        # 현재 위치와 가장 가까운 위치 인덱스 찾기
        closest_idx = None
        min_distance = float('inf')
        
        for idx, target_pos in self.position_mapping.items():
            distance = abs(current_pos - target_pos)
            if distance < min_distance:
                min_distance = distance
                closest_idx = idx
        
        # 오차 범위 체크 (±5mm 이내)
        if min_distance <= 5.0:
            old_pos = self.servo_positions.get(servo_id)
            if old_pos != closest_idx + 1:  # 위치가 변경되었을 때만 로그
                self.servo_positions[servo_id] = closest_idx + 1
                log(f"[SERVO] 서보 #{servo_id} 위치 업데이트: 인덱스 {closest_idx + 1} ({current_pos:.2f}mm)")
        else:
            # 어느 위치에도 해당하지 않음
            if servo_id in self.servo_positions:
                del self.servo_positions[servo_id]
    
    def get_current_position_index(self, servo_id: int = 0) -> Optional[int]:
        """
        서보의 현재 위치 인덱스 가져오기
        
        Args:
            servo_id: 서보 ID (기본값: 0 - 폭 제어)
            
        Returns:
            현재 위치 인덱스 (1~5) 또는 None
        """
        return self.servo_positions.get(servo_id)
    
    def should_activate_airknife(
        self, 
        airknife_num: int, 
        box_id: int, 
        detected_class: str
    ) -> bool:
        """
        특정 에어나이프를 활성화해야 하는지 판단
        
        Args:
            airknife_num: 에어나이프 번호 (1~3)
            box_id: 감지 박스 ID (1~N)
            detected_class: 감지된 객체 클래스
            
        Returns:
            에어나이프를 활성화해야 하면 True, 아니면 False
        """
        # 에어나이프 설정 가져오기
        airknife_key = f"airknife_{airknife_num}"
        if airknife_key not in self.app.config.get("airknife_config", {}):
            return False
        
        air_config = self.app.config["airknife_config"][airknife_key]
        
        # 서보 위치 기반 제어가 비활성화되어 있으면 기존 방식 사용
        if not air_config.get("servo_control_enabled", False):
            # 기존 방식: 클래스 기반 또는 항상 활성화
            return True
        
        # 서보 위치 기반 제어 활성화됨
        servo_positions = air_config.get("servo_positions", [])
        
        if not servo_positions:
            log(f"[WARN] 에어나이프 #{airknife_num}에 활성 위치가 설정되지 않음")
            return False
        
        # 현재 서보 위치 인덱스 확인 (폭 제어 서보 사용)
        current_pos_idx = self.get_current_position_index(servo_id=0)
        
        if current_pos_idx is None:
            log(f"[WARN] 서보 위치를 확인할 수 없음")
            return False
        
        # 현재 위치가 활성 위치 목록에 포함되어 있는지 확인
        if current_pos_idx in servo_positions:
            log(f"[AIR] 에어나이프 #{airknife_num} 활성화 조건 충족: "
                f"위치={current_pos_idx}, 박스={box_id}, 클래스={detected_class}")
            return True
        else:
            log(f"[AIR] 에어나이프 #{airknife_num} 비활성: "
                f"현재 위치={current_pos_idx}는 활성 위치 {servo_positions}에 없음")
            return False
    
    def get_active_airknives_for_position(self, position_idx: int) -> List[int]:
        """
        특정 위치에서 활성화되어야 하는 에어나이프 목록
        
        Args:
            position_idx: 위치 인덱스 (1~5)
            
        Returns:
            활성화되어야 하는 에어나이프 번호 리스트
        """
        active_knives = []
        
        for i in range(1, 4):  # 에어나이프 1~3
            airknife_key = f"airknife_{i}"
            if airknife_key not in self.app.config.get("airknife_config", {}):
                continue
            
            air_config = self.app.config["airknife_config"][airknife_key]
            
            # 서보 위치 기반 제어가 활성화되어 있는지 확인
            if not air_config.get("servo_control_enabled", False):
                continue
            
            # 활성 위치 목록 확인
            servo_positions = air_config.get("servo_positions", [])
            if position_idx in servo_positions:
                active_knives.append(i)
        
        return active_knives
    
    def log_status(self):
        """현재 상태 로깅"""
        log("\n" + "="*60)
        log("서보 위치 기반 에어나이프 제어 상태")
        log("="*60)
        
        for servo_id, pos_idx in self.servo_positions.items():
            log(f"서보 #{servo_id}: 위치 인덱스 {pos_idx}")
        
        log("\n에어나이프 설정:")
        for i in range(1, 4):
            airknife_key = f"airknife_{i}"
            if airknife_key not in self.app.config.get("airknife_config", {}):
                continue
            
            air_config = self.app.config["airknife_config"][airknife_key]
            enabled = air_config.get("servo_control_enabled", False)
            positions = air_config.get("servo_positions", [])
            
            log(f"  에어나이프 #{i}: "
                f"서보 제어={'활성화' if enabled else '비활성화'}, "
                f"활성 위치={positions}")
        
        log("="*60 + "\n")