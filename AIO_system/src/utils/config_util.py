# ============================================================
# region Modbus
# ============================================================
MODBUS_RTU_CONFIG = {
    "slave_ids": {
        "inverter_001": 1,
        "inverter_002": 2,
        "inverter_003": 3,
        "inverter_004": 4,
        "inverter_005": 5,
        "inverter_006": 6
    },
    "port": "COM7",
    "baudrate": 9600,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "timeout": 1
}
# ============================================================
# endregion
# ============================================================

# ============================================================
# region EtherCAT
# ============================================================

# 네트워크 인터페이스 이름 -> search_ifname.py 를 실행해서 얻은 네트워크 어댑터 이름을 사용함
IF_NAME = '\\Device\\NPF_{C7EBE891-A804-4047-85E5-4D0148B1D3EA}'

# 통신 사이클 간격
ETHERCAT_DELAY = 0.01

# 각종 ID
LS_VENDOR_ID = 30101
L7NH_PRODUCT_CODE = 0x00010001
D232A_PRODUCT_CODE = 0x10010008
TR32KA_PRODUCT_CODE = 0x10010009

# Sync Manager 는 0 ~ 3이 있고, 그 중 0과 1은 Mailbox(SDO)에 사용됨.
EC_RX_INDEX = 0x1C12 # Sync Manager 2 -> RxPDO를 매칭
EC_TX_INDEX = 0x1C13 # Sync Manager 3 -> TxPDO를 매칭

# RxPDO 매핑은 0x1600 ~ 0x1603의 4개가 존재하고, 일단 기본값인 0x1601을 사용하도록 한다.
SERVO_RX_MAP = [
    0x1601,
] # master -> slave

# TxPDO 매핑은 0x1A00 ~ 0x1A03의 4개가 존재하고, 일단 기본값인 0x1A01을 사용하도록 한다.
SERVO_TX_MAP = [
    0x1A01,
] # slave -> master

# 위에서 지정한 PDO 맵 주소에 아래의 매핑 데이터를 넣어준다.
# PDO 맵 주소의 subindex 0 에는 전체 매핑 개수, subindex 1 부터 매핑 데이터를 1개씩 할당
# PDO 매핑 구조: 0x 0000 / 00 / 00 -> 앞 2byte는 index, 중간 1byte는 subindex, 뒤 1byte는 해당 오브젝트 bit사이즈
SERVO_RX = [
    0x60400010, # 컨트롤 워드(unsigned short)
    0x60600008, # 운전 모드(signed char)
    0x607A0020, # 목표 위치(int)
    0x60FF0020, # 목표 속도(int)
]

SERVO_TX = [
    0x60410010, # 스테이터스 워드(unsigned short)
    0x60610008, # 운전 모드 표시(signed char)
    0x60640020, # 현재 위치(int)
    0x606C0020, # 현재 속도(int)
    0x603F0010, # 에러 코드(unsigned short)
    0x26140010, # 경고 코드(unsigned short)
]

OUTPUT_RX_MAP = [
    0x1700,
]

INPUT_TX_MAP = [
    0x1B00,
]

OUTPUT_RX = [
    0x32200101, # 운전 스위치 LAMP
    0x32200201, # 정지 스위치 LAMP
    0x32200301, # TOWER 정상운전 LAMP
    0x32200401, # TOWER 운전정지 LAMP
    0x32200501, # TOWER 알람 LAMP
    0x32200601, # TOWER BUZZER
    0x32200701, # 비전 1 조광기 POWER
    0x32200801, # 비전 2 조광기 POWER
    0x32200901, # 내륜모터 인버터 RUN
    0x32200A01, # 내륜모터 인버터 RESET
    0x32200B01, # 외륜모터 인버터 RUN
    0x32200C01, # 외륜모터 인버터 RESET
    0x32200D01, # 컨베이어#1 인버터 RUN
    0x32200E01, # 컨베이어#1 인버터 RESET
    0x32200F01, # 컨베이어#2 인버터 RUN
    0x32201001, # 컨베이어#2 인버터 RESET
    0x32201101, # 컨베이어#3 인버터 RUN
    0x32201201, # 컨베이어#3 인버터 RESET
    0x32201301, # 컨베이어#4 인버터 RUN
    0x32201401, # 컨베이어#4 인버터 RESET
    0x32201501, # 소재 1분리 SOL V/V
    0x32201601, # 소재 2분리 SOL V/V
    0x32201701, # 소재 3분리 SOL V/V
    0x32201801, # SPARE
    0x32201901, # 원점 복귀 LAMP
    0x32201A01, # 알람 리셋 LAMP
    0x32201B01,
    0x32201C01,
    0x32201D01,
    0x32201E01,
    0x32201F01,
    0x32202001,
]

