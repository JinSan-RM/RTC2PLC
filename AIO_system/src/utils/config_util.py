"""
각종 설정 및 유틸들
"""
from enum import IntEnum
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass

import numpy as np
from dateutil import tz
from PySide6.QtWidgets import QAbstractButton
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, QRectF
from PySide6.QtGui import QPainter, QColor, QFont
import shiboken6

# ============================================================
# Breeze Runtime
# ============================================================
HOST = '169.254.99.104'
COMMAND_PORT = 2000
EVENT_PORT = 2500
DATA_STREAM_PORT = 3000
WORKFLOW_PATH = "C:/Users/USER/Breeze/Data/Runtime/260417.xml"
# 기존 모델 260320_new.xml

# ==================== 라인 스캔 타이밍 제어 설정 ====================
# 라인 스캔 카메라는 고정된 위치에서 촬영하므로
# 스캔 라인 → 에어솔까지의 거리만 중요!

CONVEYOR_SPEED = 40.0           # cm/s - 실측 필요
SCAN_LINE_TO_AIRSOL = 40.0      # cm - 스캔 라인부터 에어솔까지 거리
LENGTH_PIXEL = 640              # px - 딜레이 계산할 때 사용할, 초분광 스캔 지점으로부터의 기준 거리
PX_CM_RATIO = 10.0              # px대 cm 비율

USE_MIN_INTERVAL = True         # 인접한 두 물체를 하나로 취급할 것인가
MIN_INTERVAL = 0.5              # sec - 두 물체를 하나로 취급할 시간 간격
MIN_PULSE_WIDTH = 0.01          # 10ms - PLC 스캔 사이클 고려

# 대형/소형 구분
GUIDELINE_MIN_X = 420
GUIDELINE_MAX_X = 428
GUIDELINE_X = 405

# 피더 배출구 막힘 해소
USE_FEEDER_CAM = False
BLOCK_DETECTION_TIME = 5 # 피더 배출구 막힘 감지 시간(초)
FEEDER_AIR_TERM = 15 # 15초마다 피더 배출부에 에어를 쏴서 막힘을 제거

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
    2: "PS",
    3: "LDPE",
    4: "HDPE",
    5: "background",
    6: "HDPE_LABEL",
    # 5: "PET",
}

PLASTIC_VALUE_MAPPING_LARGE = {
    "PP": 0x88,
    "HDPE": 0x89,
    "PS": 0x8A,
    "PET": 0x97
    # "PET": 0x90,
    # "LDPE": 0x8C,
    # "PET": 0x8E,
    # "_": 0x88,
}
PLASTIC_VALUE_MAPPING_SMALL = {
    "PP": 0x88,
    "HDPE": 0x89,
    "PS": 0x8A,
    "PET": 0x97
    # "PET": 0x90,
    # "LDPE": 0x8C,
    # "PET": 0x8E,
    # "_": 0x88,
}

STREAM_TYPE = [ "None", "Raw", "PredictionLines", "Rgb", "StreamStart/End" ]

PLASTIC_SIZE_MAPPING = {
    "large": 0x80,
    "small": 0x81
}

# ============================================================
# endregion
# ============================================================

# ============================================================
# region Modbus
# ============================================================
MODBUS_RTU_CONFIG = {
    "slave_ids": {
        "inverter_001": 1,
        "inverter_002": 2,
        "inverter_003": 3,
        "inverter_004": 4,
        "inverter_005": 5,
        "inverter_006": 6
    },
    "port": "COM7",
    "baudrate": 9600,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "timeout": 1
}
# ============================================================
# endregion
# ============================================================

# ============================================================
# region EtherCAT
# ============================================================

# 네트워크 인터페이스 이름 -> search_ifname.py 를 실행해서 얻은 네트워크 어댑터 이름을 사용함
IF_NAME = '\\Device\\NPF_{C7EBE891-A804-4047-85E5-4D0148B1D3EA}'

# 통신 사이클 간격
ETHERCAT_DELAY = 0.01
HEALTH_CHECK_TERM = ETHERCAT_DELAY * 10  # 10 주기마다 한 번 체크
WKC_MISS_COUNT_MAX = 5

# LS산전 제조사 ID
LS_VENDOR_ID = 30101

