import json
import os

APP_NAME = "RGB 카메라 뷰어"
WINDOW_SIZE = "1600x900"
FPS_VALUE = 60

IMG_FORMAT = {
    "jpg, jpeg": "jpg",
    "png": "png"
}

JSON_CONFIG = {
    "SAVE_PATH": os.path.join(os.path.dirname(__file__), "../"),
    "SAVE_FORMAT": "png"
}

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    global JSON_CONFIG
    if not os.path.exists(CONFIG_PATH):
        save_config(JSON_CONFIG)
        return JSON_CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            JSON_CONFIG = json.load(f)
            return JSON_CONFIG
    except Exception:
        return JSON_CONFIG
    
def update_config(option_name, option_value):
    global JSON_CONFIG
    changed = False
    exist_value = JSON_CONFIG[option_name]
    if exist_value and exist_value != option_value:
        JSON_CONFIG[option_name] = option_value
        changed = True
    if changed:
        save_config(JSON_CONFIG)

    return JSON_CONFIG

def save_config(config_data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f, indent = 4)