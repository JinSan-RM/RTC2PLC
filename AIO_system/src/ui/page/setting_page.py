"""
설정 페이지 - 서보, 피더, 컨베이어, 에어나이프 제어
"""

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, 
    QStackedWidget, QLabel, QPushButton, QButtonGroup
)
from PySide6.QtGui import QPixmap

from src.ui.page.settings.servo_tab import ServoTab
from src.ui.page.settings.feeder_tab import FeederTab
from src.ui.page.settings.conveyor_tab import ConveyorTab
from src.ui.page.settings.airknife_tab import AirKnifeTab

from src.utils.config_util import UI_PATH


class SettingsPage(QWidget):
    """설정 페이지 - 메인"""
    
    def __init__(self, app, title: QLabel, explain: QLabel):
        super().__init__()
        self.app = app
        self.title = title
        self.explain = explain
        self.init_ui()
    
    def init_ui(self):
        """UI 초기화"""
        # 사이드바
        self.side_widget = QFrame(self)
        side_layout = QVBoxLayout(self.side_widget)
        side_layout.setSpacing(0)
        side_layout.setContentsMargins(0, 0, 0, 0)

        self.create_sidebar(side_layout)

        side_layout.addSpacing(20)

        self.create_side_tab(side_layout)

        side_layout.addStretch()

        # 컨텐츠 영역
        self.main_widget = QFrame(self)
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.pages = QStackedWidget()
        
        # 각 탭 추가
        self.servo_tab = ServoTab(self.app)
        self.feeder_tab = FeederTab(self.app)
        self.conveyor_tab = ConveyorTab(self.app)
        self.airknife_tab = AirKnifeTab(self.app)
        
        self.pages.addWidget(self.servo_tab)
        self.pages.addWidget(self.feeder_tab)
        self.pages.addWidget(self.conveyor_tab)
        self.pages.addWidget(self.airknife_tab)
        
        main_layout.addWidget(self.pages)
        
        # 스타일 적용
        self.apply_styles()
    
    def create_sidebar(self, parent_layout):
        title_layout = QHBoxLayout()
        title_layout.setSpacing(0)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_layout.addSpacing(30)

        img_label = QLabel()
        img_label.setObjectName("side_title_logo")
        logo_img = QPixmap(str(UI_PATH / "logo/setting_page.png"))
        img_label.setPixmap(logo_img)
        img_label.setScaledContents(True)
        img_label.setFixedSize(16, 16)
        title_layout.addWidget(img_label)

        title_layout.addSpacing(10)

        title_label = QLabel("설정")
        title_label.setObjectName("side_title_label")
        title_layout.addWidget(title_label)

        parent_layout.addLayout(title_layout)

    nav_list = [
        "서보 제어",
        "피더 제어",
        "컨베이어 제어",
        "에어나이프 제어",
    ]
    
    def create_side_tab(self, parent_layout):
        self.btn_group = QButtonGroup()
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
        
        # 에어나이프 탭일 때에만 설명 텍스트 업데이트
        if index == 3:
            self.explain.setText("에어나이프는 플라스틱 분류 신호를 받은 후 설정된 타이밍에 에어를 분사합니다.")
        else:
            self.explain.setText("")
    
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
                border: none;
                min-height: 44px;
                max-height: 44px;
                color: #000000;
                text-align: left;
                padding-left: 30px;
                font-size: 14px;
                font-weight: normal;
            }
            
            #nav_button:hover {
                background-color: #FFFFFF;
                font-weight: medium;
            }
            
            #nav_button:checked {
                background-color: #FFFFFF;
                color: #2DB591;
                font-weight: medium;
            }
            """
        )