class LSProductCode(IntEnum):
    """이더캣 슬레이브 장비 제품 코드"""
    L7NH_PRODUCT_CODE = 0x00010001
    D232A_PRODUCT_CODE = 0x10010008
    TR32KA_PRODUCT_CODE = 0x10010009

# Sync Manager 는 0 ~ 3이 있고, 그 중 0과 1은 Mailbox(SDO)에 사용됨.
EC_RX_INDEX = 0x1C12 # Sync Manager 2 -> RxPDO를 매칭
EC_TX_INDEX = 0x1C13 # Sync Manager 3 -> TxPDO를 매칭

# RxPDO 매핑은 0x1600 ~ 0x1603의 4개가 존재하고, 일단 기본값인 0x1601을 사용하도록 한다.
SERVO_RX_MAP = 0x1601 # master -> slave
# TxPDO 매핑은 0x1A00 ~ 0x1A03의 4개가 존재하고, 일단 기본값인 0x1A01을 사용하도록 한다.
SERVO_TX_MAP = 0x1A01 # slave -> master

# 위에서 지정한 PDO 맵 주소에 아래의 매핑 데이터를 넣어준다.
# PDO 맵 주소의 subindex 0 에는 전체 매핑 개수, subindex 1 부터 매핑 데이터를 1개씩 할당
# PDO 매핑 구조: 0x 0000 / 00 / 00 -> 앞 2byte는 index, 중간 1byte는 subindex, 뒤 1byte는 해당 오브젝트 bit사이즈
SERVO_RX = [
    0x60400010, # 컨트롤 워드(unsigned short)
    0x60600008, # 운전 모드(signed char)
    0x607A0020, # 목표 위치(int)
    0x60FF0020, # 목표 속도(int)
]

SERVO_TX = [
    0x60410010, # 스테이터스 워드(unsigned short)
    0x60610008, # 운전 모드 표시(signed char)
    0x60640020, # 현재 위치(int)
    0x606C0020, # 현재 속도(int)
    0x603F0010, # 에러 코드(unsigned short)
    0x26140010, # 경고 코드(unsigned short)
]

OUTPUT_RX_MAP = 0x1700
INPUT_TX_MAP = 0x1B00

OUTPUT_RX = [
    0x32200101, # 운전 스위치 LAMP
    0x32200201, # 정지 스위치 LAMP
    0x32200301, # TOWER 정상운전 LAMP
    0x32200401, # TOWER 운전정지 LAMP
    0x32200501, # TOWER 알람 LAMP
    0x32200601, # TOWER BUZZER
    0x32200701, # 비전 1 조광기 POWER
    0x32200801, # 비전 2 조광기 POWER
    0x32200901, # 내륜모터 인버터 RUN
    0x32200A01, # 내륜모터 인버터 RESET
    0x32200B01, # 외륜모터 인버터 RUN
    0x32200C01, # 외륜모터 인버터 RESET
    0x32200D01, # 컨베이어#1 인버터 RUN
    0x32200E01, # 컨베이어#1 인버터 RESET
    0x32200F01, # 컨베이어#2 인버터 RUN
    0x32201001, # 컨베이어#2 인버터 RESET
    0x32201101, # 컨베이어#3 인버터 RUN
    0x32201201, # 컨베이어#3 인버터 RESET
    0x32201301, # 컨베이어#4 인버터 RUN
    0x32201401, # 컨베이어#4 인버터 RESET
    0x32201501, # 소재 1분리 SOL V/V
    0x32201601, # 소재 2분리 SOL V/V
    0x32201701, # 소재 3분리 SOL V/V
    0x32201801, # SPARE
    0x32201901, # 원점 복귀 LAMP
    0x32201A01, # 알람 리셋 LAMP
    0x32201B01,
    0x32201C01,
    0x32201D01,
    0x32201E01,
    0x32201F01,
    0x32202001,
]

