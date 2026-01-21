"""
이더캣 서브 프로세스
"""
import threading
import time
import struct

from dataclasses import dataclass, field

import multiprocessing as mp
from multiprocessing import shared_memory, Process, synchronize

import numpy as np
import pysoem

from src.utils.config_util import (
    IF_NAME, ETHERCAT_DELAY, LS_VENDOR_ID, LSProductCode,
    EC_RX_INDEX, EC_TX_INDEX, SERVO_RX_MAP, SERVO_TX_MAP, SERVO_RX, SERVO_TX,
    OUTPUT_RX_MAP, INPUT_TX_MAP, OUTPUT_RX, INPUT_TX,
    get_servo_unmodified_value, get_servo_modified_value,
    StatusMask, check_mask, OperationMode, SERVO_ACCEL, SERVO_IN_POS_WIDTH,
    SHARED_MEMORY_DTYPE, sync_shared_memory
)
from src.utils.logger import log


@dataclass
class SlaveInfo:
    """
    class for EtherCAT slaves
    """
    slave: pysoem.CdefSlave
    pdo_lock: synchronize.Lock = field(default_factory=mp.Lock)


@dataclass
class ProcessVars:
    """
    서브 프로세스의 run 함수 내에서 생성해야 하는 속성 모음
    """
    shm: shared_memory.SharedMemory = None
    shm_data: np.ndarray = None
    master: pysoem.CdefMaster = None
    check_thread: threading.Thread = None
    servo_drives: list[SlaveInfo] = None
    input_modules: list[SlaveInfo] = None
    output_modules: list[SlaveInfo] = None


