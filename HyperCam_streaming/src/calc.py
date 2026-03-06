"""
계산 함수
"""
from datetime import datetime, timedelta
from dateutil import tz

from .config_util import (
    GUIDELINE_MAX_X, GUIDELINE_MIN_X, GUIDELINE_X, LENGTH_PIXEL, PX_CM_RATIO, CONVEYOR_SPEED
)

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
