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
            current_text += digit
        else:
            if len(current_text) >= 2 and current_text[-2] == ".": # 일단 소수점 첫째 자리까지만 입력가능
                return
            
            if current_text == "0":
                current_text = digit
            else:
                current_text += digit

            float_num = float(current_text)
            if float_num > 999: # 일단 999초까지만 입력 가능하게 처리
                current_text = "999"
            elif float_num < 0:
                current_text = "0"

        self.ids.text_input.text = current_text

    def backspace(self):
        current_text = self.ids.text_input.text
        if len(current_text) > 1:
            self.ids.text_input.text = current_text[:-1]
        else:
            self.ids.text_input.text = "0"

    def confirm_time(self):
        current_text = self.ids.text_input.text
        if current_text[-1] == ".": # 소수점으로 끝나면 소수점 제거
            current_text = current_text[:-1]
        
        if len(current_text) >= 2 and current_text[-2] == "." and current_text[-1] == "0": # .0 제거
            current_text = current_text[:-2]

        is_float = False
        if "." in current_text:
            is_float = True

        option_value = int(current_text)
        if is_float:
            option_value = float(current_text)

        if option_value > 999: # 예외처리 한번 더
            option_value = 999
        elif option_value < 0: # 음수 입력 불가
            option_value = 0
        else:
            if self.callback:
                self.callback(option_value)
            self.dismiss()