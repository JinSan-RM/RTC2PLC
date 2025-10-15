from ultralytics import YOLO

def train_yolo():
    """YOLO 모델 학습 함수"""
    
    # 모델 로드 (사전 학습된 가중치)
    model = YOLO("yolo11m.pt")
    
    # 학습 시작
    results = model.train(
        # 필수 설정
        data=r"D:\학습용 데이터\전처리\yolo_dataset\data.yaml",
        epochs=100,
        imgsz=640,
        
        # 배치 및 디바이스
        batch=32,              # RTX 5070 Ti: 16~32 권장
        # batch=-1,            # 자동 배치 크기 (메모리 60% 사용)
        device=0,              # GPU 0번 사용
        
        # 데이터 로딩
        workers=8,             # Windows는 4~8 권장 (8에서 에러나면 줄이기)
        
        # 최적화
        optimizer='AdamW',
        lr0=0.001,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        
        # Early Stopping
        patience=25,
        
        # 저장 설정
        project='runs/detect',
        name='plastic_detector',
        exist_ok=False,
        save=True,
        save_period=10,
        
        # 검증
        val=True,
        
        # Data Augmentation
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=10,
        translate=0.1,
        scale=0.5,
        flipud=0.5,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
        
        # 기타
        verbose=True,
        seed=42,
    )
    
    print("\n" + "="*60)
    print("학습 완료!")
    print("="*60)
    print(f"최고 모델 위치: {results.save_dir}/weights/best.pt")
    print(f"마지막 모델 위치: {results.save_dir}/weights/last.pt")
    print("="*60)
    
    return results


if __name__ == '__main__':
    # Windows에서 multiprocessing 사용 시 필수!
    import multiprocessing
    multiprocessing.freeze_support()
    
    # 학습 시작
    results = train_yolo()