INPUT_TX = [
    0x30200101, # 수동/자동
    0x30200201, # 운전
    0x30200301, # 정지
    0x30200401, # 알람리셋
    0x30200501, # 비상정지
    0x30200601, # 내륜모터 인버터 알람
    0x30200701, # 외륜모터 인버터 알람
    0x30200801, # 컨베이어#1 인버터 알람
    0x30200901, # 컨베이어#2 인버터 알람
    0x30200A01, # 컨베이어#3 인버터 알람
    0x30200B01, # 컨베이어#4 인버터 알람
    0x30200C01, # 원점 복귀
    0x30200D01,
    0x30200E01,
    0x30200F01,
    0x30201001,
    0x30201101, # 피더 배출 제품감지센서
    0x30201201,
    0x30201301,
    0x30201401,
    0x30201501,
    0x30201601,
    0x30201701,
    0x30201801,
    0x30201901,
    0x30201A01,
    0x30201B01,
    0x30201C01,
    0x30201D01,
    0x30201E01,
    0x30201F01,
    0x30202001,
]

# 앱 자체적으로 전자 기어비 적용을 위한 부분
# 기어비(인코더 펄스 / 모터 1회전당 이동거리) 현재 1회전당 10,000 μm
# UI에서 입력 시 값 1당 1 μm 를 의미하게 됨
ENCODER_RESOLUTION = 524288 # 인코더 해상도(1회전당 펄스)
BALL_SCREW_LEAD = 20 # 볼 스크류 1회전당 이동거리(mm)
UNIT_RATIO = 0.01
SCALE_FACTOR = (ENCODER_RESOLUTION / BALL_SCREW_LEAD) * UNIT_RATIO

def get_servo_unmodified_value(value: float) -> int:
    """
    서보로 전달할 값
    
    :param value: 앱 내에서 사용하는 값(μm 단위)
    :type value: float
    :return: 서보가 사용하는 값(펄스 단위)
    :rtype: int
    """
    return int(round(value*SCALE_FACTOR))

def get_servo_modified_value(value: int | float) -> float:
    """
    UI에 출력할 값
    
    :param value: 서보가 사용하는 값(펄스 단위)
    :type value: int | float
    :return: 앱 내에서 사용하는 값(μm 단위)
    :rtype: float
    """
    return value/SCALE_FACTOR

class StatusMask(IntEnum):
    """서보 드라이브 상태 체크를 위한 비트 마스크"""
    STATUS_NOT_READY_TO_SWITCH_ON = 0x0000 # 초기화 중
    STATUS_SWITCH_ON_DISABLED = 0x0040 # 초기화 완료, 주전원 투입 불가
    STATUS_READY_TO_SWITCH_ON = 0x0021 # 주전원 투입 가능
    STATUS_SWITCHED_ON = 0x0023 # 주전원 투입 완료, 서보 OFF
    STATUS_OPERATION_ENABLED = 0x0027 # 서보 ON
    STATUS_QUICK_STOP_ACTIVE = 0x0007 # Quick stop 기능 수행 중
    STATUS_FAULT_REACTION_ACTIVE = 0x000F # 서보 알람 관련 시퀀스 처리 중
    STATUS_FAULT = 0x0008 # 서보 알람(AL 코드) 발생
    STATUS_WARNING = 0x0080 # 경보(W 코드) 발생

def check_mask(s, m) -> bool:
    """
    STATUS_MASK와 비교하여 현재 서보 드라이브 상태 체크
    
    :param s: 대상 비트
    :param m: 비교할 비트 마스크
    """
    low_bit = s & 0x00FF
    return (low_bit & m) == m

class OperationMode(IntEnum):
    """서보 운전 상태"""
    SERVO_READY = 0
    SERVO_HOMING = 6
    SERVO_CSP = 8
    SERVO_CSV = 9

# 서보 위치 이동 가속도
SERVO_ACCEL = 2000

# 위치 값이 10 펄스 이내로 들어오면 위치 도달로 추정
SERVO_IN_POS_WIDTH = 10

class InputBitMask(IntEnum):
    """입력 모듈 체크를 위한 비트 마스크"""
    MODE_SELECT = 1 << 0
    AUTO_RUN = 1 << 1
    AUTO_STOP = 1 << 2
    RESET_ALARM = 1 << 3
    EMERGENCY_STOP = 1 << 4
    SERVO_HOMING = 1 << 11
    FEEDER_OUTPUT = 1 << 16

# ============================================================
# endregion
# ============================================================

# ============================================================
# region common
# ============================================================
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

