"""
이더캣 관리자
"""
import threading
import time
import heapq

from typing import Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.function.ethercat_process import EtherCATProcess

from src.utils.config_util import (
    ETHERCAT_DELAY,
    get_servo_unmodified_value, get_servo_modified_value,
    StatusMask, check_mask, OperationMode, InputBitMask,
)
from src.utils.logger import log


@dataclass
class RxPdoData:
    """
    서보 RxPDO를 위한 데이터 클래스
    """
    ctrl: int
    mode: int = 0
    pos: int = 0
    v: int = 0


@dataclass
class CspData:
    """
    서보 실시간 위치 조작을 위한 데이터 클래스
    """
    cur_pos: float
    cur_vel: float
    tgt_pos: float
    tgt_vel: float


class EtherCATManager:
    """
    이더캣 매니저
    """
    _initialized = False
    app = None

    def __init__(self, app):
        if not self._initialized:
            self.app = app
            self.stop_event = threading.Event()
            self.shm_name = app.shm_name
            self.shm_data = app.shm_manager.data

            self.tasks = []
            heapq.heapify(self.tasks)
            self.task_lock = threading.Lock()
            self.prev_input = []
            self.input_bit_functions = {
                InputBitMask.MODE_SELECT: self.mode_select,
                InputBitMask.AUTO_RUN: self.auto_mode_run,
                InputBitMask.AUTO_STOP: self.auto_mode_stop,
                InputBitMask.RESET_ALARM: self.reset_alarm,
                InputBitMask.EMERGENCY_STOP: self.emergency_stop,
                InputBitMask.SERVO_HOMING: self.all_servo_homing,
                InputBitMask.FEEDER_OUTPUT: self.feeder_output,
            }

            self.process: EtherCATProcess = None
            self.process_thread: threading.Thread = None

            self._initialized = True

    def connect(self):
        """
        이더캣 연결 - 실제 이더캣 통신은 별도의 프로세스에서 진행
        
        :param self: Description
        """
        self.process = EtherCATProcess(self.shm_name)
        self.process.start()

        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()

    def disconnect(self):
        """
        이더캣 종료
        
        :param self: Description
        """
        self.stop_event.set()
        if hasattr(self, 'process_thread') and self.process_thread.is_alive():
            log("[INFO] process thread to terminate...")
            self.process_thread.join(timeout=5)
            if self.process_thread.is_alive():
                log("[WARNING] process_thread did not terminate properly")
        if hasattr(self, 'shm_data'):
            self.shm_data = None

        self.process.stop()
        self.process.join(timeout=5)

    # task 예약
    def _reserve_task(self, delay: float, func: Callable, *args):
        time_after = datetime.now() + timedelta(seconds=delay)
        with self.task_lock:
            heapq.heappush(self.tasks, (time_after, func, args))

    def _run_tasks(self):
        current_time = datetime.now()
        run_list = []
        with self.task_lock:
            while self.tasks and current_time > self.tasks[0][0]:
                run_list.append(heapq.heappop(self.tasks))

        for task in run_list:
            task[1](*task[2])

    def _process_loop(self):
        while not self.stop_event.is_set():
            for i in range(2):
                self._update_servo_values(i)
            self._update_input()
            self._update_output()

            self._run_tasks()

            time.sleep(ETHERCAT_DELAY)

