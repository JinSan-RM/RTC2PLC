import queue
import threading
import torch
import numpy as np
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from src.utils.logger import log


@dataclass
class DetectedObject:
    """감지된 폐플라스틱 객체 정보"""
    id: int
    class_name: str
    center: tuple
    bbox: tuple
    confidence: float
    metainfo: Optional[Dict] = None


class BatchAIManager:
    """
    여러 카메라의 AI 추론을 배치로 처리
    - 각 카메라에서 프레임을 받아서
    - 한 번에 묶어서 GPU 추론 (효율 극대화)
    - 결과를 각 카메라로 분배
    """
    
    def __init__(
        self, 
        num_cameras: int = 2,
        confidence_threshold: float = 0.5,
        img_size: int = 480,
        max_det: int = 50
    ):
        self.num_cameras = num_cameras
        self.confidence_threshold = confidence_threshold
        self.img_size = img_size
        self.max_det = max_det
        
        # 카메라별 입력 큐 (프레임 저장)
        self.input_queues = {
            i: queue.Queue(maxsize=2) for i in range(num_cameras)
        }
        
        # 카메라별 출력 큐 (결과 저장)
        self.output_queues = {
            i: queue.Queue(maxsize=2) for i in range(num_cameras)
        }
        
        # 모델 로드
        self.model = None
        self.device = None
        self.CLASS_NAMES = ['PET', 'PS', 'PP', 'PE']
        
        self.running = False
        self.inference_thread = None
        
        # 통계
        self.total_inferences = 0
        self.batch_count = 0
    
    def initialize(self, model_path: str) -> bool:
        """모델 초기화"""
        try:
            from src.AI.model_load import load_yolov11
            
            log("BatchAIManager 초기화")
            self.model, self.device = load_yolov11(model_path)
            
            if self.model is None:
                log("모델 로드 실패")
                return False
            
            # 워밍업
            dummy_frames = [np.zeros((640, 640, 3), dtype=np.uint8) for _ in range(self.num_cameras)]
            for _ in range(2):
                _ = self.model.track(
                    source=dummy_frames,
                    verbose=False,
                    device=self.device,
                    imgsz=self.img_size
                )
            
            log("BatchAIManager 초기화 완료")
            return True
            
        except Exception as e:
            log(f"BatchAIManager 초기화 실패: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def start(self):
        """배치 추론 스레드 시작"""
        if not self.model:
            log("모델이 초기화되지 않았습니다")
            return
        
        log("배치 추론 스레드 시작")
        self.running = True
        self.inference_thread = threading.Thread(
            target=self._batch_inference_loop,
            daemon=True
        )
        self.inference_thread.start()
    
    def _batch_inference_loop(self):
        """배치 추론 메인 루프"""
        log("배치 추론 루프 실행 중...")
        
        while self.running:
            try:
                # 1. 모든 카메라에서 프레임 수집 (논블로킹)
                frames = {}
                for cam_id in range(self.num_cameras):
                    try:
                        # 타임아웃 0.005초 (5ms)
                        frame = self.input_queues[cam_id].get(timeout=0.005)
                        frames[cam_id] = frame
                    except queue.Empty:
                        continue
                
                # 프레임이 하나도 없으면 다음 루프
                if not frames:
                    continue
                
                # 2. 배치 구성
                cam_ids = list(frames.keys())
                frame_list = [frames[cam_id] for cam_id in cam_ids]
                
                # 3. 배치 추론 (GPU 1번 호출!)
                t_start = time.time()
                
                results = self.model.track(
                    source=frame_list,  # ← 리스트로 전달!
                    conf=self.confidence_threshold,
                    imgsz=self.img_size,
                    device=self.device,
                    verbose=False,
                    half=True,
                    max_det=self.max_det,
                    persist=True,
                    tracker="bytetrack.yaml",
                    agnostic_nms=True,
                    classes=[0, 1, 2, 3],
                    stream=False,  # 배치 모드
                )
                
                inference_time = (time.time() - t_start) * 1000
                
                # 통계 업데이트
                self.batch_count += 1
                self.total_inferences += len(frame_list)
                
                # 100번째 배치마다 통계 출력
                if self.batch_count % 100 == 0:
                    avg_batch_size = self.total_inferences / self.batch_count
                    log(f"배치 통계: {self.batch_count}번째 배치, "
                        f"평균 배치 크기: {avg_batch_size:.2f}, "
                        f"추론 시간: {inference_time:.2f}ms")
                
                # 4. 결과 파싱 및 분배
                for i, cam_id in enumerate(cam_ids):
                    if i < len(results):
                        # 결과 파싱
                        detected_objects = self._parse_result(results[i])
                        
                        # 큐에 넣기 (큐 가득 차면 오래된 결과 버림)
                        if self.output_queues[cam_id].full():
                            try:
                                self.output_queues[cam_id].get_nowait()
                            except queue.Empty:
                                pass
                        
                        self.output_queues[cam_id].put(detected_objects)
            
            except Exception as e:
                log(f"배치 추론 오류: {e}")
    
    def _parse_result(self, result) -> List[DetectedObject]:
        """YOLO 결과 파싱"""
        detected_objects = []
        
        try:
            boxes = result.boxes
            
            if boxes is None or len(boxes) == 0:
                return detected_objects
            
            # Tracking ID 확인
            if boxes.id is None:
                # Tracking 실패 - 기본 ID 사용
                xyxy = boxes.xyxy.cpu().numpy()
                conf = boxes.conf.cpu().numpy()
                cls = boxes.cls.cpu().numpy().astype(int)
                
                for idx, (box, confidence, class_id) in enumerate(zip(xyxy, conf, cls)):
                    if class_id >= len(self.CLASS_NAMES):
                        continue
                    
                    x1, y1, x2, y2 = map(int, box)
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    
                    detected_obj = DetectedObject(
                        id=idx,
                        class_name=self.CLASS_NAMES[class_id],
                        center=(center_x, center_y),
                        bbox=(x1, y1, x2, y2),
                        confidence=float(confidence)
                    )
                    detected_objects.append(detected_obj)
                
                return detected_objects
            
            # GPU에서 배치 연산 (최적화)
            with torch.no_grad():
                # GPU에서 배치 연산
                xyxy_gpu = boxes.xyxy
                centers_gpu = torch.stack([
                    (xyxy_gpu[:, 0] + xyxy_gpu[:, 2]) / 2,
                    (xyxy_gpu[:, 1] + xyxy_gpu[:, 3]) / 2
                ], dim=1).int()
                
                # CPU로 변환
                xyxy = xyxy_gpu.cpu().numpy()
                centers = centers_gpu.cpu().numpy()
                conf = boxes.conf.cpu().numpy()
                cls = boxes.cls.cpu().numpy().astype(int)
                track_ids = boxes.id.cpu().numpy().astype(int)
            
            # 객체 생성
            for i in range(len(xyxy)):
                if cls[i] >= len(self.CLASS_NAMES):
                    continue
                
                detected_obj = DetectedObject(
                    id=int(track_ids[i]),
                    class_name=self.CLASS_NAMES[cls[i]],
                    center=(int(centers[i][0]), int(centers[i][1])),
                    bbox=tuple(map(int, xyxy[i])),
                    confidence=float(conf[i])
                )
                detected_objects.append(detected_obj)
        
        except Exception as e:
            log(f"결과 파싱 오류: {e}")
        
        return detected_objects
    
    def put_frame(self, camera_id: int, frame: np.ndarray):
        """프레임 입력 (카메라 스레드에서 호출)"""
        if camera_id >= self.num_cameras:
            return
        
        # 큐가 가득 차면 오래된 프레임 버림
        if self.input_queues[camera_id].full():
            try:
                dropped_frame = self.input_queues[camera_id].get_nowait()
                log(f"카메라 {camera_id} 프레임 드롭 발생")
            except queue.Empty:
                pass
        
        self.input_queues[camera_id].put(frame)
    
    def get_result(self, camera_id: int) -> Optional[List[DetectedObject]]:
        """결과 가져오기 (카메라 스레드에서 호출)"""
        if camera_id >= self.num_cameras:
            return None
        
        try:
            return self.output_queues[camera_id].get_nowait()
        except queue.Empty:
            return None
    
    def stop(self):
        """중지"""
        log("BatchAIManager 중지 중...")
        self.running = False
        
        if self.inference_thread and self.inference_thread.is_alive():
            self.inference_thread.join(timeout=2.0)
        
        log("BatchAIManager 중지 완료")
    
    def get_stats(self) -> Dict:
        """통계 정보 반환"""
        avg_batch = self.total_inferences / self.batch_count if self.batch_count > 0 else 0
        return {
            'total_inferences': self.total_inferences,
            'batch_count': self.batch_count,
            'avg_batch_size': avg_batch
        }
