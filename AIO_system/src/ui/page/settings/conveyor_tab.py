from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QLineEdit, QFrame, QScrollArea
)
from PySide6.QtCore import Qt

from src.utils.config_util import APP_CONFIG
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
        
        # 스크롤 영역 설정
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # 스크롤 영역의 배경을 투명하게 하여 메인 배경 위에 그룹박스가 떠있는 느낌을 줌
        scroll.setStyleSheet("""
            QScrollArea { 
                border: none; 
                background-color: transparent; 
            }
            QScrollBar:vertical {
                border: none;
                background: #0d1117;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #30363d;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # 스크롤 내부 컨텐츠 위젯
        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        # 컨텐츠 위젯도 투명하게 설정해야 그룹박스 배경색이 돋보임
        scroll_content.setStyleSheet("#scroll_content { background-color: transparent; }")
        
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(15)  # 피더 탭과 동일한 간격
        scroll_layout.setContentsMargins(20, 20, 20, 20)  # 피더 탭과 동일한 여백
        
        # CV01 ~ CV04 컨베이어 섹션 생성
        for i in range(1, 5):
            self.create_conveyor_section(scroll_layout, f"컨베이어 0{i}", f"inverter_00{i+2}")
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # 스타일 시트 적용 (피더 탭과 동일한 스타일)
        self.apply_styles()
    
    def create_conveyor_section(self, parent_layout, title, conv_id):
        """컨베이어 제어 섹션"""
        conv_group = QGroupBox(f"{title}")
        conv_group.setObjectName("group_box")  # 스타일 적용을 위한 ID
        conv_main_layout = QVBoxLayout(conv_group)
        
        # --- 상태 표시 섹션 ---
        status_layout = QHBoxLayout()
        status_layout.setSpacing(30)
        
        # 운전 상태
        status_frame = QFrame()
        status_frame_layout = QVBoxLayout(status_frame)
        status_frame_layout.setAlignment(Qt.AlignCenter)
        
        status_title = QLabel("운전 상태")
        # 라벨 배경 투명화 (그룹박스 색상 유지)
        status_title.setStyleSheet("color: #8b949e; font-size: 12px; background-color: transparent; border: none;")
        status_frame_layout.addWidget(status_title)
        
        status_label = QLabel("⚫ 정지")
        status_label.setObjectName(f"{conv_id}_status")
        status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #8b949e; background-color: transparent; border: none;")
        status_frame_layout.addWidget(status_label)
        status_layout.addWidget(status_frame)

        _conf = self.app.config["inverter_config"][conv_id]
        
        # 값 표시 (주파수, 시간 등)
        self.add_value_display(status_layout, "현재 주파수", f"{_conf[0]:.2f}", "Hz", f"{conv_id}_freq")
        self.add_value_display(status_layout, "가속 시간", f"{_conf[1]:.1f}", "s", f"{conv_id}_acc")
        self.add_value_display(status_layout, "감속 시간", f"{_conf[2]:.1f}", "s", f"{conv_id}_dec")
        
        status_layout.addStretch()
        conv_main_layout.addLayout(status_layout)
        
        conv_main_layout.addSpacing(15)
        
        # --- 설정 및 제어 섹션 ---
        control_layout = QGridLayout()
        control_layout.setSpacing(10)
        
        row = 0
        
        # 목표 주파수
        control_layout.addWidget(self.create_label("목표 주파수:"), row, 0)
        freq_input = QLineEdit(f"{_conf[0]:.2f}")
        freq_input.setObjectName("input_field")
        setattr(self, f"{conv_id}_target_freq", freq_input)
        control_layout.addWidget(freq_input, row, 1)
        control_layout.addWidget(self.create_label("Hz"), row, 2)
        
        freq_set_btn = QPushButton("설정")
        freq_set_btn.setObjectName("setting_btn")
        freq_set_btn.clicked.connect(lambda _: self.on_set_freq(conv_id))
        control_layout.addWidget(freq_set_btn, row, 3)
        row += 1
        
        # 가속 시간
        control_layout.addWidget(self.create_label("목표 가속 시간:"), row, 0)
        acc_input = QLineEdit(f"{_conf[1]:.1f}")
        acc_input.setObjectName("input_field")
        setattr(self, f"{conv_id}_target_acc", acc_input)
        control_layout.addWidget(acc_input, row, 1)
        control_layout.addWidget(self.create_label("s"), row, 2)
        
        acc_set_btn = QPushButton("설정")
        acc_set_btn.setObjectName("setting_btn")
        acc_set_btn.clicked.connect(lambda _: self.on_set_acc(conv_id))
        control_layout.addWidget(acc_set_btn, row, 3)
        row += 1
        
        # 감속 시간
        control_layout.addWidget(self.create_label("목표 감속 시간:"), row, 0)
        dec_input = QLineEdit(f"{_conf[2]:.1f}")
        dec_input.setObjectName("input_field")
        setattr(self, f"{conv_id}_target_dec", dec_input)
        control_layout.addWidget(dec_input, row, 1)
        control_layout.addWidget(self.create_label("s"), row, 2)
        
        dec_set_btn = QPushButton("설정")
        dec_set_btn.setObjectName("setting_btn")
        dec_set_btn.clicked.connect(lambda _: self.on_set_dec(conv_id))
        control_layout.addWidget(dec_set_btn, row, 3)
        
        conv_main_layout.addLayout(control_layout)
        
        conv_main_layout.addSpacing(10)
        
        # --- 운전/정지 버튼 ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # 운전 버튼
        start_btn = QPushButton("운전")
        start_btn.setObjectName("control_btn_start") # ID 부여 (스타일시트 연동)
        start_btn.setMinimumHeight(50)
        start_btn.clicked.connect(lambda _: self.on_conveyor_start(conv_id))
        btn_layout.addWidget(start_btn)
        
        # 정지 버튼
        stop_btn = QPushButton("정지")
        stop_btn.setObjectName("control_btn_stop") # ID 부여 (스타일시트 연동)
        stop_btn.setMinimumHeight(50)
        stop_btn.clicked.connect(lambda _: self.on_conveyor_stop(conv_id))
        btn_layout.addWidget(stop_btn)
        
        conv_main_layout.addLayout(btn_layout)
        
        parent_layout.addWidget(conv_group)
    
    def create_label(self, text):
        """기본 라벨 생성 헬퍼"""
        lbl = QLabel(text)
        lbl.setStyleSheet("background-color: transparent; border: none; color: #c9d1d9;")
        return lbl

    def add_value_display(self, layout, name, value, unit, obj_name):
        """값 표시 위젯 추가"""
        frame = QFrame()
        frame_layout = QVBoxLayout(frame)
        frame_layout.setAlignment(Qt.AlignCenter)
        frame_layout.setSpacing(5)
        
        # 이름
        name_label = QLabel(name)
        name_label.setStyleSheet("color: #8b949e; font-size: 12px; background-color: transparent; border: none;")
        name_label.setAlignment(Qt.AlignCenter)
        frame_layout.addWidget(name_label)
        
        # 값
        value_layout = QHBoxLayout()
        value_layout.setAlignment(Qt.AlignCenter)
        
        value_label = QLabel(value)
        value_label.setObjectName(obj_name)
        value_label.setStyleSheet("color: #58a6ff; font-size: 18px; font-weight: bold; background-color: transparent; border: none;")
        setattr(self, obj_name, value_label)
        value_layout.addWidget(value_label)
        
        unit_label = QLabel(unit)
        unit_label.setStyleSheet("color: #8b949e; font-size: 12px; background-color: transparent; border: none;")
        value_layout.addWidget(unit_label)
        
        frame_layout.addLayout(value_layout)
        layout.addWidget(frame)
    
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
                _freq.setText(f"{_list[3]:.2f}")
                _acc.setText(f"{_list[0]:.1f}")
                _dec.setText(f"{_list[1]:.1f}")
    
    def apply_styles(self):
        """스타일시트 적용 (FeederTab과 디자인 통일)"""
        self.setStyleSheet("""
            /* 그룹박스: 피더 탭과 동일한 짙은 배경색(#0d1117) 적용 */
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
                background-color: transparent;
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
            
            /* 운전 버튼 (꽉 찬 초록색) */
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
            
            /* 정지 버튼 (꽉 찬 빨간색) */
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