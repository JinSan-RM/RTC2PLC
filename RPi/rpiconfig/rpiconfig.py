import json
import os

# 상수값
TCP_HOST = "0.0.0.0"
TCP_PORT = 8888
GPIO_PINS = [1, 2, 3, 4, 5, 6, 7, 8, 9]
MANUAL_PARTS = {
    "sol" : { 1 : 1, 2 : 2, 3 : 3 },
    "convayor" : { 1 : 4, 2 : 5, 3 : 6, 4 : 7, 5 : 8, 6 : 9 },
} # 장비 각 파츠와 GPIO 매핑(추후 핀 번호 변경 필요)
CONFIG_PATH = "config.json"

# 변경 후 저장 가능한 설정값
DEFAULT_CONFIG = {
    "LOC_1" : { "start" : 0, "stop" : 999 },
    "LOC_2" : { "start" : 0, "stop" : 999 },
    "LOC_3" : { "start" : 0, "stop" : 999 },
    "LOC_4" : { "start" : 0, "stop" : 999 },
    "CHANGE_SIZE_TIME" : 10,
    "RETURN_SIZE_TIME" : 15,
    "BLOWER_1" : { "duration" : 0.5, "delay" : 4.3 },
    "BLOWER_2" : { "duration" : 0.6, "delay" : 5.3 },
    "BLOWER_3" : { "duration" : 0.5, "delay" : 5.8 },
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG

def save_config(config_data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f, indent = 4)