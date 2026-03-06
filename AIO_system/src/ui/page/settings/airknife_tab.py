"""
에어나이프 제어 탭
"""
from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QLineEdit, QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator

from src.utils.config_util import ToggleButton
from src.utils.logger import log


@dataclass
class EditInfo:
    """입력 창 정보 모음"""
    name: str = ""
    def_val: int = 0
    min_val: int = 0
    max_val: int = 0
    func: Callable = None


# region AirknifeController
class AirknifeController(QWidget):
    """에어나이프 제어 위젯"""
    def __init__(self, app, num):
        super().__init__()

        self.app = app
        self.num = num

        self._init_ui()

        self.apply_styles()

    def _init_ui(self):
        """에어나이프 제어 위젯"""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)

        self._create_airknife_header(layout)

        layout.addSpacing(15)

        # 설정 및 제어
        contents_box = QFrame()
        contents_box.setObjectName("contents_box")

        contents_layout = QVBoxLayout(contents_box)
        contents_layout.setSpacing(25)
        contents_layout.setContentsMargins(30, 30, 30, 30)

        self._create_input_layout(contents_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignLeft)
        btn_layout.setSpacing(20)

        def _create_btn(txt, obj_name, func):
            _btn = QPushButton(txt)
            _btn.setObjectName(obj_name)
            _btn.setFixedSize(498, 60)
            _btn.clicked.connect(func)
            return _btn

        # 테스트 버튼
        test_btn = _create_btn("테스트", "test_btn", self.on_test)
        btn_layout.addWidget(test_btn)

        # 설정 적용 버튼
        apply_btn = _create_btn("적용", "apply_btn", self.on_apply_settings)
        btn_layout.addWidget(apply_btn)

        contents_layout.addLayout(btn_layout)

        layout.addWidget(contents_box)

    def _create_airknife_header(self, parent_layout):
        layout = QHBoxLayout()
        air_title = QLabel(f"에어나이프 #{self.num}")
        air_title.setObjectName("title_label")
        layout.addWidget(air_title)

        layout.addSpacing(15)

        state_label = QLabel("⚫ 비활성화")
        state_label.setObjectName(f"airknife_{self.num}_status")
        state_label.setMaximumSize(1609, 16)
        state_label.setStyleSheet(
            """
            color: #616161;
            font-size: 14px;
            font-weight: normal;
            """
        )
        layout.addWidget(state_label)

        layout.addStretch()

        parent_layout.addLayout(layout)

    def _create_input_layout(self, parent_layout):
        layout = QHBoxLayout()
        layout.setSpacing(10)

        _conf = self.app.config["airknife_config"][f"airknife_{self.num}"]

        # 분사 타이밍 설정
        timing_info = EditInfo(
            name="분사 타이밍:",
            def_val=_conf['timing'],
            min_val=0,
            max_val=100000,
            func=self.on_apply_settings
        )
        _timing_edit = self._create_edit_area(layout, timing_info)
        setattr(self, f"airknife_{self.num}_timing", _timing_edit)

        layout.addSpacing(40)

        # 분사 시간 설정
        duration_info = EditInfo(
            name="분사 시간:",
            def_val=_conf['duration'],
            min_val=0,
            max_val=100000,
            func=self.on_apply_settings
        )
        _duration_edit = self._create_edit_area(layout, duration_info)
        setattr(self, f"airknife_{self.num}_duration", _duration_edit)

        layout.addStretch()

        # ON/OFF 버튼
        toggle_btn = ToggleButton(None, 126, 48, "활성화", "비활성화")
        toggle_btn.setObjectName(f"toggle_btn_{self.num}")
        toggle_btn.setChecked(True)
        toggle_btn.clicked.connect(self.on_toggle)
        layout.addWidget(toggle_btn)

        parent_layout.addLayout(layout)

    def _create_edit_area(self, parent_layout, info: EditInfo):
        _label = QLabel(f"{info.name}")
        _label.setObjectName("name_label")
        parent_layout.addWidget(_label)

        _edit = QLineEdit(f"{info.def_val}")
        _edit.setValidator(QIntValidator(info.min_val, info.max_val, parent_layout))
        _edit.setPlaceholderText(f"{info.min_val} ~ {info.max_val} 입력 가능")
        _edit.setObjectName("input_field")
        _edit.setFixedSize(300, 40)
        _edit.returnPressed.connect(info.func)

        parent_layout.addWidget(_edit)

        _unit = QLabel("ms")
        _unit.setObjectName("unit_label")
        parent_layout.addWidget(_unit)

        return _edit

    # 이벤트 핸들러
    def on_apply_settings(self):
        """설정 적용"""
        timing = getattr(self, f"airknife_{self.num}_timing").text()
        duration = getattr(self, f"airknife_{self.num}_duration").text()

        self.app.config["airknife_config"][f"airknife_{self.num}"]["timing"] = int(timing)
        self.app.config["airknife_config"][f"airknife_{self.num}"]["duration"] = int(duration)

        log(f"에어나이프 #{self.num} 설정: 타이밍={timing}ms, 시간={duration}ms")

    def on_test(self):
        """개별 테스트"""
        log(f"에어나이프 #{self.num} 테스트 분사")
        duration = getattr(self, f"airknife_{self.num}_duration").text()
        self.app.airknife_on(self.num, int(duration))

        # 상태 표시 업데이트 (시뮬레이션)
        status_label = self.findChild(QLabel, f"airknife_{self.num}_status")
        if status_label:
            status_label.setText("🟢 활성화")

    def on_toggle(self, enabled):
        """개별 ON/OFF"""
        state = "활성화" if enabled else "비활성화"
        log(f"에어나이프 #{self.num} {state}")
        # TODO: 실제 활성화/비활성화

    def apply_styles(self):
        """스타일시트 적용"""
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
            
            #apply_btn {
                background-color: #353535;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #apply_btn:hover {
                background-color: #8b949e;
            }
            
            #test_btn {
                background-color: #54B9DE;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #test_btn:hover {
                background-color: #58A6FF;
            }
            """
        )
# endregion


# region AirKnifeTab
class AirKnifeTab(QWidget):
    """에어나이프 제어 탭"""
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

        # 전체 제어
        self.create_global_control(scroll_layout)

        scroll_layout.addSpacing(40)

        # 에어나이프 3개
        for i in range(1, 4):
            air_knife = AirknifeController(self.app, i)
            scroll_layout.addWidget(air_knife)
            scroll_layout.addSpacing(30)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # 스타일 적용
        self.apply_styles()

    def create_global_control(self, parent_layout):
        """전체 제어 섹션"""
        layout = QVBoxLayout()
        layout.setSpacing(0)

        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignLeft)
        control_title = QLabel("전체 제어")
        control_title.setObjectName("title_label")
        header_layout.addWidget(control_title)

        layout.addLayout(header_layout)

        layout.addSpacing(15)

        contents_box = QFrame()
        contents_box.setObjectName("contents_box")

        contents_layout = QHBoxLayout(contents_box)
        contents_layout.setSpacing(20)
        contents_layout.setContentsMargins(30, 30, 30, 30)

        def _create_btn(name, obj_name, func):
            _btn = QPushButton(name)
            _btn.setObjectName(obj_name)
            _btn.setFixedHeight(60)
            _btn.clicked.connect(func)
            return _btn

        # 전체 활성화
        all_on_btn = _create_btn("전체 활성화", "global_btn_on", lambda: self.on_all_toggle(True))
        contents_layout.addWidget(all_on_btn)

        # 전체 비활성화
        all_off_btn = _create_btn("전체 비활성화", "global_btn_off", lambda: self.on_all_toggle(False))
        contents_layout.addWidget(all_off_btn)

        # 전체 테스트
        all_test_btn = _create_btn("전체 테스트", "global_btn_test", self.on_all_test)
        contents_layout.addWidget(all_test_btn)

        # 긴급 정지
        emergency_btn = _create_btn("전체 정지", "emergency_btn", self.on_emergency_stop)
        contents_layout.addWidget(emergency_btn)

        layout.addWidget(contents_box)

        parent_layout.addLayout(layout)

    # 이벤트 핸들러
    def on_airknife_off(self, num):
        """에어나이프 UI 표시 off로 전환"""
        log(f"에어나이프 #{num} 테스트 분사 종료")
        status_label = self.findChild(QLabel, f"airknife_{num}_status")
        if status_label:
            status_label.setText("⚫ 비활성화")

    def on_all_toggle(self, enable):
        """전체 활성화/비활성화"""
        state = "활성화" if enable else "비활성화"
        log(f"에어나이프 전체 {state}")

        # 모든 토글 버튼 상태 변경
        for i in range(1, 9):
            btn = self.findChild(ToggleButton, f"toggle_btn_{i}")
            if btn:
                btn.setChecked(enable)
        # TODO: 실제 전체 활성화/비활성화

    def on_all_test(self):
        """전체 테스트"""
        log("에어나이프 전체 테스트 분사")
        # TODO: 실제 전체 테스트

    def on_emergency_stop(self):
        """긴급 정지"""
        log("🚨 에어나이프 긴급 정지!")
        # TODO: 실제 긴급 정지

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
            
            #global_btn_on {
                background-color: #2DB591;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #global_btn_on:hover {
                background-color: #2ea043;
            }
            
            #global_btn_off {
                background-color: #606060;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #global_btn_off:hover {
                background-color: #8b949e;
            }
            
            #global_btn_test {
                background-color: #54B9DE;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #global_btn_test:hover {
                background-color: #58a6ff;
            }
            
            #emergency_btn {
                background-color: #da3633;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }
            
            #emergency_btn:hover {
                background-color: #f85149;
            }
            """
        )
# endregion
