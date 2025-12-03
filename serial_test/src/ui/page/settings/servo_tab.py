"""
서보 제어 탭
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QLineEdit, QRadioButton,
    QButtonGroup, QFrame
)
from PyQt5.QtCore import Qt

from src.config_util import get_servo_modified_value


class ServoTab(QWidget):
    """서보 제어 탭"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 상단: 상태 모니터링
        self.create_status_section(main_layout)
        
        # 중단: 제어 버튼들
        self.create_control_section(main_layout)
        
        # 하단: 위치 설정
        self.create_position_section(main_layout)
        
        # 정밀 이동
        self.create_jog_section(main_layout)
        
        main_layout.addStretch()
        
        # 스타일 적용
        self.apply_styles()
    
    def create_status_section(self, parent_layout):
        """상태 모니터링 섹션"""
        status_group = QGroupBox("현재 상태")
        status_group.setObjectName("group_box")
        status_layout = QHBoxLayout(status_group)
        status_layout.setSpacing(20)
        
        # 현재 위치
        self.add_status_item(status_layout, "현재 위치", "0.000", "mm")
        
        # 속도
        self.add_status_item(status_layout, "속도", "0.000", "mm/s")
        
        # 경보
        alarm_frame = QFrame()
        alarm_layout = QVBoxLayout(alarm_frame)
        alarm_layout.setAlignment(Qt.AlignCenter)
        alarm_label = QLabel("경보")
        alarm_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        alarm_layout.addWidget(alarm_label)
        
        self.alarm_indicator = QLabel("⚫ 정상")
        self.alarm_indicator.setObjectName("alarm_indicator")
        self.alarm_indicator.setAlignment(Qt.AlignCenter)
        alarm_layout.addWidget(self.alarm_indicator)
        status_layout.addWidget(alarm_frame)
        
        # 에러 코드
        error_frame = QFrame()
        error_layout = QVBoxLayout(error_frame)
        error_layout.setAlignment(Qt.AlignCenter)
        error_label = QLabel("에러 코드")
        error_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        error_layout.addWidget(error_label)
        
        self.error_code = QLabel("0x0000")
        self.error_code.setStyleSheet("color: #58a6ff; font-size: 18px; font-weight: bold;")
        self.error_code.setAlignment(Qt.AlignCenter)
        error_layout.addWidget(self.error_code)
        status_layout.addWidget(error_frame)
        
        parent_layout.addWidget(status_group)
    
    def add_status_item(self, layout, name, value, unit):
        """상태 항목 추가"""
        frame = QFrame()
        item_layout = QVBoxLayout(frame)
        item_layout.setAlignment(Qt.AlignCenter)
        
        # 이름
        name_label = QLabel(name)
        name_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        name_label.setAlignment(Qt.AlignCenter)
        item_layout.addWidget(name_label)
        
        # 값 + 단위
        value_layout = QHBoxLayout()
        value_layout.setAlignment(Qt.AlignCenter)
        
        value_label = QLabel(value)
        value_label.setObjectName(f"servo_{name}")
        value_label.setStyleSheet("color: #58a6ff; font-size: 20px; font-weight: bold;")
        value_layout.addWidget(value_label)
        
        unit_label = QLabel(unit)
        unit_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        value_layout.addWidget(unit_label)
        
        item_layout.addLayout(value_layout)
        layout.addWidget(frame)
        
        # 나중에 업데이트하기 위해 저장
        if not hasattr(self, 'status_values'):
            self.status_values = {}
        self.status_values[name] = value_label
    
    def create_control_section(self, parent_layout):
        """제어 버튼 섹션"""
        control_group = QGroupBox("제어")
        control_group.setObjectName("group_box")
        control_layout = QHBoxLayout(control_group)
        control_layout.setSpacing(10)
        
        # 서보 ON/OFF
        servo_on_btn = QPushButton("서보 ON")
        servo_on_btn.setObjectName("control_btn_on")
        servo_on_btn.setMinimumHeight(50)
        servo_on_btn.clicked.connect(self.on_servo_on)
        control_layout.addWidget(servo_on_btn)
        
        servo_off_btn = QPushButton("서보 OFF")
        servo_off_btn.setObjectName("control_btn_off")
        servo_off_btn.setMinimumHeight(50)
        servo_off_btn.clicked.connect(self.on_servo_off)
        control_layout.addWidget(servo_off_btn)
        
        # 리셋
        reset_btn = QPushButton("리셋")
        reset_btn.setObjectName("control_btn_reset")
        reset_btn.setMinimumHeight(50)
        reset_btn.clicked.connect(self.on_reset)
        control_layout.addWidget(reset_btn)
        
        # 정지
        stop_btn = QPushButton("정지")
        stop_btn.setObjectName("control_btn_stop")
        stop_btn.setMinimumHeight(50)
        stop_btn.clicked.connect(self.on_stop)
        control_layout.addWidget(stop_btn)
        
        parent_layout.addWidget(control_group)
    
    def create_position_section(self, parent_layout):
        """위치 설정 섹션"""
        position_group = QGroupBox("위치 설정")
        position_group.setObjectName("group_box")
        position_layout = QGridLayout(position_group)
        position_layout.setSpacing(10)
        
        row = 0
        
        # 원점 설정
        position_layout.addWidget(QLabel("원점 설정:"), row, 0)
        origin_btn = QPushButton("현재 위치를 원점으로")
        origin_btn.setObjectName("setting_btn")
        origin_btn.clicked.connect(self.on_set_origin)
        position_layout.addWidget(origin_btn, row, 1, 1, 2)
        row += 1
        
        # 상한선 / 하한선
        position_layout.addWidget(QLabel("상한선:"), row, 0)
        self.upper_limit = QLineEdit("1000")
        self.upper_limit.setObjectName("input_field")
        position_layout.addWidget(self.upper_limit, row, 1)
        position_layout.addWidget(QLabel("mm"), row, 2)
        row += 1
        
        position_layout.addWidget(QLabel("하한선:"), row, 0)
        self.lower_limit = QLineEdit("0")
        self.lower_limit.setObjectName("input_field")
        position_layout.addWidget(self.lower_limit, row, 1)
        position_layout.addWidget(QLabel("mm"), row, 2)
        row += 1
        
        # 목표 위치 / 속도
        position_layout.addWidget(QLabel("목표 위치:"), row, 0)
        self.target_position = QLineEdit("0")
        self.target_position.setObjectName("input_field")
        position_layout.addWidget(self.target_position, row, 1)
        position_layout.addWidget(QLabel("mm"), row, 2)
        row += 1
        
        position_layout.addWidget(QLabel("이동 속도:"), row, 0)
        self.move_speed = QLineEdit("100")
        self.move_speed.setObjectName("input_field")
        position_layout.addWidget(self.move_speed, row, 1)
        position_layout.addWidget(QLabel("mm/s"), row, 2)
        row += 1
        
        # 이동 버튼
        move_btn = QPushButton("지정 위치로 이동")
        move_btn.setObjectName("control_btn_move")
        move_btn.setMinimumHeight(45)
        move_btn.clicked.connect(self.on_move_to_position)
        position_layout.addWidget(move_btn, row, 0, 1, 3)
        
        parent_layout.addWidget(position_group)
    
    def create_jog_section(self, parent_layout):
        """정밀 이동 섹션"""
        jog_group = QGroupBox("정밀 이동")
        jog_group.setObjectName("group_box")
        jog_layout = QVBoxLayout(jog_group)
        
        # 모드 선택
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(20)
        
        mode_label = QLabel("이동 모드:")
        mode_layout.addWidget(mode_label)
        
        self.jog_mode = QRadioButton("조그 이동 (연속)")
        self.jog_mode.setChecked(True)
        self.jog_mode.setObjectName("radio_btn")
        mode_layout.addWidget(self.jog_mode)
        
        self.inch_mode = QRadioButton("인칭 이동 (단계)")
        self.inch_mode.setObjectName("radio_btn")
        mode_layout.addWidget(self.inch_mode)
        
        mode_layout.addStretch()
        jog_layout.addLayout(mode_layout)
        
        # 설정값
        settings_layout = QHBoxLayout()
        
        settings_layout.addWidget(QLabel("조그 속도:"))
        self.jog_speed = QLineEdit("10")
        self.jog_speed.setObjectName("input_field")
        self.jog_speed.setMaximumWidth(100)
        settings_layout.addWidget(self.jog_speed)
        settings_layout.addWidget(QLabel("mm/s"))
        
        settings_layout.addSpacing(30)
        
        settings_layout.addWidget(QLabel("인칭 거리:"))
        self.inch_distance = QLineEdit("1")
        self.inch_distance.setObjectName("input_field")
        self.inch_distance.setMaximumWidth(100)
        settings_layout.addWidget(self.inch_distance)
        settings_layout.addWidget(QLabel("mm"))
        
        settings_layout.addStretch()
        jog_layout.addLayout(settings_layout)
        
        # 이동 버튼
        move_layout = QHBoxLayout()
        move_layout.setAlignment(Qt.AlignCenter)
        
        left_btn = QPushButton("◀ 후진")
        left_btn.setObjectName("jog_btn")
        left_btn.setMinimumSize(120, 60)
        left_btn.pressed.connect(lambda: self.on_jog_move("left"))
        left_btn.clicked.connect(lambda: self.on_inch_move("left"))
        left_btn.released.connect(lambda: self.on_jog_stop())
        move_layout.addWidget(left_btn)
        
        move_layout.addSpacing(50)
        
        right_btn = QPushButton("전진 ▶")
        right_btn.setObjectName("jog_btn")
        right_btn.setMinimumSize(120, 60)
        right_btn.pressed.connect(lambda: self.on_jog_move("right"))
        right_btn.clicked.connect(lambda: self.on_inch_move("right"))
        right_btn.released.connect(lambda: self.on_jog_stop())
        move_layout.addWidget(right_btn)
        
        jog_layout.addLayout(move_layout)
        
        parent_layout.addWidget(jog_group)
    
    # 이벤트 핸들러
    def on_servo_on(self):
        self.app.on_log("서보 ON")
        self.app.servo_on(0)
    
    def on_servo_off(self):
        self.app.on_log("서보 OFF")
        self.app.servo_off(0)
    
    def on_reset(self):
        self.app.on_log("서보 리셋")
        # self.alarm_indicator.setText("⚫ 정상")
        # self.error_code.setText("0x0000")
        self.app.servo_reset(0)
    
    def on_stop(self):
        self.app.on_log("서보 정지")
        self.app.servo_stop(0)
    
    def on_set_origin(self):
        self.app.on_log("원점 설정")
        self.app.servo_set_origin(0)
    
    def on_move_to_position(self):
        position = self.target_position.text()
        speed = self.move_speed.text()
        self.app.on_log(f"위치 이동: {position}mm, 속도: {speed}mm/s")
        self.app.on_move_to_position(0, int(position*(10**3)))
    
    def on_jog_move(self, direction):
        if self.jog_mode.isChecked():
            self.app.on_log(f"조그 이동: {direction}")
            _dir = 1 if direction == "right" else -1
            v = float(self.jog_speed.text()) * (10 ** 3)
            if v == 0:
                self.app.on_log("조그 속도를 설정해주세요")
            else:
                self.app.servo_jog_move(0, v*_dir)
    
    def on_inch_move(self, direction):
        if self.inch_mode.isChecked():
            self.app.on_log(f"인칭 이동: {direction}")
            _dir = 1 if direction == "right" else -1
            dist = int(self.inch_distance.text()) * (10 ** 3)
            if dist == 0:
                self.app.on_log(f"인칭 거리를 설정해주세요")
            else:
                self.app.servo_inch_move(0, dist*_dir)
    
    def on_jog_stop(self):
        if self.jog_mode.isChecked():
            self.app.on_log("조그 이동 정지")
            self.app.servo_stop(0)
    
    def update_values(self, _data):
        ret = _data[0]
        cur_pos = get_servo_modified_value(ret[2]) / (10 ** 3)
        cur_v = get_servo_modified_value(ret[3]) / (10 ** 3)
        err_code = ret[4]

        self.status_values["현재 위치"].setText(f"{cur_pos:.03f}")
        self.status_values["속도"].setText(f"{cur_v:.03f}")

        if err_code != 0:
            self.alarm_indicator.setText("🔴 오류")
            self.error_code.setText(f"{err_code:04X}")
        else:
            self.alarm_indicator.setText("⚫ 정상")
            self.error_code.setText("0x0000")

    
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
            
            #alarm_indicator {
                font-size: 16px;
                font-weight: bold;
                padding: 5px;
            }
            
            #input_field {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 5px;
                padding: 5px;
                color: #c9d1d9;
                font-size: 13px;
            }
            
            #input_field:focus {
                border-color: #58a6ff;
            }
            
            #control_btn_on {
                background-color: #238636;
                color: white;
                border: 2px solid #2ea043;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #control_btn_on:hover {
                background-color: #2ea043;
            }
            
            #control_btn_off {
                background-color: #6e7681;
                color: white;
                border: 2px solid #8b949e;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #control_btn_off:hover {
                background-color: #8b949e;
            }
            
            #control_btn_reset, #control_btn_move {
                background-color: #1f6feb;
                color: white;
                border: 2px solid #58a6ff;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #control_btn_reset:hover, #control_btn_move:hover {
                background-color: #58a6ff;
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
            
            #setting_btn {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 5px;
                padding: 8px;
                font-size: 13px;
            }
            
            #setting_btn:hover {
                background-color: #21262d;
                border-color: #58a6ff;
            }
            
            #jog_btn {
                background-color: #6e7681;
                color: white;
                border: 2px solid #8b949e;
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
            }
            
            #jog_btn:hover {
                background-color: #8b949e;
            }
            
            #jog_btn:pressed {
                background-color: #58a6ff;
                border-color: #58a6ff;
            }
            
            QRadioButton {
                color: #c9d1d9;
                font-size: 13px;
            }
            
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
            
            QRadioButton::indicator:unchecked {
                border: 2px solid #30363d;
                border-radius: 9px;
                background-color: #161b22;
            }
            
            QRadioButton::indicator:checked {
                border: 2px solid #58a6ff;
                border-radius: 9px;
                background-color: #58a6ff;
            }
        """)