import pysoem
import threading
import asyncio
import time
import queue
import struct

from typing import Any, Optional, Dict
from concurrent.futures import ThreadPoolExecutor

from src.config_util import *

class EtherCATManager():
    _lock = threading.Lock()
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
            self._expected_slave_layout = {
                0: EtherCATDevice("D232A", LS_VENDOR_ID, D232A_PRODUCT_CODE, self.setup_input_module),
                1: EtherCATDevice("TR32KA", LS_VENDOR_ID, TR32KA_PRODUCT_CODE, self.setup_output_module),
                2: EtherCATDevice("L7NH", LS_VENDOR_ID, L7NH_PRODUCT_CODE, self.setup_servo_drive),
                3: EtherCATDevice("L7NH", LS_VENDOR_ID, L7NH_PRODUCT_CODE, self.setup_servo_drive)
            }

            self.tasks : queue.Queue[Dict] = queue.Queue()
            self._initialized = True

    def connect(self):
        try:
            self.master.open(IF_NAME)
            if not self.master.config_init() > 0:
                raise Exception("[WARNING] EtherCAT Slaves not found")

            self.servo_drives = []
            self.input_modules = []
            self.output_modules = []
            for slave in self.master.slaves:
                if slave.man == LS_VENDOR_ID:
                    # config_func는 마스터의 config_map 함수 실행 시 실행됨 -> PDO 매핑을 반드시 해야 함
                    if slave.id == L7NH_PRODUCT_CODE:
                        slave.config_func = self.setup_servo_drive
                        slave.add_emergency_callback(self.emcy_callback_servo)
                        self.servo_drives.append(slave)
                    elif slave.id == D232A_PRODUCT_CODE:
                        slave.config_func = self.setup_input_module
                        slave.add_emergency_callback(self.emcy_callback_input)
                        self.input_modules.append(slave)
                    elif slave.id == TR32KA_PRODUCT_CODE:
                        slave.config_func = self.setup_output_module
                        slave.add_emergency_callback(self.emcy_callback_output)
                        self.output_modules.append(slave)
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

            # DC(Distributed Clock) 동기화
            # slave.dc_sync(act=True, sync0_cycle_time=1_000_000) # 1,000,000 ns = 1 ms
        except Exception as e:
            self.app.on_log(f"{e}")

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
                self.task_thread = threading.Thread(target=self._process_task_loop)
                self.task_thread.start()
        except Exception as e:
            self.app.on_log(f"[ERROR] EtherCAT runtime error: {e}")

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
            self.app.on_log(f"[ERROR] EtherCAT disconnection error: {e}")

    # PDO 송수신 스레드
    def _process_data_loop(self):
        while not self.stop_event.is_set():
            self.master.send_processdata()
            self.recv = self.master.receive_processdata(timeout=100_000)
            if not self.recv == self.master.expected_wkc:
                self.app.on_log("[WARNING] incorrect wkc")
            
            self.update_io()
            self.update_monitor_values()

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
                    self.app.on_log("[INFO] OK : all slaves resumed OPERATIONAL.")
            time.sleep(ETHERCAT_DELAY)

    # task 실행 스레드
    def _process_task_loop(self):
        self.master.in_op = True

        # 동작 실행 전에 한 번 셧다운을 해줘야 이후 정상작동함
        for i, _ in enumerate(self.servo_drives):
            self.servo_shutdown(i)
        
        while not self.stop_event.is_set():
            
            while not self.tasks.empty():
                task = self.tasks.get()
                # todo: run task function
            
            # 테스트용 출력
            # ret = struct.unpack('<HbiiH', self.servo_drives[0].input)
            # status_word = ret[0]
            # cur_mode = ret[1]
            # cur_pos = ret[2]
            # cur_v = ret[3]
            # err = ret[4]
            # print(f"status:{status_word:016b}, mode:{cur_mode}, pos:{cur_pos}, v:{cur_v}, err:{err:X}")

            # temp2 = int.from_bytes(self.servo_drives[0].sdo_read(0x60F4, 0, 4), 'little', signed=True)
            # print(f"diff: {temp2}")

            time.sleep(1)

    # 서보 드라이브 셋업
    def setup_servo_drive(self, slave_pos):
        slave = self.master.slaves[slave_pos]
        try:
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

            # temp = int.from_bytes(slave.sdo_read(0x6081, 0, 4), 'little')
            # print(f"profile velocity actual value: {temp} modified: {get_servo_modified_value(temp)}")
            

        except Exception as e:
            self.app.on_log(f"[ERROR] EtherCAT PDO setting error: {e}")

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
            self.app.on_log(f"[ERROR] EtherCAT PDO setting error: {e}")

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
            self.app.on_log(f"[ERROR] EtherCAT PDO setting error: {e}")

