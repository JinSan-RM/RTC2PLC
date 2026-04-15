"""
진단 페이지 - IO 체크 및 로그
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QButtonGroup, QPushButton, QTextEdit,
    QScrollArea, QFrame, QStackedWidget,
)
from PySide6.QtCore import Qt, QDateTime
from PySide6.QtGui import QTextCursor, QPixmap

from src.utils.config_util import UI_PATH


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
        self.setFixedHeight(45)
        self.setStyleSheet(
            """
            border: none;
            border-bottom: 1px solid #E2E2E2;
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 상태 LED
        self.led = QLabel("⚫")
        self.led.setStyleSheet("border: none; font-size: 16px;")
        layout.addWidget(self.led)

        # IO 이름
        name_label = QLabel(self.io_name)
        name_label.setStyleSheet(
            """
            border: none;
            color: #1B1B1B;
            font-family: 'Pretendard';
            font-size: 14px;
            font-weight: normal;
            """)
        layout.addWidget(name_label)

        layout.addStretch()

        # IO 주소
        addr_label = QLabel(self.io_address)
        addr_label.setStyleSheet(
            """
            border: none;
            color: #000000;
            font-family: 'Pretendard';
            font-size: 14px;
            font-weight: normal;
            """)
        layout.addWidget(addr_label)

    def set_state(self, is_on: bool):
        """상태 설정"""
        if self.is_on ^ is_on:
            if is_on:
                self.led.setText("🟢")
            else:
                self.led.setText("⚫")
            self.is_on = is_on


