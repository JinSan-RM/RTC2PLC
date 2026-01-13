"""
피더 제어 탭
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QLineEdit, QFrame
)
from PySide6.QtGui import QDoubleValidator
from PySide6.QtCore import Qt

from src.utils.logger import log

class FeederTab(QWidget):
    """피더 제어 탭"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(25)
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
        
        # 내륜 모터
        self.create_motor_section(scroll_layout, "내륜 모터", "inverter_001")

        scroll_layout.addSpacing(20)
        
        # 외륜 모터
        self.create_motor_section(scroll_layout, "외륜 모터", "inverter_002")

        scroll_layout.addSpacing(30)
        
        # 배출물 사이즈 조절
        self.create_size_control(scroll_layout)

        scroll_layout.addSpacing(30)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # 스타일 적용
        self.apply_styles()
    
    def create_motor_section(self, parent_layout, title, motor_id):
        """모터 제어 섹션"""
        layout = QVBoxLayout()
        layout.setSpacing(0)

        header_layout = QHBoxLayout()
        motor_title = QLabel(title)
        motor_title.setObjectName("title_label")
        header_layout.addWidget(motor_title)

        header_layout.addSpacing(15)

        # 운전 상태
        status_label = QLabel("⚫ 정지")
        status_label.setObjectName(f"{motor_id}_status")
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

        _conf = self.app.config["inverter_config"][motor_id]
        
        # 현재 주파수
        self.add_value_display(status_layout, "현재 주파수:", f"{_conf[0]:.2f}", "Hz", f"{motor_id}_freq")
        
        # 가속 시간
        self.add_value_display(status_layout, "가속 시간:", f"{_conf[1]:.1f}", "s", f"{motor_id}_acc")
        
        # 감속 시간
        self.add_value_display(status_layout, "감속 시간:", f"{_conf[2]:.1f}", "s", f"{motor_id}_dec")

        # 출력 전류
        self.add_value_display(status_layout, "출력 전류:", "0.0", "A", f"{motor_id}_crnt")

        # 출력 전압
        self.add_value_display(status_layout, "출력 전압:", "0.0", "V", f"{motor_id}_vltg")
        
        status_layout.addStretch()
        
        contents_layout.addLayout(status_layout)
        
        # 설정 및 제어
        control_layout = QGridLayout()
        control_layout.setSpacing(10)

        row = 0
        
        # 목표 주파수
        self.create_controller(control_layout, row, motor_id, "목표 주파수:",
                               _conf[0], -120.0, 120.0, 2, "Hz", self.on_set_freq, f"{motor_id}_target_freq")
        row += 1
        
        # 가속 시간
        self.create_controller(control_layout, row, motor_id, "목표 가속 시간:",
                               _conf[1], 0.0, 999.0, 1, "s", self.on_set_acc, f"{motor_id}_target_acc")
        row += 1
        
        # 감속 시간
        self.create_controller(control_layout, row, motor_id, "목표 감속 시간:",
                               _conf[2], 0.0, 999.0, 1, "s", self.on_set_dec, f"{motor_id}_target_dec")
        
        contents_layout.addLayout(control_layout)
        
        # 운전/정지 버튼
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        btn_layout.setAlignment(Qt.AlignLeft)
        
        start_btn = QPushButton("운전")
        start_btn.setObjectName("control_btn_start")
        start_btn.setFixedSize(498, 60)
        start_btn.clicked.connect(lambda _: self.on_motor_start(motor_id))
        btn_layout.addWidget(start_btn)
        
        stop_btn = QPushButton("정지")
        stop_btn.setObjectName("control_btn_stop")
        stop_btn.setFixedSize(498, 60)
        stop_btn.clicked.connect(lambda _: self.on_motor_stop(motor_id))
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

    def create_controller(self, parent_layout, row, motor_id, name,
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
        _input.returnPressed.connect(lambda: func(motor_id))
        setattr(self, f"{attr_name}", _input)
        
        set_btn = QPushButton("설정")
        set_btn.setObjectName("setting_btn")
        set_btn.setFixedSize(112, 40)
        set_btn.clicked.connect(lambda _: func(motor_id))
        parent_layout.addWidget(set_btn, row, 3)

        parent_layout.setColumnStretch(4, 1)
    
    def create_size_control(self, parent_layout):
        """배출물 사이즈 조절"""
        layout = QVBoxLayout()
        layout.setSpacing(0)

        size_title = QLabel("배출물 사이즈 조절")
        size_title.setObjectName("title_label")
        layout.addWidget(size_title)

        layout.addSpacing(15)

        size_box = QFrame()
        size_box.setObjectName("contents_box")

        size_layout = QVBoxLayout(size_box)
        size_layout.setSpacing(0)
        size_layout.setContentsMargins(30, 30, 30, 30)

        info_label = QLabel("서보 위치를 조정하여 피더 배출물 크기를 제어합니다.")
        info_label.setObjectName("name_label")
        size_layout.addWidget(info_label)
        
        size_layout.addSpacing(10)
        
        # 프리셋 버튼들
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(20)
        
        presets = [
            ("소형", "small"),
            ("중형", "medium"),
            ("대형", "large"),
            ("사용자 정의", "custom")
        ]
        
        for text, size in presets:
            btn = QPushButton(text)
            btn.setObjectName("preset_btn")
            btn.setFixedHeight(60)
            btn.clicked.connect(lambda checked, s=size: self.on_set_size(s))
            preset_layout.addWidget(btn)
        
        size_layout.addLayout(preset_layout)

        layout.addWidget(size_box)
        
        parent_layout.addLayout(layout)
    
    # 이벤트 핸들러
    def on_set_freq(self, motor_id):
        try:
            freq = float(getattr(self, f"{motor_id}_target_freq").text())
            self.app.on_set_freq(motor_id, freq)  # motor_id 추가
            log(f"{motor_id} 주파수 설정: {freq} Hz")
            
            # 모니터링 부분에 현재 주파수 표시 업데이트
            freq_label = self.findChild(QLabel, f"{motor_id}_freq")
            if freq_label:
                freq_label.setText(f"{freq:.2f}")
                    
        except ValueError:
            log(f"잘못된 주파수 값")
    
    def on_set_acc(self, motor_id):
        try:
            acc = float(getattr(self, f"{motor_id}_target_acc").text())
            self.app.on_set_acc(motor_id, acc)
            log(f"{motor_id} 가속시간 설정: {acc} s")
            
            # 모니터링 부분 가속 시간 표시 업데이트
            acc_label = self.findChild(QLabel, f"{motor_id}_acc")
            if acc_label:
                acc_label.setText(f"{acc:.1f}")
                
        except ValueError:
            log(f"잘못된 가속시간 값")

    def on_set_dec(self, motor_id):
        try:
            dec = float(getattr(self, f"{motor_id}_target_dec").text())
            self.app.on_set_dec(motor_id, dec)
            log(f"{motor_id} 감속시간 설정: {dec} s")
            
            # 모니터링에 감속 시간 표시 업데이트
            dec_label = self.findChild(QLabel, f"{motor_id}_dec")
            if dec_label:
                dec_label.setText(f"{dec:.1f}")
        except ValueError:
            self.app.on_log(f"잘못된 감속시간 값")
    
    def on_motor_start(self, motor_id):
        self.app.motor_start(motor_id)  # 실제 모터 시작
        log(f"{motor_id} 모터 시작")
        # TODO: 실제 모터 시작
        
        # 상태 표시 업데이트
        status_label = self.findChild(QLabel, f"{motor_id}_status")
        if status_label:
            status_label.setText("🟢 운전")
            status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #3fb950;")

    def on_motor_stop(self, motor_id):
        self.app.motor_stop(motor_id)  # 실제 모터 정지
        log(f"{motor_id} 모터 정지")
        # TODO: 실제 모터 정지
        
        # 상태 표시 업데이트
        status_label = self.findChild(QLabel, f"{motor_id}_status")
        if status_label:
            status_label.setText("⚫ 정지")
            status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #8b949e;")

    def update_values(self, _data):
        for _id, _list in _data.items():
            if _list:
                _freq = self.findChild(QLabel, f"{_id}_freq")
                if _freq is None:
                    continue
                _acc = self.findChild(QLabel, f"{_id}_acc")
                _dec = self.findChild(QLabel, f"{_id}_dec")
                _crnt = self.findChild(QLabel, f"{_id}_crnt")
                _vltg = self.findChild(QLabel, f"{_id}_vltg")
                _freq.setText(f"{_list[3]:.2f}")
                _acc.setText(f"{_list[0]:.1f}")
                _dec.setText(f"{_list[1]:.1f}")
                _crnt.setText(f"{_list[2]:.1f}")
                _vltg.setText(f"{_list[4]:.1f}")
    
    def on_set_size(self, size):
        self.app.on_on_log(f"배출물 크기 설정: {size}")
        # TODO: 서보 위치 조정
    
    def apply_styles(self):
        """스타일시트 적용"""
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
            
            #preset_btn {
                background-color: #E6E6E6;
                color: #000000;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #preset_btn:hover {
                background-color: #A4A4A4;
            }
            """
        )