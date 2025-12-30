import pysoem
import threading
import time
import struct

from typing import Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from src.utils.config_util import *
from src.utils.logger import log

@dataclass
class SlaveInfo:
    slave: pysoem.CdefSlave
    input: bytearray | None = None
    output: bytearray | None = None
    worker: threading.Thread | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    tasks: list = field(default_factory=list)
    variables: dict = field(default_factory=dict)

class EtherCATManager():
    _initialized = False
    app = None

    def __init__(self, app):
        if not self._initialized:
            self.app = app

            self.stop_event = threading.Event()
            self.recv = 0
            self.master = pysoem.Master()
            self.master.in_op = False
            self.master.do_check_state = False

            self.tasks = []
            self.prev_input = []
            self.input_bit_functions = {
                INPUT_BIT.MODE_SELECT: self.mode_select,
                INPUT_BIT.AUTO_RUN: self.auto_mode_run,
                INPUT_BIT.AUTO_STOP: self.auto_mode_stop,
                INPUT_BIT.RESET_ALARM: self.reset_alarm,
                INPUT_BIT.EMERGENCY_STOP: self.emergency_stop,
                INPUT_BIT.SERVO_HOMING: self.all_servo_homing,
                INPUT_BIT.FEEDER_OUTPUT: self.feeder_output,
            }

            self._initialized = True

    def connect(self):
        try:
            self.master.open(IF_NAME)
            if not self.master.config_init() > 0:
                raise Exception("[WARNING] EtherCAT Slaves not found")

            self.servo_drives: list[SlaveInfo] = []
            self.input_modules: list[SlaveInfo] = []
            self.output_modules: list[SlaveInfo] = []
            for slave in self.master.slaves:
                if slave.man == LS_VENDOR_ID:
                    # config_func는 마스터의 config_map 함수 실행 시 실행됨 -> PDO 매핑을 반드시 해야 함
                    slave_info = SlaveInfo(slave=slave)
                    if slave.id == L7NH_PRODUCT_CODE:
                        slave.config_func = self.setup_servo_drive
                        slave.add_emergency_callback(self.emcy_callback_servo)
                        self.servo_drives.append(slave_info)
                    elif slave.id == D232A_PRODUCT_CODE:
                        slave.config_func = self.setup_input_module
                        slave.add_emergency_callback(self.emcy_callback_input)
                        self.input_modules.append(slave_info)
                    elif slave.id == TR32KA_PRODUCT_CODE:
                        slave.config_func = self.setup_output_module
                        slave.add_emergency_callback(self.emcy_callback_output)
                        self.output_modules.append(slave_info)
                    else:
                        self.master.close()
                        raise Exception("[WARNING] unexpected slave layout")
                else:
                    self.master.close()
                    raise Exception("[WARNING] unexpected slave layout")

                slave.is_lost = False

            self.master.config_map()
            if self.master.state_check(pysoem.SAFEOP_STATE, timeout=50_000) != pysoem.SAFEOP_STATE:
                self.master.close()
                raise Exception("[ERROR] not all slaves reached SAFEOP state")
            
            for servo in self.servo_drives:
                servo.input = servo.slave.input
                servo.output = servo.slave.output
            
            for module in self.input_modules:
                module.input = module.slave.input
            
            for module in self.output_modules:
                module.output = module.slave.output

            # DC(Distributed Clock) 동기화
            # slave.dc_sync(act=True, sync0_cycle_time=1_000_000) # 1,000,000 ns = 1 ms
        except Exception as e:
            log(f"{e}")

        self.run()
    
    def run(self):
        try:
            self.master.state = pysoem.OP_STATE

            # send one valid process data
            self.master.send_processdata()
            self.master.receive_processdata(timeout=2000)

            # request OP STATE for all slaves
            self.master.write_state()

            op_state_flag = False
            for i in range(40):
                self.master.state_check(pysoem.OP_STATE, timeout=50_000)
                if self.master.state == pysoem.OP_STATE:
                    op_state_flag = True
                    break

            self.check_thread = threading.Thread(target=self._check_slave_loop)
            self.check_thread.start()
            self.pd_thread = threading.Thread(target=self._process_data_loop)
            self.pd_thread.start()

            if op_state_flag:
                self.master.in_op = True
                for i, servo in enumerate(self.servo_drives):
                    servo.worker = threading.Thread(target=self._servo_worker, args=(i,), daemon=True)
                    servo.worker.start()
                for i, module in enumerate(self.input_modules):
                    module.worker = threading.Thread(target=self._input_worker, args=(i,), daemon=True)
                    module.worker.start()
                for i, module in enumerate(self.output_modules):
                    module.worker = threading.Thread(target=self._output_worker, args=(i,), daemon=True)
                    module.worker.start()
        except Exception as e:
            log(f"[ERROR] EtherCAT runtime error: {e}")

    def disconnect(self):
        print("EtherCAT disconnect start")
        try:
            self.stop_event.set()

            if hasattr(self, 'task_thread') and self.task_thread.is_alive():
                print("[INFO] process task thread to terminate...")
                self.task_thread.join(timeout=5)
                if self.task_thread.is_alive():
                    print("[WARNING] process task thread did not terminate properly")

            if hasattr(self, 'check_thread') and self.check_thread.is_alive():
                print("[INFO] slave check thread to terminate...")
                self.check_thread.join(timeout=5)
                if self.check_thread.is_alive():
                    print("[WARNING] check_thread did not terminate properly")

            if hasattr(self, 'pd_thread') and self.pd_thread.is_alive():
                print("[INFO] process data thread to terminate...")
                self.pd_thread.join(timeout=5)
                if self.pd_thread.is_alive():
                    print("[WARNING] process data thread did not terminate properly")

            # 종료 시 모든 슬레이브를 INIT STATE로 전환
            self.master.state = pysoem.INIT_STATE
            self.master.write_state()

            self.master.close()
        except Exception as e:
            log(f"[ERROR] EtherCAT disconnection error: {e}")

