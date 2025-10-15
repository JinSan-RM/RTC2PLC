import torch

def check_cuda():
    """CUDA 및 GPU 사용 가능 여부 체크"""
    
    print("=" * 60)
    print("CUDA & GPU 확인")
    print("=" * 60)
    
    # PyTorch 버전
    print(f"\n📦 PyTorch 버전: {torch.__version__}")
    
    # CUDA 사용 가능 여부
    cuda_available = torch.cuda.is_available()
    print(f"\n🔧 CUDA 사용 가능: {cuda_available}")
    
    if cuda_available:
        # CUDA 버전
        print(f"📌 CUDA 버전: {torch.version.cuda}")
        
        # cuDNN 버전
        print(f"📌 cuDNN 버전: {torch.backends.cudnn.version()}")
        
        # GPU 개수
        gpu_count = torch.cuda.device_count()
        print(f"\n🎮 사용 가능한 GPU 개수: {gpu_count}")
        
        # 각 GPU 정보
        print("\n" + "=" * 60)
        print("GPU 상세 정보")
        print("=" * 60)
        for i in range(gpu_count):
            print(f"\n[GPU {i}]")
            print(f"  이름: {torch.cuda.get_device_name(i)}")
            print(f"  총 메모리: {torch.cuda.get_device_properties(i).total_memory / 1024**3:.2f} GB")
            
            # 현재 메모리 사용량
            if torch.cuda.is_initialized():
                allocated = torch.cuda.memory_allocated(i) / 1024**3
                reserved = torch.cuda.memory_reserved(i) / 1024**3
                print(f"  할당된 메모리: {allocated:.2f} GB")
                print(f"  예약된 메모리: {reserved:.2f} GB")
        
        # 현재 사용 중인 GPU
        current_device = torch.cuda.current_device()
        print(f"\n✅ 현재 기본 GPU: {current_device} ({torch.cuda.get_device_name(current_device)})")
        
        # 간단한 CUDA 연산 테스트
        print("\n" + "=" * 60)
        print("CUDA 연산 테스트")
        print("=" * 60)
        try:
            x = torch.rand(1000, 1000).cuda()
            y = torch.rand(1000, 1000).cuda()
            z = x @ y
            print("✅ CUDA 연산 테스트 성공!")
            del x, y, z
            torch.cuda.empty_cache()
        except Exception as e:
            print(f"❌ CUDA 연산 테스트 실패: {e}")
        
        # YOLO 학습 권장 설정
        print("\n" + "=" * 60)
        print("YOLO 학습 권장 설정")
        print("=" * 60)
        print(f"✅ device=0 (또는 device={list(range(gpu_count))} for multi-GPU)")
        
        # 배치 크기 추천
        total_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
        if total_memory >= 24:
            print("✅ batch=32 이상 가능 (대용량 GPU)")
        elif total_memory >= 12:
            print("✅ batch=16~32 권장")
        elif total_memory >= 8:
            print("✅ batch=8~16 권장")
        else:
            print("✅ batch=-1 (자동 조정) 또는 batch=4~8 권장")
            
    else:
        print("\n❌ CUDA를 사용할 수 없습니다.")
        print("⚠️  CPU 모드로 학습됩니다 (매우 느림)")
        print("\n해결 방법:")
        print("  1. NVIDIA GPU가 설치되어 있는지 확인")
        print("  2. CUDA Toolkit 설치 확인")
        print("  3. PyTorch CUDA 버전 재설치:")
        print("     pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
        print("\n💡 YOLO 학습 설정: device='cpu'")
    
    print("\n" + "=" * 60)
    
    return cuda_available


def check_ultralytics_device():
    """Ultralytics에서 사용 가능한 디바이스 확인"""
    try:
        from ultralytics import YOLO
        from ultralytics.utils.torch_utils import select_device
        
        print("\n" + "=" * 60)
        print("Ultralytics 디바이스 확인")
        print("=" * 60)
        
        device = select_device('')  # 자동 선택
        print(f"✅ Ultralytics 기본 디바이스: {device}")
        
    except ImportError:
        print("\n⚠️  Ultralytics가 설치되지 않았습니다.")
        print("   설치: pip install ultralytics")


if __name__ == "__main__":
    # CUDA 체크
    cuda_available = check_cuda()
    
    # Ultralytics 디바이스 체크
    check_ultralytics_device()
    
    # 최종 요약
    print("\n" + "=" * 60)
    print("최종 요약")
    print("=" * 60)
    if cuda_available:
        print("✅ GPU 학습 가능!")
        print("   YOLO 학습 시: device=0")
    else:
        print("❌ CPU 학습만 가능")
        print("   YOLO 학습 시: device='cpu'")
    print("=" * 60)

def check_cuda():
    """CUDA 및 GPU 사용 가능 여부 체크"""
    
    print("=" * 60)
    print("CUDA & GPU 확인")
    print("=" * 60)
    
    # PyTorch 버전
    print(f"\n📦 PyTorch 버전: {torch.__version__}")
    
    # CUDA 사용 가능 여부
    cuda_available = torch.cuda.is_available()
    print(f"\n🔧 CUDA 사용 가능: {cuda_available}")
    
    if cuda_available:
        # CUDA 버전
        print(f"📌 CUDA 버전: {torch.version.cuda}")
        
        # cuDNN 버전
        print(f"📌 cuDNN 버전: {torch.backends.cudnn.version()}")
        
        # GPU 개수
        gpu_count = torch.cuda.device_count()
        print(f"\n🎮 사용 가능한 GPU 개수: {gpu_count}")
        
        # 각 GPU 정보
        print("\n" + "=" * 60)
        print("GPU 상세 정보")
        print("=" * 60)
        for i in range(gpu_count):
            print(f"\n[GPU {i}]")
            print(f"  이름: {torch.cuda.get_device_name(i)}")
            print(f"  총 메모리: {torch.cuda.get_device_properties(i).total_memory / 1024**3:.2f} GB")
            
            # 현재 메모리 사용량
            if torch.cuda.is_initialized():
                allocated = torch.cuda.memory_allocated(i) / 1024**3
                reserved = torch.cuda.memory_reserved(i) / 1024**3
                print(f"  할당된 메모리: {allocated:.2f} GB")
                print(f"  예약된 메모리: {reserved:.2f} GB")
        
        # 현재 사용 중인 GPU
        current_device = torch.cuda.current_device()
        print(f"\n✅ 현재 기본 GPU: {current_device} ({torch.cuda.get_device_name(current_device)})")
        
        # 간단한 CUDA 연산 테스트
        print("\n" + "=" * 60)
        print("CUDA 연산 테스트")
        print("=" * 60)
        try:
            x = torch.rand(1000, 1000).cuda()
            y = torch.rand(1000, 1000).cuda()
            z = x @ y
            print("✅ CUDA 연산 테스트 성공!")
            del x, y, z
            torch.cuda.empty_cache()
        except Exception as e:
            print(f"❌ CUDA 연산 테스트 실패: {e}")
        
        # YOLO 학습 권장 설정
        print("\n" + "=" * 60)
        print("YOLO 학습 권장 설정")
        print("=" * 60)
        print(f"✅ device=0 (또는 device={list(range(gpu_count))} for multi-GPU)")
        
        # 배치 크기 추천
        total_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
        if total_memory >= 24:
            print("✅ batch=32 이상 가능 (대용량 GPU)")
        elif total_memory >= 12:
            print("✅ batch=16~32 권장")
        elif total_memory >= 8:
            print("✅ batch=8~16 권장")
        else:
            print("✅ batch=-1 (자동 조정) 또는 batch=4~8 권장")
            
    else:
        print("\n❌ CUDA를 사용할 수 없습니다.")
        print("⚠️  CPU 모드로 학습됩니다 (매우 느림)")
        print("\n해결 방법:")
        print("  1. NVIDIA GPU가 설치되어 있는지 확인")
        print("  2. CUDA Toolkit 설치 확인")
        print("  3. PyTorch CUDA 버전 재설치:")
        print("     pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
        print("\n💡 YOLO 학습 설정: device='cpu'")
    
    print("\n" + "=" * 60)
    
    return cuda_available


def check_ultralytics_device():
    """Ultralytics에서 사용 가능한 디바이스 확인"""
    try:
        from ultralytics import YOLO
        from ultralytics.utils.torch_utils import select_device
        
        print("\n" + "=" * 60)
        print("Ultralytics 디바이스 확인")
        print("=" * 60)
        
        device = select_device('')  # 자동 선택
        print(f"✅ Ultralytics 기본 디바이스: {device}")
        
    except ImportError:
        print("\n⚠️  Ultralytics가 설치되지 않았습니다.")
        print("   설치: pip install ultralytics")


if __name__ == "__main__":
    # CUDA 체크
    cuda_available = check_cuda()
    
    # Ultralytics 디바이스 체크
    check_ultralytics_device()
    
    # 최종 요약
    print("\n" + "=" * 60)
    print("최종 요약")
    print("=" * 60)
    if cuda_available:
        print("✅ GPU 학습 가능!")
        print("   YOLO 학습 시: device=0")
    else:
        print("❌ CPU 학습만 가능")
        print("   YOLO 학습 시: device='cpu'")
    print("=" * 60)