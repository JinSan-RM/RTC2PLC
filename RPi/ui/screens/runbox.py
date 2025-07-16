from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty

class RunBox(BoxLayout):
    parent_page = ObjectProperty(None)
    
    def on_start(self):
        if self.controller:
            self.controller.on_start_manual(self.type, self.num)

    def on_stop(self):
        if self.controller:
            self.controller.on_stop_manual(self.type, self.num)