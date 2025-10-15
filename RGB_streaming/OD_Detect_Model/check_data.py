import cv2
import numpy as np
from ultralytics import YOLO
import torch
import time
import os

def diagnose_performance(model_path):
    """성능 병목 지점 진단"""
    
    print("="*70)
    print("🔍 YOLOv11 성능 진단 시작")
    print("="*70)
    
    # 1. GPU 확인
    print("\n[1] GPU 상태 확인")
    print(f"  CUDA 사용 가능: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  GPU 이름: {torch.cuda.get_device_name(0)}")
        print(f"  GPU 메모리: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
        print(f"  현재 할당 메모리: {torch.cuda.memory_allocated(0) / 1024**2:.2f} MB")
    
    # 2. 모델 로드
    print("\n[2] 모델 로드")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = YOLO(model_path)
    model.to(device)
    
    import os
    print(f"  모델 크기: {os.path.getsize(model_path) / 1024 / 1024:.2f} MB")
    print(f"  사용 디바이스: {device}")
    
    # 3. 워밍업
    print("\n[3] 모델 워밍업 (3회)")
    dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
    for i in range(3):
        _ = model.predict(dummy_img, verbose=False, device=device)
        print(f"  워밍업 {i+1}/3 완료")
    
    # 4. 각 해상도별 추론 속도 측정
    print("\n[4] 해상도별 추론 속도 측정 (50회 평균)")
    
    test_sizes = [320, 480, 640, 1280]
    
    for img_size in test_sizes:
        test_img = np.random.randint(0, 255, (img_size, img_size, 3), dtype=np.uint8)
        
        times = []
        for _ in range(50):
            t1 = time.time()
            results = model.predict(
                test_img, 
                verbose=False, 
                device=device,
                imgsz=img_size,
                half=True  # FP16
            )
            t2 = time.time()
            times.append((t2 - t1) * 1000)
        
        avg_time = np.mean(times)
        fps = 1000 / avg_time
        print(f"  {img_size}x{img_size}: {avg_time:.2f}ms → {fps:.1f} FPS")
    
    # 5. 실제 카메라로 전체 파이프라인 측정
    print("\n[5] 전체 파이프라인 측정 (웹캠, 100프레임)")
    
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    timing = {
        'frame_grab': [],
        'inference': [],
        'draw': [],
        'imshow': [],
        'total': []
    }
    
    for i in range(100):
        t_total = time.time()
        
        # 프레임 획득
        t1 = time.time()
        ret, frame = cap.read()
        if not ret:
            break
        t2 = time.time()
        timing['frame_grab'].append((t2 - t1) * 1000)
        
        # 추론
        t3 = time.time()
        results = model.predict(frame, verbose=False, device=device, imgsz=640)
        t4 = time.time()
        timing['inference'].append((t4 - t3) * 1000)
        
        # 그리기
        t5 = time.time()
        annotated = results[0].plot()  # YOLOv11 내장 그리기
        t6 = time.time()
        timing['draw'].append((t6 - t5) * 1000)
        
        # 화면 출력
        t7 = time.time()
        cv2.imshow('Diagnosis', annotated)
        cv2.waitKey(1)
        t8 = time.time()
        timing['imshow'].append((t8 - t7) * 1000)
        
        timing['total'].append((time.time() - t_total) * 1000)
        
        if (i + 1) % 20 == 0:
            print(f"  진행: {i+1}/100 프레임")
    
    cap.release()
    cv2.destroyAllWindows()
    
    # 6. 결과 분석
    print("\n[6] 병목 분석 결과")
    print("="*70)
    
    total_avg = np.mean(timing['total'])
    
    print(f"\n{'구간':<20} {'평균(ms)':<12} {'비중(%)':<10} {'예상FPS':<10}")
    print("-"*70)
    
    for key, values in timing.items():
        if values:
            avg = np.mean(values)
            percentage = (avg / total_avg) * 100
            fps = 1000 / avg if avg > 0 else 0
            print(f"{key:<20} {avg:>8.2f}ms    {percentage:>6.1f}%     {fps:>6.1f}")
    
    print("-"*70)
    print(f"{'전체 파이프라인':<20} {total_avg:>8.2f}ms              {1000/total_avg:>6.1f} FPS")
    print("="*70)
    
    # 7. 진단 및 권장사항
    print("\n[7] 진단 및 권장사항")
    print("="*70)
    
    inference_avg = np.mean(timing['inference'])
    frame_grab_avg = np.mean(timing['frame_grab'])
    draw_avg = np.mean(timing['draw'])
    imshow_avg = np.mean(timing['imshow'])
    
    bottleneck_found = False
    
    if inference_avg > total_avg * 0.5:
        print("\n⚠️  병목: 추론 시간 (전체의 50% 이상)")
        print(f"   현재: {inference_avg:.1f}ms")
        print("   해결책:")
        print("   1. img_size를 640 → 480 또는 320으로 줄이기")
        print("   2. YOLOv11m → YOLOv11s 또는 YOLOv11n으로 변경")
        print("   3. confidence threshold 높이기 (0.25 → 0.5)")
        bottleneck_found = True
    
    if frame_grab_avg > 30:
        print("\n⚠️  병목: 프레임 획득")
        print(f"   현재: {frame_grab_avg:.1f}ms")
        print("   해결책:")
        print("   1. 카메라 해상도 낮추기")
        print("   2. 카메라 FPS 설정 확인")
        bottleneck_found = True
    
    if draw_avg > 20:
        print("\n⚠️  병목: 그리기 연산")
        print(f"   현재: {draw_avg:.1f}ms")
        print("   해결책:")
        print("   1. bbox 그리기 최소화")
        print("   2. UI 간소화")
        bottleneck_found = True
    
    if imshow_avg > 15:
        print("\n⚠️  병목: 화면 출력")
        print(f"   현재: {imshow_avg:.1f}ms")
        print("   해결책:")
        print("   1. 화면 해상도 낮추기")
        print("   2. cv2.waitKey(1) 제거 고려")
        bottleneck_found = True
    
    if not bottleneck_found:
        print("\n✅ 주요 병목 지점이 발견되지 않았습니다.")
        print("   모든 구간이 균형적으로 처리되고 있습니다.")
    
    print("\n" + "="*70)
    print("진단 완료!")
    print("="*70)

if __name__ == "__main__":
    model_path = "C:/Users/USER/Desktop/기존파일백업/RTC2PLC/prototype/runs/detect/plastic_detector4/weights/best.pt"
    
    if not os.path.exists(model_path):
        print(f"❌ 모델 파일을 찾을 수 없습니다: {model_path}")
        exit(1)
    
    diagnose_performance(model_path)