FEEDER_TIME_1 = 90 # 피더 제품 미배출 기본 대기 시간(sec)
FEEDER_TIME_2 = 5 # 6 단계에서 1 단계로 리셋 시 추가 대기 시간(sec)

PRCS_HTH_CHECK_TERM = 1
MAX_PRCS_DEAD_COUNT = 3

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "log"

input_pdo_struct = [
    ('status_word', '<u2'),
    ('drive_mode', '<i1'),
    ('actual_position', '<i4'),
    ('actual_velocity', '<i4'),
    ('error_code', '<u2'),
    ('warning_code', '<u2')
]
output_pdo_struct = [
    ('control_word', '<u2'),
    ('drive_mode', '<i1'),
    ('target_position', '<i4'),
    ('target_velocity', '<i4')
]
variable_pdo_struct = [
    ('init_step', '<u1'),
    ('state', '<u1'),
    ('current_position', '<i4'),
    ('current_velocity', '<i4'),
    ('target_position', '<i4'),
    ('target_velocity', '<i4'),
    ('last_time', '<u8')
]
total_input_type = ('total_input', '<u4')
total_output_type = ('total_output', '<u4')
prev_input_type = ('prev_input', '<u4')
hth_check_type = [
    ('main_counter', '<u2'),
    ('sub_counter', '<u2')
]

SHM_NAME = "COMM_SHM"
SHM_DTYPE = np.dtype([
    # 서보 드라이브 관리용 np array 설정
    ('servo_0', [
        ('input_pdo', input_pdo_struct),
        ('reserved_1', 'u1'),
        ('output_pdo', output_pdo_struct),
        ('reserved_2', 'u1'),
        ('variables', variable_pdo_struct),
        ('reserved_3', 'u2')
    ]),
    ('servo_1', [
        ('input_pdo', input_pdo_struct),
        ('reserved_1', 'u1'),
        ('output_pdo', output_pdo_struct),
        ('reserved_2', 'u1'),
        ('variables', variable_pdo_struct),
        ('reserved_3', 'u2')
    ]),
    # 입출력 모듈 관리용 np array 설정
    total_input_type,
    total_output_type,
    prev_input_type,
    ('hth_counter', hth_check_type)
])

def sync_shared_memory(dst, raw_src):
    """
    PDO 데이터를 공유 메모리에 쓰기
    
    :param dst: 복사할 메모리
    :param raw_src: 원본 데이터
    """
    src = np.frombuffer(raw_src, dtype='u1').view(dst.dtype)[0]
    for name in dst.dtype.names:
        dst[name] = src[name]

@dataclass
class ProcessCheckVars:
    """process health check 속성 모음"""
    last_check_time: float
    last_counter: int = 0
    dead_count: int = 0
    start_delay_count: int = 5

def calculate_shape_metrics(border, size_event=False):
    """
    Calculate width, height, center position and size category from border coords.
    
    Args:
        border (list): List of [x, y] coordinate pairs defining the shape boundary.
        size_event (bool): If True, classify size into small/medium/large.
    
    Returns:
        dict: {
            "width": ...,
            "height": ...,
            "center_x": ...,
            "center_y": ...,
            "size_category": "small"/"medium"/"large"/"none"
        }
    """
    if not border or len(border) < 2:
        return {"width": 0, "height": 0, "center_x": 0, "center_y": 0, "size_category": "none"}

    x_coords = [p[0] for p in border]
    y_coords = [p[1] for p in border]
    width = max(x_coords) - min(x_coords)
    height = max(y_coords) - min(y_coords)
    center_x = (max(x_coords) + min(x_coords)) / 2
    center_y = (max(y_coords) + min(y_coords)) / 2

    # size_event에 따라 크기 분류
    if size_event:
        if width < 200 and height < 500:
            size_cat = "small"
        elif width < 500 and height < 1000:
            size_cat = "medium"
        else:
            size_cat = "large"
    else:
        size_cat = "none"

    return {
        "width": width,
        "height": height,
        "center_x": center_x,
        "center_y": center_y,
        "size_category": size_cat
    }