# region EtherCATProcess
class EtherCATProcess(Process):
    """
    이더캣 통신을 위한, 분리된 프로세스
    """
    _initialized = False

    def __init__(self, shm_name: str):
        if not self._initialized:
            super().__init__()

            self.recv = 0
            self.shm_name = shm_name

            self.vars = None

            self.stop_event: synchronize.Event = mp.Event()

            self._initialized = True

    def run(self):
        log("EtherCAT Process run")
        try:
            shm = shared_memory.SharedMemory(name=self.shm_name)
            self.vars = ProcessVars(
                shm=shm,
                shm_data=np.frombuffer(shm.buf, dtype=SHARED_MEMORY_DTYPE)[0]
            )

            self._connect()

            self._slave_setting()

            self._move_to_op_state()

            for _ in range(40):
                self.vars.master.state_check(pysoem.OP_STATE, timeout=50_000)
                if self.vars.master.state == pysoem.OP_STATE:
                    break

            self.vars.check_thread = threading.Thread(target=self._check_slave_loop, daemon=True)
            self.vars.check_thread.start()

            # send - receive 합을 맞추기 위해 먼저 1회 보냄
            self.vars.master.send_processdata()

            while not self.stop_event.is_set():
                self._process_loop()

                time.sleep(ETHERCAT_DELAY)

        except Exception as e:
            log(f"[ERROR] EtherCAT runtime error: {e}")
        finally:
            self._disconnect()

    def _connect(self):
        self.vars.master = pysoem.Master()
        self.vars.master.in_op = False
        self.vars.master.do_check_state = False

        self.vars.master.open(IF_NAME)
        if not self.vars.master.config_init() > 0:
            raise Exception("EtherCAT Slaves not found")

    def _slave_setting(self):
        self.vars.servo_drives = []
        self.vars.input_modules = []
        self.vars.output_modules = []
        for slave in self.vars.master.slaves:
            if slave.man == LS_VENDOR_ID:
                # config_func는 마스터의 config_map 함수 실행 시 실행됨 -> PDO 매핑을 반드시 해야 함
                match slave.id:
                    case LSProductCode.L7NH_PRODUCT_CODE:
                        slave.config_func = self._setup_servo_drive
                        slave.add_emergency_callback(self._emcy_callback_servo)
                        slave_info = self._create_slave_info(slave)
                        self.vars.servo_drives.append(slave_info)
                    case LSProductCode.D232A_PRODUCT_CODE:
                        slave.config_func = self._setup_input_module
                        slave.add_emergency_callback(self._emcy_callback_input)
                        slave_info = self._create_slave_info(slave)
                        self.vars.input_modules.append(slave_info)
                    case LSProductCode.TR32KA_PRODUCT_CODE:
                        slave.config_func = self._setup_output_module
                        slave.add_emergency_callback(self._emcy_callback_output)
                        slave_info = self._create_slave_info(slave)
                        self.vars.output_modules.append(slave_info)
                    case _:
                        self.vars.master.close()
                        raise Exception("unexpected slave layout")
            else:
                self.vars.master.close()
                raise Exception("unexpected slave layout")

            slave.is_lost = False

    def _move_to_op_state(self):
        self.vars.master.config_map()
        if self.vars.master.state_check(pysoem.SAFEOP_STATE, timeout=50_000) != pysoem.SAFEOP_STATE:
            self.vars.master.close()
            raise Exception("not all slaves reached SAFEOP state")

        # DC(Distributed Clock) 동기화: LS 산전의 이더캣 장치는 마스터와 싱크를 맞추기 때문에 DC 동기화가 필요 없음
        # slave.dc_sync(act=True, sync0_cycle_time=1_000_000) # 1,000,000 ns = 1 ms

        self.vars.master.state = pysoem.OP_STATE

        # send one valid process data
        self.vars.master.send_processdata()
        self.vars.master.receive_processdata(timeout=2000)

        for module in self.vars.input_modules:
            self.vars.shm_data['total_input'] = np.frombuffer(module.slave.input, dtype='<u4')[0]

        for module in self.vars.output_modules:
            self.vars.shm_data['total_output'] = np.frombuffer(module.slave.output, dtype='<u4')[0]

        for i, servo in enumerate(self.vars.servo_drives):
            sync_shared_memory(self.vars.shm_data[f'servo_{i}']['input_pdo'], servo.slave.input)
            sync_shared_memory(self.vars.shm_data[f'servo_{i}']['output_pdo'], servo.slave.output)
            self.vars.shm_data[f'servo_{i}']['output_pdo']['target_position'] = \
                self.vars.shm_data[f'servo_{i}']['input_pdo']['actual_position']
            servo.slave.output = self.vars.shm_data[f'servo_{i}']['output_pdo'].tobytes()

        # request OP STATE for all slaves
        self.vars.master.write_state()

    def _process_loop(self):
        self.recv = self.vars.master.receive_processdata(timeout=100_000)
        if not self.recv == self.vars.master.expected_wkc:
            log(f"""
                [WARNING] incorrect wkc. 
                recv: {self.recv} expected: {self.vars.master.expected_wkc}
                """)
            return

        for module in self.vars.input_modules:
            self._input_worker(module)

        for module in self.vars.output_modules:
            self._output_worker(module)

        for i, servo in enumerate(self.vars.servo_drives):
            self._servo_worker(i, servo)

        self.vars.master.send_processdata()

    def _disconnect(self):
        log("EtherCAT disconnect start")
        try:
            # 종료 시 모든 슬레이브를 INIT STATE로 전환
            log("close EtherCAT master")
            self.vars.master.state = pysoem.INIT_STATE
            self.vars.master.write_state()

            self.vars.master.close()

            if hasattr(self.vars, 'check_thread') and self.vars.check_thread.is_alive():
                log("[INFO] slave check thread to terminate...")
                self.vars.check_thread.join(timeout=5)
                if self.vars.check_thread.is_alive():
                    log("[WARNING] check_thread did not terminate properly")

            if hasattr(self, 'shm_data'):
                del self.vars.shm_data

            if hasattr(self, 'shm'):
                self.vars.shm.close()

            log("[INFO] EtherCAT disconnect completed")
        except Exception as e:
            log(f"[ERROR] EtherCAT disconnection error: {e}")

    def stop(self):
        """
        이더캣 통신 프로세스 정지
        
        :param self: Description
        """
        self.stop_event.set()

    def _create_slave_info(self, slave: pysoem.CdefSlave) -> SlaveInfo:
        return SlaveInfo(slave=slave)

