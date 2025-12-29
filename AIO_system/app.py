from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
import sys
import json
import os
import threading
import time
from datetime import datetime, timedelta
from itertools import cycle

from src.ui.main_window import MainWindow
from src.function.modbus_manager import ModbusManager
from src.function.ethercat_manager import EtherCATManager
from src.ui.page.monitoring_page import MonitoringPage
from src.utils.config_util import CONFIG_PATH, APP_CONFIG, FEEDER_TIME_1, FEEDER_TIME_2
from src.utils.logger import log

class App():
    def __init__(self):
        # 우선적으로 설정값부터 읽어옴
        self.config = {}
        self.load_config()

        # 자동 운전 관련
        self.auto_mode = False
        self._auto_run = False
        self._auto_thread = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._feeder_output_time = datetime.now()
        self._current_size = 0

        # 제품 배출 순서 제어
        self.use_air_sequence = False
        self.set_air_sequence_index()
        
        self.qt_app = QApplication(sys.argv)
        
        # 글로벌 폰트 설정
        font = QFont("맑은 고딕", 10)
        self.qt_app.setFont(font)
        
        self.ui = MainWindow(self)
        self.modbus_manager = ModbusManager(self)
        self.modbus_manager.connect()

        self.ethercat_manager = EtherCATManager(self)
        self.ethercat_manager.connect()
        
        self.camera_manager = MonitoringPage(self)
        
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_periodic_update)
        self.update_timer.start(100)

    def on_periodic_update(self):
        """주기적 업데이트"""
        self.ui.update_time()

    def on_update_monitor(self, _list):
        if hasattr(self.ui, 'monitoring_page'):
            self.ui.monitoring_page.update_values(_list)

    def _auto_loop(self):
        if not self.auto_mode or not self._auto_run:
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

                log(f"[INFO] feeder output size level changed {cur_size+1} to {self._current_size+1}")

            time.sleep(0.033)

# region inverter control
    def on_update_inverter_status(self, _data):
        if hasattr(self.ui, 'settings_page') and self.ui.pages.currentIndex() == 2:
            tab_index = self.ui.settings_page.tabs.currentIndex()
            if tab_index == 1 or tab_index == 2:
                self.ui.settings_page.tabs.widget(tab_index).update_values(_data)

    def on_set_freq(self, motor_id: str, value: float):
        log(f"Setting frequency for {motor_id} to {value} Hz")
        self.modbus_manager.set_freq(motor_id, value)

    def on_set_acc(self, motor_id: str, value: float):
        log(f"Setting acceleration time for {motor_id} to {value} sec")
        self.modbus_manager.set_acc(motor_id, value)

    def on_set_dec(self, motor_id: str, value: float):
        log(f"Setting deceleration time for {motor_id} to {value} sec")
        self.modbus_manager.set_dec(motor_id, value)

    def motor_start(self, motor_id: str = 'inverter_001'):
        log(f"Starting motor: {motor_id}")
        self.modbus_manager.motor_start(motor_id)

    def motor_stop(self, motor_id):
        log(f"Stopping motor: {motor_id}")
        self.modbus_manager.motor_stop(motor_id)
        
    def custom_check(self, addr):
        self.modbus_manager.custom_check(addr)
    
    def custom_write(self, addr, value):
        self.modbus_manager.custom_write(addr, value)
# endregion

# region servo control
    def on_update_servo_status(self, servo_id: int, _data):
        if hasattr(self.ui, 'settings_page') and self.ui.pages.currentIndex() == 2:
            tab_index = self.ui.settings_page.tabs.currentIndex()
            if tab_index == 0:
                self.ui.settings_page.tabs.widget(tab_index).update_values(servo_id, _data)

    def servo_on(self, servo_id: int):
        self.ethercat_manager.servo_onoff(servo_id, True)
    
    def servo_off(self, servo_id: int):
        self.ethercat_manager.servo_onoff(servo_id, False)

    def servo_reset(self, servo_id: int):
        self.ethercat_manager.servo_reset(servo_id)

    def servo_stop(self, servo_id: int):
        self.ethercat_manager.servo_halt(servo_id)
    
    def servo_homing(self, servo_id: int):
        self.ethercat_manager.servo_homing(servo_id)

    def servo_set_origin(self, servo_id: int):
        self.ethercat_manager.servo_set_home(servo_id)

    def servo_move_to_position(self, servo_id: int, pos: float, v: float):
        self.ethercat_manager.servo_move_absolute(servo_id, pos, v)

    def servo_jog_move(self, servo_id: int, v: float):
        self.ethercat_manager.servo_move_velocity(servo_id, v)

    def servo_inch_move(self, servo_id: int, dist: float, v: float = 10000.0):
        self.ethercat_manager.servo_move_relative(servo_id, dist, v)
