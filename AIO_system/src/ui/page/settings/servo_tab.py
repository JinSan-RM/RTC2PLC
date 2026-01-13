"""
서보 제어 탭
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QRadioButton,
    QFrame, QScrollArea
)
from PySide6.QtGui import QDoubleValidator
from PySide6.QtCore import Qt

from src.utils.config_util import get_servo_modified_value, ToggleButton, STATUS_MASK, check_mask
from src.utils.logger import log

class ServoTab(QWidget):
    """서보 제어 탭"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
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

        # 폭 제어
        self.create_servo_section(scroll_layout, "폭 제어", 0)

        scroll_layout.addSpacing(30)

        # 높이 제어
        self.create_servo_section(scroll_layout, "높이 제어", 1)

        scroll_layout.addSpacing(30)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # 스타일 적용
        self.apply_styles()

    def create_servo_section(self, parent_layout, title, servo_id):
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        header_layout = QHBoxLayout()

        title_label = QLabel(f"{title}")
        title_label.setStyleSheet(
            """
            color: #000000;
            font-size: 20px;
            font-weight: normal;
            """
        )
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        state_label = QLabel("⚫ 서보 OFF")
        state_label.setStyleSheet(
            """
            color: #616161;
            font-size: 14px;
            font-weight: normal;
            """
        )
        header_layout.addWidget(state_label)
        layout.addLayout(header_layout)

        layout.addSpacing(15)

        # 상단: 상태 모니터링
        self.create_status_section(layout, servo_id)

        layout.addSpacing(20)
        
        # 중단: 제어 버튼들
        self.create_control_section(layout, servo_id)

        layout.addSpacing(30)
        
        # 하단: 위치 설정
        self.create_position_section(layout, servo_id)

        layout.addSpacing(30)
        
        # 정밀 이동
        self.create_jog_section(layout, servo_id)

        layout.addStretch()

        parent_layout.addLayout(layout)

    def create_status_section(self, parent_layout, servo_id):
        """상태 모니터링 섹션"""
        status_layout = QHBoxLayout()
        status_layout.setSpacing(20)
        status_layout.setContentsMargins(0, 0, 0, 0)
        
        # 현재 위치
        self.add_status_item(status_layout, "현재 위치", "0.000 mm", f"servo_{servo_id}_pos")
        
        # 속도
        self.add_status_item(status_layout, "속도", "0.000 mm/s", f"servo_{servo_id}_speed")
        
        # 경보
        self.add_status_item(status_layout, "경보", "⚫ 정상", f"servo_{servo_id}_err_ind")
        
        # 에러 코드
        self.add_status_item(status_layout, "에러 코드", "0x0000", f"servo_{servo_id}_err")
        
        parent_layout.addLayout(status_layout)
    
    def add_status_item(self, layout, title, value, obj_name):
        """상태 항목 추가"""
        item_box = QFrame()
        item_box.setObjectName("item_box")
        item_box.setFixedHeight(130)

        item_layout = QVBoxLayout(item_box)
        item_layout.setAlignment(Qt.AlignCenter)
        
        # 이름
        name_label = QLabel(title)
        name_label.setObjectName("name_label")
        name_label.setAlignment(Qt.AlignCenter)
        item_layout.addWidget(name_label)
        
        value_label = QLabel(value)
        value_label.setObjectName(obj_name)
        value_label.setStyleSheet(
            """
            color: #000000;
            font-size: 30px;
            font-weight: 600;
            """
        )
        setattr(self, obj_name, value_label)
        item_layout.addWidget(value_label)

        layout.addWidget(item_box)
    
    def create_control_section(self, parent_layout, servo_id):
        """제어 버튼 섹션"""
        control_box = QFrame()
        control_box.setObjectName("control_box")

        control_layout = QHBoxLayout(control_box)
        control_layout.setSpacing(20)
        control_layout.setContentsMargins(30, 30, 30, 30)
        
        # 서보 ON/OFF
        toggle_btn = ToggleButton(None, 138, 48, "서보 ON", "서보 OFF")
        toggle_btn.setChecked(False)
        toggle_btn.setObjectName(f"toggle_btn_{servo_id}")
        toggle_btn.clicked.connect(lambda checked: self.on_servo_toggle(servo_id, checked))
        control_layout.addWidget(toggle_btn)
        
        # 리셋
        reset_btn = QPushButton("🔄️리셋")
        reset_btn.setObjectName("control_btn_reset")
        reset_btn.setFixedSize(199, 65)
        reset_btn.clicked.connect(lambda: self.on_reset(servo_id))
        control_layout.addWidget(reset_btn)
        
        # 정지
        stop_btn = QPushButton("⏹️정지")
        stop_btn.setObjectName("control_btn_stop")
        stop_btn.setFixedSize(199, 65)
        stop_btn.clicked.connect(lambda: self.on_stop(servo_id))
        control_layout.addWidget(stop_btn)

        # 원점복귀
        homing_btn = QPushButton("원점복귀")
        homing_btn.setObjectName("control_btn_homing")
        homing_btn.setFixedSize(199, 65)
        homing_btn.clicked.connect(lambda: self.on_homing(servo_id))
        control_layout.addWidget(homing_btn)

        control_layout.addStretch()
        
        parent_layout.addWidget(control_box)
    
    def create_position_section(self, parent_layout, servo_id):
        """위치 설정 섹션"""
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        position_title = QLabel("위치 설정")
        position_title.setObjectName("title_label")
        layout.addWidget(position_title)

        layout.addSpacing(15)

        position_box = QFrame()
        position_box.setObjectName("control_box")
        position_box.setFixedWidth(1609)

        position_layout = QGridLayout(position_box)
        position_layout.setSpacing(15)
        position_layout.setContentsMargins(30, 30, 30, 30)

        pos_name = QLabel("목표 위치")
        pos_name.setObjectName("name_label")
        position_layout.addWidget(pos_name, 0, 1)
        v_name = QLabel("속도")
        v_name.setObjectName("name_label")
        position_layout.addWidget(v_name, 0, 3)

        for i in range(6):
            self.add_position_item(position_layout, servo_id, i+1)

        layout.addWidget(position_box)
        
        parent_layout.addLayout(layout)

    def add_position_item(self, parent_layout, servo_id, row):
        _name = "폭 조정" if servo_id == 0 else "높이 조정"
        name_label = QLabel(f"{_name} {row}:")
        name_label.setObjectName("name_label")
        parent_layout.addWidget(name_label, row, 0)

        _conf = self.app.config["servo_config"][f"servo_{servo_id}"]

        target_position = QLineEdit(f"{_conf['position'][row-1][0]}")
        target_position.setValidator(QDoubleValidator(-1000.0, 1000.0, 3, parent_layout))
        target_position.setPlaceholderText("-1000.0 ~ 1000.0 입력 가능")
        target_position.setObjectName("input_field")
        target_position.setFixedSize(553, 40)
        target_position.returnPressed.connect(lambda: self.on_save_position(servo_id, row-1))
        setattr(self, f"servo_{servo_id}_target_pos_{row-1}", target_position)
        parent_layout.addWidget(target_position, row, 1)

        pos_unit = QLabel("mm")
        pos_unit.setObjectName("unit_label")
        parent_layout.addWidget(pos_unit, row, 2)

        move_speed = QLineEdit(f"{_conf['position'][row-1][1]}")
        move_speed.setValidator(QDoubleValidator(0.0, 1000.0, 3, parent_layout))
        move_speed.setPlaceholderText("0.0 ~ 1000.0 입력 가능")
        move_speed.setObjectName("input_field")
        move_speed.setFixedSize(553, 40)
        move_speed.returnPressed.connect(lambda: self.on_save_position(servo_id, row-1))
        setattr(self, f"servo_{servo_id}_target_speed_{row-1}", move_speed)
        parent_layout.addWidget(move_speed, row, 3)

        spd_unit = QLabel("mm/s")
        spd_unit.setObjectName("unit_label")
        parent_layout.addWidget(spd_unit, row, 4)

        origin_btn = QPushButton("저장")
        origin_btn.setObjectName("pos_btn")
        origin_btn.setFixedHeight(40)
        origin_btn.clicked.connect(lambda: self.on_save_position(servo_id, row-1))
        parent_layout.addWidget(origin_btn, row, 5)

        move_btn = QPushButton("이동")
        move_btn.setObjectName("pos_btn")
        move_btn.setFixedHeight(40)
        move_btn.clicked.connect(lambda: self.on_move_to_position(servo_id, row-1))
        parent_layout.addWidget(move_btn, row, 6)

    def create_jog_section(self, parent_layout, servo_id):
        """정밀 이동 섹션"""
        layout = QVBoxLayout()
        jog_title = QLabel("정밀 이동")
        jog_title.setObjectName("title_label")
        layout.addWidget(jog_title)

        layout.addSpacing(15)

        jog_box = QFrame()
        jog_box.setObjectName("control_box")
        jog_layout = QVBoxLayout(jog_box)
        jog_layout.setSpacing(20)
        jog_layout.setContentsMargins(30, 30, 30, 30)
        
        # 모드 선택
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(20)
        
        mode_label = QLabel("이동 모드:")
        mode_label.setObjectName("name_label")
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
        _conf = self.app.config["servo_config"][f"servo_{servo_id}"]

        settings_layout = QHBoxLayout()
        
        jog_spd_label = QLabel("조그 속도:")
        jog_spd_label.setObjectName("name_label")
        settings_layout.addWidget(jog_spd_label)

        jog_speed = QLineEdit(f"{_conf['jog_speed']}")
        jog_speed.setValidator(QDoubleValidator(0.0, 1000.0, 3, settings_layout))
        jog_speed.setPlaceholderText("0.0 ~ 1000.0 입력 가능")
        jog_speed.setObjectName(f"input_field")
        jog_speed.setFixedSize(152, 40)
        jog_speed.returnPressed.connect(lambda: self.save_jog_speed(servo_id))
        setattr(self, f"servo_{servo_id}_jog_speed", jog_speed)
        settings_layout.addWidget(jog_speed)

        jog_unit = QLabel("mm/s")
        jog_unit.setObjectName("unit_label")
        settings_layout.addWidget(jog_unit)
        
        settings_layout.addSpacing(30)
        
        settings_layout.addWidget(QLabel("인칭 거리:"))
        inch_distance = QLineEdit(f"{_conf['inch_distance']}")
        inch_distance.setValidator(QDoubleValidator(0.0, 1000.0, 3, settings_layout))
        inch_distance.setPlaceholderText("0.0 ~ 1000.0 입력 가능")
        inch_distance.setObjectName(f"input_field")
        inch_distance.setFixedSize(152, 40)
        inch_distance.returnPressed.connect(lambda: self.save_inch_distance(servo_id))
        setattr(self, f"servo_{servo_id}_inch_dist", inch_distance)
        settings_layout.addWidget(inch_distance)

        inch_unit = QLabel("mm")
        inch_unit.setObjectName("unit_label")
        settings_layout.addWidget(inch_unit)
        
        settings_layout.addStretch()
        jog_layout.addLayout(settings_layout)
        
        # 이동 버튼
        move_layout = QHBoxLayout()
        move_layout.setAlignment(Qt.AlignLeft)
        
        left_btn = QPushButton("◀ 후진")
        left_btn.setObjectName("jog_btn")
        left_btn.setFixedSize(199, 60)
        left_btn.pressed.connect(lambda: self.on_jog_move(servo_id, "left"))
        left_btn.clicked.connect(lambda: self.on_inch_move(servo_id, "left"))
        left_btn.released.connect(lambda: self.on_jog_stop(servo_id))
        move_layout.addWidget(left_btn)
        
        right_btn = QPushButton("전진 ▶")
        right_btn.setObjectName("jog_btn")
        right_btn.setFixedSize(199, 60)
        right_btn.pressed.connect(lambda: self.on_jog_move(servo_id, "right"))
        right_btn.clicked.connect(lambda: self.on_inch_move(servo_id, "right"))
        right_btn.released.connect(lambda: self.on_jog_stop(servo_id))
        move_layout.addWidget(right_btn)
        
        jog_layout.addLayout(move_layout)

        layout.addWidget(jog_box)
        
        parent_layout.addLayout(layout)
    
    # 이벤트 핸들러
    def on_servo_on(self, servo_id):
        log("서보 ON")
        self.app.servo_on(servo_id)
    
    def on_servo_off(self, servo_id):
        log("서보 OFF")
        self.app.servo_off(servo_id)

    def on_servo_toggle(self, servo_id, checked):
        if checked:
            log("서보 ON")
            self.app.servo_on(servo_id)
        else:
            log("서보 OFF")
            self.app.servo_off(servo_id)
    
    def on_reset(self, servo_id):
        log("서보 리셋")
        # self.alarm_indicator.setText("⚫ 정상")
        # self.error_code.setText("0x0000")
        self.app.servo_reset(servo_id)
    
    def on_stop(self, servo_id):
        log("서보 정지")
        self.app.servo_stop(servo_id)

    def on_homing(self, servo_id):
        log("서보 원점 복귀")
        self.app.servo_homing(servo_id)
    
    def on_set_origin(self, servo_id):
        log("원점 설정")
        self.app.servo_set_origin(servo_id)
    
    def on_save_position(self, servo_id, idx):
        _name = "폭 조정" if servo_id == 0 else "높이 조정"

        pos_txt = getattr(self, f"servo_{servo_id}_target_pos_{idx}")
        speed_txt = getattr(self, f"servo_{servo_id}_target_speed_{idx}")
        position = pos_txt.text()
        speed = speed_txt.text()

        pos_info = [ float(position), float(speed) ]
        self.app.config["servo_config"][f"servo_{servo_id}"]["position"][idx] = pos_info

        log(f"{_name} {idx+1} 저장. 위치: {position}mm, 속도: {speed}mm/s")
    
    def on_move_to_position(self, servo_id, idx):
        pos_txt = getattr(self, f"servo_{servo_id}_target_pos_{idx}")
        speed_txt = getattr(self, f"servo_{servo_id}_target_speed_{idx}")
        position = pos_txt.text()
        speed = speed_txt.text()
        log(f"위치 이동: {position}mm, 속도: {speed}mm/s")
        self.app.servo_move_to_position(0, float(position)*(10**3), float(speed)*(10**3))

    def save_jog_speed(self, servo_id):
        jog_speed = getattr(self, f"servo_{servo_id}_jog_speed").text()
        self.app.config["servo_config"][f"servo_{servo_id}"]["jog_speed"] = float(jog_speed)

        log(f"조그 속도 저장: {jog_speed}mm/s")

    def save_inch_distance(self, servo_id):
        inch_dist = getattr(self, f"servo_{servo_id}_inch_dist").text()
        self.app.config["servo_config"][f"servo_{servo_id}"]["inch_distance"] = float(inch_dist)

        log(f"인칭 거리 저장: {inch_dist}mm")

    def on_jog_move(self, servo_id, direction):
        is_jog = getattr(self, f"servo_{servo_id}_is_jog")
        jog_speed = getattr(self, f"servo_{servo_id}_jog_speed")
        if is_jog.isChecked():
            log(f"조그 이동: {direction}")
            _dir = 1 if direction == "right" else -1
            v = float(jog_speed.text()) * (10 ** 3)
            if v == 0:
                log("조그 속도를 설정해주세요")
            else:
                self.app.servo_jog_move(servo_id, v*_dir)
    
    def on_inch_move(self, servo_id, direction):
        is_inch = getattr(self, f"servo_{servo_id}_is_inch")
        inch_dist = getattr(self, f"servo_{servo_id}_inch_dist")
        if is_inch.isChecked():
            log(f"인칭 이동: {direction}")
            _dir = 1 if direction == "right" else -1
            dist = float(inch_dist.text()) * (10 ** 3)
            if dist == 0:
                log(f"인칭 거리를 설정해주세요")
            else:
                self.app.servo_inch_move(servo_id, dist*_dir)
    
    def on_jog_stop(self, servo_id):
        is_jog = getattr(self, f"servo_{servo_id}_is_jog")
        if is_jog.isChecked():
            log("조그 이동 정지")
            self.app.servo_stop(servo_id)

    def update_values(self, servo_id: int, _data):
        servo_on = check_mask(_data[0], STATUS_MASK.STATUS_OPERATION_ENABLED)
        btn = self.findChild(ToggleButton, f"toggle_btn_{servo_id}")
        if btn and btn.isChecked() != servo_on:
            btn.setChecked(servo_on)
        _pos = getattr(self, f"servo_{servo_id}_pos", None)
        if _pos is None:
            return
        _v = getattr(self, f"servo_{servo_id}_speed")
        _err_ind = getattr(self, f"servo_{servo_id}_err_ind")
        _err = getattr(self, f"servo_{servo_id}_err")

        cur_pos = get_servo_modified_value(_data[2]) / (10 ** 3)
        cur_v = get_servo_modified_value(_data[3]) / (10 ** 3)
        err_code = _data[4]
        warn_code = _data[5]

        _pos.setText(f"{cur_pos:.03f} mm")
        _v.setText(f"{cur_v:.03f} mm/s")
        if err_code != 0:
            _err_ind.setText("🔴 오류")
            _err.setText(f"{err_code:04X}")
        elif warn_code != 0:
            _err_ind.setText("🟡 경고")
            _err.setText(f"{warn_code:04X}")
        else:
            _err_ind.setText("⚫ 정상")
            _err.setText("0x0000")

    
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

            #combo_box {
                background-color: #FFFFFF;
                border: 1px solid #D4D4D4;
                border-radius: 4px;
                padding: 5px 10px;
                color: #4B4B4B;
            }
            
            #combo_box:hover {
                border-color: #58a6ff;
            }
            
            #combo_box::drop-down {
                border: none;
            }
            
            #combo_box QAbstractItemView {
                background-color: #FFFFFF;
                border: 1px solid #D4D4D4;
                color: #4B4B4B;
                selection-background-color: #FFFFFF;
            }

            #item_box {
                background-color: #F3F4F6;
                border: 1px solid #E2E2E2;
                border-radius: 7px;
            }

            #control_box {
                background-color: #FAFAFA;
                border: 1px solid #E2E2E2;
                border-radius: 7px;
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
            
            /* 제어 버튼 */
            #control_btn_on {
                background-color: #2DB591;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #control_btn_on:hover {
                background-color: #2ea043;
            }
            
            #control_btn_off {
                background-color: #E6E6E6;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #control_btn_off:hover {
                background-color: #8b949e;
            }
            
            #control_btn_reset, #control_btn_move {
                background-color: #353535;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #control_btn_reset:hover, #control_btn_move:hover {
                background-color: #58a6ff;
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
                           
            #control_btn_homing {
                background-color: #1f6feb;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #control_btn_homing:hover {
                background-color: #58a6ff;
            }
            
            /* 위치 저장/이동 */
            #pos_btn {
                background-color: #E6E6E6;
                color: #000000;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #pos_btn:hover {
                background-color: #C0C0C0;
            }
            
            /* 조그 또는 인칭 이동 */
            #jog_btn {
                background-color: #E6E6E6;
                color: #000000;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #jog_btn:hover {
                background-color: #C0C0C0;
            }
            
            #jog_btn:pressed {
                background-color: #A0A0A0;
            }
            
            QRadioButton {
                color: #000000;
                font-size: 14px;
                font-weight: normal;
            }
            
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border: none;
                border-radius: 1px;
            }
            
            QRadioButton::indicator:unchecked {
                background-color: #D9D9D9;
            }
            
            QRadioButton::indicator:checked {
                background-color: #2DB591;
            }
            """
        )