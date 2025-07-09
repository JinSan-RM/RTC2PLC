from kivy.properties import StringProperty
from kivy.uix.popup import Popup

class TimeInputPopup(Popup):
    raw_input = StringProperty("")
    callback = None  # 외부에서 설정할 콜백 함수

    @property
    def time_display(self):
        padded = self.raw_input.ljust(4, "_")
        return f"{padded[:2]}:{padded[2:]}"

    def add_digit(self, digit):
        if len(self.raw_input) < 4:
            self.raw_input += digit

    def backspace(self):
        self.raw_input = self.raw_input[:-1]

    def confirm_time(self):
        if len(self.raw_input) == 4:
            hour = int(self.raw_input[:2])
            minute = int(self.raw_input[2:])
            if 0 <= hour < 24 and 0 <= minute < 60:
                if self.callback:
                    self.callback(f"{hour:02}:{minute:02}")
                self.dismiss()
            else:
                self.raw_input = ""  # 잘못된 시간 초기화