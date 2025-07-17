from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
import os

from ui.screens.runbox import RunBox
from common.config import PIN_MAPPING

box_path = os.path.join(os.path.dirname(__file__), '../kv/runbox.kv')
Builder.load_file(box_path)
kv_path = os.path.join(os.path.dirname(__file__), '../kv/manualscreen.kv')
Builder.load_file(kv_path)

class ManualScreen(Screen):
    def __init__(self, gpio, **kwargs):
        super().__init__(**kwargs)
        self.gpio = gpio

    # 운전 모드 조작
    def change_mode(self):
        print("change mode pressed.")

    # 운전 시작
    def start_process(self):
        print("start_process pressed")

    # 운전 정지
    def stop_process(self):
        print("stop_process pressed")

    # 원점
    def go_to_zeropoint(self):
        print("go_to_zeropoint pressed")

    # 고장없음
    def check_breakdown(self):
        print("check_breakdown pressed")

    # 각 파트 운전
    def on_start_manual(self, part_name, part_num):
        self.gpio.write_pin(PIN_MAPPING[part_name][part_num], 1)

    # 각 파트 정지
    def on_stop_manual(self, part_name, part_num):
        self.gpio.write_pin(PIN_MAPPING[part_name][part_num], 0)

    # 위치 1
    def on_first_size(self):
        print("on_first_size pressed")

    # 위치 2
    def on_second_size(self):
        print("on_second_size pressed")

    # 위치 3
    def on_third_size(self):
        print("on_third_size pressed")

    # 위치 4
    def on_fourth_size(self):
        print("on_fourth_size pressed")