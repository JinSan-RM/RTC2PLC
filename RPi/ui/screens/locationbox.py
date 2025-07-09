from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty

class LocationBox(BoxLayout):
    controller = ObjectProperty(None)

    def on_time_setting(self, button, type):
        self.controller.popup_time_setting(button, type)