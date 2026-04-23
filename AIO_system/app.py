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
from src.function.comm_manager import CommManager, LineScanSimulator
from src.function.sharedmemory_manager import SharedMemoryManager
from src.function.modbus_manager import ModbusManager
from src.function.ethercat_manager import EtherCATManager
from src.utils.config_util import (
    CONFIG_PATH, FEEDER_TIME_1, FEEDER_TIME_2, UI_PATH, LOG_PATH, SHM_NAME,
    PRCS_HTH_CHECK_TERM, MAX_PRCS_DEAD_COUNT,
    ProcessCheckVars,
    USE_FEEDER_CAM, FEEDER_AIR_TERM
)
from src.utils.logger import log
# from src.ui.popup.alert import PopUp

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
        _LOG_PATH = os.path.join(log_dir, f"crash_log_{today}.txt")

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


@dataclass
class CommManangers:
    comm_manager: CommManager = None
    modbus_manager: ModbusManager = None
    ethercat_manager: EtherCATManager = None

class App():
    """메인 앱 클래스"""
    is_reload = False
    _use_linescan_simulator = True # 라인스캔 이미지/오버레이 확인용 시뮬레이터 사용 여부
    _use_direct_control = False

    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.config = {}
        self._load_config()

        self.shm_data = SharedMemoryManager(mem_name=SHM_NAME).data
        self.prcs_vars = ProcessCheckVars(last_check_time=time.time())

        self.auto_mode = False
        self.auto_run = False
        self._auto_thread = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._feeder_output_time = datetime.now()
        self._current_size = 0
        self.monitoring_enabled = False
        self._feeder_air_time = datetime.now()

        self.use_air_sequence = False
        self.set_air_sequence_index()

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
        self.popup =  self.ui.popup # popup 연결

        self.managers = CommManangers()
        # _use_linescan_simulator == True 인 경우 라인 스캔 시뮬레이터를 사용하여 UI 화면 업데이트 확인 가능
        if self._use_linescan_simulator:
            self.managers.comm_manager = LineScanSimulator(self, width=640)
        else:
            self.managers.comm_manager = CommManager(self, None, None)
        self.managers.comm_manager.start()

        if self._use_direct_control:
            self.managers.modbus_manager = ModbusManager(self)
            self.managers.modbus_manager.connect()

            self.managers.ethercat_manager = EtherCATManager(self)
            self.managers.ethercat_manager.connect()

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

        if not USE_FEEDER_CAM and self.monitoring_enabled:
            # 피더 카메라 사용 안하는 경우 일정 시간마다 에어 분사
            current_time = datetime.now()
            if (current_time - self._feeder_air_time).total_seconds() > FEEDER_AIR_TERM:
                # FEEDER_AIR_TERM 마다 피더 배출부에 에어 분사
                self.blow_block()
                self._feeder_air_time = current_time

    def _check_sub_process(self):
        # 정해진 시간마다 프로세스 생존 여부 체크
        cur_time = time.time()
        if cur_time - self.prcs_vars.last_check_time >= PRCS_HTH_CHECK_TERM:
            # 현재 프로세스의 카운터 증가
            self.shm_data['hth_counter']['main_counter'] += 1

            # 상대 프로세스 카운터 체크
            cur_count = self.shm_data['hth_counter']['sub_counter']
            if self.prcs_vars.last_counter == cur_count:
                if self.prcs_vars.start_delay_count > 0:
                    # 프로세스 시작 유예 카운트가 남았으면 유예 카운트만 감소
                    self.prcs_vars.start_delay_count -= 1
                else:
                    # 카운터가 동일하다면 dead_count 증가
                    self.prcs_vars.dead_count += 1
                    if self.prcs_vars.dead_count >= MAX_PRCS_DEAD_COUNT:
                        # dead_count가 최대치에 도달하면 상대 프로세스 응답없음으로 판정
                        log("[ERROR] EtherCAT sub process is dead")
            else:
                # 카운터가 변화했다면 dead_count 및 유예 카운트 0 으로
                self.prcs_vars.dead_count = 0
                self.prcs_vars.start_delay_count = 0

            self.prcs_vars.last_counter = cur_count
            self.prcs_vars.last_check_time = cur_time

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
                self._current_size = (cur_size + 1) % 6

                for i in range(2):
                    info = self.config["servo_config"][f"servo_{i}"]["position"][self._current_size]
                    self.servo_move_to_position(i, float(info[0])*(10**3), float(info[1])*(10**3))

                log(f"""
                    [INFO] feeder output size level changed 
                    {cur_size+1} to {self._current_size+1}
                    """)

                self._feeder_output_time = current_time

            #수정 & 추가
            
            # if (current_time - self._feeder_air_time).total_seconds() > self.FEEDER_AIR_TERM:
            # FEEDER_AIR_TERM 마다 피더 배출부에 에어 분사
            #    self.airknife_on(4, self.FEEDER_AIR_DURATION * 1000)
            #    self._feeder_air_time = current_time
            
            try:
                # camera_manager는 MonitoringPage 인스턴스
                if self.camera_manager:
                    # MonitoringPage.rgb_cameras는 CameraView 객체들의 리스트
                    if len(self.camera_manager.rgb_cameras) > 0:
                    
                        # 첫 번째 RGB 카메라 (피더 카메라)
                        feeder_camera_view = self.camera_manager.rgb_cameras[0]
                    
                        # CameraView 안의 camera_thread에 접근
                        if feeder_camera_view.camera_thread:
                            # feeder 막힘 감지
                            if feeder_camera_view.camera_thread.block_detector.is_blocked():
                                self.airknife_on(4, self.FEEDER_AIR_DURATION * 1000)
                                #log("💨 에어나이프 발동발동 💨")
        
            except Exception as e:
                log(f"[ERROR] Feeder blockage detection failed: {e}")
                
                import traceback
                traceback.print_exc()
        
            time.sleep(0.033)

