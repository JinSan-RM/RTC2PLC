import json
import os

from enum import Enum, auto

class DeviceRole(Enum):
    MASTER = auto()
    SLAVE = auto()

class PinRole(Enum):
    INPUT = auto()
    OUTPUT = auto()

# 상수값
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
TCP_HOST = "0.0.0.0"
TCP_PORT = 8999
USE_TCP_SLAVE = False
TCP_SLAVE_1 = "192.168.0.21" # slave rpi의 ip주소. 이거 별도의 설정 파일에서 조정 가능하던지 아니면 다른 방법을 강구해야 한다.
TCP_SLAVE_PORT = 8889

# 장비 각 파츠와 GPIO 매핑(master/slave, pin 번호)
# pin 번호는 bcm 방식(내부 번호 사용)
PIN_MAPPING = {
    "sol" : {
        1 : (DeviceRole.MASTER, 1), # 취출#1 SOL
        2 : (DeviceRole.MASTER, 2), # 취출#2 SOL
        3 : (DeviceRole.MASTER, 3)  # 취출#3 SOL
    },
    "convayor" : {
        1 : (DeviceRole.SLAVE, 4), # 취출#1 콘베어
        2 : (DeviceRole.SLAVE, 5), # 취출#2 콘베어
        3 : (DeviceRole.SLAVE, 6), # 취출#3 콘베어
        4 : (DeviceRole.SLAVE, 7), # 취출#4 콘베어
        5 : (DeviceRole.SLAVE, 8), # 취출#5 콘베어
        6 : (DeviceRole.SLAVE, 9)  # 취출#6 콘베어
    },
    "motor" : {
        1 : (DeviceRole.MASTER, 4),
        2 : (DeviceRole.MASTER, 5)
    },
    "blower_sol" : {
        1 : (DeviceRole.MASTER, 6),
    }
}

# 변경 후 json 저장할 설정값
TIME_CONFIG = {
    "LOC_1" : { "option1" : 0, "option2" : 999 }, # PUSHER 위치 1 동작/정지 시간
    "LOC_2" : { "option1" : 0, "option2" : 999 }, # PUSHER 위치 2 동작/정지 시간
    "LOC_3" : { "option1" : 0, "option2" : 999 }, # PUSHER 위치 3 동작/정지 시간
    "LOC_4" : { "option1" : 0, "option2" : 999 }, # PUSHER 위치 4 동작/정지 시간
    "SIZE_TIME" : { "option1" : 10, "option2" : 15 }, # 사이즈 변경/복귀 시간
    "BLOWER_1" : { "option1" : 0.5, "option2" : 4.3 }, # 취출#1 SOL 동작/적용 시간
    "BLOWER_2" : { "option1" : 0.6, "option2" : 5.3 }, # 취출#2 SOL 동작/적용 시간
    "BLOWER_3" : { "option1" : 0.5, "option2" : 5.8 }  # 취출#3 SOL 동작/적용 시간
}

def load_config():
    global TIME_CONFIG
    if not os.path.exists(CONFIG_PATH):
        save_config(TIME_CONFIG)
        return TIME_CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            TIME_CONFIG = json.load(f)
            return TIME_CONFIG
    except Exception:
        return TIME_CONFIG
    
def update_config(option_name, option_value):
    global TIME_CONFIG
    names = option_name.split(" ")
    changed = False
    if len(names) == 2:
        exist_value = TIME_CONFIG[names[0]][names[1]]
        if exist_value and exist_value != option_value:
            TIME_CONFIG[names[0]][names[1]] = option_value
            changed = True
    if changed:
        save_config(TIME_CONFIG)

    return TIME_CONFIG

def save_config(config_data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f, indent = 4)