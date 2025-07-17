from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
import os

from common.config import DeviceRole

kv_path = os.path.join(os.path.dirname(__file__), '../kv/mainscreen.kv')
Builder.load_file(kv_path)

class MainScreen(Screen):
    def __init__(self, gpio, **kwargs):
        super().__init__(**kwargs)
        self.gpio = gpio

    # 17번 핀을 통한 점멸 테스트용
    def gpio_test(self):
        if self.gpio != None:
            self.gpio.pulse(DeviceRole.MASTER, 17, delay = 3, duration = 3)