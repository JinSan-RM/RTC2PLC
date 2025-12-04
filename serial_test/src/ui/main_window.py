from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QFrame, QTextEdit, 
)
from PyQt5.QtCore import Qt, QDateTime, QTimer
from PyQt5.QtGui import QFont

from src.ui.page.home_page import HomePage
from src.ui.page.monitoring_page import MonitoringPage
from src.ui.page.setting_page import SettingsPage
from src.ui.page.logs_page import LogsPage

import inspect
import platform

class MainWindow(QMainWindow):
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.init_ui()
        
        # 시간 업데이트 타이머
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(1000)  # 1초마다
        
    def init_ui(self):
        self.setWindowTitle("위드위 플라스틱 선별 시스템")
        self.setGeometry(0, 0, 1920, 1080)
        
        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 메인 레이아웃
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 좌측 네비게이션
        self.nav_bar = self.create_nav_bar()
        main_layout.addWidget(self.nav_bar)
        
        # 우측 컨텐츠
        content_layout = QVBoxLayout()
        
        # 상단 헤더
        self.header = self.create_header()
        content_layout.addWidget(self.header)
        
        # 페이지 스택
        self.pages = QStackedWidget()
        self.init_pages()
        content_layout.addWidget(self.pages)
        
        main_layout.addLayout(content_layout, 1)
        
        # 스타일 적용
        self.apply_styles()
        
        # 홈 페이지로 시작
        self.show_page(0)
        
    def create_nav_bar(self):
        """좌측 네비게이션 바"""
        nav_widget = QFrame()
        nav_widget.setObjectName("nav_bar")
        nav_widget.setFixedWidth(200)
        
        layout = QVBoxLayout(nav_widget)
        layout.setSpacing(5)
        layout.setContentsMargins(10, 20, 10, 10)
        
        # 로고
        logo = QLabel("위드위")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedHeight(60)
        
        layout.addWidget(logo)
        layout.addSpacing(20)
        
        # 네비게이션 버튼들
        nav_buttons = [
            ("홈", 0),
            ("모니터링", 1),
            ("설정", 2),
            ("로그", 3),
        ]
        
        self.nav_btn_list = []
        for text, page_idx in nav_buttons:
            btn = QPushButton(text)
            btn.setObjectName("nav_button")
            btn.setFixedHeight(60)
            btn.clicked.connect(lambda checked, idx=page_idx: self.show_page(idx))
            
            layout.addWidget(btn)
            self.nav_btn_list.append(btn)
            
        layout.addStretch()
        
        # 긴급정지 버튼
        emergency_btn = QPushButton("긴급정지")
        emergency_btn.setObjectName("emergency_button")
        emergency_btn.setFixedHeight(80)
        emergency_btn.clicked.connect(self.emergency_stop)
        
        layout.addWidget(emergency_btn)
        
        return nav_widget
    
    def create_header(self):
        """상단 헤더"""
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(70)
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(30, 10, 30, 10)
        
        # 페이지 제목
        self.page_title = QLabel("홈 대시보드")
        self.page_title.setObjectName("page_title")
        layout.addWidget(self.page_title)
        
        layout.addStretch()
        
        # 시스템 상태
        self.status_label = QLabel("⚫ 대기중")
        self.status_label.setObjectName("status_label")
        layout.addWidget(self.status_label)
        
        # 현재 시간
        self.time_label = QLabel()
        self.time_label.setObjectName("time_label")
        self.update_time()
        layout.addWidget(self.time_label)
        
        return header

    def init_pages(self):
        """각 페이지 초기화"""
        self.home_page = HomePage(self.app)
        self.monitoring_page = MonitoringPage(self.app)
        self.settings_page = SettingsPage(self.app)
        self.logs_page = LogsPage(self.app)
        
        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.monitoring_page)
        self.pages.addWidget(self.settings_page)
        self.pages.addWidget(self.logs_page)
        
    def show_page(self, index):
        """페이지 전환"""
        self.pages.setCurrentIndex(index)
        
        # 페이지 제목 업데이트
        titles = ["홈 대시보드", "실시간 모니터링", "시스템 설정", "로그"]
        if index < len(titles):
            self.page_title.setText(titles[index])
        
        # 네비게이션 버튼 활성화
        for i, btn in enumerate(self.nav_btn_list):
            if i == index:
                btn.setProperty("active", True)
            else:
                btn.setProperty("active", False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        
    def update_time(self):
        """시간 업데이트"""
        current_time = QDateTime.currentDateTime().toString("yyyy/MM/dd hh:mm:ss")
        self.time_label.setText(current_time)
    
    def update_status(self, status_text, color="green"):
        """상태 업데이트"""
        icons = {
            "green": "🟢",
            "yellow": "🟡",
            "red": "🔴",
            "gray": "⚫"
        }
        icon = icons.get(color, "⚫")
        self.status_label.setText(f"{icon} {status_text}")
        
    def emergency_stop(self):
        """긴급 정지"""
        print("긴급정지")
        self.app.on_log("긴급정지 버튼 눌림")
        self.update_status("긴급정지", "red")
    
    def add_log(self, message):
        """로그 추가"""
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")
        print(f"[{timestamp}] {message}")
        # TODO: 로그 페이지에 추가
        # if hasattr(self, 'logs_page'):
        #     self.logs_page.add_log(message)
    
    def closeEvent(self, a0):
        self.app.quit()
        # return super().closeEvent(a0)
        
    def apply_styles(self):
        """스타일시트 적용"""
        self.setStyleSheet("""
            /* 메인 윈도우 */
            QMainWindow {
                background-color: #1e1e1e;
            }
            
            /* 네비게이션 바 */
            #nav_bar {
                background-color: #0d1117;
                border-right: 3px solid #30363d;
            }
            
            /* 로고 */
            #logo {
                color: #58a6ff;
                font-size: 28px;
                font-weight: bold;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0d1117, stop:1 #161b22);
                border: 2px solid #30363d;
                border-radius: 10px;
                padding: 10px;
            }
            
            /* 네비게이션 버튼 */
            #nav_button {
                background-color: #161b22;
                color: #c9d1d9;
                border: 2px solid #30363d;
                border-radius: 8px;
                text-align: left;
                padding-left: 20px;
                font-size: 15px;
                font-weight: bold;
            }
            
            #nav_button:hover {
                background-color: #21262d;
                border-color: #58a6ff;
            }
            
            #nav_button[active="true"] {
                background-color: #58a6ff;
                color: #0d1117;
                border-color: #58a6ff;
            }
            
            /* 긴급정지 버튼 */
            #emergency_button {
                background-color: #da3633;
                color: white;
                border: 3px solid #f85149;
                border-radius: 12px;
                font-size: 18px;
                font-weight: bold;
            }
            
            #emergency_button:hover {
                background-color: #f85149;
            }
            
            #emergency_button:pressed {
                background-color: #b62324;
            }
            
            /* 헤더 */
            #header {
                background-color: #161b22;
                border-bottom: 3px solid #30363d;
            }
            
            #page_title {
                color: #58a6ff;
                font-size: 24px;
                font-weight: bold;
            }
            
            #status_label {
                color: #c9d1d9;
                font-size: 15px;
                padding: 8px 20px;
                background-color: #0d1117;
                border: 2px solid #30363d;
                border-radius: 8px;
            }
            
            #time_label {
                color: #8b949e;
                font-size: 14px;
                padding: 8px 20px;
            }
        """)
    
    def log(self, message):
        """로그 메시지 추가"""
        # 호출한 위치 정보 가져오기
        frame = inspect.currentframe().f_back.f_back
        os_name = platform.system()
        if os_name == "Windows":
            sep = '\\'
        else:
            sep = '/'
        filename = frame.f_code.co_filename.split(sep)[-1]  # 파일명만
        lineno = frame.f_lineno
        funcname = frame.f_code.co_name
        
        # 시간
        timestamp = QDateTime.currentDateTime().toString("HH:mm:ss.zzz")
        
        # 포맷팅
        log_msg = f"[{timestamp}] [{filename}:{lineno} {funcname}()] {message}"
        print(log_msg)
        
        if hasattr(self, 'logs_page'):
            self.logs_page.add_log(log_msg)

if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    class DummyApp:
        def on_log(self, msg):
            print(msg)

    app = QApplication(sys.argv)
    dummy = DummyApp()
    main_window = MainWindow(dummy)
    main_window.show()
    sys.exit(app.exec_())