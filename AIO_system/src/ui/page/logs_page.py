"""
진단 페이지 - IO 체크 및 로그
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QTextEdit, QScrollArea,
    QFrame, QTabWidget
)
from PyQt5.QtCore import Qt, QDateTime
from PyQt5.QtGui import QTextCursor


class IOIndicator(QFrame):
    """IO 인디케이터 위젯"""
    
    def __init__(self, io_name, io_address):
        super().__init__()
        self.io_name = io_name
        self.io_address = io_address
        self.is_on = False
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        self.setObjectName("io_indicator")
        self.setMinimumHeight(45)
        self.setMaximumHeight(45)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # 상태 LED
        self.led = QLabel("⚫")
        self.led.setObjectName("led_off")
        self.led.setStyleSheet("font-size: 20px;")
        layout.addWidget(self.led)
        
        # IO 이름
        name_label = QLabel(self.io_name)
        name_label.setStyleSheet("color: #c9d1d9; font-size: 12px; font-weight: bold;")
        layout.addWidget(name_label)
        
        layout.addStretch()
        
        # IO 주소
        addr_label = QLabel(self.io_address)
        addr_label.setStyleSheet("color: #8b949e; font-size: 11px;")
        layout.addWidget(addr_label)
    
    def set_state(self, is_on):
        """상태 설정"""
        self.is_on = is_on
        if is_on:
            self.led.setText("🟢")
            self.led.setObjectName("led_on")
            self.setStyleSheet("""
                #io_indicator {
                    background-color: #1a2e1a;
                    border: 2px solid #2ea043;
                    border-radius: 5px;
                }
            """)
        else:
            self.led.setText("⚫")
            self.led.setObjectName("led_off")
            self.setStyleSheet("""
                #io_indicator {
                    background-color: #161b22;
                    border: 2px solid #30363d;
                    border-radius: 5px;
                }
            """)


class IOCheckTab(QWidget):
    """IO 체크 탭"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 좌측: Input
        self.create_input_section(main_layout)
        
        # 우측: Output
        self.create_output_section(main_layout)
        
        # 스타일 적용
        self.apply_styles()
    
    def create_input_section(self, parent_layout):
        """Input 섹션"""
        input_group = QGroupBox("Input (센서)")
        input_group.setObjectName("group_box")
        
        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(5)
        
        # Input IO 항목들
        self.inputs = {}
        input_list = [
            ("리턴 컨베이어 #1 원점 입력", "P000"),
            ("리턴 컨베이어 #2 원점 입력", "P001"),
            ("소팅 컨베이어 적치 감지", "P002"),
            ("대형 내륜 피더 적재 감지", "P003"),
            ("대형 외륜 피더 적재 감지", "P004"),
            ("소형 내륜 피더 적재 감지", "P005"),
            ("소형 외륜 피더 적재 감지", "P006"),
            ("대형 소팅 피더 원점", "P007"),
            ("대형 소팅 1분리 감지", "P008"),
            ("대형 소팅 2분리 감지", "P009"),
            ("대형 소팅 3분리 감지", "P00A"),
            ("소형 소팅 피더 원점", "P00B"),
            ("소형 소팅 1분리 감지", "P00C"),
            ("소형 소팅 2분리 감지", "P00D"),
            ("소형 소팅 3분리 감지", "P00E"),
        ]
        
        for name, addr in input_list:
            indicator = IOIndicator(name, addr)
            scroll_layout.addWidget(indicator)
            self.inputs[addr] = indicator
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        
        group_layout = QVBoxLayout(input_group)
        group_layout.addWidget(scroll)
        
        parent_layout.addWidget(input_group)
    
    def create_output_section(self, parent_layout):
        """Output 섹션"""
        output_group = QGroupBox("Output (에어나이프)")
        output_group.setObjectName("group_box")
        
        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(5)
        
        # Output IO 항목들
        self.outputs = {}
        output_list = [
            ("리턴 컨베이어 #1 리셋", "P040"),
            ("리턴 컨베이어 #2 리셋", "P041"),
            ("소팅 리턴 컨베이어 #1 RUN", "P042"),
            ("소팅 리턴 컨베이어 #2 RUN", "P043"),
            ("대형 내륜 피더 전진", "P044"),
            ("대형 내륜 피더 후진", "P045"),
            ("대형 1분리 에어나이프 #1", "P050"),
            ("대형 1분리 에어나이프 #2", "P051"),
            ("대형 2분리 에어나이프 #1", "P052"),
            ("대형 2분리 에어나이프 #2", "P053"),
            ("대형 3분리 에어나이프 #1", "P054"),
            ("대형 3분리 에어나이프 #2", "P055"),
            ("소형 1분리 에어나이프", "P056"),
            ("소형 2분리 에어나이프", "P057"),
            ("소형 3분리 에어나이프", "P058"),
        ]
        
        for name, addr in output_list:
            indicator = IOIndicator(name, addr)
            scroll_layout.addWidget(indicator)
            self.outputs[addr] = indicator
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        
        group_layout = QVBoxLayout(output_group)
        group_layout.addWidget(scroll)
        
        parent_layout.addWidget(output_group)
    
    def update_io_state(self, io_address, is_on):
        """IO 상태 업데이트"""
        if io_address in self.inputs:
            self.inputs[io_address].set_state(is_on)
        elif io_address in self.outputs:
            self.outputs[io_address].set_state(is_on)
    
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
        """)


class LogTab(QWidget):
    """로그 탭"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 상단: 제어
        control_layout = QHBoxLayout()
        
        # 로그 레벨 필터
        control_layout.addWidget(QLabel("로그 레벨:"))
        
        self.level_all = QPushButton("전체")
        self.level_all.setCheckable(True)
        self.level_all.setChecked(True)
        self.level_all.setObjectName("filter_btn")
        self.level_all.clicked.connect(lambda: self.filter_log("all"))
        control_layout.addWidget(self.level_all)
        
        self.level_info = QPushButton("ℹ️ 정보")
        self.level_info.setCheckable(True)
        self.level_info.setObjectName("filter_btn")
        self.level_info.clicked.connect(lambda: self.filter_log("info"))
        control_layout.addWidget(self.level_info)
        
        self.level_warning = QPushButton("⚠️ 경고")
        self.level_warning.setCheckable(True)
        self.level_warning.setObjectName("filter_btn")
        self.level_warning.clicked.connect(lambda: self.filter_log("warning"))
        control_layout.addWidget(self.level_warning)
        
        self.level_error = QPushButton("❌ 에러")
        self.level_error.setCheckable(True)
        self.level_error.setObjectName("filter_btn")
        self.level_error.clicked.connect(lambda: self.filter_log("error"))
        control_layout.addWidget(self.level_error)
        
        control_layout.addStretch()
        
        # 지우기
        clear_btn = QPushButton("로그 지우기")
        clear_btn.setObjectName("clear_btn")
        clear_btn.clicked.connect(self.clear_log)
        control_layout.addWidget(clear_btn)
        
        # 저장
        save_btn = QPushButton("저장")
        save_btn.setObjectName("save_btn")
        save_btn.clicked.connect(self.save_log)
        control_layout.addWidget(save_btn)
        
        main_layout.addLayout(control_layout)
        
        # 로그 텍스트
        self.log_text = QTextEdit()
        self.log_text.setObjectName("log_text")
        self.log_text.setReadOnly(True)
        main_layout.addWidget(self.log_text)
        
        # 스타일 적용
        self.apply_styles()
    
    def add_log(self, message, level="info"):
        """로그 추가"""
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        
        # 레벨별 색상
        colors = {
            "info": "#58a6ff",
            "warning": "#d29922",
            "error": "#f85149"
        }
        color = colors.get(level, "#c9d1d9")
        
        # 레벨 아이콘
        icons = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌"
        }
        icon = icons.get(level, "•")
        
        log_entry = f'<span style="color: #8b949e;">[{timestamp}]</span> <span style="color: {color}; font-weight: bold;">{icon} {message}</span>'
        
        self.log_text.append(log_entry)
        self.log_text.moveCursor(QTextCursor.End)
    
    def filter_log(self, level):
        """로그 필터링"""
        self.app.on_log(f"로그 필터: {level}")
        # TODO: 실제 필터링 구현
    
    def clear_log(self):
        """로그 지우기"""
        self.log_text.clear()
        self.app.on_log("로그 지움")
    
    def save_log(self):
        """로그 저장"""
        self.app.on_log("로그 저장")
        # TODO: 파일로 저장
    
    def apply_styles(self):
        """스타일시트 적용"""
        self.setStyleSheet("""
            QLabel {
                color: #c9d1d9;
                font-size: 13px;
            }
            
            #filter_btn {
                background-color: #161b22;
                color: #8b949e;
                border: 2px solid #30363d;
                border-radius: 5px;
                padding: 5px 15px;
                font-size: 12px;
            }
            
            #filter_btn:checked {
                background-color: #1f6feb;
                color: white;
                border-color: #58a6ff;
                font-weight: bold;
            }
            
            #filter_btn:hover {
                border-color: #58a6ff;
            }
            
            #clear_btn {
                background-color: #da3633;
                color: white;
                border: 2px solid #f85149;
                border-radius: 6px;
                padding: 5px 15px;
                font-size: 13px;
                font-weight: bold;
            }
            
            #clear_btn:hover {
                background-color: #f85149;
            }
            
            #save_btn {
                background-color: #1f6feb;
                color: white;
                border: 2px solid #58a6ff;
                border-radius: 6px;
                padding: 5px 15px;
                font-size: 13px;
                font-weight: bold;
            }
            
            #save_btn:hover {
                background-color: #58a6ff;
            }
            
            #log_text {
                background-color: #0d1117;
                border: 2px solid #30363d;
                border-radius: 8px;
                color: #c9d1d9;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 10px;
            }
        """)


