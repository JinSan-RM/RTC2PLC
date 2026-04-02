"""
UI 메인
"""
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QFrame, QTabBar,
)
from PySide6.QtCore import Qt, QObject, QDateTime, QTimer, Signal
from PySide6.QtGui import QPixmap

from src.ui.page.home_page import HomePage
from src.ui.page.monitoring_page import MonitoringPage
from src.ui.page.setting_page import SettingsPage
from src.ui.page.logs_page import LogsPage
from src.ui.pip_window import PiPManager
from src.utils.config_util import UI_PATH
from src.utils.logger import Logger, log

# import inspect
# import platform


@dataclass
class Pages:
    """페이지 모음"""
    home_page: HomePage = None
    monitoring_page: MonitoringPage = None
    settings_page: SettingsPage = None
    logs_page: LogsPage = None


@dataclass
class ChildrenWidget:
    """업데이트 필요한 자식 위젯 모음"""
    main_tab: QTabBar = None
    main_stack: QStackedWidget = None
    side_stack: QStackedWidget = None
    contents_title: QLabel = None
    contents_explain: QLabel = None
    status_label: QLabel = None
    time_label: QLabel = None


class UpdateSignals(QObject):
    """UI 업데이트 시그널 모음"""
    log_updated: Signal = Signal(str, str)
    servo_updated: Signal = Signal(int, object)
    inverter_updated: Signal = Signal(object)
    airknife_updated: Signal = Signal(int)
    input_updated: Signal = Signal(int)
    output_updated: Signal = Signal(int)


