from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
import os

from ui.screens.timeinputpopup import TimeInputPopup
from rpiconfig.rpiconfig import DEFAULT_CONFIG

kv_path = os.path.join(os.path.dirname(__file__), '../kv/timescreen.kv')
Builder.load_file(kv_path)

class TimeScreen(Screen):
    def __init__(self, gpio, **kwargs):
        super().__init__(**kwargs)
        self.gpio = gpio

    def popup_time_setting(self, button, option_name):
        popup = TimeInputPopup()
        popup.callback = lambda time_str: self.set_time(button, option_name, time_str)
        popup.open()
    
    def set_time(self, button, option_name, option_value):
        button.text = option_value

        app = App.get_running_app()
        app.update_config(option_name, option_value)