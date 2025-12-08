"""
서보 제어 탭
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QLineEdit, QRadioButton,
    QButtonGroup, QFrame, QScrollArea
)
from PySide6.QtCore import Qt

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
        
        self.create_servo_section(scroll_layout, "크기 제어", 0)

        self.create_servo_section(scroll_layout, "높이 제어", 1)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # 스타일 적용
        self.apply_styles()

    def create_servo_section(self, parent_layout, title, servo_id):
        servo_group = QGroupBox(f"{title}")
        servo_group.setObjectName("group_box")
        servo_main_layout = QVBoxLayout(servo_group)

        # 상단: 상태 모니터링
        self.create_status_section(servo_main_layout, servo_id)
        
        # 중단: 제어 버튼들
        self.create_control_section(servo_main_layout, servo_id)
        
        # 하단: 위치 설정
        self.create_position_section(servo_main_layout, servo_id)
        
        # 정밀 이동
        self.create_jog_section(servo_main_layout, servo_id)

        parent_layout.addWidget(servo_group)

    def create_status_section(self, parent_layout, servo_id):
        """상태 모니터링 섹션"""
        status_group = QGroupBox("현재 상태")
        status_group.setObjectName("group_box")
        status_layout = QHBoxLayout(status_group)
        status_layout.setSpacing(20)
        
        # 현재 위치
        self.add_status_item(status_layout, "현재 위치", "0.000", "mm", f"servo_{servo_id}_pos")
        
        # 속도
        self.add_status_item(status_layout, "속도", "0.000", "mm/s", f"servo_{servo_id}_speed")
        
        # 경보
        alarm_frame = QFrame()
        alarm_layout = QVBoxLayout(alarm_frame)
        alarm_layout.setAlignment(Qt.AlignCenter)
        alarm_label = QLabel("경보")
        alarm_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        alarm_layout.addWidget(alarm_label)
        
        alarm_indicator = QLabel("⚫ 정상")
        alarm_indicator.setObjectName("alarm_indicator")
        alarm_indicator.setAlignment(Qt.AlignCenter)
        setattr(self, f"servo_{servo_id}_err_ind", alarm_indicator)
        alarm_layout.addWidget(alarm_indicator)
        status_layout.addWidget(alarm_frame)
        
        # 에러 코드
        error_frame = QFrame()
        error_layout = QVBoxLayout(error_frame)
        error_layout.setAlignment(Qt.AlignCenter)
        error_label = QLabel("에러 코드")
        error_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        error_layout.addWidget(error_label)
        
        error_code = QLabel("0x0000")
        error_code.setStyleSheet("color: #58a6ff; font-size: 18px; font-weight: bold;")
        error_code.setAlignment(Qt.AlignCenter)
        setattr(self, f"servo_{servo_id}_err", error_code)
        error_layout.addWidget(error_code)
        status_layout.addWidget(error_frame)
        
        parent_layout.addWidget(status_group)
    
    def add_status_item(self, layout, title, value, unit, obj_name):
        """상태 항목 추가"""
        frame = QFrame()
        item_layout = QVBoxLayout(frame)
        item_layout.setAlignment(Qt.AlignCenter)
        
        # 이름
        name_label = QLabel(title)
        name_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        name_label.setAlignment(Qt.AlignCenter)
        item_layout.addWidget(name_label)
        
        # 값 + 단위
        value_layout = QHBoxLayout()
        value_layout.setAlignment(Qt.AlignCenter)
        
        value_label = QLabel(value)
        value_label.setObjectName(obj_name)
        value_label.setStyleSheet("color: #58a6ff; font-size: 20px; font-weight: bold;")
        setattr(self, obj_name, value_label)
        value_layout.addWidget(value_label)
        
        unit_label = QLabel(unit)
        unit_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        value_layout.addWidget(unit_label)
        
        item_layout.addLayout(value_layout)
        layout.addWidget(frame)
    
    def create_control_section(self, parent_layout, servo_id):
        """제어 버튼 섹션"""
        control_group = QGroupBox("제어")
        control_group.setObjectName("group_box")
        control_layout = QHBoxLayout(control_group)
        control_layout.setSpacing(10)
        
        # 서보 ON/OFF
        servo_on_btn = QPushButton("서보 ON")
        servo_on_btn.setObjectName("control_btn_on")
        servo_on_btn.setMinimumHeight(50)
        servo_on_btn.clicked.connect(lambda: self.on_servo_on(servo_id))
        control_layout.addWidget(servo_on_btn)
        
        servo_off_btn = QPushButton("서보 OFF")
        servo_off_btn.setObjectName("control_btn_off")
        servo_off_btn.setMinimumHeight(50)
        servo_off_btn.clicked.connect(lambda: self.on_servo_off(servo_id))
        control_layout.addWidget(servo_off_btn)
        
        # 리셋
        reset_btn = QPushButton("리셋")
        reset_btn.setObjectName("control_btn_reset")
        reset_btn.setMinimumHeight(50)
        reset_btn.clicked.connect(lambda: self.on_reset(servo_id))
        control_layout.addWidget(reset_btn)
        
        # 정지
        stop_btn = QPushButton("정지")
        stop_btn.setObjectName("control_btn_stop")
        stop_btn.setMinimumHeight(50)
        stop_btn.clicked.connect(lambda: self.on_stop(servo_id))
        control_layout.addWidget(stop_btn)
        
        parent_layout.addWidget(control_group)
    
    def create_position_section(self, parent_layout, servo_id):
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
        origin_btn.clicked.connect(lambda: self.on_set_origin(servo_id))
        position_layout.addWidget(origin_btn, row, 1, 1, 2)
        row += 1
        
        # 상한선 / 하한선
        position_layout.addWidget(QLabel("상한선:"), row, 0)
        upper_limit = QLineEdit("1000")
        upper_limit.setObjectName("input_field")
        setattr(self, f"servo_{servo_id}_upper_limit", upper_limit)
        position_layout.addWidget(upper_limit, row, 1)
        position_layout.addWidget(QLabel("mm"), row, 2)
        row += 1
        
        position_layout.addWidget(QLabel("하한선:"), row, 0)
        lower_limit = QLineEdit("0")
        lower_limit.setObjectName("input_field")
        setattr(self, f"servo_{servo_id}_lower_limit", lower_limit)
        position_layout.addWidget(lower_limit, row, 1)
        position_layout.addWidget(QLabel("mm"), row, 2)
        row += 1
        
        # 목표 위치 / 속도
        position_layout.addWidget(QLabel("목표 위치:"), row, 0)
        target_position = QLineEdit("0")
        target_position.setObjectName("input_field")
        setattr(self, f"servo_{servo_id}_target_pos", target_position)
        position_layout.addWidget(target_position, row, 1)
        position_layout.addWidget(QLabel("mm"), row, 2)
        row += 1
        
        position_layout.addWidget(QLabel("이동 속도:"), row, 0)
        move_speed = QLineEdit("100")
        move_speed.setObjectName("input_field")
        setattr(self, f"servo_{servo_id}_target_speed", move_speed)
        position_layout.addWidget(move_speed, row, 1)
        position_layout.addWidget(QLabel("mm/s"), row, 2)
        row += 1
        
        # 이동 버튼
        move_btn = QPushButton("지정 위치로 이동")
        move_btn.setObjectName("control_btn_move")
        move_btn.setMinimumHeight(45)
        move_btn.clicked.connect(lambda: self.on_move_to_position(servo_id))
        position_layout.addWidget(move_btn, row, 0, 1, 3)
        
        parent_layout.addWidget(position_group)
    
    def create_jog_section(self, parent_layout, servo_id):
        """정밀 이동 섹션"""
        jog_group = QGroupBox("정밀 이동")
        jog_group.setObjectName("group_box")
        jog_layout = QVBoxLayout(jog_group)
        
        # 모드 선택
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(20)
        
        mode_label = QLabel("이동 모드:")
        mode_layout.addWidget(mode_label)
        
        jog_mode = QRadioButton("조그 이동 (연속)")
        jog_mode.setChecked(True)
        jog_mode.setObjectName(f"servo_{servo_id}_is_jog")
        setattr(self, f"servo_{servo_id}_is_jog", jog_mode)
        mode_layout.addWidget(jog_mode)
        
        inch_mode = QRadioButton("인칭 이동 (단계)")
        inch_mode.setObjectName(f"servo_{servo_id}_is_inch")
        setattr(self, f"servo_{servo_id}_is_inch", inch_mode)
        mode_layout.addWidget(inch_mode)
        
        mode_layout.addStretch()
        jog_layout.addLayout(mode_layout)
        
        # 설정값
        settings_layout = QHBoxLayout()
        
        settings_layout.addWidget(QLabel("조그 속도:"))
        jog_speed = QLineEdit("10")
        jog_speed.setObjectName(f"servo_{servo_id}_jog_speed")
        jog_speed.setMaximumWidth(100)
        setattr(self, f"servo_{servo_id}_jog_speed", jog_speed)
        settings_layout.addWidget(jog_speed)
        settings_layout.addWidget(QLabel("mm/s"))
        
        settings_layout.addSpacing(30)
        
        settings_layout.addWidget(QLabel("인칭 거리:"))
        inch_distance = QLineEdit("1")
        inch_distance.setObjectName(f"servo_{servo_id}_inch_dist")
        inch_distance.setMaximumWidth(100)
        setattr(self, f"servo_{servo_id}_inch_dist", inch_distance)
        settings_layout.addWidget(inch_distance)
        settings_layout.addWidget(QLabel("mm"))
        
        settings_layout.addStretch()
        jog_layout.addLayout(settings_layout)
        
        # 이동 버튼
        move_layout = QHBoxLayout()
        move_layout.setAlignment(Qt.AlignCenter)
        
        left_btn = QPushButton("◀ 후진")
        left_btn.setObjectName("jog_btn")
        left_btn.setMinimumSize(120, 60)
        left_btn.pressed.connect(lambda: self.on_jog_move(servo_id, "left"))
        left_btn.clicked.connect(lambda: self.on_inch_move(servo_id, "left"))
        left_btn.released.connect(lambda: self.on_jog_stop(servo_id))
        move_layout.addWidget(left_btn)
        
        move_layout.addSpacing(50)
        
        right_btn = QPushButton("전진 ▶")
        right_btn.setObjectName("jog_btn")
        right_btn.setMinimumSize(120, 60)
        right_btn.pressed.connect(lambda: self.on_jog_move(servo_id, "right"))
        right_btn.clicked.connect(lambda: self.on_inch_move(servo_id, "right"))
        right_btn.released.connect(lambda: self.on_jog_stop(servo_id))
        move_layout.addWidget(right_btn)
        
        jog_layout.addLayout(move_layout)
        
        parent_layout.addWidget(jog_group)
    
    # 이벤트 핸들러
    def on_servo_on(self, servo_id):
        self.app.on_log("서보 ON")
        self.app.servo_on(servo_id)
    
    def on_servo_off(self, servo_id):
        self.app.on_log("서보 OFF")
        self.app.servo_off(servo_id)
    
    def on_reset(self, servo_id):
        self.app.on_log("서보 리셋")
        # self.alarm_indicator.setText("⚫ 정상")
        # self.error_code.setText("0x0000")
        self.app.servo_reset(servo_id)
    
    def on_stop(self, servo_id):
        self.app.on_log("서보 정지")
        self.app.servo_stop(servo_id)
    
    def on_set_origin(self, servo_id):
        self.app.on_log("원점 설정")
        self.app.servo_set_origin(servo_id)
    
    def on_move_to_position(self, servo_id):
        pos_txt = getattr(self, f"servo_{servo_id}_target_pos")
        speed_txt = getattr(self, f"servo_{servo_id}_target_speed")
        position = pos_txt.text()
        speed = speed_txt.text()
        self.app.on_log(f"위치 이동: {position}mm, 속도: {speed}mm/s")
        self.app.on_move_to_position(0, int(position*(10**3)))
    
    def on_jog_move(self, servo_id, direction):
        is_jog = getattr(self, f"servo_{servo_id}_is_jog")
        jog_speed = getattr(self, f"servo_{servo_id}_jog_speed")
        if is_jog.isChecked():
            self.app.on_log(f"조그 이동: {direction}")
            _dir = 1 if direction == "right" else -1
            v = float(jog_speed.text()) * (10 ** 3)
            if v == 0:
                self.app.on_log("조그 속도를 설정해주세요")
            else:
                self.app.servo_jog_move(servo_id, v*_dir)
    
    def on_inch_move(self, servo_id, direction):
        is_inch = getattr(self, f"servo_{servo_id}_is_inch")
        inch_dist = getattr(self, f"servo_{servo_id}_inch_dist")
        if is_inch.isChecked():
            self.app.on_log(f"인칭 이동: {direction}")
            _dir = 1 if direction == "right" else -1
            dist = int(inch_dist.text()) * (10 ** 3)
            if dist == 0:
                self.app.on_log(f"인칭 거리를 설정해주세요")
            else:
                self.app.servo_inch_move(servo_id, dist*_dir)
    
    def on_jog_stop(self, servo_id):
        is_jog = getattr(self, f"servo_{servo_id}_is_jog")
        if is_jog.isChecked():
            self.app.on_log("조그 이동 정지")
            self.app.servo_stop(servo_id)
    
    def update_values(self, _data):
        for i, ret in enumerate(_data):
            _pos = getattr(self, f"servo_{i}_pos", None)
            if _pos is None:
                continue
            _v = getattr(self, f"servo_{i}_speed")
            _err_ind = getattr(self, f"servo_{i}_err_ind")
            _err = getattr(self, f"servo_{i}_err")

            cur_pos = get_servo_modified_value(ret[2]) / (10 ** 3)
            cur_v = get_servo_modified_value(ret[3]) / (10 ** 3)
            err_code = ret[4]

            _pos.setText(f"{cur_pos:.03f}")
            _v.setText(f"{cur_v:.03f}")
            if err_code != 0:
                _err_ind.setText("🔴 오류")
                _err.setText(f"{err_code:04X}")
            else:
                _err_ind.setText("⚫ 정상")
                _err.setText("0x0000")

    
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