# endregion

# region I/O
    def on_update_input_status(self, input_data):
        if hasattr(self.ui, 'logs_page') and self.ui.pages.currentIndex() == 3:
            tab_index = self.ui.logs_page.tabs.currentIndex()
            if tab_index == 0:
                self.ui.logs_page.tabs.widget(tab_index).update_input_status(input_data)

    def on_update_output_status(self, output_data):
        if hasattr(self.ui, 'logs_page') and self.ui.pages.currentIndex() == 3:
            tab_index = self.ui.logs_page.tabs.currentIndex()
            if tab_index == 0:
                self.ui.logs_page.tabs.widget(tab_index).update_output_status(output_data)

    def airknife_on(self, air_num: int, on_term: int):
        self.ethercat_manager.airknife_on(0, air_num, on_term)

    def on_airknife_off(self, air_num: int):
        if hasattr(self.ui, 'settings_page'):
            self.ui.settings_page.tabs.widget(3).on_airknife_off(air_num)

    def set_auto_mode(self, is_on: bool):
        self.auto_mode = is_on
        mode = "auto" if is_on else "manual"
        log(f"[INFO] set {mode} mode")

    def auto_mode_run(self):
        self._auto_run = True
        self._auto_thread = threading.Thread(target=self._auto_loop)
        self._auto_thread.start()
        log("[INFO] auto mode run")

    def auto_mode_stop(self):
        self._stop_event.set()
        if hasattr(self, '_auto_thread') and self._auto_thread.is_alive():
            log("[INFO] auto thread to terminate...")
            self._auto_thread.join(timeout=5)
            if self._auto_thread.is_alive():
                log("[WARNING] auto thread did not terminate properly")
        self._auto_run = False

    def reset_alarm(self):
        log("[INFO] alarm reset")
        # TODO: 알람 리셋

    def emergency_stop(self):
        log("[WARNING] !!!EMERGENCY STOP BUTTON PRESSED!!!")
        # TODO: 비상정지 기능 연결

    def all_servo_homing(self):
        log("[INFO] all servo homing")

    def feeder_output(self):
        if self.auto_mode and self._auto_run:
            with self._lock:
                self._feeder_output_time = datetime.now()
            log("[INFO] feeder output checked")
    
    def hopper_empty(self):
        log("[INFO] hopper empty")
        # TODO: 호퍼 문닫기

    def hopper_full(self):
        log("[INFO] hopper full")
        # TODO: 호퍼 문열기

# endregion

    def on_auto_start(self):
        # 피더 동작 함수
        # 컨베이어 동작 함수
        self.modbus_manager.on_automode_start()

        # 카메라 동작 함수
        self.camera_manager.on_start_all()

    def on_auto_stop(self):
        # 피더 멈춤 함수
        # 컨베이어 멈춤 함수
        self.modbus_manager.on_automode_stop()

        # 카메라 멈춤 함수
        self.camera_manager.on_stop_all()

    def load_config(self):
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
        self.save_config()

    def save_config(self):
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
        _saved_seq = self.config.get("air_sequence", [])
        if _saved_seq:
            self.air_index_iter = cycle(_saved_seq)
        else:
            self.air_index_iter = None

    def run(self):
        """애플리케이션 실행"""
        self.ui.show()
        sys.exit(self.qt_app.exec())

    def quit(self):
        """애플리케이션 종료"""
        # 종료 시 설정값 저장
        self.save_config()

        self.modbus_manager.disconnect()
        self.ethercat_manager.disconnect()

if __name__ == '__main__':
    app = App()
    app.run()