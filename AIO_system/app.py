"""
메인 앱 실행
"""
import sys
import json
import os
import threading
import time
import importlib
from pathlib import Path
from datetime import datetime, timedelta
from itertools import cycle
from dataclasses import dataclass

import faulthandler
import atexit

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Signal, QObject
from PySide6.QtGui import QFont, QFontDatabase

from src.ui.main_window import MainWindow
from src.function.sharedmemory_manager import SharedMemoryManager
from src.function.modbus_manager import ModbusManager
from src.function.ethercat_manager import EtherCATManager
from src.utils.config_util import (
    CONFIG_PATH, APP_CONFIG, FEEDER_TIME_1, FEEDER_TIME_2, UI_PATH, LOG_PATH
)
from src.utils.logger import log


_LOG_FILE = None
_LOG_PATH = ""
def cleanup_empty_log():
    """
    로그 파일 내용이 비었을 경우 제거
    """
    global _LOG_FILE
    if _LOG_FILE:
        _LOG_FILE.flush()
        _LOG_FILE.close()

        if os.path.exists(_LOG_PATH) and os.path.getsize(_LOG_PATH) == 0:
            os.remove(_LOG_PATH)

def enable_crash_handler():
    """
    크래시 로그 생성
    """
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
    """
    파일 변화 감지 시그널
    """
    triggered: Signal = Signal(str)