# region threads
    @staticmethod
    def _check_slave(slave, pos):
        if slave.state == (pysoem.SAFEOP_STATE + pysoem.STATE_ERROR):
            log(f"[ERROR] slave {pos} is in SAFE_OP + ERROR, attempting ack.")
            slave.state = pysoem.SAFEOP_STATE + pysoem.STATE_ACK
            slave.write_state()
        elif slave.state == pysoem.SAFEOP_STATE:
            log(f"WARNING : slave {pos} is in SAFE_OP, try change to OPERATIONAL.")
            slave.state = pysoem.OP_STATE
            slave.write_state()
        elif slave.state > pysoem.NONE_STATE:
            if slave.reconfig():
                slave.is_lost = False
                log(f"MESSAGE : slave {pos} reconfigured")
        elif not slave.is_lost:
            slave.state_check(pysoem.OP_STATE)
            if slave.state == pysoem.NONE_STATE:
                slave.is_lost = True
                log(f"ERROR : slave {pos} lost")
        if slave.is_lost:
            if slave.state == pysoem.NONE_STATE:
                if slave.recover():
                    slave.is_lost = False
                    log(f"MESSAGE : slave {pos} recovered")
            else:
                slave.is_lost = False
                log(f"MESSAGE : slave {pos} found")

    # 슬레이브 상태 체크 스레드
    def _check_slave_loop(self):
        while not self.stop_event.is_set():
            if self.vars.master.in_op and \
            ((self.recv < self.vars.master.expected_wkc) or self.vars.master.do_check_state):
                self.vars.master.do_check_state = False
                self.vars.master.read_state()
                for i, slave in enumerate(self.vars.master.slaves):
                    if slave.state != pysoem.OP_STATE:
                        self.vars.master.do_check_state = True
                        EtherCATProcess._check_slave(slave, i)
                if not self.vars.master.do_check_state:
                    log("[INFO] OK : all slaves resumed OPERATIONAL.")
            time.sleep(ETHERCAT_DELAY)

    # 위치 제어 시 위치 계산 함수
    def _calc_move_pos(self, servo_id: int):
        current_pos = self.vars.shm_data[f'servo_{servo_id}']['variables']['current_position']
        current_vel = self.vars.shm_data[f'servo_{servo_id}']['variables']['current_velocity']
        target_pos = self.vars.shm_data[f'servo_{servo_id}']['variables']['target_position']
        target_vel = self.vars.shm_data[f'servo_{servo_id}']['variables']['target_velocity']
        last_time = self.vars.shm_data[f'servo_{servo_id}']['variables']['last_time']

        now = time.time_ns()
        dt = (now - last_time) / 1_000_000_000 # 실제 경과 시간
        self.vars.shm_data[f'servo_{servo_id}']['variables']['last_time'] = now

        # 1. 남은 거리 계산
        dist = target_pos - current_pos
        direction = dist // abs(dist) if dist != 0 else 0

        # 2. 감속 시작 시점 계산 (v^2 = 2as 공식 활용)
        stopping_dist = (current_vel ** 2) / (2 * SERVO_ACCEL)

        # 3. 속도 결정 (가속, 감속, 정속 분기)
        if abs(dist) <= stopping_dist:
            # 감속 구간
            current_vel -= SERVO_ACCEL * dt * direction
            current_vel = max(0, direction * current_vel) * direction
        else:
            # 가속 구간
            current_vel += SERVO_ACCEL * dt * direction
            # 속도 제한
            current_vel = min(target_vel, abs(current_vel)) * direction

        # 4. 차기 위치 계산 및 전송
        current_pos += current_vel * dt

        # 목표 위치에 거의 다 왔을 경우 목표 위치 값으로 고정 이동
        if abs(target_pos - current_pos) < (target_vel * dt * 0.5):
            current_pos = target_pos
            current_vel = 0

        # 연산 결과를 output_pdo에 쓰기
        self.vars.shm_data[f'servo_{servo_id}']['output_pdo']['control_word'] = 0x000F
        self.vars.shm_data[f'servo_{servo_id}']['output_pdo']['drive_mode'] = 8
        self.vars.shm_data[f'servo_{servo_id}']['output_pdo']['target_position'] = \
            get_servo_unmodified_value(current_pos)

        # 다음 업데이트 주기에 사용할 수 있도록 현재 계산된 값 저장
        self.vars.shm_data[f'servo_{servo_id}']['variables']['current_position'] = current_pos
        self.vars.shm_data[f'servo_{servo_id}']['variables']['current_velocity'] = current_vel

        # 도달 판정시 종료
        if abs(target_pos - current_pos) < SERVO_IN_POS_WIDTH:
            self.vars.shm_data[f'servo_{servo_id}']['variables']['state'] = \
                OperationMode.SERVO_READY

    # 원점 복귀 완료 시 state를 READY로 전환
    def _homing_check(self, servo_id: int):
        cur_state = self.vars.shm_data[f'servo_{servo_id}']['input_pdo']['status_word']
        cur_pos = self.vars.shm_data[f'servo_{servo_id}']['input_pdo']['actual_position']
        cur_pos = int(round(get_servo_modified_value(cur_pos)))

        homing_mask = 0x1400 # 12번과 10번 비트가 1인 경우 원점 복귀 완료
        if (cur_state & homing_mask) == homing_mask and abs(cur_pos) < SERVO_IN_POS_WIDTH:
            self.vars.shm_data[f'servo_{servo_id}']['variables']['state'] = \
                OperationMode.SERVO_READY
            log(f"[INFO] servo {servo_id} homing completed")

    def _servo_state_check(self, servo_id: int):
        init_step = self.vars.shm_data[f'servo_{servo_id}']['variables']['init_step']
        if init_step == 0:
            log(f"servo {servo_id} init shutdown")
            # 동작 실행 전에 한 번 셧다운을 해줘야 이후 정상작동함
            self.vars.shm_data[f'servo_{servo_id}']['output_pdo']['control_word'] = 0x0006
            self.vars.shm_data[f'servo_{servo_id}']['variables']['init_step'] = 1
            self.vars.shm_data[f'servo_{servo_id}']['variables']['last_time'] = time.time_ns()
            return

        # 5 주기 대기 후 원점 복귀
        last_time = self.vars.shm_data[f'servo_{servo_id}']['variables']['last_time']
        cur_time = time.time_ns()
        if init_step == 1 and cur_time - last_time > ETHERCAT_DELAY * 5 * 1_000_000:
            log(f"servo {servo_id} init homing")
            # 서보 원점 복귀
            self.vars.shm_data[f'servo_{servo_id}']['output_pdo']['control_word'] = 0x001F
            self.vars.shm_data[f'servo_{servo_id}']['output_pdo']['drive_mode'] = 6
            self.vars.shm_data[f'servo_{servo_id}']['variables']['state'] = \
                OperationMode.SERVO_HOMING
            self.vars.shm_data[f'servo_{servo_id}']['variables']['init_step'] = 2

        cur_state = self.vars.shm_data[f'servo_{servo_id}']['variables']['state']

        status_word = self.vars.shm_data[f'servo_{servo_id}']['input_pdo']['status_word']
        if not check_mask(status_word, StatusMask.STATUS_OPERATION_ENABLED):
            # 서보 ON이 아님
            return

        if cur_state == OperationMode.SERVO_HOMING:
            self._homing_check(servo_id)
            return

        # update realtime position
        if cur_state == OperationMode.SERVO_CSP:
            self._calc_move_pos(servo_id)

    def _servo_worker(self, servo_id: int, servo: SlaveInfo):
        # update status
        with servo.pdo_lock:
            sync_shared_memory(
                self.vars.shm_data[f'servo_{servo_id}']['input_pdo'],
                servo.slave.input
            )

        self._servo_state_check(servo_id)

        with servo.pdo_lock:
            servo.slave.output = self.vars.shm_data[f'servo_{servo_id}']['output_pdo'].tobytes()

    def _update_input(self, module: SlaveInfo):
        with module.pdo_lock:
            self.vars.shm_data['total_input'] = np.frombuffer(module.slave.input, dtype='<u4')[0]

    def _update_output(self, module: SlaveInfo):
        with module.pdo_lock:
            module.slave.output = self.vars.shm_data['total_output'].tobytes()

    def _input_worker(self, module: SlaveInfo):
        # update status
        self._update_input(module)

    def _output_worker(self, module: SlaveInfo):
        # update status
        self._update_output(module)