# region PLC/hyperspectral
    def on_monitoring_start(self):
        """모니터링 시작""" 
        self.monitoring_enabled = True
        if self.managers.comm_manager is not None:
            self.managers.comm_manager.start_hypercam()

    def on_monitoring_stop(self):
        """모니터링 종료""" 
        if self.managers.comm_manager is not None:
            self.managers.comm_manager.stop_hypercam()

        self.monitoring_enabled = False

    def on_pixel_line_data(self, info):
        """데이터를 UI로 전달 (메인 스레드에서 처리)""" 
        self.ui.signals.hypercam_updated.emit(info)

    def on_obj_detected(self, info, classification):
        """제품 감지""" 
        self.ui.signals.obj_detected.emit(info, classification)

    def on_legend_info(self, legend_info_list):
        """제품 범례 설정""" 
        self.ui.signals.legend_updated.emit(legend_info_list)

    def blow_block(self, air_num: int = 0):
        """피더 배출구 air 동작"""
        if self.managers.comm_manager is not None:
            self.managers.comm_manager.blow_block()

    def on_small_material_cross(self):
        """작은 재질 선 통과 감지 및 처리"""
        if self.managers.comm_manager is not None:
            self.managers.comm_manager.on_small_material_cross()
# endregion

# region inverter control
    def _update_inverter_config(self, inverter_name: str, index: int, value: float):
        conf = self.config.setdefault("inverter_config", {}).setdefault(
            inverter_name, [0.0, 1.0, 1.0]
        )
        while len(conf) < 3:
            conf.append(0.0)
        conf[index] = float(value)

    def on_update_inverter_status(self, _data):
        """피더, 컨베이어 상태 UI 업데이트"""
        if self.ui.pages.settings_page is not None and \
            self.ui.children_widget.main_stack.currentIndex() == 2:
            tab_index = self.ui.pages.settings_page.pages.currentIndex()
            if tab_index in (1, 2):
                self.ui.signals.inverter_updated.emit(_data)

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
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.set_freq(inverter_name, value)

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
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.set_acc(inverter_name, value)

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
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.set_dec(inverter_name, value)

    def motor_start(self, inverter_name: str):
        """
        인버터 운전
        
        :param self: Description
        :param inverter_name: 인버터 이름
        :type inverter_name: str
        """
        log(f"Starting motor: {inverter_name}")
        self.on_popup("info", "인버터 운전", f"Starting motor: {inverter_name}")
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.motor_start(inverter_name)
            self.on_popup("info", "인버터 운전 시작", f"{inverter_name} 모터가 시작되었습니다.")

    def motor_stop(self, inverter_name: str): 
        """
        인버터 정지
        
        :param self: Description
        :param inverter_name: 인버터 이름
        :type inverter_name: str
        """
        log(f"Stopping motor: {inverter_name}")
        self.on_popup("info", "인버터 정지", f"Stopping motor: {inverter_name}")
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.motor_stop(inverter_name)
            self.on_popup("info", "인버터 정지", f"{inverter_name} 모터가 정지되었습니다.")

    def inverter_custom_read(self, slave_id: int, addr: int):
        """
        해당 주소의 값 읽기
        
        :param self: Description
        :param slave_id: 인버터 ID
        :type slave_id: int
        :param addr: 조회할 주소 값
        :type addr: int
        """
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.custom_read(slave_id, addr)

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
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.custom_write(slave_id, addr, value)
# endregion

