import os
import shutil
from pathlib import Path
import random
from collections import defaultdict

# 설정
source_dir = Path(r"D:\학습용 데이터\전처리")  # 전처리 폴더 경로
output_dir = Path(r"D:\학습용 데이터\전처리\yolo_dataset")  # 출력 폴더 경로

# 클래스 이름 정의
classes = ['PE', 'PET', 'PP', 'PS']
class_to_id = {name: idx for idx, name in enumerate(classes)}

# 분할 비율 (train:val:test = 8:1:1)
train_ratio = 0.8
val_ratio = 0.1
test_ratio = 0.1

def create_directory_structure(base_path):
    """YOLO 데이터셋 디렉토리 구조 생성"""
    for split in ['train', 'val', 'test']:
        (base_path / split / 'images').mkdir(parents=True, exist_ok=True)
        (base_path / split / 'labels').mkdir(parents=True, exist_ok=True)

def collect_data_pairs():
    """각 클래스별 이미지-라벨 쌍 수집"""
    data_pairs = defaultdict(list)
    
    for class_name in classes:
        class_folder = source_dir / class_name
        match_images = class_folder / 'match_images'
        match_labels = class_folder / 'match_labels'
        
        if not match_images.exists() or not match_labels.exists():
            print(f"경고: {class_name} 폴더에 match_images 또는 match_labels가 없습니다.")
            continue
        
        # 이미지 파일 목록
        image_files = list(match_images.glob('*.[jp][pn][g]'))  # jpg, png 등
        
        for img_path in image_files:
            # 라벨 파일 찾기 (확장자를 .txt로 변경)
            label_name = img_path.stem + '.txt'
            label_path = match_labels / label_name
            
            if label_path.exists():
                data_pairs[class_name].append({
                    'image': img_path,
                    'label': label_path,
                    'class_id': class_to_id[class_name]
                })
            else:
                print(f"경고: {img_path.name}에 대응하는 라벨이 없습니다.")
    
    return data_pairs

def split_data(data_pairs):
    """데이터를 train/val/test로 분할"""
    splits = {'train': [], 'val': [], 'test': []}
    
    for class_name, pairs in data_pairs.items():
        random.shuffle(pairs)  # 랜덤 섞기
        total = len(pairs)
        
        train_end = int(total * train_ratio)
        val_end = train_end + int(total * val_ratio)
        
        splits['train'].extend(pairs[:train_end])
        splits['val'].extend(pairs[train_end:val_end])
        splits['test'].extend(pairs[val_end:])
        
        print(f"{class_name}: train={train_end}, val={val_end-train_end}, test={total-val_end}")
    
    return splits

def copy_files(splits, output_path):
    """파일을 train/val/test 폴더로 복사"""
    for split_name, pairs in splits.items():
        for idx, pair in enumerate(pairs):
            # 고유한 파일명 생성 (클래스명_원본파일명)
            class_name = classes[pair['class_id']]
            img_name = f"{class_name}_{pair['image'].name}"
            label_name = f"{class_name}_{pair['label'].name}"
            
            # 이미지 복사
            img_dst = output_path / split_name / 'images' / img_name
            shutil.copy2(pair['image'], img_dst)
            
            # 라벨 복사
            label_dst = output_path / split_name / 'labels' / label_name
            shutil.copy2(pair['label'], label_dst)
        
        print(f"{split_name} 세트: {len(pairs)}개 파일 복사 완료")

def create_yaml_file(output_path):
    """YOLO 학습용 data.yaml 파일 생성"""
    yaml_content = f"""# YOLO Dataset Configuration
path: {output_path.absolute()}  # dataset root dir
train: train/images  # train images
val: val/images      # val images
test: test/images    # test images (optional)

# Classes
names:
"""
    for idx, class_name in enumerate(classes):
        yaml_content += f"  {idx}: {class_name}\n"
    
    yaml_path = output_path / 'data.yaml'
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write(yaml_content)
    
    print(f"data.yaml 파일 생성 완료: {yaml_path}")

def main():
    # 랜덤 시드 고정 (재현성을 위해)
    random.seed(42)
    
    print("YOLO 데이터셋 전처리 시작...")
    
    # 1. 디렉토리 구조 생성
    create_directory_structure(output_dir)
    print(f"출력 디렉토리 생성: {output_dir}")
    
    # 2. 데이터 수집
    print("\n데이터 수집 중...")
    data_pairs = collect_data_pairs()
    
    total_samples = sum(len(pairs) for pairs in data_pairs.values())
    print(f"\n총 {total_samples}개 샘플 수집 완료")
    
    # 3. 데이터 분할
    print("\n데이터 분할 중...")
    splits = split_data(data_pairs)
    
    # 4. 파일 복사
    print("\n파일 복사 중...")
    copy_files(splits, output_dir)
    
    # 5. YAML 파일 생성
    print("\nYAML 파일 생성 중...")
    create_yaml_file(output_dir)
    
    print("\n전처리 완료!")
    print(f"출력 경로: {output_dir}")
    print(f"\n통계:")
    print(f"- Train: {len(splits['train'])}개")
    print(f"- Val: {len(splits['val'])}개")
    print(f"- Test: {len(splits['test'])}개")

if __name__ == "__main__":
    main()