# endregion

# region PDO setting
    # 서보 드라이브 셋업
    def _setup_servo_drive(self, slave_pos):
        slave = self.vars.master.slaves[slave_pos]
        try:
            # 위치 오차 범위 설정: 초기값이 매뉴얼과 다르게 적은 값으로 들어가 있어서 설정해줘야 함
            slave.sdo_write(0x6065, 0, struct.pack('<I', 5242880))

            # homing 방법 설정: 역방향 운전하면서 원점 스위치에 의해 원점 복귀
            # home 오프셋(0x607C) 지정해야 할지? 지정하는 경우 원점 스위치 on 시 오프셋 만큼 이동하여 원점 잡음
            slave.sdo_write(0x6098, 0, struct.pack('<b', 28))

            # RxPDO(master -> slave) 설정
            # sync manager 2에 RxPDO 맵으로 사용할 오브젝트의 인덱스 할당
            slave.sdo_write(EC_RX_INDEX, 0, struct.pack("<BxH", 1, SERVO_RX_MAP))

            # RxPDO 맵에 RxPDO 구성을 매핑
            rx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(SERVO_RX))]),
                len(SERVO_RX),
                *SERVO_RX
            )
            slave.sdo_write(SERVO_RX_MAP, 0, rx_bytes, ca=True)

            # TxPDO(slave -> master) 설정
            # sync manager 3에 TxPDO 맵으로 사용할 오브젝트의 인덱스 할당
            slave.sdo_write(EC_TX_INDEX, 0, struct.pack("<BxH", 1, SERVO_TX_MAP))

            # TxPDO 맵에 TxPDO 구성을 매핑
            tx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(SERVO_TX))]),
                len(SERVO_TX),
                *SERVO_TX
            )
            slave.sdo_write(SERVO_TX_MAP, 0, tx_bytes, ca=True)

        except Exception as e:
            log(f"[ERROR] EtherCAT slave {slave_pos} (servo) PDO setting error: {e}")

    # IO 모듈 셋업
    def _setup_input_module(self, slave_pos):
        slave = self.vars.master.slaves[slave_pos]
        try:
            # 입력 모듈은 TxPDO만 존재하므로 RxPDO 제거
            slave.sdo_write(EC_RX_INDEX, 0, struct.pack('<B', 0))

            # TxPDO(slave -> master) 설정
            slave.sdo_write(EC_TX_INDEX, 0, struct.pack("<BxH", 1, INPUT_TX_MAP))

            tx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(INPUT_TX))]),
                len(INPUT_TX),
                *INPUT_TX
            )
            slave.sdo_write(INPUT_TX_MAP, 0, tx_bytes, ca=True)

        except Exception as e:
            log(f"[ERROR] EtherCAT slave {slave_pos} (input module) PDO setting error: {e}")

    def _setup_output_module(self, slave_pos):
        slave = self.vars.master.slaves[slave_pos]
        try:
            # RxPDO(master -> slave) 설정
            slave.sdo_write(EC_RX_INDEX, 0, struct.pack("<BxH", 1, OUTPUT_RX_MAP))

            rx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(OUTPUT_RX))]),
                len(OUTPUT_RX),
                *OUTPUT_RX
            )
            slave.sdo_write(OUTPUT_RX_MAP, 0, rx_bytes, ca=True)

            # 출력 모듈은 RxPDO만 존재하므로 TxPDO 제거
            slave.sdo_write(EC_TX_INDEX, 0, struct.pack('<B', 0))

        except Exception as e:
            log(f"[ERROR] EtherCAT slave {slave_pos} (output module) PDO setting error: {e}")
# endregion

# region emergency functions
    # 메일박스로 긴급 호출 시 콜백 함수
    def _emcy_callback_servo(self, msg):
        log(f"[ERROR] servo emergency: {msg}")

    def _emcy_callback_input(self, msg):
        log(f"[ERROR] input emergency: {msg}")

    def _emcy_callback_output(self, msg):
        log(f"[ERROR] output emergency: {msg}")
# endregion
# endregion
