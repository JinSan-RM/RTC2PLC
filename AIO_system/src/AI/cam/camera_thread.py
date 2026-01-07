from PySide6.QtCore import QThread, Signal
import numpy as np
from src.AI.predict_AI import AIPlasticDetectionSystem
from src.utils.logger import log


"""
카메라 스레드 - AIPlasticDetectionSystem을 QThread로 래핑
"""

class CameraThread(QThread):
    """카메라 감지 스레드"""
    frame_ready = Signal(np.ndarray)
    error_occurred = Signal(str)
    
    def __init__(
        self,
        camera_index: int = 0,
        confidence_threshold: float = 0.7,
        img_size: int = 640,
        airknife_callback=None,
        app=None
    ):
        super().__init__()
        self.camera_index = camera_index
        self.confidence_threshold = confidence_threshold
        self.img_size = img_size
        self.airknife_callback = airknife_callback
        self.app = app
        self.running = False
        self.detector = None
    
    def run(self):
        """스레드 실행"""
        log(f"🎬 카메라 {self.camera_index + 1} 스레드 시작")
        self.running = True
        
        try:
            # AI 시스템 초기화
            log(f"📦 카메라 {self.camera_index + 1} AI 시스템 초기화 중...")
            self.detector = AIPlasticDetectionSystem(
                confidence_threshold=self.confidence_threshold,
                img_size=self.img_size,
                airknife_callback=self.airknife_callback,
                app=self.app,
                camera_index=self.camera_index  # 카메라 인덱스 전달
            )
            log(f"✅ 카메라 {self.camera_index + 1} AI 시스템 초기화 완료")
            
        except Exception as e:
            error_msg = f"카메라 {self.camera_index + 1} 초기화 실패: {e}"
            log(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(error_msg)
            return
        
        try:
            # run() 제너레이터 실행
            log(f"▶️ 카메라 {self.camera_index + 1} 프레임 처리 시작")
            frame_generator = self.detector.run()
            frame_count = 0
            
            for frame in frame_generator:
                if not self.running:
                    log(f"⏹ 카메라 {self.camera_index + 1} 정지 요청됨")
                    break
                
                if frame is not None:
                    self.frame_ready.emit(frame)
                    frame_count += 1
                    
                    # 100 프레임마다 로그
                    if frame_count % 100 == 0:
                        log(f"📊 카메라 {self.camera_index + 1}: {frame_count} 프레임 처리 (FPS: {self.detector.current_fps})")
            
            log(f"✅ 카메라 {self.camera_index + 1} 정상 종료")
            
        except Exception as e:
            error_msg = f"카메라 {self.camera_index + 1} 실행 오류: {e}"
            log(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(error_msg)
        finally:
            log(f"🛑 카메라 {self.camera_index + 1} 스레드 종료")
    
    def stop(self):
        """스레드 정지"""
        log(f"⏹ 카메라 {self.camera_index + 1} 정지 요청")
        self.running = False