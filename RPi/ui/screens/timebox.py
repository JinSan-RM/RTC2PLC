from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty

class TimeBox(BoxLayout):
    parent_page = ObjectProperty(None)

    def on_time_setting(self, button, option_name):
        self.parent_page.popup_time_setting(button, option_name)