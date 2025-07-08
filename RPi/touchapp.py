from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager

from screens.mainscreen import MainScreen
from screens.manualscreen import ManualScreen
from screens.timescreen import TimeScreen
from screens.servoscreen import ServoScreen

class TouchApp(App):
    def build(self):
        Builder.load_file("kv/mainscreen.kv")
        Builder.load_file("kv/manualscreen.kv")
        Builder.load_file("kv/timescreen.kv")
        Builder.load_file("kv/servoscreen.kv")

        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(ManualScreen(name='manual'))
        sm.add_widget(TimeScreen(name='time'))
        sm.add_widget(ServoScreen(name='servo'))
        return sm

if __name__ == '__main__':
    TouchApp().run()