# retion servo control
    def on_update_servo_status(self, servo_id: int, _data):
        """서보 상태 UI 업데이트"""
        if self.ui.pages.settings_page and \
            self.ui.children_widget.main_stack.currentIndex() == 2:
            tab_index = self.ui.pages.settings_page.pages.currentIndex()
            if tab_index == 0:
                self.ui.signals.servo_updated.emit(servo_id, _data)

    def servo_on(self, servo_id: int):
        """
        서보 on
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.servo_onoff(servo_id, True)

    def servo_off(self, servo_id: int):
        """
        서보 off
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.servo_onoff(servo_id, False)

    def servo_reset(self, servo_id: int):
        """
        서보 알람 리셋
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.servo_reset(servo_id)

    def servo_stop(self, servo_id: int):
        """
        서보 정지
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.servo_halt(servo_id)

    def servo_homing(self, servo_id: int):
        """
        서보 원점 복귀
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        """
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.servo_homing(servo_id)

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
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.servo_move_absolute(servo_id, pos, v)

    def servo_jog_move(self, servo_id: int, v: float):
        """
        서보 조그
        
        :param self: Description
        :param servo_id: 서보 ID
        :type servo_id: int
        :param v: 이동 속도
        :type v: float
        """
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.servo_move_velocity(servo_id, v)

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
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.servo_move_relative(servo_id, dist, v)
# endregion