class UpdateHandler(FileSystemEventHandler):
    """
    파일 변화 감지 핸들러
    """
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
    """
    메인 앱 클래스
    """
    is_reload = False

    def __init__(self):
        # 우선적으로 설정값부터 읽어옴
        self.config = {}
        self._load_config()

        # 자동 운전 관련
        self.auto_mode = False
        self.auto_run = False
        self._auto_thread = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._feeder_output_time = datetime.now()
        self._current_size = 0

        # 제품 배출 순서 제어
        self.use_air_sequence = False
        self.set_air_sequence_index()

        self.shm_name = "COMM_SHM"
        self.shm_manager = SharedMemoryManager(mem_name=self.shm_name, create=True)

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
        self.modbus_manager = ModbusManager(self)
        self.modbus_manager.connect()

        self.ethercat_manager = EtherCATManager(self)
        self.ethercat_manager.connect()

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_periodic_update)
        self.update_timer.start(100)
        
    @property
    def camera_manger(self):
        """UI의 monitoring_page를 camera_manager로 참조"""
        if hasattr(self.ui, 'monitoring_page'):
            return self.ui.monitoring_page
        return None

    def on_periodic_update(self):
        """주기적 업데이트"""
        self.ui.update_time()

    def on_update_monitor(self, _list):
        if hasattr(self.ui, 'monitoring_page'):
            self.ui.monitoring_page.update_values(_list)

    def _auto_loop(self):
        if not self.auto_mode or not self.auto_run:
            return

        while not self._stop_event.is_set():
            # 피더 미배출 체크
            cur_size = self._current_size
            check_sec = FEEDER_TIME_1 + ((cur_size // 5) * FEEDER_TIME_2)
            current_time = datetime.now()
            with self._lock:
                check_time = self._feeder_output_time + timedelta(seconds=check_sec)

            if current_time > check_time:
                # 배출물 사이즈 변경
                # TODO: 제품 감지 박스 연동, 서보 위치 이동
                self._current_size = (cur_size + 1) % 6

                for i in range(2):
                    info = self.config["servo_config"][f"servo_{i}"]["position"][self._current_size]
                    self.servo_move_to_position(i, float(info[0])*(10**3), float(info[1])*(10**3))

                log(f"""
                    [INFO] feeder output size level changed 
                    {cur_size+1} to {self._current_size+1}
                    """)

                self._feeder_output_time = current_time

            time.sleep(0.033)

# region inverter control
    def on_update_inverter_status(self, _data):
        """
        피더, 컨베이어 상태 UI 업데이트
        
        :param self: Description
        :param _data: 상태 데이터
        """
        if hasattr(self.ui, 'settings_page') and self.ui.main_stack.currentIndex() == 2:
            tab_index = self.ui.settings_page.pages.currentIndex()
            if tab_index == 1 or tab_index == 2:
                self.ui.inverter_updated.emit(_data)

    def on_set_freq(self, inverter_name: str, value: float):
        """
        인버터 주파수 설정
        
        :param self: Description
        :param inverter_name: 인버터 이름
        :type inverter_name: str
        :param value: 주파수 값
        :type value: float
        """
        log(f"Setting frequency for {inverter_name} to {value} Hz")
        self.modbus_manager.set_freq(inverter_name, value)

    def on_set_acc(self, inverter_name: str, value: float):
        """
        인버터 가속 시간 설정
        
        :param self: Description
        :param inverter_name: 인버터 이름
        :type inverter_name: str
        :param value: 가속 시간 값
        :type value: float
        """
        log(f"Setting acceleration time for {inverter_name} to {value} sec")
        self.modbus_manager.set_acc(inverter_name, value)

    def on_set_dec(self, inverter_name: str, value: float):
        """
        인버터 감속 시간 설정
        
        :param self: Description
        :param inverter_name: 인버터 이름
        :type inverter_name: str
        :param value: 감속 시간 값
        :type value: float
        """
        log(f"Setting deceleration time for {inverter_name} to {value} sec")
        self.modbus_manager.set_dec(inverter_name, value)

    def motor_start(self, inverter_name: str):
        """
        인버터 운전
        
        :param self: Description
        :param inverter_name: 인버터 이름
        :type inverter_name: str
        """
        log(f"Starting motor: {inverter_name}")
        self.modbus_manager.motor_start(inverter_name)

    def motor_stop(self, inverter_name: str):
        """
        인버터 정지
        
        :param self: Description
        :param inverter_name: 인버터 이름
        :type inverter_name: str
        """
        log(f"Stopping motor: {inverter_name}")
        self.modbus_manager.motor_stop(inverter_name)

    def inverter_custom_read(self, slave_id: int, addr: int):
        """
        해당 주소의 값 읽기
        
        :param self: Description
        :param slave_id: 인버터 ID
        :type slave_id: int
        :param addr: 조회할 주소 값
        :type addr: int
        """
        self.modbus_manager.custom_read(slave_id, addr)

    def inverter_custom_write(self, slave_id: int, addr: int, value: int):
        """
        해당 주소에 값 쓰기
        
        :param self: Description
        :param slave_id: 인버터 ID
        :type slave_id: int
        :param addr: 값을 쓸 주소 값
        :type addr: int
        :param value: 쓸 값
        :type value: int
        """
        self.modbus_manager.custom_write(slave_id, addr, value)
# endregion

# region servo control
    def on_update_servo_status(self, servo_id: int, _data):
        """
        서보 상태 UI 업데이트
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        :param _data: 상태 데이터
        """
        if hasattr(self.ui, 'settings_page') and self.ui.main_stack.currentIndex() == 2:
            tab_index = self.ui.settings_page.pages.currentIndex()
            if tab_index == 0:
                self.ui.servo_updated.emit(servo_id, _data)

    def servo_on(self, servo_id: int):
        """
        서보 on
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        self.ethercat_manager.servo_onoff(servo_id, True)

    def servo_off(self, servo_id: int):
        """
        서보 off
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        self.ethercat_manager.servo_onoff(servo_id, False)

    def servo_reset(self, servo_id: int):
        """
        서보 알람 리셋
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        self.ethercat_manager.servo_reset(servo_id)

    def servo_stop(self, servo_id: int):
        """
        서보 정지
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        self.ethercat_manager.servo_halt(servo_id)

    def servo_homing(self, servo_id: int):
        """
        서보 원점 복귀
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        self.ethercat_manager.servo_homing(servo_id)

    def servo_move_to_position(self, servo_id: int, pos: float, v: float):
        """
        서보 위치 이동
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        :param pos: 이동할 좌표
        :type pos: float
        :param v: 이동 속도
        :type v: float
        """
        self.ethercat_manager.servo_move_absolute(servo_id, pos, v)

    def servo_jog_move(self, servo_id: int, v: float):
        """
        서보 조그
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        :param v: 이동 속도
        :type v: float
        """
        self.ethercat_manager.servo_move_velocity(servo_id, v)

    def servo_inch_move(self, servo_id: int, dist: float, v: float = 10000.0):
        """
        서보 인칭
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        :param dist: 인칭 거리
        :type dist: float
        :param v: 이동 속도
        :type v: float
        """
        self.ethercat_manager.servo_move_relative(servo_id, dist, v)
# endregion

# region I/O
    def on_update_input_status(self, total_input: int):
        """
        입력 모듈 상태 UI 업데이트
        
        :param self: Description
        :param total_input: 입력 모듈 bit 값
        :type total_input: int
        """
        if hasattr(self.ui, 'logs_page') and self.ui.main_stack.currentIndex() == 3:
            tab_index = self.ui.logs_page.pages.currentIndex()
            if tab_index == 0:
                self.ui.input_updated.emit(total_input)

    def on_update_output_status(self, total_output: int):
        """
        출력 모듈 상태 UI 업데이트
        
        :param self: Description
        :param total_output: 출력 모듈 bit 값
        :type total_output: int
        """
        if hasattr(self.ui, 'logs_page') and self.ui.main_stack.currentIndex() == 3:
            tab_index = self.ui.logs_page.pages.currentIndex()
            if tab_index == 0:
                self.ui.output_updated.emit(total_output)

    def airknife_on(self, air_num: int, on_term: int):
        """
        에어나이프 켜기
        
        :param self: Description
        :param air_num: 에어나이프 번호(1~3)
        :type air_num: int
        :param on_term: Description
        :type on_term: int
        """
        self.ethercat_manager.airknife_on(air_num, on_term)

    def on_airknife_off(self, air_num: int):
        """
        에어나이프 정지 시 UI 업데이트
        
        :param self: Description
        :param air_num: Description
        :type air_num: int
        """
        if hasattr(self.ui, 'settings_page'):
            self.ui.airknife_updated.emit(air_num)

    def set_auto_mode(self, is_on: bool):
        """
        자동/수동 모드 세팅
        
        :param self: Description
        :param is_on: Description
        :type is_on: bool
        """
        self.auto_mode = is_on
        mode = "auto" if is_on else "manual"
        log(f"[INFO] set {mode} mode")

    def auto_mode_run(self):
        """
        자동 모드 운전 시작
        
        :param self: Description
        """
        self.auto_run = True

        # 피더, 컨베이어 동작 함수
        self.modbus_manager.on_automode_start()

        # 카메라 동작 함수
        self.camera_manager.on_start_all()

        self._auto_thread = threading.Thread(target=self._auto_loop)
        self._auto_thread.start()
        log("[INFO] auto mode run")

    def auto_mode_stop(self):
        """
        자동 모드 운전 정지
        
        :param self: Description
        """
        self._stop_event.set()

        if hasattr(self, '_auto_thread') and self._auto_thread.is_alive():
            log("[INFO] auto thread to terminate...")
            self._auto_thread.join(timeout=5)
            if self._auto_thread.is_alive():
                log("[WARNING] auto thread did not terminate properly")
        # 피더, 컨베이어 멈춤 함수
        self.modbus_manager.on_automode_stop()

        # 카메라 멈춤 함수
        self.camera_manager.on_stop_all()

        self.auto_run = False

    def reset_alarm(self):
        """
        알람 리셋
        
        :param self: Description
        """
        log("[INFO] alarm reset")
        # TODO: 알람 리셋

    def emergency_stop(self):
        """
        비상 정지
        
        :param self: Description
        """
        log("[WARNING] !!!EMERGENCY STOP BUTTON PRESSED!!!")
        # TODO: 비상정지 기능 연결

    def all_servo_homing(self):
        """
        서보 원점 복귀
        
        :param self: Description
        """
        log("[INFO] all servo homing")

    def feeder_output(self):
        """
        피더 제품 출력 감지 시 호출
        
        :param self: Description
        """
        if self.auto_mode and self.auto_run:
            with self._lock:
                self._feeder_output_time = datetime.now()
            log("[INFO] feeder output checked")

    def hopper_empty(self):
        """
        호퍼 비었을 때 호출
        
        :param self: Description
        """
        log("[INFO] hopper empty")
        # TODO: 호퍼 문닫기

    def hopper_full(self):
        """
        호퍼 가득 찼을 때 호출
        
        :param self: Description
        """
        log("[INFO] hopper full")
        # TODO: 호퍼 문열기
# endregion

    def on_auto_start(self):
        """
        자동 모드 시작
        
        :param self: Description
        """
        log("auto mode started")
        self.set_auto_mode(True)
        self.auto_mode_run()

    def on_auto_stop(self):
        """
        자동 모드 종료
        
        :param self: Description
        """
        log("auto mode stopped")
        self.auto_mode_stop()
        self.set_auto_mode(False)

    def _load_config(self):
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)

                log("[INFO] config loaded")
                return
        except FileNotFoundError as fnfe:
            log(f"[ERROR] can't find config file: {fnfe}")
        except json.JSONDecodeError as jde:
            log(f"[ERROR] wrong json format: {jde}")
        except Exception as e:
            log(f"[ERROR] config file load failed: {e}")

        self.config = APP_CONFIG.copy()
        self._save_config()

    def _save_config(self):
        try:
            dir_name = os.path.dirname(CONFIG_PATH)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name)

            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)

            log("[INFO] config saved")
        except IOError as ioe:
            log(f"[ERROR] config file io error: {ioe}")
        except Exception as e:
            log(f"[ERROR] config file save failed: {e}")

    def set_air_sequence_index(self):
        """
        제품 분류 순서 지정
        
        :param self: Description
        """
        _saved_seq = self.config.get("air_sequence", [])
        if _saved_seq:
            self.air_index_iter = cycle(_saved_seq)
        else:
            self.air_index_iter = None

    def reload_ui(self, module_name: str):
        """
        UI 리로드
        
        :param self: Description
        :param module_name: Description
        :type module_name: str
        """
        if module_name is None:
            return

        log("UI reload start")

        self.is_reload = True

        self.update_timer.stop()
        self.update_timer.timeout.disconnect()

        if self.ui:
            self.ui.close()
            self.ui.deleteLater()
            self.ui = None

        if self.modbus_manager:
            self.modbus_manager.disconnect()
            self.modbus_manager = None

        if self.ethercat_manager:
            self.ethercat_manager.disconnect()
            self.ethercat_manager = None

        if self.shm_manager:
            self.shm_manager.close()
            self.shm_manager = None

        to_delete = [
            name for name in sys.modules \
                if name.startswith("src") and not name.startswith("src.utils.logger")
        ]
        for name in to_delete:
            del sys.modules[name]
            log(f"cache cleared: {name}")


        shm_module = importlib.import_module("src.function.sharedmemory_manager")
        ui_module = importlib.import_module("src.ui.main_window")
        modbus_module = importlib.import_module("src.function.modbus_manager")
        ethercat_module = importlib.import_module("src.function.ethercat_manager")
        importlib.import_module("src.utils.config_util")

        self.shm_manager = shm_module.SharedMemoryManager(mem_name=self.shm_name, create=True)

        self.ui = ui_module.MainWindow(self)

        self.modbus_manager = modbus_module.ModbusManager(self)
        self.modbus_manager.connect()

        self.ethercat_manager = ethercat_module.EtherCATManager(self)
        self.ethercat_manager.connect()

        self.update_timer.timeout.connect(self.on_periodic_update)
        self.update_timer.start(100)

        self.ui.show()
        self.ui.activateWindow()

        self.is_reload = False

        log("UI reload end")

    def run(self):
        """애플리케이션 실행"""
        self.ui.show()
        return self.qt_app.exec()

    def quit(self):
        """애플리케이션 종료"""
        # 종료 시 설정값 저장
        self._save_config()

        self.modbus_manager.disconnect()
        self.ethercat_manager.disconnect()
        self.shm_manager.close()


if __name__ == '__main__':
    # 시스템 레벨의 에러 발생 시 파일에 로그 남김
    enable_crash_handler()

    app = App()

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
