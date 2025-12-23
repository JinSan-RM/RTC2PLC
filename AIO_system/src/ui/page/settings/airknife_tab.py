"""
에어나이프 제어 탭
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QLineEdit, QScrollArea,
    QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator

from src.utils.config_util import APP_CONFIG
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
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 안내 메시지
        info_label = QLabel("에어나이프는 플라스틱 분류 신호를 받은 후 설정된 타이밍에 에어를 분사합니다.")
        info_label.setStyleSheet("color: #8b949e; font-size: 13px; padding: 10px; background-color: #0d1117; border-radius: 5px;")
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)
        
        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
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
        
        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        # 컨텐츠 위젯도 투명하게 설정해야 그룹박스 배경색이 돋보임
        scroll_content.setStyleSheet("#scroll_content { background-color: transparent; }")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)
        
        # 에어나이프 3개
        for i in range(1, 4):
            self.create_airknife(scroll_layout, i)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        # 하단: 전체 제어
        self.create_global_control(main_layout)
        
        # 스타일 적용
        self.apply_styles()
    
    def create_airknife(self, parent_layout, num):
        """에어나이프 제어 위젯"""
        group = QGroupBox(f"에어나이프 #{num}")
        group.setObjectName("group_box")
        group_layout = QHBoxLayout(group)
        group_layout.setSpacing(15)
        
        # 상태 표시
        status_frame = QFrame()
        status_layout = QVBoxLayout(status_frame)
        status_layout.setAlignment(Qt.AlignCenter)
        
        status_title = QLabel("상태")
        status_title.setStyleSheet("color: #8b949e; font-size: 11px;")
        status_layout.addWidget(status_title)
        
        status_indicator = QLabel("⚫ 대기")
        status_indicator.setObjectName(f"airknife_{num}_status")
        status_indicator.setStyleSheet("font-size: 14px; font-weight: bold; color: #8b949e;")
        status_layout.addWidget(status_indicator)
        
        group_layout.addWidget(status_frame)
        
        # 구분선
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.VLine)
        separator1.setStyleSheet("background-color: #30363d;")
        group_layout.addWidget(separator1)

        _conf = self.app.config["airknife_config"][f"airknife_{num}"]
        
        # 분사 타이밍 설정
        group_layout.addWidget(QLabel("분사 타이밍:"))
        timing = QLineEdit(f"{_conf['timing']}")
        timing.setValidator(QIntValidator(0, 100000, group_layout))
        timing.setPlaceholderText("0 ~ 100000 입력 가능")
        timing.setObjectName("input_field")
        timing.setMaximumWidth(70)
        timing.setAlignment(Qt.AlignRight)
        timing.returnPressed.connect(lambda: self.on_apply_settings(num))
        setattr(self, f"airknife_{num}_timing", timing)
        group_layout.addWidget(timing)
        group_layout.addWidget(QLabel("ms"))
        
        # 분사 시간 설정
        group_layout.addWidget(QLabel("분사 시간:"))
        duration = QLineEdit(f"{_conf['duration']}")
        duration.setValidator(QIntValidator(0, 100000, group_layout))
        duration.setPlaceholderText("0 ~ 100000 입력 가능")
        duration.setObjectName("input_field")
        duration.setMaximumWidth(70)
        duration.setAlignment(Qt.AlignRight)
        duration.returnPressed.connect(lambda: self.on_apply_settings(num))
        setattr(self, f"airknife_{num}_duration", duration)
        group_layout.addWidget(duration)
        group_layout.addWidget(QLabel("ms"))
        
        # 구분선
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setStyleSheet("background-color: #30363d;")
        group_layout.addWidget(separator2)
        
        # 설정 적용 버튼
        apply_btn = QPushButton("적용")
        apply_btn.setObjectName("apply_btn")
        apply_btn.setMinimumHeight(35)
        apply_btn.setMaximumWidth(70)
        apply_btn.clicked.connect(lambda: self.on_apply_settings(num))
        group_layout.addWidget(apply_btn)
        
        # 테스트 버튼
        test_btn = QPushButton("테스트")
        test_btn.setObjectName("test_btn")
        test_btn.setMinimumHeight(35)
        test_btn.setMaximumWidth(90)
        test_btn.clicked.connect(lambda: self.on_test(num))
        group_layout.addWidget(test_btn)
        
        # ON/OFF 버튼
        toggle_btn = QPushButton("활성화")
        toggle_btn.setObjectName(f"toggle_btn_{num}")
        toggle_btn.setCheckable(True)
        toggle_btn.setChecked(True)
        toggle_btn.setMinimumHeight(35)
        toggle_btn.setMaximumWidth(80)
        toggle_btn.clicked.connect(lambda checked: self.on_toggle(num, checked))
        group_layout.addWidget(toggle_btn)
        
        group_layout.addStretch()
        parent_layout.addWidget(group)
    
    def create_global_control(self, parent_layout):
        """전체 제어 섹션"""
        global_group = QGroupBox("전체 제어")
        global_group.setObjectName("group_box")
        global_layout = QHBoxLayout(global_group)
        global_layout.setSpacing(15)
        
        # 전체 활성화
        all_on_btn = QPushButton("전체 활성화")
        all_on_btn.setObjectName("global_btn_on")
        all_on_btn.setMinimumHeight(50)
        all_on_btn.clicked.connect(lambda: self.on_all_toggle(True))
        global_layout.addWidget(all_on_btn)
        
        # 전체 비활성화
        all_off_btn = QPushButton("전체 비활성화")
        all_off_btn.setObjectName("global_btn_off")
        all_off_btn.setMinimumHeight(50)
        all_off_btn.clicked.connect(lambda: self.on_all_toggle(False))
        global_layout.addWidget(all_off_btn)
        
        # 전체 테스트
        all_test_btn = QPushButton("전체 테스트")
        all_test_btn.setObjectName("global_btn_test")
        all_test_btn.setMinimumHeight(50)
        all_test_btn.clicked.connect(self.on_all_test)
        global_layout.addWidget(all_test_btn)
        
        # 긴급 정지
        emergency_btn = QPushButton("긴급 정지")
        emergency_btn.setObjectName("emergency_btn")
        emergency_btn.setMinimumHeight(50)
        emergency_btn.clicked.connect(self.on_emergency_stop)
        global_layout.addWidget(emergency_btn)
        
        parent_layout.addWidget(global_group)
    
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
        
        # 버튼 텍스트 변경
        btn = self.findChild(QPushButton, f"toggle_btn_{num}")
        if btn:
            btn.setText("활성화" if enabled else "비활성화")
        # TODO: 실제 활성화/비활성화
    
    def on_all_toggle(self, enable):
        """전체 활성화/비활성화"""
        state = "활성화" if enable else "비활성화"
        log(f"에어나이프 전체 {state}")
        
        # 모든 토글 버튼 상태 변경
        for i in range(1, 9):
            btn = self.findChild(QPushButton, f"toggle_btn_{i}")
            if btn:
                btn.setChecked(enable)
                btn.setText("활성화" if enable else "비활성화")
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
                font-size: 12px;
            }
            
            #input_field {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 5px;
                padding: 5px;
                color: #c9d1d9;
                font-size: 12px;
            }
            
            #input_field:focus {
                border-color: #58a6ff;
            }
            
            #apply_btn {
                background-color: #1f6feb;
                color: white;
                border: 2px solid #58a6ff;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            
            #apply_btn:hover {
                background-color: #58a6ff;
            }
            
            #test_btn {
                background-color: #6e7681;
                color: white;
                border: 2px solid #8b949e;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            
            #test_btn:hover {
                background-color: #8b949e;
            }
            
            QPushButton[objectName^="toggle_btn"] {
                background-color: #238636;
                color: white;
                border: 2px solid #2ea043;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            
            QPushButton[objectName^="toggle_btn"]:checked {
                background-color: #238636;
                border-color: #2ea043;
            }
            
            QPushButton[objectName^="toggle_btn"]:!checked {
                background-color: #6e7681;
                border-color: #8b949e;
            }
            
            QPushButton[objectName^="toggle_btn"]:hover {
                opacity: 0.8;
            }
            
            #global_btn_on {
                background-color: #238636;
                color: white;
                border: 2px solid #2ea043;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #global_btn_on:hover {
                background-color: #2ea043;
            }
            
            #global_btn_off {
                background-color: #6e7681;
                color: white;
                border: 2px solid #8b949e;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #global_btn_off:hover {
                background-color: #8b949e;
            }
            
            #global_btn_test {
                background-color: #1f6feb;
                color: white;
                border: 2px solid #58a6ff;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #global_btn_test:hover {
                background-color: #58a6ff;
            }
            
            #emergency_btn {
                background-color: #da3633;
                color: white;
                border: 2px solid #f85149;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #emergency_btn:hover {
                background-color: #f85149;
            }
        """)