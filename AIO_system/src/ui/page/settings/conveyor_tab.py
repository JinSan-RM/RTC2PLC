"""
컨베이어 제어 탭
"""
from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QScrollArea, QDoubleSpinBox
)
from PySide6.QtGui import QDoubleValidator
from PySide6.QtCore import Qt

from src.utils.logger import log


@dataclass
class ValueInfo:
    """현재 상태 표시 정보 모음"""
    name: str = ""
    value: str = "0.0"
    unit: str = ""
    obj_name: str = ""


@dataclass
class ControllerInfo:
    """제어 부분 정보 모음"""
    name: str = ""
    unit: str = ""
    func: Callable = None
    attr_name: str = ""


@dataclass
class ControllerValueInfo:
    """제어 부분 값 정보 모음"""
    def_val: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0
    decimal_point: int = 0


# region ConveyorController
class ConveyorController(QWidget):
    """개별 컨베이어 제어 박스"""
    def __init__(self, app, conv_id):
        super().__init__()

        self.app = app
        self.conv_id = conv_id
        self.inverter_name = f"inverter_00{conv_id+2}"

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)

        self._create_header_layout(layout, f"컨베이어 0{self.conv_id}")

        layout.addSpacing(10)

        contents_box = QFrame()
        contents_box.setObjectName("contents_box")

        contents_layout = QVBoxLayout(contents_box)
        contents_layout.setSpacing(25)
        contents_layout.setContentsMargins(30, 30, 30, 30)

        # 상태 표시
        self._create_status_layout(contents_layout)

        # --- 설정 및 제어 섹션 ---
        self._create_control_layout(contents_layout)

        # --- 운전/정지 버튼 ---
        self._create_btn_layout(contents_layout)

        layout.addWidget(contents_box)

    def _create_header_layout(self, parent_layout, title):
        layout = QHBoxLayout()
        conv_title = QLabel(title)
        conv_title.setObjectName("title_label")
        layout.addWidget(conv_title)

        layout.addSpacing(15)

        # 운전 상태
        status_label = QLabel("⚫ 정지")
        status_label.setObjectName(f"{self.inverter_name}_status")
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
        layout.addWidget(status_label)

        layout.addStretch()

        parent_layout.addLayout(layout)

    def _create_status_layout(self, parent_layout):
        layout = QHBoxLayout()
        layout.setSpacing(50)

        _conf = self.app.config["inverter_config"][self.inverter_name]

        # 값 표시 (주파수, 시간 등)
        freq_info = ValueInfo(
            name="현재 주파수",
            value=f"{_conf[0]:.2f}",
            unit="Hz",
            obj_name=f"{self.inverter_name}_freq"
        )
        self._add_value_display(layout, freq_info)

        acc_info = ValueInfo(
            name="가속 시간",
            value=f"{_conf[1]:.1f}",
            unit="s",
            obj_name=f"{self.inverter_name}_acc"
        )
        self._add_value_display(layout, acc_info)

        dec_info = ValueInfo(
            name="감속 시간",
            value=f"{_conf[2]:.1f}",
            unit="s",
            obj_name=f"{self.inverter_name}_dec"
        )
        self._add_value_display(layout, dec_info)

        current_info = ValueInfo(
            name="출력 전류",
            value="0.0",
            unit="A",
            obj_name=f"{self.inverter_name}_crnt"
        )
        self._add_value_display(layout, current_info)

        voltage_info = ValueInfo(
            name="출력 전압",
            value="0.0",
            unit="V",
            obj_name=f"{self.inverter_name}_vltg"
        )
        self._add_value_display(layout, voltage_info)

        layout.addStretch()

        parent_layout.addLayout(layout)

    def _add_value_display(self, parent_layout, info: ValueInfo):
        """값 표시 위젯 추가"""
        layout = QHBoxLayout()
        layout.setSpacing(0)

        # 이름
        name_label = QLabel(info.name)
        name_label.setObjectName("name_label")
        layout.addWidget(name_label)

        layout.addSpacing(10)

        value_label = QLabel(info.value)
        value_label.setObjectName(info.obj_name)
        value_label.setStyleSheet(
            """
            color: #2DB591;
            font-size: 26px;
            font-weight: 600;
            """
        )
        layout.addWidget(value_label)

        layout.addSpacing(5)

        unit_label = QLabel(info.unit)
        unit_label.setStyleSheet(
            """
            color: #000000;
            font-size: 26px;
            font-weight: 600;
            """
        )
        layout.addWidget(unit_label)
        parent_layout.addLayout(layout)

    def _create_control_layout(self, parent_layout):
        _conf = self.app.config["inverter_config"][self.inverter_name]

        layout = QGridLayout()
        layout.setSpacing(10)

        row = 0

        # 목표 주파수
        freq_info = ControllerInfo(
            name="목표 주파수:",
            unit="Hz",
            func=self.on_set_freq,
            attr_name=f"{self.inverter_name}_target_freq"
        )
        freq_value = ControllerValueInfo(
            def_val=_conf[0],
            min_val=-120.0,
            max_val=120.0,
            decimal_point=2
        )
        self._create_controller(layout, row, freq_info, freq_value)
        row += 1

        # 가속 시간
        acc_info = ControllerInfo(
            name="목표 가속 시간:",
            unit="s",
            func=self.on_set_acc,
            attr_name=f"{self.inverter_name}_target_acc"
        )
        acc_value = ControllerValueInfo(
            def_val=_conf[1],
            min_val=0.0,
            max_val=999.0,
            decimal_point=1
        )
        self._create_controller(layout, row, acc_info, acc_value)
        row += 1

        # 감속 시간
        dec_info = ControllerInfo(
            name="목표 감속 시간:",
            unit="s",
            func=self.on_set_dec,
            attr_name=f"{self.inverter_name}_target_dec"
        )
        dec_value = ControllerValueInfo(
            def_val=_conf[2],
            min_val=0.0,
            max_val=999.0,
            decimal_point=1
        )
        self._create_controller(layout, row, dec_info, dec_value)

        parent_layout.addLayout(layout)

    def _create_controller(self, parent_layout, row,
                           info: ControllerInfo, value_info: ControllerValueInfo):
        name_label = QLabel(info.name)
        name_label.setObjectName("name_label")
        parent_layout.addWidget(name_label, row, 0)
        _input = QLineEdit(f"{value_info.def_val}")
        # _input = QDoubleSpinBox(f"{value_info.def_val}")
        _input.setValidator(QDoubleValidator(
            value_info.min_val,
            value_info.max_val,
            value_info.decimal_point,
            parent_layout
        ))
        _input.setPlaceholderText(f"{value_info.min_val} ~ {value_info.max_val} 입력 가능")
        _input.setObjectName("input_field")
        _input.setFixedSize(600, 40)
        parent_layout.addWidget(_input, row, 1)

        unit_label = QLabel(f"{info.unit}")
        unit_label.setObjectName("unit_label")
        parent_layout.addWidget(unit_label, row, 2)
        _input.returnPressed.connect(lambda: info.func(self.inverter_name))
        setattr(self, f"{info.attr_name}", _input)

        set_btn = QPushButton("설정")
        set_btn.setObjectName("setting_btn")
        set_btn.setFixedSize(112, 40)
        set_btn.clicked.connect(lambda: info.func(self.inverter_name))
        parent_layout.addWidget(set_btn, row, 3)

        parent_layout.setColumnStretch(4, 1)

    def _create_btn_layout(self, parent_layout):
        layout = QHBoxLayout()
        layout.setSpacing(10)

        # 운전 버튼
        layout = QHBoxLayout()
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignLeft)

        def _create_btn(name, obj_name, func):
            _btn = QPushButton(name)
            _btn.setObjectName(obj_name)
            _btn.setFixedSize(498, 60)
            _btn.clicked.connect(func)
            return _btn

        start_btn = _create_btn(
            "운전",
            "control_btn_start",
            lambda _: self.on_conveyor_start(self.inverter_name)
        )
        layout.addWidget(start_btn)

        stop_btn = _create_btn(
            "정지",
            "control_btn_stop",
            lambda _: self.on_conveyor_stop(self.inverter_name)
        )
        layout.addWidget(stop_btn)

        parent_layout.addLayout(layout)

    # --- 이벤트 핸들러 ---
    def on_set_freq(self, inverter_name: str):
        """주파수 설정"""
        try:
            freq = float(getattr(self, f"{inverter_name}_target_freq").text())
            self.app.on_set_freq(inverter_name, freq)
            log(f"{inverter_name} 주파수 설정: {freq} Hz")
            self.app.on_popup("info", "주파수 설정", f"{inverter_name} 목표 주파수 설정: {freq} Hz")

            freq_label = self.findChild(QLabel, f"{inverter_name}_freq")
            if freq_label:
                freq_label.setText(f"{freq:.2f}")
        except ValueError:
            txt = getattr(self, f"{inverter_name}_target_freq").text()
            log(f"잘못된 주파수 값: {txt}")
            self.app.on_popup("error", f"잘못된 주파수 값: {txt}", "주파수 값을 확인해 주세요.")

    def on_set_acc(self, inverter_name: str):
        """가속 시간 설정"""
        try:
            acc = float(getattr(self, f"{inverter_name}_target_acc").text())
            self.app.on_set_acc(inverter_name, acc)
            log(f"{inverter_name} 가속시간 설정: {acc} s")
            self.app.on_popup("info", "가속 시간 설정", f"{inverter_name} 가속 시간 설정: {acc} s")

            acc_label = self.findChild(QLabel, f"{inverter_name}_acc")
            if acc_label:
                acc_label.setText(f"{acc:.1f}")
        except ValueError:
            txt = getattr(self, f"{inverter_name}_target_acc").text()
            log(f"잘못된 가속시간 값: {txt}")
            self.app.on_popup("error", f"잘못된 가속 시간 값: {txt}", "가속 시간을 확인해 주세요.")

    def on_set_dec(self, inverter_name: str):
        """감속 시간 설정"""
        try:
            dec = float(getattr(self, f"{inverter_name}_target_dec").text())
            self.app.on_set_dec(inverter_name, dec)
            log(f"{inverter_name} 감속 시간 설정: {dec} s")
            self.app.on_popup("info","감속 시간 설정" , f"{inverter_name} 감속 시간 설정: {dec} s")

            dec_label = self.findChild(QLabel, f"{inverter_name}_dec")
            if dec_label:
                dec_label.setText(f"{dec:.1f}")
        except ValueError:
            txt = getattr(self, f"{inverter_name}_target_dec").text()
            log(f"잘못된 감속시간 값: {txt}")
            self.app.on_popup("error", f"잘못된 감속 시간 값: {txt}", "감속 시간을 확인해 주세요.")

    def on_conveyor_start(self, inverter_name: str):
        """개별 컨베이어 운전"""
        self.app.motor_start(inverter_name)

        status_label = self.findChild(QLabel, f"{inverter_name}_status")
        if status_label:
            status_label.setText("🟢 운전")
            status_label.setStyleSheet(
                """
                font-size: 16px;
                font-weight: bold;
                color: #3fb950;
                background-color: transparent;
                border: none;
                """
            )

    def on_conveyor_stop(self, inverter_name):
        """개별 컨베이어 정지"""
        self.app.motor_stop(inverter_name)

        status_label = self.findChild(QLabel, f"{inverter_name}_status")
        if status_label:
            status_label.setText("⚫ 정지")
            status_label.setStyleSheet(
                """
                font-size: 16px;
                font-weight: bold;
                color: #8b949e;
                background-color: transparent;
                border: none;
                """
            )

    def apply_styles(self):
        """스타일시트 적용 (FeederTab과 디자인 통일)"""
        self.setStyleSheet(
            """
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
# endregion


# region ConveyorTab
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
            _controller = ConveyorController(self.app, i)
            scroll_layout.addWidget(_controller)
            scroll_layout.addSpacing(20)

        scroll_layout.addSpacing(10)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # 스타일 시트 적용 (피더 탭과 동일한 스타일)
        self.apply_styles()

    # --- 이벤트 핸들러 ---
    def update_values(self, _data):
        """컨베이어 상태 UI 업데이트"""
        for _name, _list in _data.items():
            if _list:
                _freq = self.findChild(QLabel, f"{_name}_freq")
                if _freq is None:
                    continue
                _acc = self.findChild(QLabel, f"{_name}_acc")
                _dec = self.findChild(QLabel, f"{_name}_dec")
                _crnt = self.findChild(QLabel, f"{_name}_crnt")
                _vltg = self.findChild(QLabel, f"{_name}_vltg")
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
            """
        )
# endregion