def classify_object_size(center_x):
    """
    객체의 중심점 X 좌표로 대형/소형 구분
    
    center_x가 가이드라인 기준:
    - 왼쪽에 있으면 → 대형
    - 오른쪽에 있으면 → 소형
    """
    # 가이드라인 영역 (무시)
    if GUIDELINE_MIN_X <= center_x <= GUIDELINE_MAX_X:
        return None

    # 중심점이 가이드라인 왼쪽 = 대형
    if center_x < GUIDELINE_X:
        return "large"

    # 중심점이 가이드라인 오른쪽 = 소형
    else:
        return "small"

def calc_delay(y_position):
    """제품이 비전 룸을 벗어날 때까지의 딜레이 계산"""
    remain_px = LENGTH_PIXEL - y_position   # 객체 중심이 끝점 지나기까지 남은 거리(px)
    if remain_px < 0:
        return 0

    remain_cm = remain_px / PX_CM_RATIO     # cm 단위로 변환
    delay = remain_cm / CONVEYOR_SPEED      # 딜레이 초 단위로 구함
    return delay

def convert_ticks_to_datetime(ticks):
    """주어진 ticks를 datetime으로 변환"""
    return (
        datetime(1, 1, 1) + timedelta(microseconds=ticks // 10)
    ).replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())

def get_border_coords(border):
    """제품 테두리의 x, y 좌표 최대 최소값"""
    x_coords = [p[0] for p in border]
    y_coords = [p[1] for p in border]
    return min(x_coords), max(x_coords), min(y_coords), max(y_coords)

# ============================================================
# endregion
# ============================================================


# ============================================================
# region Cam options
# ============================================================
@dataclass
class DetectBoxInfo:
    """감지 박스 위치 정보"""
    width: int
    height: int
    x1: int
    y1: int
    x2: int
    y2: int

CAMERA_CONFIGS = {
    0: {  # 카메라 1
        'camera_ip': '192.168.1.210',
        'type': 'line',
        'roi':{
            'x': 0,
            'y': 350,
            'width': 1280,
            'height': 400
        },
        # 'boxes': [
        #     {
        #         'box_id': 1,
        #         'x': 50,
        #         'y': 300,
        #         'width': 350,
        #         'height': 400,
        #         # 'target_classes': ['PP', 'PET', 'PE', 'BOTTLE_PET'],
        #         'target_classes': ['PLASTIC'],
        #         'airknife_id': 1
        #     },
            # {
            #     'box_id': 2,
            #     'x': 300,
            #     'y': 200,
            #     'width': 150,
            #     'height': 200,
            #     'target_classes': ['PP', 'PS'],
            #     'airknife_id': 2
            # }
        # ],
        # 'entrance_boxes': [
        #     {
        #         'box_id': 1,
        #         'x': 50,
        #         'y': 200,
        #         'width': 350,
        #         'height': 400,
        #         # 'target_classes': ['PP', 'PET', 'PE', 'BOTTLE_PET'],
        #         'target_classes': ['PLASTIC'],
        #         'airknife_id': 1
        #     },
        # ],
        'line': [
            {
                'line_id': 1,
                'x': 700,
                'y': 10,
                'width': 5,
                'height': 1000,
            }
        ]
    },
    # 1: {  # 카메라 2
    #     'camera_ip': '192.168.1.101',
    #     'type': 'box',
    #     'roi':{
    #         'x': 0,
    #         'y': 0,
    #         'width': 1920,
    #         'height': 1080
    #     },
    #     'boxes': [
    #         {
    #             'box_id': 2,
    #             'x': 50,
    #             'y': 750,
    #             'width': 400,
    #             'height': 330,
    #             # 'target_classes': ['PE'],
    #             'target_classes': ['PP', 'PS', 'PET', 'PE', 'BOTTLE_PET'],
    #             'airknife_id': 3
    #         },
    #         {
    #             'box_id': 3,
    #             'x': 30,
    #             'y': 70,
    #             'width': 400,
    #             'height': 430,
    #             'target_classes': ['PP', 'PS', 'PET', 'PE', 'BOTTLE_PET'],
    #             # 'target_classes': ['PP', 'PE', 'BOTTLE_PET'],
    #             'airknife_id': 2
    #         }
    #     ]
    # }
}

# ============================================================
# endregion
# ============================================================


# ============================================================
# region UI
# ============================================================

