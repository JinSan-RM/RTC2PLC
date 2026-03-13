"""
메인 앱 실행
"""
import sys
import os
import time
# import importlib
from pathlib import Path
from datetime import datetime

import faulthandler
import atexit

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Signal, QObject
from PySide6.QtGui import QFont, QFontDatabase

from src.ui.main_window import MainWindow
from src.function.comm_manager import CommManager
from src.utils.config_util import UI_PATH, LOG_PATH
from src.utils.logger import log


_LOG_FILE = None
_LOG_PATH = ""

def cleanup_empty_log():
    """로그 파일 내용이 비었을 경우 제거"""
    global _LOG_FILE
    if _LOG_FILE:
        _LOG_FILE.flush()
        _LOG_FILE.close()

        if os.path.exists(_LOG_PATH) and os.path.getsize(_LOG_PATH) == 0:
            os.remove(_LOG_PATH)

def enable_crash_handler():
    """크래시 로그 생성"""
    global _LOG_FILE, _LOG_PATH
    try:
        log_dir = str(LOG_PATH)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        today = datetime.now().strftime("%y%m%d(%a)_%H%M%S")
        _LOG_PATH = os.path.join(log_dir, f"\\crash_log_{today}.txt")

        _LOG_FILE = open(_LOG_PATH, 'w', encoding='utf-8')
        faulthandler.enable(file=_LOG_FILE)
        atexit.register(cleanup_empty_log)
    except Exception as e:
        log(f"[ERROR] crash handler setup failed: {e}")


class ReloadSignal(QObject):
    """파일 변화 감지 시그널"""
    triggered: Signal = Signal(str)


class UpdateHandler(FileSystemEventHandler):
    """파일 변화 감지 핸들러"""
    def __init__(self, signal: ReloadSignal):
        super().__init__()
        self.signal = signal
        self.last_time = 0

    def _path_to_module_name(self, src_path: bytes | str):
        if isinstance(src_path, bytes):
            src_path = src_path.decode("utf-8")

        root_path = Path(__file__).resolve().parent
        file_path = Path(src_path).resolve()

        try:
            relative_path = file_path.relative_to(root_path)
        except ValueError as e:
            print(f"ValueError: {e}")
            return None

        module_parts = relative_path.with_suffix('').parts

        return ".".join(module_parts)

    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            cur_time = time.time()
            if cur_time - self.last_time < 0.5:
                return

            print(f"[{event.src_path}] is changed")
            module_name = self._path_to_module_name(event.src_path)
            print(f"modulename: {module_name}")
            self.signal.triggered.emit(module_name)

            self.last_time = cur_time


class App():
    """메인 앱 클래스"""
    is_reload = False

    def __init__(self):
        self.qt_app = QApplication(sys.argv)

        font_files = [
            "fonts/Poppins-Bold.ttf",
            "fonts/Poppins-Medium.ttf",
            "fonts/Poppins-Regular.ttf",
            "fonts/Poppins-semiBold.ttf",
            "fonts/Pretendard-Bold.otf",
            "fonts/Pretendard-Medium.otf",
            "fonts/Pretendard-Regular.otf",
            "fonts/Pretendard-semiBold.otf",
        ]

        for _path in font_files:
            font_path = str(UI_PATH / _path)
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id == -1:
                log(f"[WARNING] font load failed: {font_path}")
            else:
                font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
                log(f"[INFO] font load success: {font_family}")

        # 글로벌 폰트 설정
        font = QFont("Poppins")
        font.setLetterSpacing(QFont.PercentageSpacing, 98)
        self.qt_app.setFont(font)

        self.ui = MainWindow(self)
        self.comm_manager = CommManager(self)
        self.comm_manager.start()

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_periodic_update)
        self.update_timer.start(100)

    @property
    def camera_manager(self):
        """UI의 monitoring_page를 camera_manager로 참조"""
        if self.ui.pages.monitoring_page:
            return self.ui.pages.monitoring_page
        return None

    def on_periodic_update(self):
        """주기적 업데이트"""
        self.ui.update_time()

    def on_btn_clicked(self, pixel_format):
        """픽셀 형식 버튼 클릭"""
        self.comm_manager.change_pixel_format(pixel_format)

    def on_blend_btn_clicked(self, onoff):
        """블렌드 버튼 클릭"""
        self.comm_manager.set_visualization_blend(onoff)

    def on_pixel_line_data(self, info):
        """데이터를 UI로 전달 (메인 스레드에서 처리)"""
        self.ui.signals.hypercam_updated.emit(info)

    def on_obj_detected(self, info):
        """제품 감지 시 호출"""
        self.ui.img_data.overlay_info.append(info)

    def reload_ui(self, module_name: str):
        """UI 리로드"""
        # if module_name is None:
        #     return

        # log("UI reload start")

        # self.is_reload = True

        # self.update_timer.stop()
        # self.update_timer.timeout.disconnect()

        # if self.camera_manager:
        #     self.camera_manager.on_stop_all()

        # if self.ui:
        #     self.ui.close()
        #     self.ui.deleteLater()
        #     self.ui = None

        # to_delete = [
        #     name for name in sys.modules \
        #         if name.startswith("src") and not name.startswith("src.utils.logger")
        # ]
        # for name in to_delete:
        #     del sys.modules[name]
        #     log(f"cache cleared: {name}")

        # # 상위 모듈들 리로드
        # ui_module = importlib.import_module("src.ui.main_window")
        # importlib.import_module("src.utils.config_util")

        # self.ui: MainWindow = ui_module.MainWindow(self)

        # self.update_timer.timeout.connect(self.on_periodic_update)
        # self.update_timer.start(100)

        # self.ui.show()
        # self.ui.activateWindow()

        # self.is_reload = False

        # log("UI reload end")
        log("PLC 제어 버전의 UI reload 기능은 추후 추가")

    def run(self):
        """애플리케이션 실행"""
        self.ui.show()
        return self.qt_app.exec()

    def quit(self):
        """애플리케이션 종료"""
        self.comm_manager.quit()
        self.comm_manager.join(timeout=5)
        if self.comm_manager.is_alive():
            log("comm manager thread did not terminate properly")

        self.update_timer.stop()


if __name__ == '__main__':
    # 시스템 레벨의 에러 발생 시 파일에 로그 남김
    enable_crash_handler()

    app = App()

    # 파일 갱신 체크 및 리로드
    sig = ReloadSignal()
    sig.triggered.connect(app.reload_ui)

    handler = UpdateHandler(sig)
    observer = Observer()
    observer.schedule(
        handler,
        path=str(Path(__file__).parent.absolute()), recursive=True
    )
    observer.start()

    exit_code = app.run()

    observer.stop()
    observer.join()

    sys.exit(exit_code)