# region threads
    # PDO 송수신 스레드
    def _process_data_loop(self):
        while not self.stop_event.is_set():
            for servo in self.servo_drives:
                with servo.lock:
                    servo.slave.output = bytes(servo.output)

            for module in self.output_modules:
                with module.lock:
                    module.slave.output = bytes(module.output)

            self.master.send_processdata()
            self.recv = self.master.receive_processdata(timeout=100_000)
            if not self.recv == self.master.expected_wkc:
                log("[WARNING] incorrect wkc")

            for servo in self.servo_drives:
                with servo.lock:
                    servo.input = servo.slave.input

            for module in self.input_modules:
                with module.lock:
                    module.input = module.slave.input

            time.sleep(ETHERCAT_DELAY)

    @staticmethod
    def _check_slave(slave, pos):
        app = EtherCATManager.app
        if slave.state == (pysoem.SAFEOP_STATE + pysoem.STATE_ERROR):
            if app:
                app.on_log(f"[ERROR] slave {pos} is in SAFE_OP + ERROR, attempting ack.")
            slave.state = pysoem.SAFEOP_STATE + pysoem.STATE_ACK
            slave.write_state()
        elif slave.state == pysoem.SAFEOP_STATE:
            if app:
                app.on_log(f"WARNING : slave {pos} is in SAFE_OP, try change to OPERATIONAL.")
            slave.state = pysoem.OP_STATE
            slave.write_state()
        elif slave.state > pysoem.NONE_STATE:
            if slave.reconfig():
                slave.is_lost = False
                if app:
                    app.on_log(f"MESSAGE : slave {pos} reconfigured")
        elif not slave.is_lost:
            slave.state_check(pysoem.OP_STATE)
            if slave.state == pysoem.NONE_STATE:
                slave.is_lost = True
                if app:
                    app.on_log(f"ERROR : slave {pos} lost")
        if slave.is_lost:
            if slave.state == pysoem.NONE_STATE:
                if slave.recover():
                    slave.is_lost = False
                    if app:
                        app.on_log(f"MESSAGE : slave {pos} recovered")
            else:
                slave.is_lost = False
                if app:
                    app.on_log(f"MESSAGE : slave {pos} found")
    
    # 슬레이브 상태 체크 스레드
    def _check_slave_loop(self):
        while not self.stop_event.is_set():
            if self.master.in_op and ((self.recv < self.master.expected_wkc) or self.master.do_check_state):
                self.master.do_check_state = False
                self.master.read_state()
                for i, slave in enumerate(self.master.slaves):
                    if slave.state != pysoem.OP_STATE:
                        self.master.do_check_state = True
                        EtherCATManager._check_slave(slave, i)
                if not self.master.do_check_state:
                    log("[INFO] OK : all slaves resumed OPERATIONAL.")
            time.sleep(ETHERCAT_DELAY)

    # task 예약
    def _reserve_task(self, slave: SlaveInfo, delay: float, func: Callable, *args):
        time_after = datetime.now() + timedelta(seconds=delay)
        with slave.lock:
            slave.tasks.append((time_after, func, args))

    # 위치 제어 시 위치 계산 함수
    def _calc_move_pos(self, servo: SlaveInfo):
        with servo.lock:
            current_pos = servo.variables['current_pos']
            current_vel = servo.variables['current_vel']
            target_pos = servo.variables['target_pos']
            target_vel = servo.variables['target_vel']
            last_time = servo.variables['last_time']
        now = time.time()
        dt = now - last_time # 실제 경과 시간
        with servo.lock:
            servo.variables['last_time'] = now

        # 1. 남은 거리 계산
        dist = target_pos - current_pos
        direction = dist // abs(dist)

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

        # _set_servo_rx_pdo 내에서 lock 처리 및 스케일 연산 처리 하고 있음
        self._set_servo_rx_pdo(servo, 0x000F, 8, current_pos)

        # 다음 업데이트 주기에 사용할 수 있도록 현재 계산된 값 저장
        with servo.lock:
            servo.variables['current_pos'] = current_pos
            servo.variables['current_vel'] = current_vel

        # 도달 판정시 종료
        if abs(target_pos - current_pos) < SERVO_IN_POS_WIDTH:
            with servo.lock:
                servo.variables['state'] = SERVO_STATE.SERVO_READY
    
    # 원점 복귀 완료 시 state를 READY로 전환
    def _homing_check(self, servo: SlaveInfo):
        try:
            with servo.lock:
                cur_state = servo.input[0:2]
                cur_pos = servo.input[3:7]
            cur_state = int.from_bytes(cur_state, 'little')
            cur_pos = int(round(get_servo_modified_value(int.from_bytes(cur_pos, 'little', signed=True))))

            homing_mask = 0x1400 # 12번과 10번 비트가 1인 경우 원점 복귀 완료
            if (cur_state & homing_mask) == homing_mask and abs(cur_pos) < SERVO_IN_POS_WIDTH:
                with servo.lock:
                    servo.variables['state'] = SERVO_STATE.SERVO_READY
        except Exception as e:
            log(f"[ERROR] homing check failed: {e}")

    def _run_tasks(self, slave: SlaveInfo):
        try:
            current_time = datetime.now()
            with slave.lock:
                for i, task in enumerate(slave.tasks):
                    if current_time > task[0]:
                        task[1](*task[2])
                        del slave.tasks[i]
        except Exception as e:
            log(f"[ERROR] run slave tasks failed: {e}")

    def _servo_worker(self, index: int):
        servo = self.servo_drives[index]
        servo.variables['state'] = SERVO_STATE.SERVO_INIT

        # 동작 실행 전에 한 번 셧다운을 해줘야 이후 정상작동함
        self.servo_shutdown(index)
        time.sleep(0.1)

        # 서보 원점 복귀
        self.servo_homing(index)

        while not self.stop_event.is_set():
            # update status
            tx_pdo = self.update_servo_values(index)
            with servo.lock:
                cur_state = servo.variables['state']

            if cur_state == SERVO_STATE.SERVO_SHUTDOWN:
                continue

            if cur_state == SERVO_STATE.SERVO_HOMING:
                self._homing_check(servo)
                continue

            # update realtime position
            if cur_state == SERVO_STATE.SERVO_CSP:
                self._calc_move_pos(servo)

            # run tasks with delay
            self._run_tasks(servo)

            time.sleep(ETHERCAT_DELAY)

    def _input_bit_check(self, module: SlaveInfo, total_input: int):
        try:
            prev_input = module.variables.get('prev_input', 0)
            _changed = prev_input ^ total_input
            if _changed != 0:
                for _bit_mask in INPUT_BIT:
                    if _changed & _bit_mask:
                        is_on = bool(total_input&_bit_mask)
                        self.input_bit_functions[_bit_mask](is_on)
                module.variables['prev_input'] = total_input
        except Exception as e:
            log(f"[ERROR] input bit check failed: {e}")

    def _input_worker(self, input_id: int):
        module = self.input_modules[input_id]
        while not self.stop_event.is_set():
            # update status
            total_input = self.update_input(input_id)
            self._input_bit_check(module, total_input)

            time.sleep(ETHERCAT_DELAY)
    
    def _output_worker(self, output_id: int):
        module = self.output_modules[output_id]
        while not self.stop_event.is_set():
            # update status
            self.update_output(output_id)

            # run tasks with delay
            self._run_tasks(module)

            time.sleep(ETHERCAT_DELAY)

