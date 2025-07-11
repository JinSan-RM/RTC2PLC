from kivy.properties import StringProperty
from kivy.uix.popup import Popup

class TimeInputPopup(Popup):
    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback

    def add_digit(self, digit):
        current_text = self.ids.text_input.text
        if digit == ".":
            if "." in current_text:
                return
        else:
            current_text += digit
            float_num = float(current_text)
            if float_num > 999: # 일단 999초까지만 입력 가능하게 처리
                current_text = "999"
            elif float_num < 0:
                current_text = "0"

    def backspace(self):
        self.ids.text_input.text = self.ids.text_input.text[:-1]

    def confirm_time(self):
        current_text = self.ids.text_input.text
        if current_text[-1] == ".": # 소수점으로 끝나면 .0으로 만들어줌
            current_text += "0"

        float_num = float(current_text)
        if float_num > 999: # 예외처리 한번 더
            current_text = "999"
        elif float_num < 0:
            current_text = "0"
        else:
            if self.callback:
                self.callback(current_text)
            self.dismiss()