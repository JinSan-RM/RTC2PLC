import torch
from ultralytics import YOLO

def load_yolov11(model_path):
    """YOLOv11 모델 로드 (GPU 우선)"""
    try:
        # CUDA 사용 가능 여부 확인
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"PyTorch 버전: {torch.__version__}")
        print(f"CUDA 사용 가능: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            print(f"GPU 장치: {torch.cuda.get_device_name(0)}")
            print(f"GPU 메모리: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
        
        # YOLOv11 모델 로드
        print(f"\nYOLOv11 모델 로드 중: {model_path}")
        model = YOLO(model_path)
        
        # GPU로 모델 이동
        model.to(device)
        
        print(f"✅ YOLOv11 모델 로드 성공!")
        print(f"🎮 사용 장치: {device.upper()}")
        
        return model, device
        
    except Exception as e:
        print(f"모델 로드 실패: {e}")
        return None, None