# region I/O
    def on_update_input_status(self, total_input: int):
        """
        입력 모듈 상태 UI 업데이트
        
        :param self: Description
        :param total_input: 입력 모듈 bit 값
        :type total_input: int
        """
        if self.ui.pages.logs_page is not None and \
            self.ui.children_widget.main_stack.currentIndex() == 3:
            tab_index = self.ui.pages.logs_page.pages.currentIndex()
            if tab_index == 0:
                self.ui.signals.input_updated.emit(total_input)

    def on_update_output_status(self, total_output: int):
        """
        출력 모듈 상태 UI 업데이트
        
        :param self: Description
        :param total_output: 출력 모듈 bit 값
        :type total_output: int
        """
        if self.ui.pages.logs_page is not None and \
            self.ui.children_widget.main_stack.currentIndex() == 3:
            tab_index = self.ui.pages.logs_page.pages.currentIndex()
            if tab_index == 0:
                self.ui.signals.output_updated.emit(total_output)

    def airknife_on(self, air_num: int, on_term: int = 500):
        """
        에어나이프 켜기
        
        :param self: Description
        :param air_num: 에어나이프 번호(1~3)
        :type air_num: int
        :param on_term: Description
        :type on_term: int
        """
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.airknife_on(air_num, on_term)

    def on_airknife_off(self, air_num: int):
        """에어나이프 정지 시 UI 업데이트"""
        if self.ui.pages.settings_page is not None:
            self.ui.signals.airknife_updated.emit(air_num)
            self.on_popup("info", "에어나이프 정지", f"airknife {air_num} OFF")

    def set_auto_mode(self, is_on: bool):
        """자동/수동 모드 세팅"""
        self.auto_mode = is_on
        mode = "auto" if is_on else "manual"
        log(f"[INFO] set {mode} mode")

    def auto_mode_run(self):
        """자동 모드 운전 시작"""
        self.auto_run = True

        # 피더, 컨베이어 동작 함수
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.on_automode_start()

        # 카메라 동작 함수
        self.camera_manager.on_start_all()

        self._auto_thread = threading.Thread(target=self._auto_loop)
        self._auto_thread.start()
        log("[INFO] auto mode run")

    def auto_mode_stop(self):
        """자동 모드 운전 정지"""
        self._stop_event.set()

        if self._auto_thread is not None and self._auto_thread.is_alive():
            log("[INFO] auto thread to terminate...")
            self._auto_thread.join(timeout=5)
            if self._auto_thread.is_alive():
                log("[WARNING] auto thread did not terminate properly")
        # 피더, 컨베이어 멈춤 함수
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.on_automode_stop()

        # 카메라 멈춤 함수
        self.camera_manager.on_stop_all()

        self.auto_run = False

    def reset_alarm(self):
        """알람 리셋"""
        log("[INFO] alarm reset")
        # TODO: 알람 리셋

    def emergency_stop(self):
        """비상 정지"""
        log("[WARNING] !!!EMERGENCY STOP BUTTON PRESSED!!!")
        # TODO: 비상정지 기능 연결

    def all_servo_homing(self):
        """서보 원점 복귀"""
        log("[INFO] all servo homing")

    def feeder_output(self):
        """피더 제품 출력 감지 시 호출"""
        if self.auto_mode and self.auto_run:
            with self._lock:
                self._feeder_output_time = datetime.now()
            log("[INFO] feeder output checked")

    def hopper_empty(self):
        """호퍼 비었을 때 호출"""
        log("[INFO] hopper empty")
        # TODO: 호퍼 문닫기
        self.on_popup("info", "알림", "호퍼가 비어있습니다.")

    def hopper_full(self):
        """호퍼 가득 찼을 때 호출"""
        log("[INFO] hopper full")
        # TODO: 호퍼 문열기
        self.on_popup("info", "알림", "호퍼가 가득 찼습니다.")
# endregion

    def on_auto_start(self):
        self.auto_mode = True
        self.auto_run = True
        log("auto start")

    def on_auto_stop(self):
        self.auto_run = False
        log("auto stop")

    def on_log(self, message: str, level: str = "info"):
        self.ui.signals.log_updated.emit(message, level)

    def on_on_log(self, message: str):
        self.on_log(message)

    def on_popup(self, popup_type: str, title: str, message: str): 
        self.ui.signals.show_popup.emit(popup_type, title, message)

    def _build_default_config(self):
        inverter_config = {f"inverter_00{i}": [0.0, 1.0, 1.0] for i in range(1, 7)}
        base_positions = [[0.0, 0.0] for _ in range(6)]
        airknife_config = {
            f"airknife_{i}": {"timing": 0, "duration": 100}
            for i in range(1, 4)
        }

        return {
            "air_sequence": [],
            "inverter_config": inverter_config,
            "servo_config": {
                "servo_0": {
                    "position": [pos[:] for pos in base_positions],
                    "jog_speed": 0.0,
                    "inch_distance": 0.0,
                },
                "servo_1": {
                    "position": [pos[:] for pos in base_positions],
                    "jog_speed": 0.0,
                    "inch_distance": 0.0,
                },
            },
            "airknife_config": airknife_config,
        }

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

        self.config = self._build_default_config()
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
        """제품 분류 순서 지정"""
        _saved_seq = self.config.get("air_sequence", [])
        if _saved_seq:
            self.air_index_iter = cycle(_saved_seq)
        else:
            self.air_index_iter = None

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
        self._save_config()

        if self.managers.comm_manager is not None:
            self.managers.comm_manager.quit()
            self.managers.comm_manager.join(timeout=5)
            if self.managers.comm_manager.is_alive():
                log("comm manager thread did not terminate properly")
        
        if self.managers.modbus_manager is not None:
            self.managers.modbus_manager.disconnect()
        
        if self.managers.ethercat_manager is not None:
            self.managers.ethercat_manager.disconnect()

        self.update_timer.stop()
        if hasattr(self, "shm_data"):
            del self.shm_data


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
