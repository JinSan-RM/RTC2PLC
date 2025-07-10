from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
import os

from rpiconfig.rpiconfig import MANUAL_PARTS

kv_path = os.path.join(os.path.dirname(__file__), '../kv/manualscreen.kv')
Builder.load_file(kv_path)

class ManualScreen(Screen):
    def __init__(self, gpio, **kwargs):
        super().__init__(**kwargs)
        self.gpio = gpio

    # 운전 모드 조작
    def change_mode(self):
        return
    
    # 운전 시작
    def start_process(self):
        return
    
    # 운전 정지
    def stop_process(self):
        return
    
    # 원점
    def go_to_zeropoint(self):
        return
    
    # 고장없음
    def check_breakdown(self):
        return
    
    # 각 파트 운전
    def on_start_manual(self, part_name, part_num):
        self.gpio.set_high(MANUAL_PARTS[part_name][part_num])
    
    # 각 파트 정지
    def on_stop_manual(self, part_name, part_num):
        self.gpio.set_low(MANUAL_PARTS[part_name][part_num])