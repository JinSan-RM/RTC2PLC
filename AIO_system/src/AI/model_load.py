"""
모델 로더
"""
import os
import torch
from ultralytics import YOLO
from src.utils.logger import log

def load_yolov11(model_path, half_precision=True, force_device: str = "auto"):
    """YOLOv11 모델 로드 (장치 선택 가능)"""
    try:
        # 장치 선택 우선순위: force_device > auto
        req_device = (force_device or "auto").strip().lower()
        if req_device not in ("auto", "cpu", "cuda"):
            log(f"[WARNING] Unknown force_device='{force_device}', fallback to auto")
            req_device = "auto"

        if req_device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        elif req_device == "cuda":
            if torch.cuda.is_available():
                device = "cuda"
            else:
                log("[WARNING] CUDA requested but unavailable, fallback to CPU")
                device = "cpu"
        else:
            device = "cpu"

        log(f"PyTorch 버전: {torch.__version__}")
        log(f"CUDA 사용 가능: {torch.cuda.is_available()}")
        log(f"요청 장치: {req_device.upper()}")

        if torch.cuda.is_available():
            log(f"GPU 장치: {torch.cuda.get_device_name(0)}")
            log(f"GPU 메모리: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")

        # YOLOv11 모델 로드
        log(f"\nYOLOv11 모델 로드 중: {model_path}")
        model = YOLO(model_path, task="detect")

        ext = os.path.splitext(model_path)[1].lower()

        # TensorRT engine은 CPU 강제가 불가하므로 .pt/.onnx 사용 권장
        if ext == ".engine" and device == "cpu":
            log("[WARNING] TensorRT .engine은 CPU 강제 실행이 어렵습니다. .pt 모델 사용 권장")
        elif ext != ".engine":
            model.to(device)

        # Ultralytics 내부 추론 기본 장치도 명시적으로 고정
        model.overrides["device"] = device

        log("YOLOv11 모델 로드 성공!")
        log(f"사용 장치: {device.upper()}")

        return model, device

    except Exception as e:
        log(f"모델 로드 실패: {e}")
        return None, None
