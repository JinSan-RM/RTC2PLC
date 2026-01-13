from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap

from src.utils.config_util import UI_PATH
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
        self.setFixedHeight(130)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        
        # 제목
        title_label = QLabel(title)
        title_label.setObjectName("card_title")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 값
        value_txt = f"{value} {unit}" if unit else value
        self.value_label = QLabel(value_txt)
        self.value_label.setObjectName("card_value")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet(
            f"""
            color: {self.color};
            font-size: 30px;
            font-weight: bold;
            """
        )
        layout.addWidget(self.value_label)
        
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
        # 사이드바
        self.side_widget = QFrame(self)
        side_layout = QVBoxLayout(self.side_widget)
        side_layout.setSpacing(0)
        side_layout.setContentsMargins(0, 0, 0, 0)

        self.create_sidebar(side_layout)

        side_layout.addStretch()

        # 컨텐츠 영역
        self.main_widget = QFrame(self)
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.addSpacing(25)
        
        # 상태 카드 영역
        self.create_status_cards(main_layout)

        main_layout.addSpacing(50)
        
        # 컨트롤러
        for i in range(1):
            self.create_controller(main_layout, i)
        
        main_layout.addStretch()
        
        # 스타일 적용
        self.apply_styles()

    def create_sidebar(self, parent_layout):
        title_layout = QHBoxLayout()
        title_layout.setSpacing(0)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_layout.addSpacing(30)

        img_label = QLabel()
        img_label.setObjectName("side_title_logo")
        logo_img = QPixmap(str(UI_PATH / "logo/home_page.png"))
        img_label.setPixmap(logo_img)
        img_label.setScaledContents(True)
        img_label.setFixedSize(16, 16)
        title_layout.addWidget(img_label)

        title_layout.addSpacing(10)

        title_label = QLabel("홈 대시보드")
        title_label.setObjectName("side_title_label")
        title_layout.addWidget(title_label)

        parent_layout.addLayout(title_layout)
        
    def create_status_cards(self, parent_layout):
        """상태 카드 생성"""
        card_layout = QHBoxLayout()
        card_layout.setSpacing(20)
        
        self.cards = {}
        
        card_info = [
            ("시스템 상태", "정상", "", "#2DB591"),
            ("활성 알람", "0", "건", "#FF2427"),
            ("피더 가동", "1/1", "개", "#000000"),
            ("컨베이어", "4/4", "개", "#000000"),
        ]
        
        for title, value, unit, color in card_info:
            card = StatusCard(title, value, unit, color)
            card_layout.addWidget(card)
            self.cards[title] = card
            
        parent_layout.addLayout(card_layout)

    def create_controller(self, parent_layout, index):
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.create_controller_header(layout, index)

        layout.addSpacing(10)

        self.create_controller_body(layout)

        parent_layout.addLayout(layout)

    def create_controller_header(self, parent_layout, index):
        layout = QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        controller_title = QLabel(f"withwe_{index}")
        controller_title.setObjectName("controller_title")
        layout.addWidget(controller_title)

        layout.addSpacing(10)

        run_btn = QPushButton("정지")
        run_btn.setObjectName("controller_run_btn")
        run_btn.setFixedHeight(34)
        layout.addWidget(run_btn)

        layout.addStretch()

        state_title = QLabel("운전 상태:")
        state_title.setObjectName("state_title")
        layout.addWidget(state_title)

        state_mark = QLabel("")
        state_mark.setObjectName("state_mark")
        layout.addWidget(state_mark)

        state_txt = QLabel("정지")
        state_txt.setObjectName("state_txt")
        layout.addWidget(state_txt)

        parent_layout.addLayout(layout)

    def create_controller_body(self, parent_layout):
        lower_box = QFrame()
        lower_box.setObjectName("controller_lower_box")
        layout = QVBoxLayout(lower_box)
        layout.setSpacing(0)
        layout.setContentsMargins(30, 30, 30, 30)

        # 실시간 모니터링 영역
        self.create_monitoring_area(layout)

        layout.addSpacing(40)
        
        # 제어 영역
        self.create_control_area(layout)

        parent_layout.addWidget(lower_box)
    
    def create_monitoring_area(self, parent_layout):
        """실시간 모니터링 영역 생성"""
        # 상단: 인버터 출력 정보
        output_layout = QGridLayout()
        output_layout.setSpacing(175)
        
        # 출력 주파수
        self.add_monitor_item(output_layout, 0, 0, "출력 주파수", "0.00", "Hz")
        # 출력 전류
        self.add_monitor_item(output_layout, 0, 1, "출력 전류", "0.0", "A")
        # 출력 전압
        self.add_monitor_item(output_layout, 0, 2, "출력 전압", "0", "V")
        # DC Link 전압
        self.add_monitor_item(output_layout, 0, 3, "DC Link 전압", "0", "V")
        # 출력 파워
        self.add_monitor_item(output_layout, 0, 4, "출력 파워", "0.0", "kW")
        
        parent_layout.addLayout(output_layout)
    
    def add_monitor_item(self, parent_layout, row, col, name, value, unit):
        """모니터링 항목 추가"""
        layout = QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        # 이름
        name_label = QLabel(name)
        name_label.setStyleSheet(
            """
            border: none;
            color: #4B4B4B;
            font-size: 14px;
            font-weight: normal;
            """
        )
        layout.addWidget(name_label)

        layout.addStretch()
        
        # 값
        value_label = QLabel(value)
        value_label.setObjectName(f"monitor_{name}")
        value_label.setStyleSheet(
            """
            border: none;
            color: #000000;
            font-size: 18px;
            font-weight: bold;
            """
        )
        layout.addWidget(value_label)

        layout.addSpacing(10)
        
        # 단위
        unit_label = QLabel(unit)
        unit_label.setStyleSheet(
            """
            border: none;
            color: #B8B8B8;
            font-size: 14px;
            font-weight: normal;
            """
        )
        layout.addWidget(unit_label)
        
        # 나중에 업데이트하기 위해 저장
        if not hasattr(self, 'monitor_values'):
            self.monitor_values = {}
        self.monitor_values[name] = value_label

        parent_layout.addLayout(layout, row, col)
    
    def create_control_area(self, parent_layout):
        """제어 영역 생성"""
        layout = QHBoxLayout()
        layout.setSpacing(30)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 리셋 버튼
        reset_btn = QPushButton("리셋")
        reset_btn.setObjectName("control_btn_reset")
        reset_btn.setFixedHeight(60)
        reset_btn.clicked.connect(self.on_reset_clicked)
        layout.addWidget(reset_btn)

        # 정지 버튼
        stop_btn = QPushButton("정지")
        stop_btn.setObjectName("control_btn_stop")
        stop_btn.setFixedHeight(60)
        stop_btn.clicked.connect(self.on_stop_clicked)
        layout.addWidget(stop_btn)
        
        # 시작 버튼
        start_btn = QPushButton("시작")
        start_btn.setObjectName("control_btn_start")
        start_btn.setFixedHeight(60)
        start_btn.clicked.connect(self.on_start_clicked)
        layout.addWidget(start_btn)
        
        parent_layout.addLayout(layout)
        
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
                    self.status_labels[state].setStyleSheet(
                        """
                        background-color: #238636;
                        border: 2px solid #2ea043;
                        border-radius: 6px;
                        padding: 5px 10px;
                        font-size: 13px;
                        color: white;
                        font-weight: bold;
                        """
                    )
                else:
                    self.status_labels[state].setText(f"⚪ {state}")
                    self.status_labels[state].setStyleSheet(
                        """
                        background-color: #161b22;
                        border: 2px solid #30363d;
                        border-radius: 6px;
                        padding: 5px 10px;
                        font-size: 13px;
                        color: #8b949e;
                        """
                    )
                    
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
        self.side_widget.setStyleSheet(
            """
            /* 사이드바 제목 */
            #side_title_label {
                color: #000000;
                font-size: 16px;
                font-weight: medium;
            }
            """
        )
        self.main_widget.setStyleSheet(
            """
            /* 상태 카드 */
            #status_card {
                background-color: #F3F4F6;
                border: 1px solid #E2E2E2;
                border-radius: 7px;
            }
            
            #card_title {
                color: #4B4B4B;
                font-size: 14px;
                font-weight: normal;
            }
            
            /* 컨트롤러 상단 */
            #controller_title {
                color: #000000;
                font-size: 16px;
                font-weight: medium;
            }

            #controller_run_btn {
                background-color: #F3F4F6;
                color: #4B4B4B;
                border: 1px solid #E2E2E2;
                border-radius: 4px;
                font-size: 14px;
                font-weight: normal;
                padding: 5px;
            }

            #state_title {
                color: #000000;
                font-size: 16px;
                font-weight: medium;
            }

            #state_mark {
            }

            #state_txt {
                color: #4B4B4B;
                font-size: 14px;
                font-weight: normal;
            }

            #controller_lower_box {
                background-color: #FAFAFA;
                border: 1px solid #E2E2E2;
                border-radius: 7px;
            }
            
            /* 제어 버튼 */
            #control_btn_start {
                background-color: #2DB591;
                border: 1px solid transparent;
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 16px;
                font-weight: medium;
            }
            
            #control_btn_start:hover {
                background-color: #45CAA6;
            }
            
            #control_btn_stop {
                background-color: #FF2427;
                border: 1px solid transparent;
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 16px;
                font-weight: medium;
            }
            
            #control_btn_stop:hover {
                background-color: #FF6467;
            }
            
            #control_btn_reset {
                background-color: #353535;
                border: 1px solid transparent;
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 16px;
                font-weight: medium;
            }
            
            #control_btn_reset:hover {
                background-color: #555555;
            }
            """
        )