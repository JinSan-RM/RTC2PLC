import torch
from ultralytics import YOLO
from src.utils.logger import log

def load_yolov11(model_path, half_precision=True):
    """YOLOv11 모델 로드 (GPU 우선)"""
    try:
        # CUDA 사용 가능 여부 확인
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        log(f"PyTorch 버전: {torch.__version__}")
        log(f"CUDA 사용 가능: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            log(f"GPU 장치: {torch.cuda.get_device_name(0)}")
            log(f"GPU 메모리: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
        
        # YOLOv11 모델 로드
        log(f"\nYOLOv11 모델 로드 중: {model_path}")
        model = YOLO(model_path)
        
        # GPU로 모델 이동
        model.to(device)
        
        # FP16 최적화 (GPU 메모리 50% 절감 + 속도 2배 예상)
        # if half_precision and device == 'cuda':
        #     model.model.half()
        
        log(f"✅ YOLOv11 모델 로드 성공!")
        log(f"🎮 사용 장치: {device.upper()}")
        
        return model, device
        
    except Exception as e:
        log(f"모델 로드 실패: {e}")
        return None, None
