from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty

class TimeBox(BoxLayout):
    controller = ObjectProperty(None)

    def on_time_setting(self, button):
        self.controller.popup_time_setting(button)