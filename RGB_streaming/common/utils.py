import os
import re

from PIL import Image

"""
    경로를 스마트하게 줄여서 표시

    Parameters:
        path_text (str): 변환할 경로 텍스트
        max_chars (int): 이 길이를 넘으면 변환

    우선순위: 드라이브 + ... + 중요한 폴더들 + 현재 폴더
"""
def smart_path_display(path_text, max_chars = 40):
    if len(path_text) <= max_chars:
        return path_text

    # 경로를 분할
    drive, path_without_drive = os.path.splitdrive(path_text)
    parts = path_without_drive.strip(os.sep).split(os.sep)

    if len(parts) <= 2:
        return path_text

    # 마지막 폴더는 항상 표시
    last_part = parts[-1]

    # 드라이브 + ... + 마지막 폴더
    if drive:
        short_path = f"{drive}{os.sep}...{os.sep}{last_part}"
    else:
        short_path = f"...{os.sep}{last_part}"

    # 길이가 허용 범위 내라면 더 많은 부분 추가
    if len(short_path) < max_chars and len(parts) > 1:
        # 마지막에서 두 번째 폴더도 추가
        second_last = parts[-2]
        if drive:
            candidate = f"{drive}{os.sep}...{os.sep}{second_last}{os.sep}{last_part}"
        else:
            candidate = f"...{os.sep}{second_last}{os.sep}{last_part}"
        
        if len(candidate) <= max_chars:
            short_path = candidate

    return short_path

"""
    폴더 내의 파일 이름을 확인하여 가장 높은 번호를 반환합니다.

    Parameters:
        folder_path (str): 파일이 저장된 폴더 경로
        file_prefix (str): 파일 이름의 접두사 (예: 'file_')
        file_extension (str): 파일 확장자 (예: '.txt')

    Returns:
        int: 가장 높은 번호 (없을 경우 0 반환)
"""
def get_highest_file_number(folder_path, file_prefix="file_", file_extension=".txt"):
    # 폴더 내의 파일 목록 가져오기
    try:
        files = os.listdir(folder_path)
    except FileNotFoundError:
        print(f"폴더 {folder_path}가 존재하지 않습니다.")
        return 0

    # 번호를 저장할 리스트
    numbers = []

    # 파일 이름에서 번호 추출 (예: file_001.txt -> 001)
    pattern = re.compile(rf'^{file_prefix}(\d+){file_extension}$')

    for file_name in files:
        match = pattern.match(file_name)
        if match:
            # 번호 부분을 정수로 변환
            number = int(match.group(1))
            numbers.append(number)

    # 번호 리스트가 비어있으면 0 반환, 아니면 최대값 반환
    return max(numbers) if numbers else 0

"""
    다음 파일 이름을 생성합니다.

    Parameters:
        folder_path (str): 파일이 저장될 폴더 경로
        file_prefix (str): 파일 이름의 접두사
        file_extension (str): 파일 확장자

    Returns:
        str: 다음 파일 이름 (예: file_003.txt)
"""
def generate_next_filename(folder_path, file_prefix="file_", file_extension=".txt"):
    
    highest_number = get_highest_file_number(folder_path, file_prefix, file_extension)
    next_number = highest_number + 1
    return f"{file_prefix}{next_number:06d}{file_extension}"

"""
    비율을 유지하면서 이미지 크기 조정

    Parameters:
        image (Image): Pillow Image
        max_width (int): 변경할 최대 너비
        max_height (int): 변경할 최대 높이
"""
def resize_image_proportional(image, max_width, max_height):
    # 원본 크기
    width, height = image.size

    # 비율 계산
    ratio = min(max_width/width, max_height/height)

    # 새로운 크기 계산
    new_width = int(width * ratio)
    new_height = int(height * ratio)

    # resize 사용 (원본 보존)
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)