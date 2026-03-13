"""
각종 설정 및 유틸들
"""
from pathlib import Path
from datetime import datetime, timedelta
from dateutil import tz

from PySide6.QtWidgets import QAbstractButton
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, QRectF
from PySide6.QtGui import QPainter, QColor, QFont

# ============================================================
# Breeze Runtime
# ============================================================
HOST = '169.254.188.53'
COMMAND_PORT = 2000
EVENT_PORT = 2500
DATA_STREAM_PORT = 3000
WORKFLOW_PATH = "C:/Users/USER/Breeze/Data/Runtime/251111.xml"

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
    4: "PET",
    5: "background",
}

PLASTIC_VALUE_MAPPING_LARGE = {
    "PP": 0x88,
    "HDPE": 0x89,
    "PS": 0x8A,
    "PET": 0x90,
    # "LDPE": 0x8C,
    # "PET": 0x8E,
    # "_": 0x88,
}
PLASTIC_VALUE_MAPPING_SMALL = {
    "PP": 0x8B,
    "HDPE": 0x8C,
    "PS": 0x8E,
    "PET": 0x8F,
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
# region common
# ============================================================
LOG_PATH = Path(__file__).resolve().parent.parent.parent / "log"

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
CAMERA_CONFIGS = {
    0: {  # 카메라 1
        'camera_ip': '192.168.1.100',
        'roi':{
            'x': 500,
            'y': 0,
            'width': 500,
            'height': 1920
        },
        'boxes': [
            {
                'box_id': 1,
                'x': 50,
                'y': 300,
                'width': 350,
                'height': 400,
                # 'target_classes': ['PP', 'PET', 'PE', 'BOTTLE_PET'],
                'target_classes': ['PE'],
                'airknife_id': 1
            },
            # {
            #     'box_id': 2,
            #     'x': 300,
            #     'y': 200,
            #     'width': 150,
            #     'height': 200,
            #     'target_classes': ['PP', 'PS'],
            #     'airknife_id': 2
            # }
        ]
    },
    1: {  # 카메라 2
        'camera_ip': '192.168.1.101',
        'roi':{
            'x': 500,
            'y': 0,
            'width': 500,
            'height': 1080
        },
        'boxes': [
            {
                'box_id': 2,
                'x': 50,
                'y': 750,
                'width': 400,
                'height': 330,
                # 'target_classes': ['PE'],
                'target_classes': ['PP', 'PS', 'PET', 'PE', 'BOTTLE_PET'],
                'airknife_id': 3
            },
            {
                'box_id': 3,
                'x': 30,
                'y': 70,
                'width': 400,
                'height': 430,
                'target_classes': ['PP', 'PS', 'PET', 'PE', 'BOTTLE_PET'],
                # 'target_classes': ['PP', 'PE', 'BOTTLE_PET'],
                'airknife_id': 2
            }
        ]
    }
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

    def paintEvent(self, event): # pylint: disable=unused-argument
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
