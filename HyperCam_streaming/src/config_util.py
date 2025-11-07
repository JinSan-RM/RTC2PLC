# Breeze Runtime 관련 설정
HOST = '169.254.188.53'
COMMAND_PORT = 2000
EVENT_PORT = 2500
DATA_STREAM_PORT = 3000

# ==================== 라인 스캔 타이밍 제어 설정 ====================
# 라인 스캔 카메라는 고정된 위치에서 촬영하므로 
# 스캔 라인 → 에어솔까지의 거리만 중요!

CONVEYOR_SPEED = 40.0           # cm/s - 실측 필요
SCAN_LINE_TO_AIRSOL = 40.0      # cm - 스캔 라인부터 에어솔까지 거리
LENGTH_PIXEL = 640              # px - 딜레이 계산할 때 사용할, 초분광 스캔 지점으로부터의 기준 거리
PX_CM_RATIO = 10.0              # px대 cm 비율

USE_MIN_INTERVAL = True         # 인접한 두 물체를 하나로 취급할 것인가
MIN_INTERVAL = 0.5              # sec - 두 물체를 하나로 취급할 시간 간격

# 대형/소형 구분
GUIDELINE_MIN_X = 420
GUIDELINE_MAX_X = 428
GUIDELINE_X = 405

# 플라스틱 분류와 PLC 주소 맵핑
"""
    sol 매칭
    0x88: 대형#1
    0x89: 대형#2
    0x8A: 대형#3
    0x8B: 대형#4

    0x8C: 소형#1
    0x8D: 소형#2
    0x8E: 소형#3
    0x8F: 소형#4

    0x90: 대형#1-1
    0x91: 대형#2-1
    0x92: 대형#3-1
    0x93: 미사용
    
    0x94: 소형#1-1
    0x95: 소형#2-1
    0x96: 소형#3-1
    0x97: 미사용
"""
CLASS_MAPPING = {
    0: "_",
    1: "PP",
    2: "HDPE",
    3: "PS",
    4: "LDPE",
    5: "ABS",
    6: "PET"
}

PLASTIC_VALUE_MAPPING_LARGE = {
    "PP": 0x88,
    "ABS": 0x89,
    "HDPE": 0x8A,
    "PS": 0x90,
    "LDPE": 0x8C,
    "PET": 0x8E,
    # "_": 0x88,
}
PLASTIC_VALUE_MAPPING_SMALL = {
    "PP": 0x8B,
    "ABS": 0x8C,
    "HDPE": 0x8E,
    "PS": 0x8F,
    "LDPE": 0x8C,
    "PET": 0x8E,
    # "_": 0x88,
}

PLASTIC_SIZE_MAPPING = {
    "large": 0x80,
    "small": 0x81
}