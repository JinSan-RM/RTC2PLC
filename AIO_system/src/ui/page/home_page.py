from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QGroupBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from src.utils.logger import log


class StatusCard(QFrame):
    """상태 카드 위젯"""
    
    def __init__(self, title, value="0", unit="", color="#58a6ff"):
        super().__init__()
        self.color = color
        self.init_ui(title, value, unit)
        
    def init_ui(self, title, value, unit):
        """UI 초기화"""
        self.setObjectName("status_card")
        self.setMinimumHeight(120)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        
        # 제목
        title_label = QLabel(title)
        title_label.setObjectName("card_title")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 값
        self.value_label = QLabel(value)
        self.value_label.setObjectName("card_value")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet(f"color: {self.color}; font-size: 36px; font-weight: bold;")
        layout.addWidget(self.value_label)
        
        # 단위
        if unit:
            unit_label = QLabel(unit)
            unit_label.setObjectName("card_unit")
            unit_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(unit_label)
        
    def update_value(self, value):
        """값 업데이트"""
        self.value_label.setText(str(value))


class HomePage(QWidget):
    """홈 페이지 - 시스템 개요"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
        
        # 업데이트 타이머
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(1000)  # 1초마다 업데이트
        
    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        # 상태 카드 영역
        self.create_status_cards(main_layout)
        
        # 실시간 모니터링 영역
        self.create_monitoring_area(main_layout)
        
        # 제어 영역
        self.create_control_area(main_layout)
        
        main_layout.addStretch()
        
        # 스타일 적용
        self.apply_styles()
        
    def create_status_cards(self, parent_layout):
        """상태 카드 생성"""
        card_layout = QHBoxLayout()
        card_layout.setSpacing(20)
        
        self.cards = {}
        
        card_info = [
            ("시스템 상태", "정상", "", "#3fb950"),
            ("활성 알람", "0", "건", "#f85149"),
            ("피더 가동", "1/1", "개", "#58a6ff"),
            ("컨베이어", "4/4", "개", "#58a6ff"),
        ]
        
        for title, value, unit, color in card_info:
            card = StatusCard(title, value, unit, color)
            card_layout.addWidget(card)
            self.cards[title] = card
            
        parent_layout.addLayout(card_layout)
    
    def create_monitoring_area(self, parent_layout):
        """실시간 모니터링 영역 생성"""
        monitoring_group = QGroupBox("실시간 모니터링")
        monitoring_group.setObjectName("monitoring_group")
        monitoring_main_layout = QVBoxLayout(monitoring_group)
        
        # 상단: 인버터 출력 정보
        output_layout = QGridLayout()
        output_layout.setSpacing(15)
        
        row = 0
        # 출력 주파수
        self.add_monitor_item(output_layout, row, 0, 
                             "출력 주파수", "0.00", "Hz", "#58a6ff")
        # 출력 전류
        self.add_monitor_item(output_layout, row, 1,
                             "출력 전류", "0.0", "A", "#58a6ff")
        # 출력 전압
        self.add_monitor_item(output_layout, row, 2,
                             "출력 전압", "0", "V", "#58a6ff")
        
        row += 1
        # DC Link 전압
        self.add_monitor_item(output_layout, row, 0,
                             "DC Link 전압", "0", "V", "#58a6ff")
        # 출력 파워
        self.add_monitor_item(output_layout, row, 1,
                             "출력 파워", "0.0", "kW", "#58a6ff")
        
        monitoring_main_layout.addLayout(output_layout)
        monitoring_main_layout.addSpacing(20)
        
        # 하단: 운전 상태 (가로 배치)
        status_container = QFrame()
        status_container.setObjectName("status_container")
        status_layout = QHBoxLayout(status_container)
        status_layout.setSpacing(10)
        
        status_title = QLabel("운전 상태:")
        status_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #c9d1d9;")
        status_layout.addWidget(status_title)
        
        self.status_labels = {}
        states = ["정지", "운전(정)", "운전(역)", "Fault", "가속", "감속"]
        for state in states:
            label = QLabel(f"⚪ {state}")
            label.setObjectName("status_indicator")
            label.setMinimumWidth(80)
            label.setAlignment(Qt.AlignCenter)
            status_layout.addWidget(label)
            self.status_labels[state] = label
        
        status_layout.addStretch()
        monitoring_main_layout.addWidget(status_container)
        
        parent_layout.addWidget(monitoring_group)
    
    def add_monitor_item(self, layout, row, col, name, value, unit, color):
        """모니터링 항목 추가"""
        # 이름
        name_label = QLabel(name)
        name_label.setStyleSheet("font-size: 13px; color: #8b949e;")
        layout.addWidget(name_label, row, col * 3)
        
        # 값
        value_label = QLabel(value)
        value_label.setObjectName(f"monitor_{name}")
        value_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")
        layout.addWidget(value_label, row, col * 3 + 1)
        
        # 단위
        unit_label = QLabel(unit)
        unit_label.setStyleSheet("font-size: 13px; color: #8b949e;")
        layout.addWidget(unit_label, row, col * 3 + 2)
        
        # 나중에 업데이트하기 위해 저장
        if not hasattr(self, 'monitor_values'):
            self.monitor_values = {}
        self.monitor_values[name] = value_label
    
    def create_control_area(self, parent_layout):
        """제어 영역 생성"""
        controls_group = QGroupBox("제어")
        controls_group.setObjectName("controls_group")
        controls_layout = QHBoxLayout(controls_group)
        controls_layout.setSpacing(15)
        
        # 시작 버튼
        start_btn = QPushButton("시작")
        start_btn.setObjectName("control_btn_start")
        start_btn.setMinimumHeight(60)
        start_btn.clicked.connect(self.on_start_clicked)
        controls_layout.addWidget(start_btn)
        
        # 정지 버튼
        stop_btn = QPushButton("정지")
        stop_btn.setObjectName("control_btn_stop")
        stop_btn.setMinimumHeight(60)
        stop_btn.clicked.connect(self.on_stop_clicked)
        controls_layout.addWidget(stop_btn)
        
        # 리셋 버튼
        reset_btn = QPushButton("리셋")
        reset_btn.setObjectName("control_btn_reset")
        reset_btn.setMinimumHeight(60)
        reset_btn.clicked.connect(self.on_reset_clicked)
        controls_layout.addWidget(reset_btn)
        
        parent_layout.addWidget(controls_group)
        
    def update_data(self):
        """실시간 데이터 업데이트 (1초마다 호출)"""
        # TODO: 실제 데이터로 업데이트
        pass
    
    def update_monitor_values(self, data):
        """모니터링 값 업데이트"""
        # data = [acc_time, dec_time, out_current, out_freq, out_voltage, dc_voltage, out_power, run_state]
        if len(data) >= 8:
            self.monitor_values["출력 주파수"].setText(f"{data[3]:.2f}")
            self.monitor_values["출력 전류"].setText(f"{data[2]:.1f}")
            self.monitor_values["출력 전압"].setText(f"{data[4]:.0f}")
            self.monitor_values["DC Link 전압"].setText(f"{data[5]:.0f}")
            self.monitor_values["출력 파워"].setText(f"{data[6]:.1f}")
            
            # 운전 상태 업데이트 (라디오 버튼 스타일)
            run_state = data[7]
            states = ["정지", "운전(정)", "운전(역)", "Fault", "가속", "감속"]
            for i, state in enumerate(states):
                if run_state & (1 << i):
                    self.status_labels[state].setText(f"🟢 {state}")
                    self.status_labels[state].setStyleSheet("""
                        background-color: #238636;
                        border: 2px solid #2ea043;
                        border-radius: 6px;
                        padding: 5px 10px;
                        font-size: 13px;
                        color: white;
                        font-weight: bold;
                    """)
                else:
                    self.status_labels[state].setText(f"⚪ {state}")
                    self.status_labels[state].setStyleSheet("""
                        background-color: #161b22;
                        border: 2px solid #30363d;
                        border-radius: 6px;
                        padding: 5px 10px;
                        font-size: 13px;
                        color: #8b949e;
                    """)
                    
    def on_start_clicked(self):
        """시작 버튼 클릭"""
        log("시스템 시작")
        self.app.on_auto_start()
    
    def on_stop_clicked(self):
        """정지 버튼 클릭"""
        log("시스템 정지")
        self.app.on_auto_stop()
    
    def on_reset_clicked(self):
        """리셋 버튼 클릭"""
        log("시스템 리셋")
        # TODO: 실제 리셋 로직
    
    def apply_styles(self):
        """스타일시트 적용"""
        self.setStyleSheet("""
            /* 상태 카드 */
            #status_card {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 12px;
                padding: 15px;
            }
            
            #card_title {
                color: #8b949e;
                font-size: 14px;
                font-weight: bold;
            }
            
            #card_unit {
                color: #8b949e;
                font-size: 14px;
            }
            
            /* 그룹 박스 */
            QGroupBox {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 12px;
                padding-top: 20px;
                margin-top: 10px;
                font-size: 16px;
                font-weight: bold;
                color: #c9d1d9;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 5px 15px;
                background-color: #0d1117;
                border: 2px solid #30363d;
                border-radius: 6px;
                color: #58a6ff;
            }
            
            /* 운전 상태 컨테이너 */
            #status_container {
                background-color: #0d1117;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 10px;
            }
            
            /* 운전 상태 인디케이터 */
            #status_indicator {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 13px;
                color: #8b949e;
            }
            
            /* 제어 버튼 */
            #control_btn_start {
                background-color: #238636;
                color: white;
                border: 2px solid #2ea043;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }
            
            #control_btn_start:hover {
                background-color: #2ea043;
            }
            
            #control_btn_stop {
                background-color: #da3633;
                color: white;
                border: 2px solid #f85149;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }
            
            #control_btn_stop:hover {
                background-color: #f85149;
            }
            
            #control_btn_reset {
                background-color: #1f6feb;
                color: white;
                border: 2px solid #58a6ff;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }
            
            #control_btn_reset:hover {
                background-color: #58a6ff;
            }
        """)