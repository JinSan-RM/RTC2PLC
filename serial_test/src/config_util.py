MODBUS_RTU_CONFIG = {
    "slave_ids": {
        "inverter_001": 1,
        "inverter_002": 2
    },
    "port": "COM7",
    "baudrate": 9600,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "timeout": 1
}

import tkinter as tk
from tkinter import ttk, messagebox

class DigitInput(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.current_input = ""

        self.title("입력")
        self.geometry("300x400")
        self.resizable(False, False)

        # 모달 윈도우로 설정
        self.transient(parent)
        self.grab_set()

        self.create_widgets()

        # 창을 부모 중앙에 위치
        self.center_window(parent)

    # 부모 창 중앙에 위치시키기
    def center_window(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    # 계산기 UI 구성
    def create_widgets(self):
        # 메인 프레임
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 디스플레이
        self.display = tk.Entry(main_frame, font=("Arial", 18), justify="right", state="readonly")
        self.display.pack(fill=tk.X, pady=(0, 10))

        # 버튼 프레임
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.BOTH, expand=True)

        # 버튼 레이아웃
        buttons = [
            ['7', '8', '9'],
            ['4', '5', '6'],
            ['1', '2', '3'],
            ['0', '.'],
        ]

        # 버튼 생성
        for row_idx, row in enumerate(buttons):
            for col_idx, btn_text in enumerate(row):
                btn = tk.Button(button_frame, text=btn_text, font=("Arial", 14, "bold"),
                                command=lambda t=btn_text: self.button_click(t))
                btn.grid(row=row_idx, column=col_idx, sticky="nsew", padx=2, pady=2)

        # 그리드 가중치 설정
        for i in range(4):
            button_frame.grid_rowconfigure(i, weight=1)
            button_frame.grid_columnconfigure(i, weight=1)

        # 하단 버튼들
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        # 지우기 버튼
        clear_btn = tk.Button(bottom_frame, text="지우기 (C)", 
                              font=("Arial", 11),
                              command=self.clear_display)
        clear_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        # 한 글자 삭제 버튼
        backspace_btn = tk.Button(bottom_frame, text="← 삭제",
                                  font=("Arial", 11),
                                  command=self.backspace)
        backspace_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 확인 버튼
        ok_btn = tk.Button(bottom_frame, text="확인",
                           font=("Arial", 11, "bold"),
                           bg="#4CAF50", fg="white",
                           command=self.confirm)
        ok_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # 키보드 바인딩
        self.bind('<Key>', self.key_press)
        self.bind('<Return>', lambda e: self.confirm())
        self.bind('<Escape>', lambda e: self.destroy())

    # 버튼 클릭 처리
    def button_click(self, value):
        self.current_input += value
        self.update_display()

    # 디스플레이 초기화
    def clear_display(self):
        self.current_input = ""
        self.update_display()

    # 마지막 글자 삭제
    def backspace(self):
        self.current_input = self.current_input[:-1]
        self.update_display()

    # 디스플레이 업데이트
    def update_display(self):
        self.display.config(state="normal")
        self.display.delete(0, tk.END)
        self.display.insert(0, self.current_input if self.current_input else "0")
        self.display.config(state="readonly")

    # 키보드 입력 처리
    def key_press(self, event):
        key = event.char.upper()
        if key in '0123456789.':
            self.button_click(key)
        elif event.keysym == 'BackSpace':
            self.backspace()
        elif event.keysym == 'Delete':
            self.clear_display()

    # 확인 버튼 - 입력값 전달
    def confirm(self):
        if self.current_input:
            self.callback(float(self.current_input))
            self.destroy()
        else:
            messagebox.showwarning("입력 오류", "값을 입력해주세요.", parent=self)