class MainWindow(QMainWindow):
    """UI 메인"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.pages = Pages()
        self.children_widget = ChildrenWidget()

        self._init_ui()

        # UI 업데이트 함수와 연결
        self.signals = UpdateSignals()

        self.signals.log_updated.connect(self.pages.logs_page.add_log)
        self.signals.servo_updated.connect(self.pages.settings_page.servo_tab.update_values)
        self.signals.inverter_updated.connect(self.pages.settings_page.feeder_tab.update_values)
        self.signals.inverter_updated.connect(self.pages.settings_page.conveyor_tab.update_values)
        self.signals.airknife_updated.connect(self.pages.settings_page.airknife_tab.on_airknife_off)
        self.signals.input_updated.connect(self.pages.logs_page.io_tab.update_input_status)
        self.signals.output_updated.connect(self.pages.logs_page.io_tab.update_output_status)

        Logger.set_callback(self.add_log_to_ui)
        # 시간 업데이트 타이머
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(1000)  # 1초마다

        # PiP 매니저는 반드시 MonitoringPage 생성 이후 초기화해야 함
        # : 초기 카메라 선택 시 monitoring_page.rgb_cameras 참조가 필요하니까
        self.pip_manager = PiPManager(self)
        if self.pages.monitoring_page.rgb_cameras:
            # 기본값: 첫 번째 RGB 카메라를 PiP 소스로 연결
            self.pip_manager.select_camera(self.pages.monitoring_page.rgb_cameras[0])

    def _init_ui(self):
        self.setWindowTitle("위드위 플라스틱 선별 시스템")
        self.setGeometry(0, 0, 1920, 1080)
        self.setFixedSize(1920,1080)

        # 중앙 위젯
        central_widget = QWidget()
        central_widget.setFixedSize(1920, 1080)
        self.setCentralWidget(central_widget)

        # 메인 레이아웃
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 헤더 타이틀
        self._create_header_title(main_layout)

        # 헤더 탭
        self._create_header_tab(main_layout)

        # 컨텐츠 영역
        self._create_contents_area(main_layout)

        # 스타일 적용
        self.apply_styles()

        # 홈 페이지로 시작
        self.change_page(0)

    def _create_header_title(self, parent_layout):
        """헤더 타이틀"""
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(85)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(30, 0, 0, 0)

        # 로고
        logo_path = str(UI_PATH / "logo/logo_withwe.png")
        logo_label = QLabel()
        logo_label.setObjectName("header_logo")
        logo_img = QPixmap(logo_path)
        logo_label.setPixmap(logo_img)
        logo_label.setScaledContents(True)
        logo_label.setFixedSize(150, 28)
        layout.addWidget(logo_label)
        layout.addSpacing(19)

        # 구분선
        separator_line = QFrame()
        separator_line.setFrameShape(QFrame.VLine)
        separator_line.setFixedSize(1, 20)
        separator_line.setStyleSheet(
            """
            border: 1px solid #DDDDDD;
            """
        )
        layout.addWidget(separator_line)
        layout.addSpacing(17)

        # 앱 제목
        main_title = QLabel("위드위 장비 관리자 페이지")
        main_title.setObjectName("header_title")
        layout.addWidget(main_title)

        app_ver = QLabel("ver 0.1")
        app_ver.setObjectName("app_version")
        layout.addWidget(app_ver)

        layout.addStretch()

        parent_layout.addWidget(header)

    def _create_header_tab(self, parent_layout):
        """헤더 탭"""
        tab_box = QFrame()
        tab_box.setObjectName("header_tab_box")
        tab_layout = QHBoxLayout(tab_box)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addSpacing(30)

        main_tab = self.children_widget.main_tab = QTabBar()
        main_tab.setObjectName("header_tab")
        main_tab.setExpanding(False)
        main_tab.setDrawBase(False)

        main_tab.addTab("대시보드")
        main_tab.addTab("모니터링")
        main_tab.addTab("설정")
        main_tab.addTab("로그")

        tab_layout.addWidget(main_tab)
        tab_layout.addStretch(1)
        parent_layout.addWidget(tab_box)

        main_tab.currentChanged.connect(self.change_page)

    def _create_contents_area(self, parent_layout):
        """컨텐츠 영역"""
        contents_area = QFrame()
        contents_area.setObjectName("contents_area")

        contents_layout = QHBoxLayout(contents_area)
        contents_layout.setContentsMargins(0, 0, 0, 0)

        # 좌측 사이드바
        self._create_side_bar(contents_layout)

        # 컨텐츠 영역
        self._create_contents_main(contents_layout)

        # 2개의 QStackedWidget에 내용 채우기
        home_page = self.pages.home_page = HomePage(self.app)
        monitoring_page = self.pages.monitoring_page = MonitoringPage(self.app)
        settings_page = self.pages.settings_page = SettingsPage(
            self.app,
            self.children_widget.contents_title,
            self.children_widget.contents_explain
        )
        logs_page = self.pages.logs_page = LogsPage(
            self.app,
            self.children_widget.contents_title
        )

        self.children_widget.side_stack.addWidget(home_page.side_widget)
        self.children_widget.side_stack.addWidget(monitoring_page.side_widget)
        self.children_widget.side_stack.addWidget(settings_page.side_widget)
        self.children_widget.side_stack.addWidget(logs_page.side_widget)

        self.children_widget.main_stack.addWidget(home_page.main_widget)
        self.children_widget.main_stack.addWidget(monitoring_page.main_widget)
        self.children_widget.main_stack.addWidget(settings_page.main_widget)
        self.children_widget.main_stack.addWidget(logs_page.main_widget)

        parent_layout.addWidget(contents_area)

    def _create_side_bar(self, parent_layout):
        """좌측 사이드바"""
        side_bar = QFrame()
        side_bar.setObjectName("side_bar")
        side_bar.setFixedWidth(238)

        side_layout = QVBoxLayout(side_bar)
        side_layout.setSpacing(0)
        side_layout.setContentsMargins(0, 0, 0, 0)

        side_layout.addSpacing(40)

        side_stack = self.children_widget.side_stack = QStackedWidget()
        side_stack.setStyleSheet("background: transparent;")
        side_layout.addWidget(side_stack)

        # 긴급정지 버튼
        emergency_btn = QPushButton("긴급 정지")
        emergency_btn.setObjectName("emergency_button")
        emergency_btn.setFixedSize(177, 80)
        emergency_btn.clicked.connect(self.emergency_stop)
        side_layout.addWidget(emergency_btn)

        side_layout.addSpacing(40)

        parent_layout.addWidget(side_bar)

    def _create_contents_main(self, parent_layout):
        """메인 컨텐츠 영역"""
        main_layout = QVBoxLayout()

        main_layout.setContentsMargins(30, 30, 30, 0)
        main_layout.setSpacing(0)

        header_box = QFrame()
        header_box.setObjectName("contents_header_box")
        contents_header = QHBoxLayout(header_box)
        contents_header.setContentsMargins(0, 0, 0, 0)

        # 컨텐츠 제목
        contents_title = self.children_widget.contents_title = QLabel("홈 대시보드")
        contents_title.setObjectName("contents_title")
        contents_title.setFixedHeight(50)
        contents_header.addWidget(contents_title)

        contents_header.addSpacing(10)

        contents_explain = self.children_widget.contents_explain = QLabel()
        contents_explain.setStyleSheet(
            """
            color: #4B4B4B;
            font-size: 14px;
            font-weight: normal;
            """
        )

        contents_header.addWidget(contents_explain)

        contents_header.addStretch()

        # 우측 상태 및 시각 표시
        status_layout = QHBoxLayout()

        status_label = self.children_widget.status_label = QLabel("대기중")
        status_label.setObjectName("status_label")
        status_label.setFixedSize(82, 28)
        status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(status_label)

        status_layout.addSpacing(10)

        time_label = self.children_widget.time_label = QLabel()
        time_label.setObjectName("time_label")
        self.update_time()
        status_layout.addWidget(time_label)

        contents_header.addLayout(status_layout)

        main_layout.addWidget(header_box)

        main_stack = self.children_widget.main_stack = QStackedWidget()
        main_stack.setStyleSheet("background: transparent;")
        main_layout.addWidget(main_stack)

        parent_layout.addLayout(main_layout)

    def change_page(self, index):
        """상단 탭 페이지 전환"""
        self.children_widget.side_stack.setCurrentIndex(index)
        self.children_widget.main_stack.setCurrentIndex(index)
        self.children_widget.contents_explain.setText("")

        # 페이지 전환이 PiP 표시 정책의 단일 진입점.
        # monitoring(index=1)에서는 항상 숨김, 그 외 페이지에서는 enabled 상태에 따라 표시.
        # pip_manager는 _init_ui 이후 생성되므로 초기 호출 타이밍 보호
        if hasattr(self, 'pip_manager'):
            self.pip_manager.on_page_changed(index)

        match index:
            case 0:
                self.children_widget.contents_title.setText("홈 대시보드")
            case 1:
                self.children_widget.contents_title.setText("실시간 모니터링")
            case 2:
                self.pages.settings_page.btn_group.button(0).setChecked(True)
                self.pages.settings_page.show_page(0)
            case 3:
                self.pages.logs_page.btn_group.button(0).setChecked(True)
                self.pages.logs_page.show_page(0)

    def update_time(self):
        """시간 업데이트"""
        current_time = QDateTime.currentDateTime().toString("yyyy/MM/dd hh:mm:ss")
        self.children_widget.time_label.setText(current_time)

    def update_status(self, status_text, color="green"):
        """상태 업데이트"""
        icons = {
            "green": "🟢",
            "yellow": "🟡",
            "red": "🔴",
            "gray": "⚫"
        }
        icon = icons.get(color, "⚫")
        self.children_widget.status_label.setText(f"{icon} {status_text}")

    def emergency_stop(self):
        """긴급 정지"""
        log("긴급정지")
        self.update_status("긴급정지", "red")

    def closeEvent(self, a0): # pylint: disable=invalid-name, disable=unused-argument
        """UI 닫는 이벤트 발생 시 호출됨"""
        if self.app.is_reload:
            # 리로드 시 앱 종료 방지
            return
        if hasattr(self, 'pip_manager'):
            # PiP signal 연결 해제 + 창 종료를 먼저 수행해 정리 순서 보장
            self.pip_manager.cleanup()
        self.signals.log_updated.disconnect()
        self.signals.servo_updated.disconnect()
        self.signals.inverter_updated.disconnect()
        self.signals.airknife_updated.disconnect()
        self.signals.input_updated.disconnect()
        self.signals.output_updated.disconnect()

        self.app.quit()
        # return super().closeEvent(a0)

    def apply_styles(self):
        """스타일시트 적용"""
        self.setStyleSheet(
            """
            /* 메인 윈도우 */
            QMainWindow {
                background-color: #FFFFFF;
            }
            
            /* 헤더 */
            #header {
                background-color: #2D3039;
                min-height: 85px;
                border: none;
            }

            /* 로고 */
            #header_logo {
                background: transparent;
                border: none;
            }

            /* 앱 제목 */
            #header_title {
                color: #FFFFFF;
                font-family: 'Pretendard';
                font-size: 20px;
                font-weight: bold;
                background: transparent;
                min-width: 239px;
                min-height: 24px;
            }

            /* 앱 버전 */
            #app_version {
                color: #FFFFFF;
                font-size: 10px;
                font-weight: medium;
                background: transparent;
                min-width: 18px;
                min-height: 15px;
                margin-top: 10px;
            }
            
            /* 헤더 탭 */
            #header_tab_box {
                background: transparent;
                border-bottom: 1px solid #E2E2E2;
            }

            QTabBar {
                background-color: transparent;
                border: none;
                alignment: left;
            }

            QTabBar::tab {
                background: transparent;
                color: #787878;
                width: 100px;
                height: 60px;
                font-size: 14px;
                font-weight: normal;
                border: none;
                border-bottom: 2px solid transparent;
            }

            QTabBar::tab:hover {
                color: #000000;
            }

            QTabBar::tab:selected {
                color: #000000;
                border-bottom: 2px solid #2DB591;
            }

            /* 사이드바 */
            #side_bar {
                background-color: #F3F4F6;
                border: none;
                border-right: 1px solid #E2E2E2;
                width: 238px;
            }

            #emergency_button {
                background-color: #FF2427;
                color: #FFFFFF;
                min-width: 177px;
                min-height: 80px;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
                margin-left: 30px;
                margin-right: 30px;
            }

            #emergency_button:hover {
                background-color: #FF6467;
            }

            /* 컨텐츠 영역 헤더 */
            #contents_header_box {
                background: transparent;
                border-bottom: 2px solid #E2E2E2;;
            }

            #contents_title {
                color: #000000;
                background: transparent;
                font-size: 18px;
                font-weight: medium;
                border-bottom: 2px solid #2DB591;
            }

            #status_label {
                color: #A4A4A4;
                font-family: 'pretendard';
                font-size: 12px;
                font-weight: medium;
                background-color: #F5F4F8;
                border: 1px solid #A4A4A4;
                border-radius: 4px;
            }
            
            #time_label {
                color: #A4A4A4;
                font-family: 'Pretendard';
                font-size: 12px;
                font-weight: normal;
                background: transparent
            }
            """
        )

    def add_log_to_ui(self, log_msg, level):
        """UI에 로그 추가"""
        if hasattr(self, 'logs_page'):
            # self.pages.logs_page.add_log(log_msg)
            self.signals.log_updated.emit(log_msg, level)

# if __name__ == "__main__":
#     import sys
#     from PySide6.QtWidgets import QApplication

#     class DummyApp:
#         def on_log(self, msg):
#             print(msg)

#     app = QApplication(sys.argv)
#     dummy = DummyApp()
#     main_window = MainWindow(dummy)
#     main_window.show()
#     sys.exit(app.exec_())
