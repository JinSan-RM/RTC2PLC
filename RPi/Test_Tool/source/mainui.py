import tkinter as tk
from tkinter import scrolledtext

from typing import Optional

from .comm_manager import CommManager

class MainUI:
    def __init__(self, app, root: Optional[tk.Tk], comm_manager: CommManager):
        self.app = app
        self.root = root
        self.comm_manager = comm_manager

        self.setup_ui()

    def setup_ui(self):
        self.root.title("장비 동작 테스트 툴")
        self.root.geometry("1024x768")

        frame_bg = tk.Frame(self.root, padx=20, pady=20)
        frame_bg.pack(fill=tk.BOTH, expand=True)

        label_title = tk.Label(frame_bg, text="장비 동작 테스트 툴", font=("Arial", 16, "bold"))
        label_title.pack(pady=(0, 20))

        frame_btn = tk.Frame(frame_bg)
        frame_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        btn_gpio = tk.Button(frame_btn,
                             text="블로워 테스트",
                             width=12, height=2,
                             font=("Arial", 10),
                             command=self.gpio_clicked())
        btn_gpio.pack(fill=tk.X)
        
        btn_ethercat = tk.Button(frame_btn,
                                 text="서보 테스트",
                                 width=12, height=2,
                                 font=("Arial", 10),
                                 command=self.ethercat_clicked())
        btn_ethercat.pack(fill=tk.X)
        
        btn_modbus = tk.Button(frame_btn,
                               text="인버터 테스트",
                               width=12, height=2,
                               font=("Arial", 10),
                               command=self.modbus_clicked())
        btn_modbus.pack(fill=tk.X)

        frame_log = tk.Frame(frame_bg)
        frame_log.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(
            frame_bg,
            wrap=tk.WORD,
            state='disabled',
            height=30,
            font=('Consolas', 9)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def gpio_clicked(self):
        self.comm_manager.gpio_test()
        pass

    def ethercat_clicked(self):
        print("추후 추가 예정")
        # self.comm_manager.ethercat_test()
        pass

    def modbus_clicked(self):
        self.comm_manager.modbus_test()
        pass

    def add_log(self, txt: str):
        def _append():
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, txt + '\n')
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        self.root.after(0, _append)