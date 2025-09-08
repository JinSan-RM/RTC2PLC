import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font
from PIL import Image, ImageTk

import os
from pathlib import Path
from typing import Optional

from .comm_manager import CommManager
from .consts import LSDataType

class MainUI:
    def __init__(self, app, root: Optional[tk.Tk], comm_manager: CommManager):
        self.app = app
        self.root = root
        self.comm_manager = comm_manager

        self.setup_ui()

    def setup_ui(self):
        self.root.title("PLC 동작 테스터")
        self.root.geometry("1000x250")

        frame_bg = tk.Frame(self.root, padx=20, pady=20)
        frame_bg.pack(fill=tk.BOTH, expand=True)

        label_title = tk.Label(frame_bg, text="PLC 동작 테스터", font=("Arial", 16, "bold"))
        label_title.pack(pady=(0, 20))

        frame_btn = tk.Frame(frame_bg)
        frame_btn.pack(expand=True)

        ind = 0x88
        for i in range(2):
            for j in range(8):
                button_name = f"P{ind:03X}"
                btn = tk.Button(frame_btn,
                                text=button_name,
                                width=12, height=2,
                                font=("Arial", 10),
                                command=lambda name=button_name, num=ind: self.btn_clicked(name, num))
                btn.grid(row=i, column=j, padx=5, pady=5)

                ind += 1

        self.label_status = tk.Label(frame_bg, text="테스트 대기 중...", font=("Arial", 12))
        self.label_status.pack(pady=(20, 0))

    def btn_clicked(self, name: str, num: int):
        self.comm_manager.send_command_async(num, lambda ret, name=name: self.on_plc_response(name, ret))

    def on_plc_response(self, name: str, ret):
        self.root.after(0, self._update_after_response, name, ret)

    def _update_after_response(self, name, ret):
        if ret:
            self.label_status.config(text=f"{name} 쓰기 성공")
        else:
            self.label_status.config(text=f"{name} 쓰기 실패")