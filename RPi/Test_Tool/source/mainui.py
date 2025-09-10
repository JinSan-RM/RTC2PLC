import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font
from PIL import Image, ImageTk

import os
from pathlib import Path
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

        frame_gpio = tk.Frame(frame_bg)
        frame_gpio.pack(expand=True)
        btn_gpio = tk.Button(frame_gpio,
                             text="블로워 테스트",
                             width=12, height=2,
                             font=("Arial", 10),
                             command=self.gpio_clicked())
        btn_gpio.pack(fill=tk.X)
        
        frame_ethercat = tk.Frame(frame_bg)
        frame_ethercat.pack(expand=True)
        btn_ethercat = tk.Button(frame_gpio,
                                 text="서보 테스트",
                                 width=12, height=2,
                                 font=("Arial", 10),
                                 command=self.ethercat_clicked())
        btn_ethercat.pack(fill=tk.X)
        
        frame_modbus = tk.Frame(frame_bg)
        frame_modbus.pack(expand=True)
        btn_modbus = tk.Button(frame_gpio,
                               text="인버터 테스트",
                               width=12, height=2,
                               font=("Arial", 10),
                               command=self.modbus_clicked())
        btn_modbus.pack(fill=tk.X)

    def gpio_clicked(self):
        self.comm_manager.gpio_test()

    def ethercat_clicked(self):
        # self.comm_manager.ethercat_test()
        pass

    def modbus_clicked(self):
        self.comm_manager.modbus_test()