class LogsPage(QWidget):
    """로그 페이지 - IO 체크 및 로그"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 탭 위젯
        self.tabs = QTabWidget()
        self.tabs.setObjectName("diagnosis_tabs")
        
        # IO 체크 탭
        self.io_tab = IOCheckTab(self.app)
        self.tabs.addTab(self.io_tab, "IO 체크")
        
        # 로그 탭
        self.log_tab = LogTab(self.app)
        self.tabs.addTab(self.log_tab, "로그")
        
        main_layout.addWidget(self.tabs)
        
        # 스타일 적용
        self.apply_styles()
    
    def add_log(self, message, level="info"):
        """로그 추가 (외부 호출용)"""
        self.log_tab.add_log(message, level)
    
    def apply_styles(self):
        """스타일시트 적용"""
        self.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #30363d;
                border-radius: 8px;
                background-color: #161b22;
                top: -1px;
            }
            
            QTabBar::tab {
                background-color: #0d1117;
                color: #8b949e;
                padding: 12px 24px;
                margin-right: 2px;
                border: 2px solid #30363d;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            QTabBar::tab:selected {
                background-color: #161b22;
                color: #58a6ff;
                border-color: #30363d;
            }
            
            QTabBar::tab:hover {
                background-color: #21262d;
                color: #c9d1d9;
            }
        """)