# region servo functions
    # RxPDO 설정
    def _set_servo_rx_pdo(self, servo_id: int, data: RxPdoData):
        self.shm_data[f'servo_{servo_id}']['output_pdo']['control_word'] = data.ctrl
        self.shm_data[f'servo_{servo_id}']['output_pdo']['drive_mode'] = data.mode
        self.shm_data[f'servo_{servo_id}']['output_pdo']['target_position'] = \
            get_servo_unmodified_value(data.pos)
        self.shm_data[f'servo_{servo_id}']['output_pdo']['target_velocity'] = \
            get_servo_unmodified_value(data.v)

    def _get_servo_tx_pdo(self, servo_id: int) -> list:
        ret = self.shm_data[f'servo_{servo_id}']['input_pdo'].tolist()
        return ret

    def _update_servo_values(self, servo_id: int):
        try:
            tx_pdo = self._get_servo_tx_pdo(servo_id)
            self.app.on_update_servo_status(servo_id, tx_pdo)
        except Exception as e:
            log(f"[ERROR] servo {servo_id} TxPDO read failed {e}")

    def servo_onoff(self, servo_id: int, onoff: bool):
        """
        서보 on/off
        
        :param self: Description
        :param servo_id: Description
        :type servo_id: int
        :param onoff: Description
        :type onoff: bool
        """
        try:
            if onoff:
                self._set_servo_rx_pdo(servo_id, RxPdoData(ctrl=0x000F))
            else:
                self._set_servo_rx_pdo(servo_id, RxPdoData(ctrl=0x0106))
            log(f"[INFO] servo {servo_id} ON: {onoff}")
        except Exception as e:
            log(f"[ERROR] servo {servo_id} on/off failed: {e}")

    def servo_homing(self, servo_id: int):
        """
        단일 서보 원점 복귀 
        
        :param self: Description
        :param servo_id: Description
        :type servo_id: int
        """
        try:
            self._set_servo_rx_pdo(servo_id, RxPdoData(ctrl=0x001F, mode=6))
            self.shm_data[f'servo_{servo_id}']['variables']['state'] = OperationMode.SERVO_HOMING
            log(f"[INFO] servo {servo_id} homing")
        except Exception as e:
            log(f"[ERROR] servo {servo_id} homing failed: {e}")

    def _start_csp(self, servo_id: int, data: CspData):
        self.shm_data[f'servo_{servo_id}']['variables']['current_position'] = data.cur_pos
        self.shm_data[f'servo_{servo_id}']['variables']['current_velocity'] = data.cur_vel
        self.shm_data[f'servo_{servo_id}']['variables']['target_position'] = data.tgt_pos
        self.shm_data[f'servo_{servo_id}']['variables']['target_velocity'] = data.tgt_vel
        self.shm_data[f'servo_{servo_id}']['variables']['last_time'] = time.time_ns()
        self.shm_data[f'servo_{servo_id}']['variables']['state'] = OperationMode.SERVO_CSP

    def servo_move_absolute(self, servo_id: int, pos: float, v: float):
        """
        실시간 위치 제어 모드(CSP) - 절대 위치 이동
        
        :param self: Description
        :param servo_id: Description
        :type servo_id: int
        :param pos: Description
        :type pos: float
        :param v: Description
        :type v: float
        """
        try:
            cur_state = self.shm_data[f'servo_{servo_id}']['input_pdo']['status_word']
            cur_pos = self.shm_data[f'servo_{servo_id}']['input_pdo']['actual_position']
            cur_vel = self.shm_data[f'servo_{servo_id}']['input_pdo']['actual_velocity']
            if not check_mask(cur_state, StatusMask.STATUS_OPERATION_ENABLED):
                raise Exception("servo is not ready to work. servo ON first")

            cur_pos = get_servo_modified_value(cur_pos)
            cur_vel = get_servo_modified_value(cur_vel)
            self._start_csp(servo_id, CspData(cur_pos, cur_vel, pos, v))
            log(f"""
                [INFO] servo {servo_id} move by absolute position: 
                position({pos:.1f} μm), velocity({v:.1f} μm/s)
                """)
        except Exception as e:
            log(f"[ERROR] servo {servo_id} CSP move failed: {e}")

    def servo_move_relative(self, servo_id: int, dist: float, v: float):
        """
        실시간 위치 제어 모드(CSP) - 상대 위치 이동
        
        :param self: Description
        :param servo_id: Description
        :type servo_id: int
        :param dist: Description
        :type dist: float
        :param v: Description
        :type v: float
        """
        try:
            cur_state = self.shm_data[f'servo_{servo_id}']['input_pdo']['status_word']
            cur_pos = self.shm_data[f'servo_{servo_id}']['input_pdo']['actual_position']
            cur_vel = self.shm_data[f'servo_{servo_id}']['input_pdo']['actual_velocity']
            if not check_mask(cur_state, StatusMask.STATUS_OPERATION_ENABLED):
                raise Exception("servo is not ready to work. servo ON first")

            cur_pos = get_servo_modified_value(cur_pos)
            cur_vel = get_servo_modified_value(cur_vel)
            pos = cur_pos + dist

            self._start_csp(servo_id, CspData(cur_pos, cur_vel, pos, v))
            log(f"""
                [INFO] servo {servo_id} move by relative position: 
                distance({dist:.1f} μm), velocity({v:.1f} μm/s)
            """)
        except Exception as e:
            log(f"[ERROR] servo {servo_id} CSP move failed: {e}")

    def servo_move_velocity(self, servo_id: int, v: float):
        """
        실시간 속도 제어(CSV) 모드
        
        :param self: Description
        :param servo_id: Description
        :type servo_id: int
        :param v: Description
        :type v: float
        """
        try:
            cur_state = self.shm_data[f'servo_{servo_id}']['input_pdo']['status_word']
            if not check_mask(cur_state, StatusMask.STATUS_OPERATION_ENABLED):
                raise Exception("servo is not ready to work. servo ON first")

            self._set_servo_rx_pdo(servo_id, RxPdoData(ctrl=0x000F, mode=9, v=v))
            self.shm_data[f'servo_{servo_id}']['variables']['state'] = OperationMode.SERVO_CSV
            log(f"[INFO] servo {servo_id} move by velocity: velocity({v:.1f} μm/s)")
        except Exception as e:
            log(f"[ERROR] servo {servo_id} CSV move failed: {e}")

    def servo_halt(self, servo_id: int):
        """
        서보 정지
        
        :param self: Description
        :param servo_id: Description
        :type servo_id: int
        """
        try:
            self._set_servo_rx_pdo(servo_id, RxPdoData(ctrl=0x010F))
            self.shm_data[f'servo_{servo_id}']['variables']['state'] = OperationMode.SERVO_READY
            log(f"[INFO] servo {servo_id} halt")
        except Exception as e:
            log(f"[ERROR] servo {servo_id} halt failed: {e}")

    def servo_reset(self, servo_id: int):
        """
        서보 알람 리셋
        
        :param self: Description
        :param servo_id: Description
        :type servo_id: int
        """
        try:
            self._set_servo_rx_pdo(servo_id, RxPdoData(ctrl=0x008F))
            self.shm_data[f'servo_{servo_id}']['variables']['state'] = OperationMode.SERVO_READY
            log(f"[INFO] servo {servo_id} reset")
        except Exception as e:
            log(f"[ERROR] servo {servo_id} reset failed: {e}")

    def servo_shutdown(self, servo_id: int):
        """
        서보 off
        
        :param self: Description
        :param servo_id: Description
        :type servo_id: int
        """
        try:
            self._set_servo_rx_pdo(servo_id, RxPdoData(ctrl=0x0006))
            log(f"[INFO] servo {servo_id} shutdown")
        except Exception as e:
            log(f"[ERROR] servo {servo_id} shutdown failed: {e}")