# region servo functions
    # RxPDO 설정
    def _set_rx_pdo(self, slave, ctrl: int = 0, mode: int = 0, pos: int = 0, v: int = 0):
        buf = bytearray(11)
        buf = struct.pack("<H", ctrl) + struct.pack("b", mode) + struct.pack("<i", get_servo_unmodified_value(pos)) + struct.pack("<i", get_servo_unmodified_value(v))
        slave.output = bytes(buf)

    def update_monitor_values(self):
        def _get_tx_pdo(servo):
            return struct.unpack('<HbiiH', servo.input)

        _data = []
        for servo in self.servo_drives:
            tx_pdo = _get_tx_pdo(servo)
            _data.append(tx_pdo)
        
        self.app.on_update_servo_status(_data)

    # 서보 on/off
    def servo_onoff(self, servo_id: int, onoff: bool):
        try:
            servo = self.servo_drives[servo_id]
            if onoff:
                self._set_rx_pdo(servo, 0x000F)
            else:
                self._set_rx_pdo(servo, 0x0106)
        except Exception as e:
            self.app.on_log(f"[ERROR] servo on/off failed: {e}")

    # 원점 지정
    def servo_set_home(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            # cur_pos = struct.unpack('<i', servo.input[4:8])[0]
            cur_pos = int.from_bytes(servo.input[4:8], 'little', signed=True)
            servo.sdo_write(0x607C, 0, struct.pack('<i', get_servo_unmodified_value(cur_pos)))
        except Exception as e:
            self.app.on_log(f"[ERROR] servo set home failed: {e}")

    # 하한 설정
    def servo_set_min_limit(self, servo_id: int, pos: int):
        try:
            servo = self.servo_drives[servo_id]
            servo.sdo_write(0x607D, 1, struct.pack('<i', get_servo_unmodified_value(pos)))
        except Exception as e:
            self.app.on_log(f"[ERROR] servo set minimum position limit failed: {e}")

    # 상한 설정
    def servo_set_min_limit(self, servo_id: int, pos: int):
        try:
            servo = self.servo_drives[servo_id]
            servo.sdo_write(0x607D, 2, struct.pack('<i', get_servo_unmodified_value(pos)))
        except Exception as e:
            self.app.on_log(f"[ERROR] servo set maximum position limit failed: {e}")

    # 원점 복귀
    def servo_homing(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            cur_pos = int.from_bytes(servo.input[3:7], 'little', signed=True)
            if cur_pos >= 0:
                servo.sdo_write(0x6098, 0, struct.pack('b', 33))
            else:
                servo.sdo_write(0x6098, 0, struct.pack('b', 34))
            threading.Timer(0.01, lambda: self._set_rx_pdo(servo, 0x001F, 6))
        except Exception as e:
            self.app.on_log(f"[ERROR] servo homing failed: {e}")

    # 절대 위치 이동
    def servo_move_absolute(self, servo_id: int, pos: float):
        try:
            servo = self.servo_drives[servo_id]
            # cur_state = struct.unpack('<H', servo.input[0:2])[0]
            cur_state = int.from_bytes(servo.input[0:2], 'little')
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")
            
            self._set_rx_pdo(servo, 0x000F, 8, pos, 0)
        except Exception as e:
            self.app.on_log(f"[ERROR] servo CSP move failed: {e}")

    # 상대 위치 이동
    def servo_move_relative(self, servo_id: int, dist: float):
        try:
            servo = self.servo_drives[servo_id]
            # cur_state = struct.unpack('<H', servo.input[0:2])[0]
            cur_state = int.from_bytes(servo.input[0:2], 'little')
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")
            
            # cur_pos = struct.unpack('<i', servo.input[4:8])[0]
            cur_pos = int.from_bytes(servo.input[4:8], 'little', signed=True)
            pos = cur_pos + dist
            self._set_rx_pdo(servo, 0x000F, 8, pos, 0)
        except Exception as e:
            self.app.on_log(f"[ERROR] servo CSP move failed: {e}")

    # 속도 이동
    def servo_move_velocity(self, servo_id: int, v:float):
        try:
            servo = self.servo_drives[servo_id]
            # cur_state = struct.unpack('<H', servo.input[0:2])[0]
            cur_state = int.from_bytes(servo.input[0:2], 'little')
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")

            self._set_rx_pdo(servo, 0x000F, 9, 0, v)

        except Exception as e:
            self.app.on_log(f"[ERROR] servo CSV move failed: {e}")

    # 정지(대기 상태로 전환)
    def servo_halt(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            # cur_state = struct.unpack('<H', servo.input[0:2])[0]
            cur_state = int.from_bytes(servo.input[0:2], 'little')
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")

            self._set_rx_pdo(servo, 0x010F)

        except Exception as e:
            self.app.on_log(f"[ERROR] halt failed: {e}")

    def servo_reset(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            self._set_rx_pdo(servo, 0x008F)

        except Exception as e:
            self.app.on_log(f"[ERROR] reset failed: {e}")

    def servo_shutdown(self, servo_id: int):
        try:
            servo = self.servo_drives[servo_id]
            self._set_rx_pdo(servo, 0x0006)

        except Exception as e:
            self.app.on_log(f"[ERROR] shutdown failed: {e}")

# endregion

# region IO functions
    # IO 기능
    def update_io(self):
        for _i in self.input_modules:
            for _byte in _i.input:
                continue
            # todo: on 비트에 대한 처리

    # 비트 쓰기
    def io_write_bit(self, output_id: int, byte_offset: int, data: bool):
        module = self.output_modules[output_id]
        tmp = bytearray(module.output)
        tmp[byte_offset] = data
        module.output = tmp

    def airknife_onoff(self, output_id: int, air_num: int, on_term: int):
        """
        airknife_onoff
        
        :param self:
        :param output_id: 출력 모듈 번호(0)
        :type output_id: int
        :param air_num: 에어나이프 번호(1~3)
        :type air_num: int
        :param on_term: 에어 출력 시간값
        :type on_term: int
        """
        try:
            self.io_write_bit(output_id, air_num+19, True)
            threading.Timer(on_term/1000, lambda: self.io_write_bit(output_id, air_num+19, False))
        except Exception as e:
            self.app.on_log(f"[ERROR] airknife onoff failed: {e}")

# endregion

# region emergency functions
    # 메일박스로 긴급 호출 시 콜백 함수
    def emcy_callback_servo(self, msg):
        self.app.on_log(f"[ERROR] servo emergency: {msg}")

    def emcy_callback_input(self, msg):
        self.app.on_log(f"[ERROR] input emergency: {msg}")

    def emcy_callback_output(self, msg):
        self.app.on_log(f"[ERROR] output emergency: {msg}")