from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QScrollArea
)
from PySide6.QtGui import QDoubleValidator
from PySide6.QtCore import Qt

from src.utils.logger import log

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
        
        # 스크롤
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        scroll_content.setMaximumWidth(1610)

        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setAlignment(Qt.AlignTop)
        scroll_layout.setSpacing(0)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        scroll_layout.addSpacing(25)
        
        # CV01 ~ CV04 컨베이어 섹션 생성
        for i in range(1, 5):
            self.create_conveyor_section(scroll_layout, f"컨베이어 0{i}", f"inverter_00{i+2}")
            scroll_layout.addSpacing(20)

        scroll_layout.addSpacing(10)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # 스타일 시트 적용 (피더 탭과 동일한 스타일)
        self.apply_styles()
    
    def create_conveyor_section(self, parent_layout, title, conv_id):
        """컨베이어 제어 섹션"""
        layout = QVBoxLayout()
        layout.setSpacing(0)

        header_layout = QHBoxLayout()
        conv_title = QLabel(title)
        conv_title.setObjectName("title_label")
        header_layout.addWidget(conv_title)

        header_layout.addSpacing(15)

        # 운전 상태
        status_label = QLabel("⚫ 정지")
        status_label.setObjectName(f"{conv_id}_status")
        status_label.setFixedSize(74, 34)
        status_label.setStyleSheet(
            """
            background-color: #F3F4F6;
            border: 1px solid #E2E2E2;
            border-radius: 4px;
            color: #4B4B4B;
            font-size: 14px;
            font-weight: normal;
            """
        )
        header_layout.addWidget(status_label)

        header_layout.addStretch()

        layout.addLayout(header_layout)

        layout.addSpacing(10)

        # 상태 표시
        contents_box = QFrame()
        contents_box.setObjectName("contents_box")

        contents_layout = QVBoxLayout(contents_box)
        contents_layout.setSpacing(25)
        contents_layout.setContentsMargins(30, 30, 30, 30)

        status_layout = QHBoxLayout()
        status_layout.setSpacing(50)

        _conf = self.app.config["inverter_config"][conv_id]
        
        # 값 표시 (주파수, 시간 등)
        self.add_value_display(status_layout, "현재 주파수", f"{_conf[0]:.2f}", "Hz", f"{conv_id}_freq")
        self.add_value_display(status_layout, "가속 시간", f"{_conf[1]:.1f}", "s", f"{conv_id}_acc")
        self.add_value_display(status_layout, "감속 시간", f"{_conf[2]:.1f}", "s", f"{conv_id}_dec")
        self.add_value_display(status_layout, "출력 전류", "0.0", "A", f"{conv_id}_crnt")
        self.add_value_display(status_layout, "출력 전압", "0.0", "V", f"{conv_id}_vltg")
        
        status_layout.addStretch()
        
        contents_layout.addLayout(status_layout)
        
        # --- 설정 및 제어 섹션 ---
        control_layout = QGridLayout()
        control_layout.setSpacing(10)
        
        row = 0
        
        # 목표 주파수
        self.create_controller(control_layout, row, conv_id, "목표 주파수:",
                               _conf[0], -120.0, 120.0, 2, "Hz", self.on_set_freq, f"{conv_id}_target_freq")
        row += 1
        
        # 가속 시간
        self.create_controller(control_layout, row, conv_id, "목표 가속 시간:",
                               _conf[1], 0.0, 999.0, 1, "s", self.on_set_acc, f"{conv_id}_target_acc")
        row += 1
        
        # 감속 시간
        self.create_controller(control_layout, row, conv_id, "목표 감속 시간:",
                               _conf[2], 0.0, 999.0, 1, "s", self.on_set_dec, f"{conv_id}_target_dec")
        
        contents_layout.addLayout(control_layout)
        
        # --- 운전/정지 버튼 ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # 운전 버튼
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        btn_layout.setAlignment(Qt.AlignLeft)
        
        start_btn = QPushButton("운전")
        start_btn.setObjectName("control_btn_start")
        start_btn.setFixedSize(498, 60)
        start_btn.clicked.connect(lambda _: self.on_motor_start(conv_id))
        btn_layout.addWidget(start_btn)
        
        stop_btn = QPushButton("정지")
        stop_btn.setObjectName("control_btn_stop")
        stop_btn.setFixedSize(498, 60)
        stop_btn.clicked.connect(lambda _: self.on_motor_stop(conv_id))
        btn_layout.addWidget(stop_btn)
        
        contents_layout.addLayout(btn_layout)

        layout.addWidget(contents_box)
        
        parent_layout.addLayout(layout)

    def add_value_display(self, parent_layout, name, value, unit, obj_name):
        """값 표시 위젯 추가"""
        layout = QHBoxLayout()
        layout.setSpacing(0)
        
        # 이름
        name_label = QLabel(name)
        name_label.setObjectName("name_label")
        layout.addWidget(name_label)

        layout.addSpacing(10)
        
        value_label = QLabel(value)
        value_label.setObjectName(obj_name)
        value_label.setStyleSheet(
            """
            color: #2DB591;
            font-size: 26px;
            font-weight: 600;
            """
        )
        layout.addWidget(value_label)

        layout.addSpacing(5)
        
        unit_label = QLabel(unit)
        unit_label.setStyleSheet(
            """
            color: #000000;
            font-size: 26px;
            font-weight: 600;
            """
        )
        layout.addWidget(unit_label)
        parent_layout.addLayout(layout)
    
    def create_controller(self, parent_layout, row, conv_id, name,
                          def_val, min, max, decimal, unit, func, attr_name):
        name_label = QLabel(f"{name}")
        name_label.setObjectName("name_label")
        parent_layout.addWidget(name_label, row, 0)
        _input = QLineEdit(f"{def_val}")
        _input.setValidator(QDoubleValidator(min, max, decimal, parent_layout))
        _input.setPlaceholderText(f"{min} ~ {max} 입력 가능")
        _input.setObjectName("input_field")
        _input.setFixedSize(600, 40)
        parent_layout.addWidget(_input, row, 1)

        unit_label = QLabel(f"{unit}")
        unit_label.setObjectName("unit_label")
        parent_layout.addWidget(unit_label, row, 2)
        _input.returnPressed.connect(lambda: func(conv_id))
        setattr(self, f"{attr_name}", _input)
        
        set_btn = QPushButton("설정")
        set_btn.setObjectName("setting_btn")
        set_btn.setFixedSize(112, 40)
        set_btn.clicked.connect(lambda _: func(conv_id))
        parent_layout.addWidget(set_btn, row, 3)

        parent_layout.setColumnStretch(4, 1)
    
    # --- 이벤트 핸들러 ---
    def on_set_freq(self, conv_id):
        try:
            freq = float(getattr(self, f"{conv_id}_target_freq").text())
            self.app.on_set_freq(conv_id, freq)
            log(f"{conv_id} 주파수 설정: {freq} Hz")
            
            freq_label = self.findChild(QLabel, f"{conv_id}_freq")
            if freq_label:
                freq_label.setText(f"{freq:.2f}")
        except ValueError:
            log(f"잘못된 주파수 값")
    
    def on_set_acc(self, conv_id):
        try:
            acc = float(getattr(self, f"{conv_id}_target_acc").text())
            self.app.on_set_acc(conv_id, acc)
            log(f"{conv_id} 가속시간 설정: {acc} s")
            
            acc_label = self.findChild(QLabel, f"{conv_id}_acc")
            if acc_label:
                acc_label.setText(f"{acc:.1f}")
        except ValueError:
            log(f"잘못된 가속시간 값")
    
    def on_set_dec(self, conv_id):
        try:
            dec = float(getattr(self, f"{conv_id}_target_dec").text())
            self.app.on_set_dec(conv_id, dec)
            log(f"{conv_id} 감속시간 설정: {dec} s")
            
            dec_label = self.findChild(QLabel, f"{conv_id}_dec")
            if dec_label:
                dec_label.setText(f"{dec:.1f}")
        except ValueError:
            log(f"잘못된 감속시간 값")
    
    def on_conveyor_start(self, conv_id):
        self.app.motor_start(conv_id)
        
        status_label = self.findChild(QLabel, f"{conv_id}_status")
        if status_label:
            status_label.setText("🟢 운전")
            status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #3fb950; background-color: transparent; border: none;")
    
    def on_conveyor_stop(self, conv_id):
        self.app.motor_stop(conv_id)
        
        status_label = self.findChild(QLabel, f"{conv_id}_status")
        if status_label:
            status_label.setText("⚫ 정지")
            status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #8b949e; background-color: transparent; border: none;")

    def update_values(self, _data):
        for _id, _list in _data.items():
            if _list:
                _freq = getattr(self, f"{_id}_freq", None)
                if _freq is None:
                    continue
                _acc = getattr(self, f"{_id}_acc")
                _dec = getattr(self, f"{_id}_dec")
                _crnt = getattr(self, f"{_id}_crnt")
                _vltg = getattr(self, f"{_id}_vltg")
                _freq.setText(f"{_list[3]:.2f}")
                _acc.setText(f"{_list[0]:.1f}")
                _dec.setText(f"{_list[1]:.1f}")
                _crnt.setText(f"{_list[2]:.1f}")
                _vltg.setText(f"{_list[4]:.1f}")
    
    def apply_styles(self):
        """스타일시트 적용 (FeederTab과 디자인 통일)"""
        self.setStyleSheet(
            """
            /* 스크롤바 */
            QScrollArea { 
                border: none; 
                background-color: transparent; 
            }

            QScrollBar:vertical {
                border: none;
                background: #F3F4F6;
                width: 5px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background: #E2E2E2;
                min-height: 20px;
                border-radius: 5px;
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            #scroll_content {
                background-color: transparent;
            }
            
            #contents_box {
                background-color: #FAFAFA;
                border: 1px solid #E2E2E2;
                border-radius: 7px;
            }
            
            #title_label {
                color: #000000;
                font-size: 16px;
                font-weight: medium;
            }

            #name_label {
                color: #4B4B4B;
                font-size: 14px;
                font-weight: normal;
            }

            #unit_label {
                color: #A8A8A8;
                font-size: 14px;
                font-weight: normal;
            }
            
            #input_field {
                background-color: #FFFFFF;
                border: 1px solid #D4D4D4;
                border-radius: 4px;
                padding: 10;
                color: #000000;
                font-size: 14px;
                font-weight: normal;
            }
            
            #input_field:focus {
                border-color: #AAAAAA;
            }
            
            #setting_btn {
                background-color: #F5F4F8;
                border: 1px solid #A4A4A4;
                border-radius: 4px;
                color: #A4A4A4;
                font-size: 14px;
                font-weight: medium;
            }
            
            #setting_btn:hover {
                background-color: #FAFAFA;
            }
            
            #control_btn_start {
                background-color: #2DB591;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #control_btn_start:hover {
                background-color: #2ea043;
            }
            
            #control_btn_stop {
                background-color: #FF2427;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #control_btn_stop:hover {
                background-color: #f85149;
            }
            """
        )