class IOCheckTab(QWidget):
    """IO 체크 탭"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.inputs: dict[str, IOIndicator] = {}
        self.outputs: dict[str, IOIndicator] = {}
        self.init_ui()

    def init_ui(self):
        """UI 초기화"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 좌측: Input
        self._create_input_section(main_layout)

        # 우측: Output
        self._create_output_section(main_layout)

        # 스타일 적용
        self.apply_styles()

    def _create_input_section(self, parent_layout):
        """Input 섹션"""
        layout = QVBoxLayout()
        layout.setSpacing(0)

        layout.addSpacing(30)

        header_layout = QHBoxLayout()
        input_title = QLabel("Input(센서)")
        input_title.setObjectName("title_label")
        header_layout.addWidget(input_title)

        header_layout.addSpacing(15)

        layout.addLayout(header_layout)

        layout.addSpacing(15)

        outer_box = QFrame()
        outer_box.setObjectName("contents_box")

        contents_layout = QVBoxLayout(outer_box)

        # 스크롤
        scroll = QScrollArea(outer_box)
        scroll.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        scroll_content.setMaximumWidth(1610)

        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setAlignment(Qt.AlignTop)
        scroll_layout.setSpacing(0)
        scroll_layout.setContentsMargins(25, 10, 25, 10)

        # Input IO 항목들
        input_list = [
            ("수동/자동", "I00"),
            ("운전", "I01"),
            ("정지", "I02"),
            ("알람 리셋", "I03"),
            ("비상정지", "I04"),
            ("내륜모터 인버터 알람", "I05"),
            ("외륜모터 인버터 알람", "I06"),
            ("컨베이어#1 인버터 알람", "I07"),
            ("컨베이어#2 인버터 알람", "I08"),
            ("컨베이어#3 인버터 알람", "I09"),
            ("컨베이어#4 인버터 알람", "I10"),
            ("원점 복귀", "I11"),
            ("입력 접점 12", "I12"),
            ("입력 접점 13", "I13"),
            ("입력 접점 14", "I14"),
            ("입력 접점 15", "I15"),
            ("피더 배출 제품감지센서", "I16"),
            ("입력 접점 17", "I17"),
            ("입력 접점 18", "I18"),
            ("입력 접점 19", "I19"),
            ("입력 접점 20", "I20"),
            ("입력 접점 21", "I21"),
            ("입력 접점 22", "I22"),
            ("입력 접점 23", "I23"),
            ("입력 접점 24", "I24"),
            ("입력 접점 25", "I25"),
            ("입력 접점 26", "I26"),
            ("입력 접점 27", "I27"),
            ("입력 접점 28", "I28"),
            ("입력 접점 29", "I29"),
            ("입력 접점 30", "I30"),
            ("입력 접점 31", "I31"),
        ]

        for name, addr in input_list:
            indicator = IOIndicator(name, addr)
            scroll_layout.addWidget(indicator)
            self.inputs[addr] = indicator

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)

        contents_layout.addWidget(scroll)

        layout.addWidget(outer_box)

        layout.addSpacing(25)

        parent_layout.addLayout(layout)

    def _create_output_section(self, parent_layout):
        """Output 섹션"""
        layout = QVBoxLayout()
        layout.setSpacing(0)

        layout.addSpacing(30)

        header_layout = QHBoxLayout()
        output_title = QLabel("Output(에어나이프)")
        output_title.setObjectName("title_label")
        header_layout.addWidget(output_title)

        header_layout.addSpacing(15)

        layout.addLayout(header_layout)

        layout.addSpacing(15)

        outer_box = QFrame()
        outer_box.setObjectName("contents_box")

        contents_layout = QVBoxLayout(outer_box)

        # 스크롤
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        scroll_content.setMaximumWidth(1610)

        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setAlignment(Qt.AlignTop)
        scroll_layout.setSpacing(0)
        scroll_layout.setContentsMargins(25, 10, 25, 10)

        # Output IO 항목들
        output_list = [
            ("운전 스위치 램프", "O00"),
            ("정지 스위치 램프", "O01"),
            ("타워 정상운전 램프", "O02"),
            ("타워 운전정지 램프", "O03"),
            ("타워 알람 램프", "O04"),
            ("타워 버저", "O05"),
            ("비전 1 조광기 파워", "O06"),
            ("비전 2 조광기 파워", "O07"),
            ("내륜모터 인버터 동작", "O08"),
            ("내륜모터 인버터 리셋", "O09"),
            ("외륜모터 인버터 동작", "O10"),
            ("외륜모터 인버터 리셋", "O11"),
            ("컨베이어#1 인버터 동작", "O12"),
            ("컨베이어#1 인버터 리셋", "O13"),
            ("컨베이어#2 인버터 동작", "O14"),
            ("컨베이어#2 인버터 리셋", "O15"),
            ("컨베이어#3 인버터 동작", "O16"),
            ("컨베이어#3 인버터 리셋", "O17"),
            ("컨베이어#4 인버터 동작", "O18"),
            ("컨베이어#4 인버터 리셋", "O19"),
            ("소재 1분리 SOL V/V", "O20"),
            ("소재 2분리 SOL V/V", "O21"),
            ("소재 3분리 SOL V/V", "O22"),
            ("SPARE", "O23"),
            ("원점 복귀 램프", "O24"),
            ("알람 리셋 램프", "O25"),
            ("출력 접점 26", "O26"),
            ("출력 접점 27", "O27"),
            ("출력 접점 28", "O28"),
            ("출력 접점 29", "O29"),
            ("출력 접점 30", "O30"),
            ("출력 접점 31", "O31"),
        ]

        for name, addr in output_list:
            indicator = IOIndicator(name, addr)
            scroll_layout.addWidget(indicator)
            self.outputs[addr] = indicator

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)

        contents_layout.addWidget(scroll)

        layout.addWidget(outer_box)

        layout.addSpacing(25)

        parent_layout.addLayout(layout)

    def update_io_state(self, io_address: str, is_on: bool):
        """IO 상태 업데이트"""
        if io_address in self.inputs:
            self.inputs[io_address].set_state(is_on)
        elif io_address in self.outputs:
            self.outputs[io_address].set_state(is_on)

    # input_id, output_id 는 추후 입출력 모듈이 추가되는 경우 사용
    def update_input_status(self, total_input: int):
        """입력 접점 on/off 체크"""
        for bit in range(32):
            if total_input & (1 << bit):
                self.update_io_state(f"I{bit:02d}", True)
            else:
                self.update_io_state(f"I{bit:02d}", False)

    def update_output_status(self, total_output: int):
        """출력 접점 on/off 체크"""
        for bit in range(32):
            if total_output & (1 << bit):
                self.update_io_state(f"O{bit:02d}", True)
            else:
                self.update_io_state(f"O{bit:02d}", False)

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
            """
        )


class LogTab(QWidget):
    """로그 탭"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()

    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.addSpacing(25)

        # 상단: 제어
        control_layout = QHBoxLayout()

        # 로그 레벨 필터
        lv_title = QLabel("로그 레벨:")
        lv_title.setObjectName("title_label")
        control_layout.addWidget(lv_title)

        control_layout.addSpacing(15)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.btn_group.idClicked.connect(self.filter_log)

        self.level_all = QPushButton("전체")
        self.level_all.setFixedSize(104, 34)
        self.level_all.setCheckable(True)
        self.level_all.setChecked(True)
        self.level_all.setObjectName("left_filter_btn")
        control_layout.addWidget(self.level_all)
        self.btn_group.addButton(self.level_all, 0)

        self.level_info = QPushButton("ℹ️ 정보")
        self.level_info.setFixedSize(104, 34)
        self.level_info.setCheckable(True)
        self.level_info.setObjectName("filter_btn")
        control_layout.addWidget(self.level_info)
        self.btn_group.addButton(self.level_info, 1)

        self.level_warning = QPushButton("⚠️ 경고")
        self.level_warning.setFixedSize(104, 34)
        self.level_warning.setCheckable(True)
        self.level_warning.setObjectName("filter_btn")
        control_layout.addWidget(self.level_warning)
        self.btn_group.addButton(self.level_warning, 2)

        self.level_error = QPushButton("❌ 에러")
        self.level_error.setFixedSize(104, 34)
        self.level_error.setCheckable(True)
        self.level_error.setObjectName("right_filter_btn")
        control_layout.addWidget(self.level_error)
        self.btn_group.addButton(self.level_error, 3)

        control_layout.addStretch()

        # 지우기
        clear_btn = QPushButton("로그 지우기")
        clear_btn.setObjectName("clear_btn")
        clear_btn.setFixedSize(141, 40)
        clear_btn.clicked.connect(self.clear_log)
        control_layout.addWidget(clear_btn)

        control_layout.addSpacing(15)

        # 저장
        save_btn = QPushButton("저장")
        save_btn.setObjectName("save_btn")
        save_btn.setFixedSize(141, 40)
        save_btn.clicked.connect(self.save_log)
        control_layout.addWidget(save_btn)

        main_layout.addLayout(control_layout)

        main_layout.addSpacing(15)

        # 로그 텍스트
        outer_box = QFrame()
        outer_box.setObjectName("contents_box")

        contents_layout = QVBoxLayout(outer_box)

        self.log_text = QTextEdit()
        self.log_text.setObjectName("log_text")
        self.log_text.setReadOnly(True)
        contents_layout.addWidget(self.log_text)
        main_layout.addWidget(outer_box)
        main_layout.addSpacing(25)

        # 스타일 적용
        self.apply_styles()

    def add_log(self, message, level="info"):
        """로그 추가"""
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")

        level = level.lower()

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

        log_entry = f"""
            <span style="color: #8b949e;">[{timestamp}]</span> 
            <span style="color: {color}; font-weight: bold;">{icon} {message}</span>
            """

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
        self.app.on_popup("info", "로그 지우기 ", "로그가 지워졌습니다.")

    def save_log(self):
        """로그 저장"""
        self.app.on_log("로그 저장")
        # TODO: 파일로 저장
        self.app.on_popup("info", "로그 저장", "로그가 저장되었습니다.")

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
            
            #filter_btn {
                background-color: #F2F2F2;
                border: 1px solid #E2E2E2;
                color: #7F7F7F;
                font-size: 14px;
                font-weight: normal;
            }
            
            #filter_btn:checked {
                background-color: #2DB591;
                color: #FFFFFF;
                font-weight: medium;
            }
            
            #filter_btn:hover {
                color: #000000;
            }

            #left_filter_btn {
                background-color: #F2F2F2;
                border: 1px solid #E2E2E2;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                color: #7F7F7F;
                font-size: 14px;
                font-weight: normal;
            }
            
            #left_filter_btn:checked {
                background-color: #2DB591;
                color: #FFFFFF;
                font-weight: medium;
            }
            
            #left_filter_btn:hover {
                color: #000000;
            }

            #right_filter_btn {
                background-color: #F2F2F2;
                border: 1px solid #E2E2E2;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                color: #7F7F7F;
                font-size: 14px;
                font-weight: normal;
            }
            
            #right_filter_btn:checked {
                background-color: #2DB591;
                color: #FFFFFF;
                font-weight: medium;
            }
            
            #right_filter_btn:hover {
                color: #000000;
            }
            
            #clear_btn {
                background-color: #353535;
                border: none;
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 16px;
                font-weight: medium;
            }
            
            #clear_btn:hover {
                background-color: #f85149;
            }
            
            #save_btn {
                background-color: #2DB591;
                border: none;
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 16px;
                font-weight: medium;
            }
            
            #save_btn:hover {
                background-color: #58a6ff;
            }
            
            #log_text {
                background-color: transparent;
                border: none;
                color: #1B1B1B;
                font-family: 'Pretendard';
                font-size: 14px;
            }
            """
        )


class LogsPage(QWidget):
    """로그 페이지 - IO 체크 및 로그"""
    def __init__(self, app, title: QLabel):
        super().__init__()
        self.app = app
        self.title = title
        self.init_ui()

    def init_ui(self):
        """UI 초기화"""
        # 사이드바
        self.side_widget = QFrame(self)
        side_layout = QVBoxLayout(self.side_widget)
        side_layout.setSpacing(0)
        side_layout.setContentsMargins(0, 0, 0, 0)

        self._create_sidebar(side_layout)

        side_layout.addSpacing(20)

        self._create_side_tab(side_layout)

        side_layout.addStretch()

        # 컨텐츠 영역
        self.main_widget = QFrame(self)
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.pages = QStackedWidget()

        # 탭 추가
        self.io_tab = IOCheckTab(self.app)
        self.log_tab = LogTab(self.app)

        self.pages.addWidget(self.io_tab)
        self.pages.addWidget(self.log_tab)

        main_layout.addWidget(self.pages)

        # 스타일 적용
        self.apply_styles()

    def _create_sidebar(self, parent_layout):
        title_layout = QHBoxLayout()
        title_layout.setSpacing(0)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_layout.addSpacing(30)

        img_label = QLabel()
        img_label.setObjectName("side_title_logo")
        logo_img = QPixmap(str(UI_PATH / "logo/log_page.png"))
        img_label.setPixmap(logo_img)
        img_label.setScaledContents(True)
        img_label.setFixedSize(16, 16)
        title_layout.addWidget(img_label)

        title_layout.addSpacing(10)

        title_label = QLabel("로그")
        title_label.setObjectName("side_title_label")
        title_layout.addWidget(title_label)

        parent_layout.addLayout(title_layout)

    nav_list = [
        "IO 체크",
        "로그",
    ]

    def _create_side_tab(self, parent_layout):
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.btn_group.idClicked.connect(self.show_page)

        for i, text in enumerate(self.nav_list):
            btn = QPushButton(text)
            btn.setObjectName("nav_button")
            btn.setCheckable(True)
            btn.setFixedHeight(44)

            parent_layout.addWidget(btn)
            self.btn_group.addButton(btn, i)

    def show_page(self, index):
        """페이지 전환"""
        self.pages.setCurrentIndex(index)

        # 페이지 제목 업데이트
        if index < len(self.nav_list):
            self.title.setText(self.nav_list[index])

    def add_log(self, message, level="info"):
        """로그 추가 (외부 호출용)"""
        self.log_tab.add_log(message, level)

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

            /* 네비게이션 버튼 */
            #nav_button {
                background-color: transparent;
                min-height: 44px;
                max-height: 44px;
                color: #000000;
                border: none;
                text-align: left;
                padding-left: 30px;
                font-size: 14px;
                font-weight: normal;
            }
            
            #nav_button:hover {
                background-color: #FFFFFF;
                font-weight:500;
            }
            
            #nav_button:checked {
                background-color: #FFFFFF;
                color: #2DB591;
                font-weight: medium;
            }
            """
        )