INPUT_TX = [
    0x30200101, # 수동/자동
    0x30200201, # 운전
    0x30200301, # 정지
    0x30200401, # 알람리셋
    0x30200501, # 비상정지
    0x30200601, # 내륜모터 인버터 알람
    0x30200701, # 외륜모터 인버터 알람
    0x30200801, # 컨베이어#1 인버터 알람
    0x30200901, # 컨베이어#2 인버터 알람
    0x30200A01, # 컨베이어#3 인버터 알람
    0x30200B01, # 컨베이어#4 인버터 알람
    0x30200C01, # 원점 복귀
    0x30200D01,
    0x30200E01,
    0x30200F01,
    0x30201001,
    0x30201101, # 피더 배출 제품감지센서
    0x30201201,
    0x30201301,
    0x30201401,
    0x30201501,
    0x30201601,
    0x30201701,
    0x30201801,
    0x30201901,
    0x30201A01,
    0x30201B01,
    0x30201C01,
    0x30201D01,
    0x30201E01,
    0x30201F01,
    0x30202001,
]

# 앱 자체적으로 전자 기어비 적용을 위한 부분
# 기어비(인코더 펄스 / 모터 1회전당 이동거리) 현재 1회전당 10,000 μm
# UI에서 입력 시 값 1당 1 μm 를 의미하게 됨
ENCODER_RESOLUTION = 524288 # 인코더 해상도(1회전당 펄스)
BALL_SCREW_LEAD = 10 # 볼 스크류 1회전당 이동거리(mm)
UNIT_RATIO = 0.001 # 1 UserUnit당 실거리 비율(0.001mm = 1μm)
SCALE_FACTOR = (ENCODER_RESOLUTION / BALL_SCREW_LEAD) * UNIT_RATIO
# 서보로 전달할 값
def get_servo_unmodified_value(value):
    return int(round(value*SCALE_FACTOR))

# UI에 출력할 값
def get_servo_modified_value(value):
    return value/SCALE_FACTOR

from enum import IntEnum
# 서보 상태 체크용 bit mask
class STATUS_MASK(IntEnum):
    STATUS_NOT_READY_TO_SWITCH_ON = 0x0000
    STATUS_SWITCH_ON_DISABLED = 0x0040
    STATUS_READY_TO_SWITCH_ON = 0x0021
    STATUS_OPERATION_ENABLED = 0x0027
    STATUS_QUICK_STOP_ACTIVE = 0x0007
    STATUS_FAULT_REACTION_ACTIVE = 0x000F
    STATUS_FAULT = 0x0008
    STATUS_WARNING = 0x0080

def check_mask(s, m):
    low_bit = s & 0x00FF
    return (low_bit & m) == m

class SERVO_STATE(IntEnum):
    SERVO_READY = 0
    SERVO_INIT = 1
    SERVO_SHUTDOWN = 2
    SERVO_STOP = 3
    SERVO_HOMING = 6
    SERVO_CSP = 8
    SERVO_CSV = 9

SERVO_ACCEL = 2000

# ============================================================
# endregion
# ============================================================

# ============================================================
# region Config for load&save
# ============================================================
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

APP_CONFIG = {
    "inverter_config": {
        # 주파수, 가속 시간, 감속 시간 순
        "inverter_001": [ 20.0, 5.0, 10.0 ],
        "inverter_002": [ 40.0, 5.0, 10.0 ],
        "inverter_003": [ 20.0, 5.0, 10.0 ],
        "inverter_004": [ 30.0, 5.0, 10.0 ],
        "inverter_005": [ 40.0, 5.0, 10.0 ],
        "inverter_006": [ 30.0, 5.0, 10.0 ],
    },
    "servo_config": {
        # position: 위치, 속도 쌍으로 각 위치별 정보 저장
        "servo_0": {
            "position": [
                [ 65.0, 5.0 ],
                [ 85.0, 5.0 ],
                [ 110.0, 5.0 ],
                [ 140.0, 5.0 ],
                [ 180.0, 5.0 ],
                [ 250.0, 5.0 ],
            ],
            "jog_speed": 10.0,
            "inch_distance": 1.0,
        },
        "servo_1": {
            "position": [
                [ 150.0, 5.0 ],
                [ 250.0, 5.0 ],
                [ 300.0, 5.0 ],
                [ 350.0, 5.0 ],
                [ 400.0, 5.0 ],
                [ 450.0, 5.0 ],
            ],
            "jog_speed": 10.0,
            "inch_distance": 1.0,
        }
    },
    "airknife_config": {
        "airknife_1": {
            "timing": 100,
            "duration": 500,
        },
        "airknife_2": {
            "timing": 100,
            "duration": 500,
        },
        "airknife_3": {
            "timing": 100,
            "duration": 500,
        },
    },
}

FEEDER_TIME_1 = 20
FEEDER_TIME_2 = 30

# ============================================================
# endregion
# ============================================================

# ============================================================
# region Others
# ============================================================
import tkinter as tk
from tkinter import ttk, messagebox

# 변수 입력용 키패드
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

# ============================================================
# endregion
# ============================================================