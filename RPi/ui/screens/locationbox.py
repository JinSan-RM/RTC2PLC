from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty

class LocationBox(BoxLayout):
    parent_page = ObjectProperty(None)

    def on_time_setting(self, button, type):
        self.parent_page.popup_time_setting(button, type)