"""
피더 제어 탭
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QLineEdit, QFrame
)
from PyQt5.QtCore import Qt
from src.function.comm_manager import ModbusManager

class FeederTab(QWidget):
    """피더 제어 탭"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 내륜 모터
        self.create_motor_section(main_layout, "내륜 모터", "inverter_001")
        
        # 외륜 모터
        self.create_motor_section(main_layout, "외륜 모터", "inverter_002")
        
        # 배출물 사이즈 조절
        self.create_size_control(main_layout)
        
        main_layout.addStretch()
        
        # 스타일 적용
        self.apply_styles()
    
    def create_motor_section(self, parent_layout, title, motor_id):
        """모터 제어 섹션"""
        motor_group = QGroupBox(f"{title}")
        motor_group.setObjectName("group_box")
        motor_main_layout = QVBoxLayout(motor_group)
        
        # 상태 표시
        status_layout = QHBoxLayout()
        status_layout.setSpacing(30)
        
        # 운전 상태
        status_frame = QFrame()
        status_frame_layout = QVBoxLayout(status_frame)
        status_frame_layout.setAlignment(Qt.AlignCenter)
        
        QLabel("운전 상태").setParent(status_frame)
        status_label = QLabel("⚫ 정지")
        status_label.setObjectName(f"{motor_id}_status")
        status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #8b949e;")
        status_frame_layout.addWidget(status_label)
        status_layout.addWidget(status_frame)
        
        # 현재 주파수
        self.add_value_display(status_layout, "현재 주파수", "0.00", "Hz", f"{motor_id}_freq")
        
        # 가속 시간
        self.add_value_display(status_layout, "가속 시간", "0.0", "s", f"{motor_id}_acc")
        
        # 감속 시간
        self.add_value_display(status_layout, "감속 시간", "0.0", "s", f"{motor_id}_dec")
        
        status_layout.addStretch()
        motor_main_layout.addLayout(status_layout)
        
        motor_main_layout.addSpacing(15)
        
        # 설정 및 제어
        control_layout = QGridLayout()
        control_layout.setSpacing(10)
        
        row = 0
        
        # 목표 주파수
        control_layout.addWidget(QLabel("목표 주파수:"), row, 0)
        freq_input = QLineEdit("0.00")
        freq_input.setObjectName("input_field")
        setattr(self, f"{motor_id}_target_freq", freq_input)
        control_layout.addWidget(freq_input, row, 1)
        control_layout.addWidget(QLabel("Hz"), row, 2)
        
        freq_set_btn = QPushButton("설정")
        freq_set_btn.setObjectName("setting_btn")
        freq_set_btn.clicked.connect(lambda: self.on_set_freq(motor_id))
        control_layout.addWidget(freq_set_btn, row, 3)
        row += 1
        
        # 가속 시간
        control_layout.addWidget(QLabel("목표 가속 시간:"), row, 0)
        acc_input = QLineEdit("0.0")
        acc_input.setObjectName("input_field")
        setattr(self, f"{motor_id}_target_acc", acc_input)
        control_layout.addWidget(acc_input, row, 1)
        control_layout.addWidget(QLabel("s"), row, 2)
        
        acc_set_btn = QPushButton("설정")
        acc_set_btn.setObjectName("setting_btn")
        acc_set_btn.clicked.connect(lambda: self.on_set_acc(motor_id))
        control_layout.addWidget(acc_set_btn, row, 3)
        row += 1
        
        # 감속 시간
        control_layout.addWidget(QLabel("목표 감속 시간:"), row, 0)
        dec_input = QLineEdit("0.0")
        dec_input.setObjectName("input_field")
        setattr(self, f"{motor_id}_target_dec", dec_input)
        control_layout.addWidget(dec_input, row, 1)
        control_layout.addWidget(QLabel("s"), row, 2)
        
        dec_set_btn = QPushButton("설정")
        dec_set_btn.setObjectName("setting_btn")
        dec_set_btn.clicked.connect(lambda: self.on_set_dec(motor_id))
        control_layout.addWidget(dec_set_btn, row, 3)
        
        motor_main_layout.addLayout(control_layout)
        
        motor_main_layout.addSpacing(10)
        
        # 운전/정지 버튼
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        
        start_btn = QPushButton("운전")
        start_btn.setObjectName("control_btn_start")
        start_btn.setMinimumHeight(50)
        start_btn.clicked.connect(lambda m=motor_id: self.app.motor_start(m))
        btn_layout.addWidget(start_btn)
        
        stop_btn = QPushButton("정지")
        stop_btn.setObjectName("control_btn_stop")
        stop_btn.setMinimumHeight(50)
        stop_btn.clicked.connect(lambda m=motor_id: self.app.motor_stop(m))
        btn_layout.addWidget(stop_btn)
        
        motor_main_layout.addLayout(btn_layout)
        
        parent_layout.addWidget(motor_group)
    
    def add_value_display(self, layout, name, value, unit, obj_name):
        """값 표시 위젯 추가"""
        frame = QFrame()
        frame_layout = QVBoxLayout(frame)
        frame_layout.setAlignment(Qt.AlignCenter)
        frame_layout.setSpacing(5)
        
        # 이름
        name_label = QLabel(name)
        name_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        name_label.setAlignment(Qt.AlignCenter)
        frame_layout.addWidget(name_label)
        
        # 값
        value_layout = QHBoxLayout()
        value_layout.setAlignment(Qt.AlignCenter)
        
        value_label = QLabel(value)
        value_label.setObjectName(obj_name)
        value_label.setStyleSheet("color: #58a6ff; font-size: 18px; font-weight: bold;")
        value_layout.addWidget(value_label)
        
        unit_label = QLabel(unit)
        unit_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        value_layout.addWidget(unit_label)
        
        frame_layout.addLayout(value_layout)
        layout.addWidget(frame)
    
    def create_size_control(self, parent_layout):
        """배출물 사이즈 조절"""
        size_group = QGroupBox("배출물 사이즈 조절")
        size_group.setObjectName("group_box")
        size_layout = QVBoxLayout(size_group)
        
        info_label = QLabel("서보 위치를 조정하여 피더 배출물 크기를 제어합니다.")
        info_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        size_layout.addWidget(info_label)
        
        size_layout.addSpacing(10)
        
        # 프리셋 버튼들
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(10)
        
        presets = [
            ("소형", "small"),
            ("중형", "medium"),
            ("대형", "large"),
            ("사용자 정의", "custom")
        ]
        
        for text, size in presets:
            btn = QPushButton(text)
            btn.setObjectName("preset_btn")
            btn.setMinimumHeight(45)
            btn.clicked.connect(lambda checked, s=size: self.on_set_size(s))
            preset_layout.addWidget(btn)
        
        size_layout.addLayout(preset_layout)
        
        parent_layout.addWidget(size_group)
    
    # 이벤트 핸들러
    def on_set_freq(self, motor_id):
        freq = getattr(self, f"{motor_id}_target_freq").text()
        self.app.on_log(f"{motor_id} 주파수 설정: {freq} Hz")
        # TODO: 실제 주파수 설정
    
    def on_set_acc(self, motor_id):
        acc = getattr(self, f"{motor_id}_target_acc").text()
        self.app.on_log(f"{motor_id} 가속시간 설정: {acc} s")
        # TODO: 실제 가속시간 설정
    
    def on_set_dec(self, motor_id):
        dec = getattr(self, f"{motor_id}_target_dec").text()
        self.app.on_log(f"{motor_id} 감속시간 설정: {dec} s")
        # TODO: 실제 감속시간 설정
    
    def on_motor_start(self, motor_id):
        self.app.on_log(f"{motor_id} 모터 시작")
        # TODO: 실제 모터 시작
    
    def on_motor_stop(self, motor_id):
        self.app.on_log(f"{motor_id} 모터 정지")
        # TODO: 실제 모터 정지
    
    def on_set_size(self, size):
        self.app.on_log(f"배출물 크기 설정: {size}")
        # TODO: 서보 위치 조정
    
    def apply_styles(self):
        """스타일시트 적용"""
        self.setStyleSheet("""
            QGroupBox {
                background-color: #0d1117;
                border: 2px solid #30363d;
                border-radius: 8px;
                padding-top: 15px;
                margin-top: 10px;
                font-size: 14px;
                font-weight: bold;
                color: #c9d1d9;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 3px 10px;
                color: #58a6ff;
            }
            
            QLabel {
                color: #c9d1d9;
                font-size: 13px;
            }
            
            #input_field {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 5px;
                padding: 5px;
                color: #c9d1d9;
                font-size: 13px;
                min-width: 100px;
            }
            
            #input_field:focus {
                border-color: #58a6ff;
            }
            
            #setting_btn {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 5px;
                padding: 5px 15px;
                font-size: 13px;
            }
            
            #setting_btn:hover {
                background-color: #21262d;
                border-color: #58a6ff;
            }
            
            #control_btn_start {
                background-color: #238636;
                color: white;
                border: 2px solid #2ea043;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #control_btn_start:hover {
                background-color: #2ea043;
            }
            
            #control_btn_stop {
                background-color: #da3633;
                color: white;
                border: 2px solid #f85149;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #control_btn_stop:hover {
                background-color: #f85149;
            }
            
            #preset_btn {
                background-color: #1f6feb;
                color: white;
                border: 2px solid #58a6ff;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #preset_btn:hover {
                background-color: #58a6ff;
            }
        """)