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
        self.root.geometry("1024x768")

        frame_bg = tk.Frame(self.root, padx=20, pady=20)
        frame_bg.pack(fill=tk.BOTH, expand=True)

        label_title = tk.Label(frame_bg, text="PLC 동작 테스터", font=("Arial", 16, "bold"))
        label_title.pack(pady=(0, 20))

        frame_btn = tk.Frame(frame_bg)
        frame_btn.pack(expand=True)

        ind = 0x88
        var_type = LSDataType.WORD
        for i in range(4):
            for j in range(8):
                if j % 2 == 0:
                    val = 1
                    button_name = f"P{ind:03X} On"
                else: 
                    val = 0
                    button_name = f"P{ind:03X} Off"

                btn = tk.Button(frame_btn,
                                text=button_name,
                                width=12, height=2,
                                font=("Arial", 10),
                                command=lambda name=button_name, address=ind, var_type=var_type, val=val: self.btn_clicked(name, address, var_type, val))
                btn.grid(row=((i//2)*2)+(j%2), column=4*(i%2)+(j//2), padx=5, pady=5)

                if j % 2 == 1:
                    ind += 1

        self.label_status = tk.Label(frame_bg, text="테스트 대기 중...", font=("Arial", 12))
        self.label_status.pack(pady=(20, 0))

    def btn_clicked(self, name: str, address: int, var_type: LSDataType, val: Optional[int]):
        self.comm_manager.send_command_async(address, var_type, val, lambda ret, name=name: self.on_plc_response(name, ret))

    def on_plc_response(self, name: str, ret):
        self.root.after(0, self._update_after_response, name, ret)

    def _update_after_response(self, name: str, ret):
        if ret:
            self.label_status.config(text=f"{name} 성공")
        else:
            self.label_status.config(text=f"{name} 실패")