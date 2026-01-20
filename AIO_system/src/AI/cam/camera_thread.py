# src/AI/camera_thread.py
from PySide6.QtCore import QThread, Signal
import numpy as np
import cv2
from typing import List, Optional
from src.utils.logger import log
from src.AI.cam.basler_manager import BaslerCameraManager
from src.utils.config_util import CAMERA_CONFIGS
from src.AI.tracking.detection_box import ConveyorBoxZone, ConveyorBoxManager, DetectedObject


class CameraThread(QThread):
    """
    카메라 캡처 전용 스레드
    - 프레임 캡처만 담당
    - AI 추론은 BatchAIManager가 처리
    """
    frame_ready = Signal(np.ndarray)
    error_occurred = Signal(str)
    
    # 클래스 상수
    CLASS_COLORS = {
        'PET': (0, 165, 255),
        'PE': (255, 0, 0),
        'PP': (0, 255, 0),
        'PS': (255, 0, 255)
    }
    
    def __init__(
        self,
        camera_index: int = 0,
        ai_manager=None,  # BatchAIManager 인스턴스
        airknife_callback=None,
        app=None
    ):
        super().__init__()
        self.camera_index = camera_index
        self.ai_manager = ai_manager
        self.airknife_callback = airknife_callback
        self.app = app
        self.running = False
        
        # 카메라 설정 로드
        self.config = CAMERA_CONFIGS.get(camera_index, {})
        roi = self.config.get('roi', None)
        
        # Basler 카메라 초기화
        self.camera_manager = BaslerCameraManager(
            camera_index=camera_index, 
            roi=roi
        )
        
        # 박스 매니저 생성
        self.box_manager = self._create_box_manager()
        
        # 캐싱된 결과 (프레임 스킵용)
        self.last_detected_objects = []
        self.frame_count = 0
        self.inference_interval = 2  # 2프레임마다 추론
        
        # 통계
        self.fps_counter = 0
        self.fps_start_time = 0
        self.current_fps = 0
    
    def _create_box_manager(self):
        """카메라별 박스 생성"""
        boxes = []
        for box_cfg in self.config.get('boxes', []):
            box = ConveyorBoxZone(
                box_id=box_cfg['box_id'],
                x=box_cfg['x'],
                y=box_cfg['y'],
                width=box_cfg['width'],
                height=box_cfg['height'],
                target_classes=box_cfg['target_classes']
            )
            boxes.append(box)
        log(f"카메라 {self.camera_index}: {len(boxes)}개 박스 생성")
        return ConveyorBoxManager(boxes)
    
    def run(self):
        """스레드 실행"""
        log(f"📷 카메라 {self.camera_index + 1} 스레드 시작")
        self.running = True
        
        # 카메라 초기화
        camera_ip = None
        if not self.camera_manager.initialize(camera_ip=camera_ip):
            log(f"카메라 {self.camera_index + 1} Basler 실패, 웹캠 시도")
            
            # 웹캠 폴백
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                error_msg = f"카메라 {self.camera_index + 1} 초기화 실패"
                log(error_msg)
                self.error_occurred.emit(error_msg)
                return
            
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 60)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            use_basler = False
        else:
            self.camera_manager.start_grabbing()
            use_basler = True
            cap = None
        
        log(f"카메라 {self.camera_index + 1} 초기화 완료 ({'Basler' if use_basler else '웹캠'})")
        
        # FPS 타이머 시작
        import time
        self.fps_start_time = time.time()
        
        try:
            while self.running:
                # 1. 프레임 캡처
                if use_basler:
                    frame = self.camera_manager.grab_frame()
                    if frame is None:
                        continue
                else:
                    ret, frame = cap.read()
                    if not ret:
                        break
                
                self.frame_count += 1
                
                # 2. AI 추론 요청 (N프레임마다)
                if self.frame_count % self.inference_interval == 0:
                    # BatchAIManager에 프레임 전달
                    if self.ai_manager:
                        self.ai_manager.put_frame(self.camera_index, frame)
                
                # 3. AI 결과 받기
                detected_objects = None
                if self.ai_manager:
                    result = self.ai_manager.get_result(self.camera_index)
                    if result is not None:
                        detected_objects = result
                        self.last_detected_objects = detected_objects
                    else:
                        # 결과 없으면 이전 결과 사용
                        detected_objects = self.last_detected_objects
                else:
                    detected_objects = []
                
                # 4. 박스 매니저 업데이트
                self.box_manager.update_detections(detected_objects)
                
                # 5. AirKnife 동작
                if len(detected_objects) > 0:
                    self._handle_airknife()
                
                # 6. 프레임에 그리기
                frame = self._draw_frame(frame, detected_objects)
                
                # 7. 프레임 전송
                self.frame_ready.emit(frame)
                
                # FPS 계산
                self._update_fps()
            
            log(f"카메라 {self.camera_index + 1} 정상 종료")
        
        except Exception as e:
            error_msg = f"카메라 {self.camera_index + 1} 실행 오류: {e}"
            log(error_msg)
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(error_msg)
        
        finally:
            # 정리
            if use_basler:
                self.camera_manager.stop_grabbing()
                self.camera_manager.close()
            else:
                if cap:
                    cap.release()
            
            log(f"카메라 {self.camera_index + 1} 스레드 종료")
    
    def _handle_airknife(self):
        """AirKnife 동작 처리"""
        if self.app and self.app.use_air_sequence and self.app.air_index_iter:
            try:
                box_id = int(next(self.app.air_index_iter))
                if box_id < len(self.box_manager.boxes):
                    box = self.box_manager.boxes[box_id]
                    if box.is_active:
                        self._send_airknife_signal(box.box_id, 1000)
            except StopIteration:
                pass
        else:
            # 순차 모드
            for box in self.box_manager.boxes:
                if box.is_active:
                    self._send_airknife_signal(box.box_id, 1000)
    
    def _send_airknife_signal(self, air_num: int, on_term: int):
        """AirKnife 신호 전송"""
        if self.airknife_callback:
            self.airknife_callback(air_num, on_term)
    
    def _draw_frame(self, frame: np.ndarray, detected_objects: List[DetectedObject]) -> np.ndarray:
        """프레임에 그리기"""
        # 1. 박스 그리기
        frame = self.box_manager.draw_all(frame)
        
        # 2. 감지된 객체 그리기
        for obj in detected_objects:
            x1, y1, x2, y2 = obj.bbox
            color = self.CLASS_COLORS.get(obj.class_name, (128, 128, 128))
            
            # 바운딩 박스
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # 라벨
            label = f"{obj.class_name}: {obj.confidence:.2f}"
            cv2.putText(
                frame, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, color, 1, cv2.LINE_AA
            )
        
        # 3. FPS 표시
        cv2.putText(
            frame, f"Cam{self.camera_index + 1} FPS: {self.current_fps}", 
            (10, 30), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.6, (0, 255, 0), 2
        )
        
        return frame
    
    def _update_fps(self):
        """
        FPS 미리 보기
        """
        import time
        self.fps_counter += 1
        
        elapsed = time.time() - self.fps_start_time
        if elapsed >= 1.0:
            self.current_fps = int(self.fps_counter / elapsed)
            self.fps_counter = 0
            self.fps_start_time = time.time()
    
    def stop(self):
        """스레드 정지"""
        log(f"카메라 {self.camera_index + 1} 정지 요청")
        self.running = False