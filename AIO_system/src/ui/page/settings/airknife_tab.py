"""
에어나이프 제어 탭
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QLineEdit, QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator

from src.utils.config_util import ToggleButton
from src.utils.logger import log


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
            self.create_airknife(scroll_layout, i)
            scroll_layout.addSpacing(30)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # 스타일 적용
        self.apply_styles()
    
    def create_airknife(self, parent_layout, num):
        """에어나이프 제어 위젯"""
        layout = QVBoxLayout()
        layout.setSpacing(0)

        header_layout = QHBoxLayout()
        air_title = QLabel(f"에어나이프 #{num}")
        air_title.setObjectName("title_label")
        header_layout.addWidget(air_title)

        header_layout.addSpacing(15)

        state_label = QLabel("⚫ 대기")
        state_label.setObjectName(f"airknife_{num}_status")
        state_label.setMaximumSize(1609, 16)
        state_label.setStyleSheet(
            """
            color: #616161;
            font-size: 14px;
            font-weight: normal;
            """
        )
        header_layout.addWidget(state_label)

        header_layout.addStretch()

        layout.addLayout(header_layout)

        layout.addSpacing(15)

        # 설정 및 제어
        contents_box = QFrame()
        contents_box.setObjectName("contents_box")

        contents_layout = QVBoxLayout(contents_box)
        contents_layout.setSpacing(25)
        contents_layout.setContentsMargins(30, 30, 30, 30)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        _conf = self.app.config["airknife_config"][f"airknife_{num}"]
        
        # 분사 타이밍 설정
        timing_label = QLabel("분사 타이밍:")
        timing_label.setObjectName("name_label")
        input_layout.addWidget(timing_label)

        timing = QLineEdit(f"{_conf['timing']}")
        timing.setValidator(QIntValidator(0, 100000, input_layout))
        timing.setPlaceholderText("0 ~ 100000 입력 가능")
        timing.setObjectName("input_field")
        timing.setFixedSize(300, 40)
        timing.returnPressed.connect(lambda: self.on_apply_settings(num))
        setattr(self, f"airknife_{num}_timing", timing)
        input_layout.addWidget(timing)

        timing_unit = QLabel("ms")
        timing_unit.setObjectName("unit_label")
        input_layout.addWidget(timing_unit)

        input_layout.addSpacing(40)
        
        # 분사 시간 설정
        duration_label = QLabel("분사 시간:")
        duration_label.setObjectName("name_label")
        input_layout.addWidget(duration_label)
        
        duration = QLineEdit(f"{_conf['duration']}")
        duration.setValidator(QIntValidator(0, 100000, input_layout))
        duration.setPlaceholderText("0 ~ 100000 입력 가능")
        duration.setObjectName("input_field")
        duration.setFixedSize(300, 40)
        duration.returnPressed.connect(lambda: self.on_apply_settings(num))
        setattr(self, f"airknife_{num}_duration", duration)
        input_layout.addWidget(duration)

        duration_unit = QLabel("ms")
        duration_unit.setObjectName("unit_label")
        input_layout.addWidget(duration_unit)

        input_layout.addStretch()
        
        # ON/OFF 버튼
        toggle_btn = ToggleButton(None, 126, 48, "활성화", "비활성화")
        toggle_btn.setObjectName(f"toggle_btn_{num}")
        toggle_btn.setChecked(True)
        toggle_btn.clicked.connect(lambda checked: self.on_toggle(num, checked))
        input_layout.addWidget(toggle_btn)

        contents_layout.addLayout(input_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignLeft)
        btn_layout.setSpacing(20)

        # 테스트 버튼
        test_btn = QPushButton("테스트")
        test_btn.setObjectName("test_btn")
        test_btn.setFixedSize(498, 60)
        test_btn.clicked.connect(lambda: self.on_test(num))
        btn_layout.addWidget(test_btn)

        # 설정 적용 버튼
        apply_btn = QPushButton("적용")
        apply_btn.setObjectName("apply_btn")
        apply_btn.setFixedSize(498, 60)
        apply_btn.clicked.connect(lambda: self.on_apply_settings(num))
        btn_layout.addWidget(apply_btn)

        contents_layout.addLayout(btn_layout)

        layout.addWidget(contents_box)
        
        parent_layout.addLayout(layout)
    
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
        
        # 전체 활성화
        all_on_btn = QPushButton("전체 활성화")
        all_on_btn.setObjectName("global_btn_on")
        all_on_btn.setFixedHeight(60)
        all_on_btn.clicked.connect(lambda: self.on_all_toggle(True))
        contents_layout.addWidget(all_on_btn)
        
        # 전체 비활성화
        all_off_btn = QPushButton("전체 비활성화")
        all_off_btn.setObjectName("global_btn_off")
        all_off_btn.setFixedHeight(60)
        all_off_btn.clicked.connect(lambda: self.on_all_toggle(False))
        contents_layout.addWidget(all_off_btn)
        
        # 전체 테스트
        all_test_btn = QPushButton("전체 테스트")
        all_test_btn.setObjectName("global_btn_test")
        all_test_btn.setFixedHeight(60)
        all_test_btn.clicked.connect(self.on_all_test)
        contents_layout.addWidget(all_test_btn)
        
        # 긴급 정지
        emergency_btn = QPushButton("전체 정지")
        emergency_btn.setObjectName("emergency_btn")
        emergency_btn.setFixedHeight(60)
        emergency_btn.clicked.connect(self.on_emergency_stop)
        contents_layout.addWidget(emergency_btn)

        layout.addWidget(contents_box)
        
        parent_layout.addLayout(layout)
    
    # 이벤트 핸들러
    def on_apply_settings(self, num):
        """설정 적용"""
        timing = getattr(self, f"airknife_{num}_timing").text()
        duration = getattr(self, f"airknife_{num}_duration").text()
        
        self.app.config["airknife_config"][f"airknife_{num}"]["timing"] = int(timing)
        self.app.config["airknife_config"][f"airknife_{num}"]["duration"] = int(duration)
        
        log(f"에어나이프 #{num} 설정: 타이밍={timing}ms, 시간={duration}ms")
    
    def on_test(self, num):
        """개별 테스트"""
        log(f"에어나이프 #{num} 테스트 분사")
        # TODO: 실제 테스트 분사
        duration = getattr(self, f"airknife_{num}_duration").text()
        self.app.airknife_on(num, int(duration))
        
        # 상태 표시 업데이트 (시뮬레이션)
        status_label = self.findChild(QLabel, f"airknife_{num}_status")
        if status_label:
            status_label.setText("🟢 분사")
            status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #3fb950;")
            # TODO: 일정 시간 후 "대기" 상태로 복귀
    
    def on_airknife_off(self, num):
        log(f"에어나이프 #{num} 테스트 분사 종료")
        status_label = self.findChild(QLabel, f"airknife_{num}_status")
        if status_label:
            status_label.setText("⚫ 대기")
            status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #8b949e;")
    
    def on_toggle(self, num, enabled):
        """개별 ON/OFF"""
        state = "활성화" if enabled else "비활성화"
        log(f"에어나이프 #{num} {state}")
        # TODO: 실제 활성화/비활성화
    
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