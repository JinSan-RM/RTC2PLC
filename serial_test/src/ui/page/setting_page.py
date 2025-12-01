"""
설정 페이지 - 서보, 피더, 컨베이어, 에어나이프 제어
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget
)

from src.ui.page.settings.servo_tab import ServoTab
from src.ui.page.settings.feeder_tab import FeederTab
from src.ui.page.settings.conveyor_tab import ConveyorTab
from src.ui.page.settings.airknife_tab import AirKnifeTab


class SettingsPage(QWidget):
    """설정 페이지 - 메인"""
    
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
        self.tabs.setObjectName("settings_tabs")
        
        # 각 탭 추가
        self.servo_tab = ServoTab(self.app)
        self.feeder_tab = FeederTab(self.app)
        self.conveyor_tab = ConveyorTab(self.app)
        self.airknife_tab = AirKnifeTab(self.app)
        
        self.tabs.addTab(self.servo_tab, "서보 제어")
        self.tabs.addTab(self.feeder_tab, "피더 제어")
        self.tabs.addTab(self.conveyor_tab, "컨베이어 제어")
        self.tabs.addTab(self.airknife_tab, "에어나이프 제어")
        
        main_layout.addWidget(self.tabs)
        
        # 스타일 적용
        self.apply_styles()
    
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