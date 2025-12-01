import tkinter as tk
from tkinter import ttk, scrolledtext

import time
from datetime import datetime

from .config_util import *

class MainUI:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.root.title("RS 485 Tester")
        self.root.geometry("800x1000")

        # UI 업데이트 빈도 제한
        self.last_update_time = 0
        self.update_interval = 0.033

        # UI 구성
        self.setup_monitor_ui()
        self.setup_ctrl_ui()
        self.setup_run_ui()
        self.setup_log_ui()

# region ui setting
    # 모니터
    def setup_monitor_ui(self):
        monitor_frame = ttk.LabelFrame(self.root, text="모니터", padding=10)
        monitor_frame.pack(fill=tk.X, padx=10, pady=5)

        monitor_top = ttk.Frame(monitor_frame, relief=tk.FLAT, borderwidth=0)
        monitor_top.pack(fill=tk.BOTH)

        out_a_name = tk.Label(monitor_top, text="출력 전류", font=("Arial", 12))
        out_a_name.grid(row=0, column=0, padx=(10, 0))
        out_freq_name = tk.Label(monitor_top, text="출력 주파수", font=("Arial", 12))
        out_freq_name.grid(row=0, column=1)
        out_v_name = tk.Label(monitor_top, text="출력 전압", font=("Arial", 12))
        out_v_name.grid(row=0, column=2)
        out_dc_name = tk.Label(monitor_top, text="DC Link 전압", font=("Arial", 12))
        out_dc_name.grid(row=0, column=3)
        out_p_name = tk.Label(monitor_top, text="출력 파워", font=("Arial", 12))
        out_p_name.grid(row=0, column=4, padx=(0, 10))

        self.out_a_var = tk.StringVar(value="0.0")
        out_a_value = tk.Label(monitor_top, textvariable=self.out_a_var, font=("Arial", 12))
        out_a_value.grid(row=1, column=0, padx=(10, 0))
        self.out_freq_var = tk.StringVar(value="0.00")
        out_freq_value = tk.Label(monitor_top, textvariable=self.out_freq_var, font=("Arial", 12))
        out_freq_value.grid(row=1, column=1)
        self.out_v_var = tk.StringVar(value="0")
        out_v_value = tk.Label(monitor_top, textvariable=self.out_v_var, font=("Arial", 12))
        out_v_value.grid(row=1, column=2)
        self.out_dc_var = tk.StringVar(value="0")
        out_dc_value = tk.Label(monitor_top, textvariable=self.out_dc_var, font=("Arial", 12))
        out_dc_value.grid(row=1, column=3)
        self.out_p_var = tk.StringVar(value="0.0")
        out_p_value = tk.Label(monitor_top, textvariable=self.out_p_var, font=("Arial", 12))
        out_p_value.grid(row=1, column=4, padx=(0, 10))

        monitor_bottom = ttk.Frame(monitor_frame, relief=tk.FLAT, borderwidth=0)
        monitor_bottom.pack(fill=tk.BOTH)

        stop_name = tk.Label(monitor_bottom, text="정지", font=("Arial", 12))
        stop_name.grid(row=0, column=0, padx=(10, 0))
        run_p_name = tk.Label(monitor_bottom, text="운전중(정)", font=("Arial", 12))
        run_p_name.grid(row=0, column=1)
        run_n_name = tk.Label(monitor_bottom, text="운전중(역)", font=("Arial", 12))
        run_n_name.grid(row=0, column=2)
        fault_name = tk.Label(monitor_bottom, text="Fault", font=("Arial", 12))
        fault_name.grid(row=0, column=3)
        acc_name = tk.Label(monitor_bottom, text="가속중", font=("Arial", 12))
        acc_name.grid(row=0, column=4)
        dec_name = tk.Label(monitor_bottom, text="감속중", font=("Arial", 12))
        dec_name.grid(row=0, column=5, padx=(0, 10))

        self.run_state_bit = 0
        self.run_state_var_list = []
        for i in range(6):
            str_var = tk.StringVar(value="OFF")
            self.run_state_var_list.append(str_var)
            run_value = tk.Label(monitor_bottom, textvariable=str_var, font=("Arial", 12))
            padx = (0, 0)
            if i == 0:
                padx = (10, 0)
            elif i == 5:
                padx = (0, 10)
            run_value.grid(row=1, column=i, padx=padx)

    # 설정
    def setup_ctrl_ui(self):
        ctrl_frame = ttk.LabelFrame(self.root, text="설정", padding=10)
        ctrl_frame.pack(fill=tk.BOTH, padx=10, pady=5)

        set_freq_name = tk.Label(ctrl_frame, text="설정 주파수(Hz)", font=("Arial", 12))
        set_freq_name.grid(row=0, column=0, padx=(10, 0))
        set_acc_name = tk.Label(ctrl_frame, text="설정 가속시간(sec)", font=("Arial", 12))
        set_acc_name.grid(row=0, column=1)
        set_dec_name = tk.Label(ctrl_frame, text="설정 감속시간(sec)", font=("Arial", 12))
        set_dec_name.grid(row=0, column=2, padx=(0, 10))

        self.set_freq_var = tk.StringVar(value="0.00")
        set_freq_btn = ttk.Button(ctrl_frame, textvariable=self.set_freq_var,
                                  command=lambda: self.open_digit_input(self.set_freq))
        set_freq_btn.grid(row=1, column=0, padx=(10, 0))
        self.set_acc_var = tk.StringVar(value="0.0")
        set_acc_value = ttk.Button(ctrl_frame, textvariable=self.set_acc_var,
                                   command=lambda: self.open_digit_input(self.set_acc))
        set_acc_value.grid(row=1, column=1)
        self.set_dec_var = tk.StringVar(value="0.0")
        set_dec_value = ttk.Button(ctrl_frame, textvariable=self.set_dec_var,
                                   command=lambda: self.open_digit_input(self.set_dec))
        set_dec_value.grid(row=1, column=2, padx=(0, 10))

        cur_freq_name = tk.Label(ctrl_frame, text="출력 주파수(Hz)", font=("Arial", 12))
        cur_freq_name.grid(row=2, column=0, padx=(10, 0))
        cur_acc_name = tk.Label(ctrl_frame, text="가속시간(sec)", font=("Arial", 12))
        cur_acc_name.grid(row=2, column=1)
        cur_dec_name = tk.Label(ctrl_frame, text="감속시간(sec)", font=("Arial", 12))
        cur_dec_name.grid(row=2, column=2, padx=(0, 10))

        self.cur_freq_var = tk.StringVar(value="0.00")
        cur_freq_value = tk.Label(ctrl_frame, textvariable=self.cur_freq_var, font=("Arial", 12))
        cur_freq_value.grid(row=3, column=0, padx=(10, 0))
        self.cur_acc_var = tk.StringVar(value="0.0")
        cur_acc_value = tk.Label(ctrl_frame, textvariable=self.cur_acc_var, font=("Arial", 12))
        cur_acc_value.grid(row=3, column=1)
        self.cur_dec_var = tk.StringVar(value="0.0")
        cur_dec_value = tk.Label(ctrl_frame, textvariable=self.cur_dec_var, font=("Arial", 12))
        cur_dec_value.grid(row=3, column=2, padx=(0, 10))

    # 운전
    def setup_run_ui(self):
        run_frame = ttk.LabelFrame(self.root, text="운전", padding=10)
        run_frame.pack(fill=tk.BOTH, padx=10, pady=5)

        run_btn = ttk.Button(run_frame, text="운전", command=self.motor_start)
        run_btn.grid(row=0, column=0, padx=10)
        stop_btn = ttk.Button(run_frame, text="정지", command=self.motor_stop)
        stop_btn.grid(row=0, column=1, padx=10)

        custom_label = tk.Label(run_frame, text="직접 주소 입력:")
        custom_label.grid(row=1, column=0, padx=10)
        self.custom_input = tk.Entry(run_frame, font=("Arial", 12))
        self.custom_input.grid(row=1, column=1, padx=10)
        custom_btn = ttk.Button(run_frame, text="읽기", command=self.check_custom_register)
        custom_btn.grid(row=1, column=2, padx=10)
        self.custom_write = tk.Entry(run_frame, font=("Arial", 12))
        self.custom_write.grid(row=1, column=3, padx=10)
        write_btn = ttk.Button(run_frame, text="쓰기", command=self.write_custom_register)
        write_btn.grid(row=1, column=4, padx=10)

    # 로그
    def setup_log_ui(self):
        log_frame = ttk.LabelFrame(self.root, text="로그", padding=10)
        log_frame.pack(fill=tk.BOTH, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
# endregion

# region functions
    def update_monitor(self, _list):
        # if True: return
        self.out_a_var.set(f"{_list[2]:.1f} A")
        self.out_freq_var.set(f"{_list[3]:.2f} Hz")
        self.out_v_var.set(f"{_list[4]} V")
        self.out_dc_var.set(f"{_list[5]} V")
        self.out_p_var.set(f"{_list[6]:.1f} kW")
        
        def _toggle_state(var: tk.StringVar):
            if var.get() == "OFF":
                var.set("ON")
            else:
                var.set("OFF")

        bit_ret = self.run_state_bit ^ _list[7]
        for i, var in enumerate(self.run_state_var_list):
            if bit_ret & (1 << i):
                _toggle_state(var)
                self.run_state_bit ^= (1 << i)

        self.cur_freq_var.set(f"{_list[3]:.2f}")
        self.cur_acc_var.set(f"{_list[0]:.1f}")
        self.cur_dec_var.set(f"{_list[1]:.1f}")
    
    def open_digit_input(self, callback):
        DigitInput(self.root, callback)

    def set_freq(self, value):
        self.set_freq_var.set(f"{value:.2f}")
        self.app.on_set_freq(value)

    def set_acc(self, value):
        self.set_acc_var.set(f"{value:.1f}")
        self.app.on_set_acc(value)

    def set_dec(self, value):
        self.set_dec_var.set(f"{value:.1f}")
        self.app.on_set_dec(value)

    def motor_start(self):
        self.app.on_start_clicked()

    def motor_stop(self):
        self.app.on_stop_clicked()

    def check_custom_register(self):
        txt = self.custom_input.get().strip()
        if not txt:
            self.log("입력 창이 비어있습니다.")
            return

        try:
            if txt.lower().startswith("0x"):
                txt = txt[2:]

            addr = int(txt, 16)
            self.app.custom_check(addr)
        except Exception as e:
            self.log(f"{e}")

    def write_custom_register(self):
        txt = self.custom_input.get().strip()
        txt2 = self.custom_write.get().strip()
        if not txt or not txt2:
            self.log("입력 창이 비어있습니다.")
            return

        try:
            if txt.lower().startswith("0x"):
                txt = txt[2:]

            addr = int(txt, 16)
            value = int(txt2)
            self.app.custom_write(addr, value)
        except Exception as e:
            self.log(f"{e}")

    def log(self, message):
        """로그 메시지 추가"""
        now = datetime.now()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{now.strftime('%H:%M:%S.%f')[:-3]}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
# endregion