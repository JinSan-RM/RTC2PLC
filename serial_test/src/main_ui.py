import tkinter as tk
from tkinter import ttk, scrolledtext

import time
from datetime import datetime

class MainUI:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.root.title("RS 485 Tester")
        self.root.geometry("800x1000")

        # 연결 상태
        self.connected = False
        self.running = False
        self.sock = None
        self.receive_thread = None

        # UI 업데이트 빈도 제한
        self.last_update_time = 0
        self.update_interval = 0.033

        # UI 구성
        self.setup_ui()

    def setup_ui(self):
        # 모니터링
        monitor_frame = ttk.LabelFrame(self.root, text="모니터링", padding=10)
        monitor_frame.pack(fill=tk.X, padx=10, pady=5)

        # 주 운전
        set_frame = ttk.LabelFrame(self.root, text="설정", padding=10)
        set_frame.pack(fill=tk.X, padx=10, pady=5)

        self.connect_btn = ttk.Button(set_frame, text="체크", command=self.check_model)
        self.connect_btn.grid(row=0, column=4, padx=10)

        # 로그 프레임
        log_frame = ttk.LabelFrame(self.root, text="로그", padding=10)
        log_frame.pack(fill=tk.BOTH, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message):
        """로그 메시지 추가"""
        now = datetime.now()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{now.strftime('%H:%M:%S.%f')[:-3]}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def check_model(self):
        self.app.on_btn_clicked()