# endregion

# region IO functions
    def _input_bit_check(self, total_input: int):
        prev_input = self.shm_data['prev_input']
        _changed = prev_input ^ total_input
        if _changed != 0:
            for _bit_mask in InputBitMask:
                if _changed & _bit_mask:
                    is_on = bool(total_input&_bit_mask)
                    self.input_bit_functions[_bit_mask](is_on)
            self.shm_data['prev_input'] = total_input

    def _update_input(self) -> int:
        total_input = self.shm_data['total_input']
        self.app.on_update_input_status(total_input)

        self._input_bit_check(total_input)

    def _update_output(self):
        total_output = self.shm_data['total_output']
        self.app.on_update_output_status(total_output)

    def io_write_bit(self, on_mask: int = 0, off_mask: int = 0):
        """
        offset번째 비트의 값을 0/1로 변경
        
        :param self:
        :param on_mask: 1로 만들어 줄 비트 마스크
        :type on_mask: int | None
        :param off_mask: 0으로 만들어 줄 비트 마스크
        :type off_mask: int | None
        """
        if on_mask > 0xFFFFFFFF or off_mask > 0xFFFFFFFF:
            log(f"""
                [WARNING] bit mask must be integer between 0 and 0xFFFFFFFF.
                current value: {on_mask:X}, {off_mask:X}
                """)
            return

        try:
            total_bits = self.shm_data['total_output']
            total_bits = (total_bits & ~off_mask) | on_mask
            self.shm_data['total_output'] = total_bits
        except Exception as e:
            log(f"[ERROR] write output bit failed: {e}")

    def airknife_on(self, air_num: int, on_term: int):
        """
        에어나이프 켜기
        
        :param self:
        :param air_num: 에어나이프 번호(1~3)
        :type air_num: int
        :param on_term: 에어 출력 시간값
        :type on_term: int
        """
        try:
            on_mask = 1 << (air_num + 19)
            self.io_write_bit(on_mask=on_mask)
            log(f"[INFO] Airknife {air_num} on")
            self._reserve_task(on_term/1000, self.airknife_off, air_num)
        except Exception as e:
            log(f"[ERROR] airknife on failed: {e}")

    def airknife_off(self, air_num: int):
        """
        에어나이프 끄기
        
        :param self:
        :param air_num: 에어나이프 번호(1~3)
        :type air_num: int
        """
        try:
            off_mask = 1 << (air_num + 19)
            self.io_write_bit(off_mask=off_mask)
            log(f"[INFO] Airknife {air_num} off")
            self.app.on_airknife_off(air_num)
        except Exception as e:
            log(f"[ERROR] airknife off failed: {e}")

    def mode_select(self, is_on: bool):
        """
        수동/자동 스위치 조작 시 호출
        
        :param self: Description
        :param is_on: Description
        :type is_on: bool
        """
        try:
            if self.app.auto_mode ^ is_on:
                self.auto_mode_stop(True)
                bit_mask = 0b11
                self.io_write_bit(
                    on_mask=bit_mask if is_on else None,
                    off_mask=bit_mask if not is_on else None
                )
                self.app.set_auto_mode(is_on)
        except Exception as e:
            log(f"[ERROR] mode selection failed: {e}")

    def auto_mode_run(self, is_on: bool):
        """
        운전 버튼 누를 시 호출
        
        :param self: Description
        :param is_on: Description
        :type is_on: bool
        """
        if not self.app.auto_mode:
            return

        try:
            if not self.app.auto_run and is_on:
                on_mask = 0b10
                off_mask = 0b100
                self.io_write_bit(on_mask=on_mask, off_mask=off_mask)
                self.app.auto_mode_run()
        except Exception as e:
            log(f"[ERROR] automode start failed: {e}")

    def auto_mode_stop(self, is_on: bool):
        """
        정지 버튼 누를 시 호출
        
        :param self: Description
        :param is_on: Description
        :type is_on: bool
        """
        if not self.app.auto_mode:
            return

        try:
            if self.app.auto_run and is_on:
                on_mask = 0b100
                off_mask = 0b10
                self.io_write_bit(on_mask=on_mask, off_mask=off_mask)
                self.app.auto_mode_stop()
        except Exception as e:
            log(f"[ERROR] automode stop failed: {e}")

    def reset_alarm(self, is_on: bool):
        """
        알람 리셋 버튼 누를 시 호출
        
        :param self: Description
        :param is_on: Description
        :type is_on: bool
        """
        try:
            if is_on:
                off_mask = 0b110000
                self.io_write_bit(off_mask=off_mask)
                self.app.reset_alarm()
        except Exception as e:
            log(f"[ERROR] alarm reset failed: {e}")

    def emergency_stop(self, is_on: bool):
        """
        정지 버튼 누를 시 호출
        
        :param self: Description
        :param is_on: Description
        :type is_on: bool
        """
        try:
            if is_on:
                self.app.emergency_stop()
        except Exception as e:
            log(f"[ERROR] emergency stop failed: {e}")

    def all_servo_homing(self, is_on: bool):
        """
        모든 서보를 다 원점 복귀 하려고 할 때 호출 
        
        :param self: Description
        :param is_on: Description
        :type is_on: bool
        """
        try:
            if is_on:
                self.app.all_servo_homing()
        except Exception as e:
            log(f"[ERROR] all servo homing failed: {e}")

    def feeder_output(self, is_on: bool):
        """
        피더 제품 배출 감지 센서가 뭔가를 감지하면 호출
        
        :param self: Description
        :param is_on: Description
        :type is_on: bool
        """
        if is_on:
            self.app.feeder_output()

    def hopper_empty(self, is_on: bool):
        """
        호퍼 상/하단 센서가 모두 off일 때 호출
        
        :param self: Description
        :param is_on: sensor is on
        :type is_on: bool
        """
        if is_on:
            self.app.hopper_empty()

    def hopper_full(self, is_on: bool):
        """
        호퍼 상/하단 센서가 모두 on일 때 호출
        
        :param self: Description
        :param is_on: sensor is on
        :type is_on: bool
        """
        if is_on:
            self.app.hopper_full()
# endregion
# endregion
