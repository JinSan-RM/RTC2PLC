import cv2
import numpy as np
from ultralytics import YOLO
import torch
from pypylon import pylon
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import json
import os
from XGT_run import XGTTester
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vision_plc_actions.log'),
        logging.StreamHandler()
    ]
)

def load_yolov11(model_path):
    """YOLOv11 모델 로드 (GPU 우선)"""
    try:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"PyTorch 버전: {torch.__version__}")
        print(f"CUDA 사용 가능: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            print(f"GPU 장치: {torch.cuda.get_device_name(0)}")
            print(f"GPU 메모리: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
        
        print(f"\nYOLOv11 모델 로드 중: {model_path}")
        model = YOLO(model_path)
        model.to(device)
        
        print(f"YOLOv11 모델 로드 성공!")
        print(f"사용 장치: {device.upper()}")
        
        return model, device
        
    except Exception as e:
        print(f"모델 로드 실패: {e}")
        return None, None

@dataclass
class DetectedObject:
    """감지된 플라스틱 객체 정보"""
    id: int
    class_name: str
    center: Tuple[int, int]
    bbox: Tuple[int, int, int, int]
    confidence: float
    metainfo: Optional[Dict] = None

class PlasticClassifier:
    """AI Hub 플라스틱 4종 분류기"""
    
    PLASTIC_CLASSES = {
        'PET': '폴리에틸렌 테레프탈레이트',
        'PE': '폴리에틸렌',
        'PP': '폴리프로필렌',
        'PS': '폴리스티렌'
    }
    
    # PLC 주소 매핑 (Breeze_predict.py와 동일한 방식)
    # PLASTIC_VALUE_MAPPING = {
    #     "HDPE": 0x88,
    #     "PS": 0x88,
    #     "PP": 0x88,
    #     "LDPE": 0x88,
    #     "ABS": 0x88,
    #     "PET": 0x88,
    #     "PE": 0x88,
    #     "_": 0x88,
    # }
    PLASTIC_VALUE_MAPPING = {
        "PE": 0x94,
        "PS": 0x94,
        "PP": 0x94,
        "PET": 0x94,
        "_": 0x88,
    }
    @classmethod
    def get_plastic_info(cls, class_name: str) -> str:
        return cls.PLASTIC_CLASSES.get(class_name, '알 수 없는 플라스틱')
    
    @classmethod
    def get_plc_address(cls, class_name: str) -> Optional[int]:
        """클래스명에 해당하는 PLC 주소 반환"""
        return cls.PLASTIC_VALUE_MAPPING.get(class_name.upper())
    
    @classmethod
    def parse_metainfo(cls, metainfo_name: str) -> Dict:
        try:
            parts = metainfo_name.split('_')
            return {
                'container_type': parts[0] if len(parts) > 0 else '기타',
                'transparency': parts[1] if len(parts) > 1 else '불투명',
                'shape': parts[2] if len(parts) > 2 else '기타',
                'size': parts[3] if len(parts) > 3 else '기타',
                'compression': parts[4] if len(parts) > 4 else '비압축'
            }
        except:
            return {'container_type': '기타', 'transparency': '불투명', 'shape': '기타', 'size': '기타', 'compression': '비압축'}

class LineCounter:
    """컨베이어 벨트 스타일 카운팅 라인 + PLC 통신"""
    
    def __init__(self, line_start: Tuple[int, int], line_end: Tuple[int, int], 
                 thickness: int = 3, buffer_zone: int = 50):
                #  thickness: int = 3, buffer_zone: int = 50, xgt_tester: Optional[XGTTester] = None):
        self.line_start = line_start
        self.line_end = line_end
        self.thickness = thickness
        self.buffer_zone = buffer_zone
        self.tracked_objects = {}
        self.crossed_objects = set()
        
        # PLC 통신 객체
        # self.xgt = xgt_tester
        
        self.class_counts = {
            'PET': 0, 'PE': 0, 'PP': 0, 'PS': 0
        }
        self.detailed_stats = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        
    def is_line_crossed(self, obj_id: int, center: Tuple[int, int], class_name: str) -> bool:
        """라인 교차 체크 및 PLC 신호 전송"""
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
                
                # PLC 신호 전송
                # self._send_plc_signal(class_name)
                
                return True
        
        self.tracked_objects[obj_id] = {
            'side': current_side,
            'center': center,
            'last_seen': time.time()
        }
        return False
    
    def _send_plc_signal(self, class_name: str):
        """PLC에 신호 전송 (Breeze_predict.py 방식)"""
        if self.xgt is None:
            logging.warning("XGT 객체가 초기화되지 않았습니다.")
            return
        
        plc_value = PlasticClassifier.get_plc_address(class_name)
        
        if plc_value is None:
            logging.warning(f"PLC 주소를 찾을 수 없습니다: {class_name}")
            return
        
        # try:
        #     # 새로운 비트 ON
        #     success = self.xgt.write_bit_packet(address=0x81, onoff=1)
        #     success = self.xgt.write_bit_packet(address=plc_value, onoff=1)
            
        #     if success:
        #         # 0.1초 후 OFF 스케줄링
        #         self.xgt.schedule_bit_off(address=0x81, delay=0.1)
        #         self.xgt.schedule_bit_off(address=plc_value, delay=0.1)
        #         logging.info(f" PLC 신호 전송 성공: P{plc_value:3X} ({class_name})")
        #     else:
        #         logging.warning(f" PLC 신호 전송 실패: {class_name}")
                
        # except Exception as e:
        #     logging.error(f" PLC 통신 오류: {e}")
    
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

class PlasticSortingSystem:
    """AI Hub 플라스틱 자동 선별 시스템"""
    
    def __init__(self):
        self.sorting_actions = {
            'PET': self.handle_pet,
            'PE': self.handle_pe,
            'PP': self.handle_pp,
            'PS': self.handle_ps
        }
        self.sorting_log = []
        self.bins = {
            'PET': {'count': 0, 'bin_id': 'A', 'color': (0, 165, 255)},
            'PE': {'count': 0, 'bin_id': 'B', 'color': (255, 0, 0)},
            'PP': {'count': 0, 'bin_id': 'C', 'color': (0, 255, 0)},
            'PS': {'count': 0, 'bin_id': 'D', 'color': (255, 0, 255)}
        }
    
    def execute_sorting(self, class_name: str, metainfo: Dict = None):
        if class_name in self.sorting_actions:
            self.sorting_actions[class_name](metainfo)
        else:
            self.handle_unknown(class_name, metainfo)
    
    def handle_pet(self, metainfo: Dict = None):
        self.bins['PET']['count'] += 1
    
    def handle_pe(self, metainfo: Dict = None):
        self.bins['PE']['count'] += 1
    
    def handle_pp(self, metainfo: Dict = None):
        self.bins['PP']['count'] += 1
    
    def handle_ps(self, metainfo: Dict = None):
        self.bins['PS']['count'] += 1
    
    def handle_unknown(self, class_name: str, metainfo: Dict = None):
        pass

class BaslerCameraManager:
    """Basler 산업용 카메라 관리"""
    
    def __init__(self, camera_index: int = 0):
        self.camera = None
        self.converter = None
        self.camera_index = camera_index
        self.is_connected = False
    
    def initialize(self, camera_ip: str = None) -> bool:
        try:
            tlFactory = pylon.TlFactory.GetInstance()
            
            if camera_ip:
                device_info = pylon.DeviceInfo()
                device_info.SetIpAddress(camera_ip)
                self.camera = pylon.InstantCamera(tlFactory.CreateDevice(device_info))
            else:
                devices = tlFactory.EnumerateDevices()
                if not devices:
                    return False
                if self.camera_index >= len(devices):
                    return False
                self.camera = pylon.InstantCamera(tlFactory.CreateDevice(devices[self.camera_index]))
            
            self.camera.Open()
            self.setup_camera_parameters()
            
            self.converter = pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            
            self.is_connected = True
            print(f"Basler 카메라 연결 성공!")
            return True
        except Exception as e:
            print(f"카메라 연결 실패: {e}")
            return False
    
    def setup_camera_parameters(self):
        """카메라 파라미터 설정 - FPS 최적화"""
        try:
            print("\nBasler 카메라 설정 시작...")
            
            self.camera.MaxNumBuffer.Value = 5
            print("버퍼 크기: 5")
            
            max_width = self.camera.Width.Max
            max_height = self.camera.Height.Max
            target_width = min(1280, max_width)
            target_height = min(720, max_height)
            
            self.camera.Width.Value = target_width
            self.camera.Height.Value = target_height
            print(f"해상도: {target_width}x{target_height}")
            
            try:
                if hasattr(self.camera, 'ExposureAuto'):
                    self.camera.ExposureAuto.SetValue('Off')
                    print(f"자동 노출: Off")
            except Exception as e:
                print(f"자동 노출 설정 실패: {e}")
            
            try:
                if hasattr(self.camera, 'ExposureTime'):
                    current_exposure = self.camera.ExposureTime.GetValue()
                    print(f"  • 현재 노출 시간: {current_exposure:.0f}μs ({1000000/current_exposure:.1f} fps 제한)")
                    
                    target_exposure = 10000
                    min_exposure = self.camera.ExposureTime.Min
                    max_exposure = self.camera.ExposureTime.Max
                    
                    new_exposure = max(min_exposure, min(target_exposure, max_exposure))
                    self.camera.ExposureTime.SetValue(new_exposure)
                    
                    actual_exposure = self.camera.ExposureTime.GetValue()
                    max_fps = 1000000 / actual_exposure
                    print(f"새 노출 시간: {actual_exposure:.0f}μs (최대 {max_fps:.1f} fps)")
            except Exception as e:
                print(f"노출 시간 설정 실패: {e}")
            
            try:
                if hasattr(self.camera, 'GainAuto'):
                    self.camera.GainAuto.SetValue('Off')
                    print(f"자동 게인: Off")
            except Exception as e:
                print(f"자동 게인 설정 실패: {e}")
            
            try:
                if hasattr(self.camera, 'TriggerMode'):
                    self.camera.TriggerMode.SetValue('Off')
                    print(f"트리거 모드: Off")
            except Exception as e:
                print(f"트리거 모드 설정 실패: {e}")
            
            try:
                if hasattr(self.camera, 'AcquisitionMode'):
                    self.camera.AcquisitionMode.SetValue('Continuous')
                    print(f"Acquisition Mode: Continuous")
            except Exception as e:
                print(f"Acquisition 모드 설정 실패: {e}")
            
            print(" 카메라 설정 완료!\n")
            
        except Exception as e:
            print(f" 카메라 설정 오류: {e}")
    
    def grab_frame(self) -> Optional[np.ndarray]:
        if not self.is_connected or not self.camera:
            return None
        try:
            if self.camera and self.camera.IsGrabbing():
                grabResult = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
                if grabResult.GrabSucceeded():
                    image = self.converter.Convert(grabResult)
                    frame = image.GetArray()
                    grabResult.Release()
                    return frame
                else:
                    grabResult.Release()
        except Exception as e:
            print(f"프레임 캡처 오류: {e}")
        return None
    
    def start_grabbing(self):
        if self.camera and self.is_connected:
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    
    def stop_grabbing(self):
        if self.camera and self.is_connected:
            self.camera.StopGrabbing()
    
    def close(self):
        try:
            if self.camera and self.camera.IsOpen():
                if self.camera.IsGrabbing():
                    self.camera.StopGrabbing()
                self.camera.Close()
            self.is_connected = False
        except Exception as e:
            print(f"카메라 해제 오류: {e}")

class AIHubPlasticDetectionSystem:
    """YOLOv11 기반 AI Hub 플라스틱 감지 시스템 (GPU 가속 + PLC 통신)"""
    
    CLASS_NAMES = ['PET', 'PS', 'PP', 'PE']
    
    def __init__(self, model_path: str, confidence_threshold: float = 0.7, img_size: int = 640, 
                 plc_ip: str = '192.168.1.3', plc_port: int = 2004):
        self.model, self.device = load_yolov11(model_path)
        if self.model is None:
            raise RuntimeError("YOLOv11 모델 로드 실패")
        
        self.confidence_threshold = confidence_threshold
        self.img_size = img_size
        self.camera_manager = BaslerCameraManager()
        self.line_counter = None
        self.sorting_system = PlasticSortingSystem()
        
        # PLC 통신 초기화
        # self.xgt = XGTTester(ip=plc_ip, port=plc_port)
        # logging.info(f"PLC 연결 시도: {plc_ip}:{plc_port}")
        # if not self.xgt.connect():
        #     logging.warning(" PLC 연결 실패. PLC 없이 계속 진행합니다.")
        # else:
        #     logging.info(" PLC 연결 성공!")
        
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.current_fps = 0
        self.total_processed = 0
        
        # 모델 워밍업
        print("모델 워밍업 중...")
        dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
        for _ in range(3):
            _ = self.model.predict(dummy_img, verbose=False, device=self.device, imgsz=self.img_size)
        print("워밍업 완료!")
        
        # 모델 클래스명 가져오기
        if hasattr(self.model, 'names'):
            self.CLASS_NAMES = [self.model.names[i].upper() for i in range(len(self.model.names))]
            print(f"모델 클래스: {self.CLASS_NAMES}")
    
    def detect(self, frame: np.ndarray) -> List[DetectedObject]:
        """YOLOv11을 사용한 객체 감지 + 추적 (GPU 가속)"""
        try:
            # YOLOv11 추론 + 추적
            results = self.model.track(
                source=frame,
                conf=self.confidence_threshold,
                imgsz=self.img_size,
                device=self.device,
                verbose=False,
                half=True,
                max_det=100,
                persist=True,
                tracker="bytetrack.yaml"
            )
            
            detected_objects = []
            
            for result in results:
                boxes = result.boxes
                
                if boxes is None or len(boxes) == 0:
                    continue
                
                if boxes.id is None:
                    xyxy = boxes.xyxy.cpu().numpy()
                    conf = boxes.conf.cpu().numpy()
                    cls = boxes.cls.cpu().numpy().astype(int)
                    
                    for idx, (box, confidence, class_id) in enumerate(zip(xyxy, conf, cls)):
                        if class_id >= len(self.CLASS_NAMES):
                            continue
                        
                        class_name = self.CLASS_NAMES[class_id]
                        x1, y1, x2, y2 = map(int, box)
                        center_x = (x1 + x2) // 2
                        center_y = (y1 + y2) // 2
                        
                        detected_obj = DetectedObject(
                            id=idx,
                            class_name=class_name,
                            center=(center_x, center_y),
                            bbox=(x1, y1, x2, y2),
                            confidence=float(confidence)
                        )
                        detected_objects.append(detected_obj)
                    continue
                
                xyxy = boxes.xyxy.cpu().numpy()
                conf = boxes.conf.cpu().numpy()
                cls = boxes.cls.cpu().numpy().astype(int)
                track_ids = boxes.id.cpu().numpy().astype(int)
                
                for box, confidence, class_id, track_id in zip(xyxy, conf, cls, track_ids):
                    if class_id >= len(self.CLASS_NAMES):
                        continue
                    
                    class_name = self.CLASS_NAMES[class_id]
                    x1, y1, x2, y2 = map(int, box)
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    
                    detected_obj = DetectedObject(
                        id=int(track_id),
                        class_name=class_name,
                        center=(center_x, center_y),
                        bbox=(x1, y1, x2, y2),
                        confidence=float(confidence)
                    )
                    detected_objects.append(detected_obj)
            
            return detected_objects
            
        except Exception as e:
            print(f"감지 오류: {e}")
            return []
    
    def setup_conveyor_line(self, frame_shape: Tuple[int, int]):
        """컨베이어 라인 설정 (XGT 객체 전달)"""
        height, width = frame_shape[:2]
        line_start = (width // 2, height // 4)
        line_end = (width // 2, 6 * height // 4)
        # self.line_counter = LineCounter(line_start, line_end, buffer_zone=60, xgt_tester=self.xgt)
        self.line_counter = LineCounter(line_start, line_end, buffer_zone=60)
    
    def draw_detections(self, frame: np.ndarray, detected_objects: List[DetectedObject]) -> np.ndarray:
        """감지 결과 그리기"""
        class_colors = {
            'PET': (0, 165, 255),
            'PE': (255, 0, 0),
            'PP': (0, 255, 0),
            'PS': (255, 0, 255)
        }
        
        for obj in detected_objects:
            x1, y1, x2, y2 = obj.bbox
            color = class_colors.get(obj.class_name, (128, 128, 128))
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, obj.center, 5, (0, 0, 255), -1)
            
            label = f"{obj.class_name}: {obj.confidence:.2f}"
            cv2.putText(frame, label, (x1, y1 - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        return frame
    
    def draw_ui(self, frame: np.ndarray) -> np.ndarray:
        """UI 그리기"""
        height, width = frame.shape[:2]
        
        self.fps_counter += 1
        if time.time() - self.fps_start_time >= 1.0:
            self.current_fps = self.fps_counter
            self.fps_counter = 0
            self.fps_start_time = time.time()
        
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (550, 200), (0, 0, 0), -1)
        frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
        
        device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
        # plc_status = "Connected" if self.xgt.connected else "Disconnected"
        # plc_color = (0, 255, 0) if self.xgt.connected else (0, 0, 255)
        
        cv2.putText(frame, f"YOLOv11 + PLC ({device_name})", (10, 25), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        # cv2.putText(frame, f"PLC: {plc_status}", (10, 50), 
        #            cv2.FONT_HERSHEY_SIMPLEX, 0.5, plc_color, 2)
        cv2.putText(frame, f"FPS: {self.current_fps} | Total: {self.total_processed}", 
                   (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        y_offset = 100
        if self.line_counter:
            for class_name, count in self.line_counter.class_counts.items():
                color = self.sorting_system.bins[class_name]['color']
                bin_id = self.sorting_system.bins[class_name]['bin_id']
                cv2.putText(frame, f"{class_name}({bin_id}): {count}", 
                           (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                y_offset += 25
        
        cv2.putText(frame, "Press 'q':Quit | 'r':Reset | 's':Stats", 
                   (10, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        return frame
    
    def run(self):
        """메인 실행 루프"""
        print("AI Hub 플라스틱 감지 시스템 시작 (YOLOv11 + GPU + PLC)")
        
        timing_grab = []
        timing_inference = []
        timing_draw = []
        timing_total = []
        
        camera_ip = None
        if not self.camera_manager.initialize(camera_ip=camera_ip):
            print("Basler 카메라 실패. 웹캠 사용")
            
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            
            if not cap.isOpened():
                print("카메라 인덱스 0 실패, 인덱스 1 시도...")
                cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
            
            if not cap.isOpened():
                print(" 사용 가능한 카메라를 찾을 수 없습니다.")
                return
            
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 60)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = cap.get(cv2.CAP_PROP_FPS)
            print(f"카메라 설정: {actual_width}x{actual_height} @ {actual_fps}fps")
            
            use_basler = False
        else:
            self.camera_manager.start_grabbing()
            use_basler = True
        
        try:
            print("시스템 준비 완료. 플라스틱 감지 시작...")
            print("타이밍 측정 활성화 - 100 프레임 후 통계 출력\n")
            
            frame_count = 0
            
            while True:
                t_total_start = time.time()
                
                # 1. 프레임 획득 시간
                t1 = time.time()
                if use_basler:
                    frame = self.camera_manager.grab_frame()
                    if frame is None:
                        continue
                else:
                    ret, frame = cap.read()
                    if not ret:
                        break
                t2 = time.time()
                timing_grab.append((t2 - t1) * 1000)
                
                if self.line_counter is None:
                    self.setup_conveyor_line(frame.shape)
                
                # 2. 추론 시간
                t3 = time.time()
                detected_objects = self.detect(frame)
                t4 = time.time()
                timing_inference.append((t4 - t3) * 1000)
                
                # 라인 크로싱 체크 (PLC 신호 전송 포함)
                for obj in detected_objects:
                    if self.line_counter.is_line_crossed(obj.id, obj.center, obj.class_name):
                        metainfo = PlasticClassifier.parse_metainfo("기본_투명_병류_대_비압축")
                        self.line_counter.update_stats(obj.class_name, metainfo)
                        self.sorting_system.execute_sorting(obj.class_name, metainfo)
                        self.total_processed += 1
                
                # 기존 ON 비트들 OFF
                # self.xgt.process_bit_off()

                # 30프레임마다 정리
                frame_count += 1
                if frame_count % 30 == 0:
                    self.line_counter.cleanup_old_tracks()
                
                # 3. 그리기 시간
                t5 = time.time()
                frame = self.draw_detections(frame, detected_objects)
                frame = self.line_counter.draw_line(frame)
                frame = self.draw_ui(frame)
                
                cv2.imshow('YOLOv11 + PLC Detection', frame)
                t6 = time.time()
                timing_draw.append((t6 - t5) * 1000)
                
                timing_total.append((time.time() - t_total_start) * 1000)
                
                # 100프레임마다 타이밍 통계 출력
                if frame_count == 100:
                    print("\n" + "="*70)
                    print("  타이밍 분석 (100 프레임 평균)")
                    print("="*70)
                    print(f"{'구간':<20} {'평균(ms)':<15} {'예상 FPS':<15}")
                    print("-"*70)
                    print(f"{'프레임 획득':<20} {np.mean(timing_grab):>10.2f}ms    {1000/np.mean(timing_grab):>10.1f} fps")
                    print(f"{'추론':<20} {np.mean(timing_inference):>10.2f}ms    {1000/np.mean(timing_inference):>10.1f} fps")
                    print(f"{'그리기+표시':<20} {np.mean(timing_draw):>10.2f}ms    {1000/np.mean(timing_draw):>10.1f} fps")
                    print(f"{'전체':<20} {np.mean(timing_total):>10.2f}ms    {1000/np.mean(timing_total):>10.1f} fps")
                    print("="*70)
                    
                    timing_grab.clear()
                    timing_inference.clear()
                    timing_draw.clear()
                    timing_total.clear()
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.line_counter.class_counts = {'PET': 0, 'PE': 0, 'PP': 0, 'PS': 0}
                    self.line_counter.crossed_objects.clear()
                    for bin_info in self.sorting_system.bins.values():
                        bin_info['count'] = 0
                    self.sorting_system.sorting_log.clear()
                    self.total_processed = 0
                elif key == ord('s'):
                    self.print_statistics()
        
        except KeyboardInterrupt:
            print("\n시스템 중단")
        except Exception as e:
            print(f"\n시스템 오류: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # PLC 연결 종료
            # if self.xgt.connected:
            #     logging.info("PLC 연결 종료 중...")
            #     self.xgt.disconnect()
            
            if use_basler:
                self.camera_manager.stop_grabbing()
                self.camera_manager.close()
            else:
                cap.release()
            cv2.destroyAllWindows()
    
    def print_statistics(self):
        """통계 출력"""
        print("\n" + "="*60)
        print("AI Hub 플라스틱 감지 시스템 통계")
        print("="*60)
        total_count = sum(self.line_counter.class_counts.values())
        print(f"총 처리량: {total_count}개")
        print(f"현재 FPS: {self.current_fps}")
        print(f"사용 장치: {self.device.upper()}")
        # print(f"PLC 상태: {'연결됨' if self.xgt.connected else '연결 끊김'}")
        if torch.cuda.is_available():
            print(f"GPU 메모리 사용량: {torch.cuda.memory_allocated(0) / 1024**2:.2f} MB")

if __name__ == "__main__":
    print("AI Hub 플라스틱 감지 시스템 v5.0 (YOLOv11 + GPU + PLC)")
    
    model_path = "C:/Users/USER/Desktop/기존파일백업/RTC2PLC/prototype/runs/detect/plastic_detector4/weights/best.pt"
    
    if not os.path.exists(model_path):
        print(f"\n 모델 파일을 찾을 수 없습니다: {model_path}")
        exit(1)
    
    try:
        detector = AIHubPlasticDetectionSystem(
            model_path=model_path,
            confidence_threshold=0.7,
            img_size=640,
            plc_ip='192.168.1.3',  # PLC IP 주소
            plc_port=2004           # PLC 포트
        )
        detector.run()
    except Exception as e:
        print(f"\n오류: {e}")
        import traceback
        traceback.print_exc()
