"""
컨베이어 제어 탭
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QLineEdit, QFrame, QScrollArea
)
from PyQt5.QtCore import Qt


class ConveyorTab(QWidget):
    """컨베이어 제어 탭 (CV01~CV04)"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(15)
        scroll_layout.setContentsMargins(20, 20, 20, 20)
        
        # CV01 ~ CV04 컨베이어
        for i in range(1, 5):
            self.create_conveyor_section(scroll_layout, f"CV0{i}", i)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # 스타일 적용
        self.apply_styles()
    
    def create_conveyor_section(self, parent_layout, conv_id, conv_num):
        """컨베이어 제어 섹션"""
        conv_group = QGroupBox(f"컨베이어 {conv_id}")
        conv_group.setObjectName("group_box")
        conv_main_layout = QVBoxLayout(conv_group)
        
        # 상태 표시
        status_layout = QHBoxLayout()
        status_layout.setSpacing(30)
        
        # 운전 상태
        status_frame = QFrame()
        status_frame_layout = QVBoxLayout(status_frame)
        status_frame_layout.setAlignment(Qt.AlignCenter)
        
        status_title = QLabel("운전 상태")
        status_title.setStyleSheet("color: #8b949e; font-size: 12px;")
        status_frame_layout.addWidget(status_title)
        
        status_label = QLabel("⚫ 정지")
        status_label.setObjectName(f"{conv_id}_status")
        status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #8b949e;")
        status_frame_layout.addWidget(status_label)
        status_layout.addWidget(status_frame)
        
        # 현재 주파수
        self.add_value_display(status_layout, "현재 주파수", "0.00", "Hz", f"{conv_id}_freq")
        
        # 가속 시간
        self.add_value_display(status_layout, "가속 시간", "0.0", "s", f"{conv_id}_acc")
        
        # 감속 시간
        self.add_value_display(status_layout, "감속 시간", "0.0", "s", f"{conv_id}_dec")
        
        status_layout.addStretch()
        conv_main_layout.addLayout(status_layout)
        
        conv_main_layout.addSpacing(15)
        
        # 설정 및 제어
        control_layout = QGridLayout()
        control_layout.setSpacing(10)
        
        row = 0
        
        # 목표 주파수
        control_layout.addWidget(QLabel("목표 주파수:"), row, 0)
        freq_input = QLineEdit("0.00")
        freq_input.setObjectName("input_field")
        setattr(self, f"{conv_id}_target_freq", freq_input)
        control_layout.addWidget(freq_input, row, 1)
        control_layout.addWidget(QLabel("Hz"), row, 2)
        
        freq_set_btn = QPushButton("설정")
        freq_set_btn.setObjectName("setting_btn")
        freq_set_btn.clicked.connect(lambda: self.on_set_freq(conv_id))
        control_layout.addWidget(freq_set_btn, row, 3)
        row += 1
        
        # 가속 시간
        control_layout.addWidget(QLabel("목표 가속 시간:"), row, 0)
        acc_input = QLineEdit("0.0")
        acc_input.setObjectName("input_field")
        setattr(self, f"{conv_id}_target_acc", acc_input)
        control_layout.addWidget(acc_input, row, 1)
        control_layout.addWidget(QLabel("s"), row, 2)
        
        acc_set_btn = QPushButton("설정")
        acc_set_btn.setObjectName("setting_btn")
        acc_set_btn.clicked.connect(lambda: self.on_set_acc(conv_id))
        control_layout.addWidget(acc_set_btn, row, 3)
        row += 1
        
        # 감속 시간
        control_layout.addWidget(QLabel("목표 감속 시간:"), row, 0)
        dec_input = QLineEdit("0.0")
        dec_input.setObjectName("input_field")
        setattr(self, f"{conv_id}_target_dec", dec_input)
        control_layout.addWidget(dec_input, row, 1)
        control_layout.addWidget(QLabel("s"), row, 2)
        
        dec_set_btn = QPushButton("설정")
        dec_set_btn.setObjectName("setting_btn")
        dec_set_btn.clicked.connect(lambda: self.on_set_dec(conv_id))
        control_layout.addWidget(dec_set_btn, row, 3)
        
        conv_main_layout.addLayout(control_layout)
        
        conv_main_layout.addSpacing(10)
        
        # 운전/정지 버튼
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        start_btn = QPushButton("운전")
        start_btn.setObjectName("control_btn_start")
        start_btn.setMinimumHeight(50)
        start_btn.clicked.connect(lambda: self.on_conveyor_start(conv_id))
        btn_layout.addWidget(start_btn)
        
        stop_btn = QPushButton("정지")
        stop_btn.setObjectName("control_btn_stop")
        stop_btn.setMinimumHeight(50)
        stop_btn.clicked.connect(lambda: self.on_conveyor_stop(conv_id))
        btn_layout.addWidget(stop_btn)
        
        conv_main_layout.addLayout(btn_layout)
        
        parent_layout.addWidget(conv_group)
    
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
    
    # 이벤트 핸들러
    def on_set_freq(self, conv_id):
        freq = getattr(self, f"{conv_id}_target_freq").text()
        self.app.on_log(f"{conv_id} 주파수 설정: {freq} Hz")
        # TODO: 실제 주파수 설정
    
    def on_set_acc(self, conv_id):
        acc = getattr(self, f"{conv_id}_target_acc").text()
        self.app.on_log(f"{conv_id} 가속시간 설정: {acc} s")
        # TODO: 실제 가속시간 설정
    
    def on_set_dec(self, conv_id):
        dec = getattr(self, f"{conv_id}_target_dec").text()
        self.app.on_log(f"{conv_id} 감속시간 설정: {dec} s")
        # TODO: 실제 감속시간 설정
    
    def on_conveyor_start(self, conv_id):
        self.app.on_log(f"{conv_id} 컨베이어 시작")
        # TODO: 실제 컨베이어 시작
    
    def on_conveyor_stop(self, conv_id):
        self.app.on_log(f"{conv_id} 컨베이어 정지")
        # TODO: 실제 컨베이어 정지
    
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
        """)