# endregion

# region PDO setting
    # 서보 드라이브 셋업
    def setup_servo_drive(self, slave_pos):
        slave = self.master.slaves[slave_pos]
        try:
            # 회전 방향 변경(0: ccw, 1: cw)
            # slave.sdo_write(0x2004, 0, struct.pack('<H', 1))

            # 위치 오차 범위 설정: 초기값이 매뉴얼과 다르게 적은 값으로 들어가 있어서 설정해줘야 함
            slave.sdo_write(0x6065, 0, struct.pack('<I', 5242880))

            # 센서 1~3(POT, NOT, HOME) A->B접점 방식 변경
            # for i in range(3):
            #     slave.sdo_write(0x2200+i, 0, struct.pack('<H', 0x8001+i))

            # homing 방법 설정: 역방향 운전하면서 원점 스위치에 의해 원점 복귀
            # home 오프셋(0x607C) 지정해야 할지? 지정하는 경우 원점 스위치 on 시 오프셋 만큼 이동하여 원점 잡음
            slave.sdo_write(0x6098, 0, struct.pack('<b', -5))

            # RxPDO(master -> slave) 설정
            # sync manager 2에 RxPDO 맵으로 사용할 오브젝트의 인덱스 할당
            rx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(SERVO_RX_MAP))]),
                len(SERVO_RX_MAP),
                *SERVO_RX_MAP
            )
            slave.sdo_write(index=EC_RX_INDEX, subindex=0, data=rx_map_bytes, ca=True)

            # RxPDO 맵에 RxPDO 구성을 매핑
            rx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(SERVO_RX))]),
                len(SERVO_RX),
                *SERVO_RX
            )
            slave.sdo_write(index=SERVO_RX_MAP[0], subindex=0, data=rx_bytes, ca=True)

            # TxPDO(slave -> master) 설정
            # sync manager 3에 TxPDO 맵으로 사용할 오브젝트의 인덱스 할당
            tx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(SERVO_TX_MAP))]),
                len(SERVO_TX_MAP),
                *SERVO_TX_MAP
            )
            slave.sdo_write(index=EC_TX_INDEX, subindex=0, data=tx_map_bytes, ca=True)

            # TxPDO 맵에 TxPDO 구성을 매핑
            tx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(SERVO_TX))]),
                len(SERVO_TX),
                *SERVO_TX
            )
            slave.sdo_write(index=SERVO_TX_MAP[0], subindex=0, data=tx_bytes, ca=True)

        except Exception as e:
            log(f"[ERROR] EtherCAT PDO setting error: {e}")

    # IO 모듈 셋업
    def setup_input_module(self, slave_pos):
        slave = self.master.slaves[slave_pos]
        try:
            # 입력 모듈은 TxPDO만 존재
            # RxPDO 제거
            slave.sdo_write(index=EC_RX_INDEX, subindex=0, data=struct.pack('<B', 0))
            # TxPDO(slave -> master) 설정
            tx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(INPUT_TX_MAP))]),
                len(INPUT_TX_MAP),
                *INPUT_TX_MAP
            )
            slave.sdo_write(index=EC_TX_INDEX, subindex=0, data=tx_map_bytes, ca=True)

            tx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(INPUT_TX))]),
                len(INPUT_TX),
                *INPUT_TX
            )
            slave.sdo_write(index=INPUT_TX_MAP[0], subindex=0, data=tx_bytes, ca=True)

        except Exception as e:
            log(f"[ERROR] EtherCAT PDO setting error: {e}")

    def setup_output_module(self, slave_pos):
        slave = self.master.slaves[slave_pos]
        try:
            # 출력 모듈은 RxPDO만 존재
            # RxPDO(master -> slave) 설정
            rx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(OUTPUT_RX_MAP))]),
                len(OUTPUT_RX_MAP),
                *OUTPUT_RX_MAP
            )
            slave.sdo_write(index=EC_RX_INDEX, subindex=0, data=rx_map_bytes, ca=True)

            rx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(OUTPUT_RX))]),
                len(OUTPUT_RX),
                *OUTPUT_RX
            )
            slave.sdo_write(index=OUTPUT_RX_MAP[0], subindex=0, data=rx_bytes, ca=True)

            # TxPDO 제거
            slave.sdo_write(index=EC_TX_INDEX, subindex=0, data=struct.pack('<B', 0))

        except Exception as e:
            log(f"[ERROR] EtherCAT PDO setting error: {e}")