UI_PATH = Path(__file__).resolve().parent.parent / "ui"

MAX_IMG_LINES = 480 # 이미지 뷰어 화면에 표시할 라인 수
UI_UPDATE_INTERVAL = 0.033 # 30fps 제한

def clear_layout(layout):
    """레이아웃 내부 위젯 제거"""
    if layout is not None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                clear_layout(item.layout())
        
        shiboken6.delete(layout)


class ToggleButton(QAbstractButton):
    """UI 알약 모양 토글 버튼 구현"""
    def __init__(self, parent=None, width=60, height=28, on_text="ON", off_text="OFF"):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(width, height) # 알약 크기 조절

        self.on_text = on_text
        self.off_text = off_text

        # 애니메이션 설정: 흰색 원의 위치를 제어
        self._handle_position = self._get_end_pos() # 초기 위치 (왼쪽)
        self.animation = QPropertyAnimation(self, b"handle_position", self)
        self.animation.setDuration(100) # 이동 속도 (ms)
        self.animation.setEasingCurve(QEasingCurve.InOutSine)

        # 색상 설정
        self._bg_color_off = QColor("#727272") # 꺼졌을 때 그레이
        self._bg_color_on = QColor("#2DB591")  # 켜졌을 때 테마색
        self._circle_color = QColor("#FFFFFF") # 내부 원 흰색

    # 애니메이션을 위한 속성(Property) 정의
    @Property(float)
    def handle_position(self):
        """토글 동그라미 위치"""
        return self._handle_position

    @handle_position.setter
    def handle_position(self, pos):
        self._handle_position = pos
        self.update() # 화면 다시 그리기 호출

    def _get_end_pos(self):
        return 3 if self.isChecked() else self.width() - self.height() + 3

    def _start_transition(self):
        self.animation.stop()
        self.animation.setStartValue(self._handle_position)
        self.animation.setEndValue(self._get_end_pos())
        self.animation.start()

    def setChecked(self, checked):
        if self.isChecked() != checked:
            super().setChecked(checked)
            self._start_transition()

    def nextCheckState(self):
        # 클릭 시 상태 전환 및 애니메이션 시작
        super().nextCheckState()
        self._start_transition()

    def resizeEvent(self, event):
        self._handle_position = self._get_end_pos()
        super().resizeEvent(event)

    def paintEvent(self, event):
        # 직접 위젯 그리기
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing) # 부드럽게 처리

        # 1. 배경(알약 모양) 그리기
        color = self._bg_color_on if self.isChecked() else self._bg_color_off
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), self.height()/2, self.height()/2)

        # 2. 텍스트 그리기 로직
        painter.setPen(QColor("#FFFFFF")) # 글자 색상
        font = painter.font()
        font.setFamily("Poppins")
        font.setPixelSize(16)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)

        # 상태에 따라 텍스트 내용과 위치 결정
        if self.isChecked():
            # 켜졌을 때: 원이 왼쪽에 있으므로 텍스트는 오른쪽에 배치
            text = self.on_text
            text_rect = QRectF(self.width() * 0.25, 0, self.width() * 0.75, self.height())
            alignment = Qt.AlignCenter | Qt.AlignRight
            padding = 18
        else:
            # 꺼졌을 때: 원이 오른쪽에 있으므로 텍스트는 왼쪽에 배치
            text = self.off_text
            text_rect = QRectF(0, 0, self.width() * 0.75, self.height())
            alignment = Qt.AlignCenter | Qt.AlignLeft
            padding = 8

        # 텍스트 그리기 (여백 적용을 위해 text_rect 내부에서 정렬)
        # 조금 더 세밀한 조정을 원하면 QRectF 좌표에 padding을 가감하세요.
        painter.drawText(text_rect.adjusted(padding, 0, -padding, 0), alignment, text)

        # 3. 흰색 원(핸들) 그리기 (텍스트 위에 덮어씌워지지 않도록 마지막에 그림)
        painter.setBrush(self._circle_color)
        painter.setPen(Qt.NoPen)
        margin = 3
        circle_size = self.height() - (margin * 2)
        painter.drawEllipse(QRectF(self._handle_position, margin, circle_size, circle_size))

# ============================================================
# endregion
# ============================================================
