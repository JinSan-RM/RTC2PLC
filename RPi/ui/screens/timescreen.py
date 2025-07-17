from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
import os

from ui.screens.locationbox import LocationBox
from ui.screens.timebox import TimeBox
from ui.screens.timeinputpopup import TimeInputPopup

popup_path = os.path.join(os.path.dirname(__file__), '../kv/timeinputpopup.kv')
Builder.load_file(popup_path)
kv_path = os.path.join(os.path.dirname(__file__), '../kv/timescreen.kv')
Builder.load_file(kv_path)

class TimeScreen(Screen):
    def __init__(self, gpio, **kwargs):
        super().__init__(**kwargs)
        self.gpio = gpio

    def on_kv_post(self, parent):
        app = App.get_running_app()
        if not app.config_data:
            return
        
        for part_name, sub in app.config_data.items():
            box = self.ids[part_name]
            if box:
                for option_name, option_value in sub.items():
                    btn = box.ids[option_name]
                    if btn:
                        btn.text = str(option_value) + " 초"

    def popup_time_setting(self, button, option_name: str):
        popup = TimeInputPopup(lambda option_value: self.set_time(button, option_name, option_value))
        popup.open()
    
    def set_time(self, button, option_name, option_value):
        button.text = str(option_value) + " 초"

        app = App.get_running_app()
        app.update_config(option_name, option_value)