# endregion

# region servo functions
    # RxPDO 설정
    def _set_servo_rx_pdo(self, servo: SlaveInfo, ctrl: int = 0, mode: int = 0, pos: int = 0, v: int = 0):
        try:
            buf = bytearray(11)
            buf = struct.pack("<H", ctrl) + struct.pack("b", mode) + struct.pack("<i", get_servo_unmodified_value(pos)) + struct.pack("<i", get_servo_unmodified_value(v))
            with servo.lock:
                servo.output = buf
        except Exception as e:
            log(f"[ERROR] servo RxPDO set failed: {e}")

    def _get_servo_tx_pdo(self, servo: SlaveInfo):
        with servo.lock:
            temp = servo.input
        ret = struct.unpack('<HbiiHH', temp)
        return ret

    def update_servo_values(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            tx_pdo = self._get_servo_tx_pdo(servo)
            self.app.on_update_servo_status(servo_id, tx_pdo)
            return tx_pdo
        except Exception as e:
            log(f"[ERROR] servo {servo_id} TxPDO read failed {e}")
            return None

    # 서보 on/off
    def servo_onoff(self, servo_id: int, onoff: bool):
        try:
            servo = self.servo_drives[servo_id]
            if onoff:
                self._set_servo_rx_pdo(servo, 0x000F)
            else:
                self._set_servo_rx_pdo(servo, 0x0106)
        except Exception as e:
            log(f"[ERROR] servo on/off failed: {e}")

    # 원점 오프셋 지정
    def servo_set_home(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            with servo.lock:
                temp = servo.input[4:8]
            cur_pos = int.from_bytes(temp, 'little', signed=True)
            servo.sdo_write(0x607C, 0, struct.pack('<i', get_servo_unmodified_value(cur_pos)))
        except Exception as e:
            log(f"[ERROR] servo set home failed: {e}")

    # 하한 설정
    def servo_set_min_limit(self, servo_id: int, pos: int):
        try:
            servo = self.servo_drives[servo_id]
            servo.sdo_write(0x607D, 1, struct.pack('<i', get_servo_unmodified_value(pos)))
        except Exception as e:
            log(f"[ERROR] servo set minimum position limit failed: {e}")

    # 상한 설정
    def servo_set_max_limit(self, servo_id: int, pos: int):
        try:
            servo = self.servo_drives[servo_id]
            servo.sdo_write(0x607D, 2, struct.pack('<i', get_servo_unmodified_value(pos)))
        except Exception as e:
            log(f"[ERROR] servo set maximum position limit failed: {e}")

    # 원점 복귀
    def servo_homing(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            self._set_servo_rx_pdo(servo, 0x001F, 6)
            with servo.lock:
                servo.variables['state'] = SERVO_STATE.SERVO_HOMING
        except Exception as e:
            log(f"[ERROR] servo homing failed: {e}")

    def _start_csp(self, servo_id: int, cur_pos: float, cur_vel: float, tgt_pos: float, tgt_vel: float):
        servo = self.servo_drives[servo_id]
        with servo.lock:
            servo.variables['current_pos'] = cur_pos
            servo.variables['current_vel'] = cur_vel
            servo.variables['target_pos'] = tgt_pos
            servo.variables['target_vel'] = tgt_vel
            servo.variables['last_time'] = time.time()
            servo.variables['state'] = SERVO_STATE.SERVO_CSP

    # 절대 위치 이동
    def servo_move_absolute(self, servo_id: int, pos: float, v: float):
        try:
            log(f"servo_move_absolute({servo_id}, {pos:.1f}, {v:.1f})")
            servo = self.servo_drives[servo_id]
            with servo.lock:
                temp = servo.input[0:2]
            cur_state = int.from_bytes(temp, 'little')
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")

            with servo.lock:
                temp1 = servo.input[3:7]
                temp2 = servo.input[7:11]
            cur_pos = get_servo_modified_value(int.from_bytes(temp1, 'little', signed=True))
            cur_vel = get_servo_modified_value(int.from_bytes(temp2, 'little', signed=True))

            self._start_csp(servo_id, cur_pos, cur_vel, pos, v)
        except Exception as e:
            log(f"[ERROR] servo CSP move failed: {e}")

    # 상대 위치 이동
    def servo_move_relative(self, servo_id: int, dist: float, v: float):
        try:
            servo = self.servo_drives[servo_id]
            with servo.lock:
                temp = servo.input[0:2]
            cur_state = int.from_bytes(temp, 'little')
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")
            
            with servo.lock:
                temp1 = servo.input[3:7]
                temp2 = servo.input[7:11]
            cur_pos = get_servo_modified_value(int.from_bytes(temp1, 'little', signed=True))
            cur_vel = get_servo_modified_value(int.from_bytes(temp2, 'little', signed=True))
            pos = cur_pos + dist

            self._start_csp(servo_id, cur_pos, cur_vel, pos, v)
        except Exception as e:
            log(f"[ERROR] servo CSP move failed: {e}")

    # 속도 이동
    def servo_move_velocity(self, servo_id: int, v:float):
        try:
            servo = self.servo_drives[servo_id]
            with servo.lock:
                temp = servo.input[0:2]
            cur_state = int.from_bytes(temp, 'little')
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")

            self._set_servo_rx_pdo(servo, 0x000F, 9, 0, v)
            with servo.lock:
                servo.variables['state'] = SERVO_STATE.SERVO_CSV
        except Exception as e:
            log(f"[ERROR] servo CSV move failed: {e}")

    # 정지(대기 상태로 전환)
    def servo_halt(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            self._set_servo_rx_pdo(servo, 0x010F)
            with servo.lock:
                servo.variables['state'] = SERVO_STATE.SERVO_READY
        except Exception as e:
            log(f"[ERROR] halt failed: {e}")

    def servo_reset(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            self._set_servo_rx_pdo(servo, 0x008F)
            with servo.lock:
                servo.variables['state'] = SERVO_STATE.SERVO_READY
        except Exception as e:
            log(f"[ERROR] reset failed: {e}")

    def servo_shutdown(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            self._set_servo_rx_pdo(servo, 0x0006)
            with servo.lock:
                servo.variables['state'] = SERVO_STATE.SERVO_SHUTDOWN
        except Exception as e:
            log(f"[ERROR] shutdown failed: {e}")

# endregion

# region IO functions
    # IO 기능
    def update_input(self, input_id: int) -> int:
        module = self.input_modules[input_id]
        with module.lock:
            temp = module.input
        total_input = int.from_bytes(temp, 'little')

        self.app.on_update_input_status(input_id, total_input)
        return total_input

    def update_output(self, output_id: int):
        module = self.output_modules[output_id]
        with module.lock:
            temp = module.output
        total_output = int.from_bytes(temp, 'little')

        self.app.on_update_output_status(output_id, total_output)

    # 비트 쓰기
    def io_write_bit(self, output_id: int, offset_dict: dict[int, bool]):
        """
        offset번째 비트의 값을 0/1로 변경
        
        :param self:
        :param output_id: 출력 모듈 번호(0)
        :type output_id: int
        :param offset_dict: 변경할 비트 인덱스(0~31)와 데이터의 딕셔너리
        :type offset_dict: dict[int, bool]
        """
        for _offset, _ in offset_dict.items():
            if _offset > 31 or _offset < 0:
                log(f"[WARNING] bit offset must be integer between 0 and 31. current value: {_offset}")
                return

        try:
            module = self.output_modules[output_id]
            with module.lock:
                temp = module.output
            total_bits = int.from_bytes(temp, 'little')
    
            for _offset, _data in offset_dict.items():
                target_bit = 1 << _offset
                if _data:
                    total_bits |= target_bit
                else:
                    total_bits &= ~target_bit

            ret = struct.pack('<I', total_bits)
            with module.lock:
                module.output = ret
        except Exception as e:
            log(f"[ERROR] write output bit failed: {e}")

    def airknife_on(self, output_id: int, air_num: int, on_term: int):
        """
        에어나이프 켜기
        
        :param self:
        :param output_id: 출력 모듈 번호(0)
        :type output_id: int
        :param air_num: 에어나이프 번호(1~3)
        :type air_num: int
        :param on_term: 에어 출력 시간값
        :type on_term: int
        """
        try:
            self.io_write_bit(output_id, {air_num+19: True})
            log(f"[INFO] Airknife {air_num} on")
            module = self.output_modules[output_id]
            self._reserve_task(module, on_term/1000, self.airknife_off, output_id, air_num)
        except Exception as e:
            log(f"[ERROR] airknife on failed: {e}")

    def airknife_off(self, output_id: int, air_num: int):
        """
        에어나이프 끄기
        
        :param self:
        :param output_id: 출력 모듈 번호(0)
        :type output_id: int
        :param air_num: 에어나이프 번호(1~3)
        :type air_num: int
        """
        try:
            self.io_write_bit(output_id, {air_num+19: False})
            log(f"[INFO] Airknife {air_num} off")
            self.app.on_airknife_off(air_num)
        except Exception as e:
            log(f"[ERROR] airknife off failed: {e}")

    def mode_select(self, is_on: bool):
        try:
            if self.app.auto_mode ^ is_on:
                self.auto_mode_stop(True)
                _dict = { 0: is_on, 1: is_on }
                self.io_write_bit(0, _dict)
                self.app.set_auto_mode(is_on)
        except Exception as e:
            log(f"[ERROR] mode selection failed: {e}")

    def auto_mode_run(self, is_on: bool):
        if not self.app.auto_mode:
            return
        
        try:
            if not self.app.auto_run and is_on:
                _dict = { 2: True, 3: False }
                self.io_write_bit(0, _dict)
                self.app.auto_mode_run()
        except Exception as e:
            log(f"[ERROR] automode start failed: {e}")

    def auto_mode_stop(self, is_on: bool):
        if not self.app.auto_mode:
            return
        
        try:
            if self.app.auto_run and is_on:
                _dict = { 2: False, 3: True }
                self.io_write_bit(0, _dict)
                self.app.auto_mode_stop()
        except Exception as e:
            log(f"[ERROR] automode stop failed: {e}")
        
    def reset_alarm(self, is_on: bool):
        try:
            if is_on:
                _dict = { 4: False, 5: False }
                self.io_write_bit(0, _dict)
                self.app.reset_alarm()
        except Exception as e:
            log(f"[ERROR] alarm reset failed: {e}")

    def emergency_stop(self, is_on: bool):
        try:
            if is_on:
                self.app.emergency_stop()
        except Exception as e:
            log(f"[ERROR] emergency stop failed: {e}")
    
    def all_servo_homing(self, is_on: bool):
        try:
            if is_on:
                self.app.all_servo_homing()
        except Exception as e:
            log(f"[ERROR] all servo homing failed: {e}")
    
    def feeder_output(self, is_on: bool):
        if is_on:
            self.app.feeder_output()

    def hopper_empty(self, is_on: bool):
        if is_on:
            self.app.hopper_empty()

    def hopper_full(self, is_on: bool):
        if is_on:
            self.app.hopper_full()

# endregion

# region emergency functions
    # 메일박스로 긴급 호출 시 콜백 함수
    def emcy_callback_servo(self, msg):
        log(f"[ERROR] servo emergency: {msg}")

    def emcy_callback_input(self, msg):
        log(f"[ERROR] input emergency: {msg}")

    def emcy_callback_output(self, msg):
        log(f"[ERROR] output emergency: {msg}")