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

    def __init__(self, app):
        if not self._initialized:
            self.app = app

            self.master = pysoem.Master()
            self.stop_event = threading.Event()
            
            self.tasks : queue.Queue[Dict] = queue.Queue()
            self._initialized = True

    def connect(self):
        try:
            self.master.open(IF_NAME)
            if not self.master.config_init() > 0:
                raise Exception("[WARNING] EtherCAT Slaves not found")

            self.slaves = []
            for slave in self.master.slaves:
                if slave.man == 30101:
                    if slave.id == 0x00010001:
                        slave.config_func = self.setup_servo_drive
                    elif slave.id == 0x10010002:
                        slave.config_func = self.setup_input_module
                    elif slave.id == 0x10010003:
                        slave.config_func = self.setup_output_module
                    else:
                        self.master.close()
                        raise Exception("[WARNING] unexpected slave layout")
                else:
                    self.master.close()
                    raise Exception("[WARNING] unexpected slave layout")

                self.slaves.append(slave)
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

            self.check_thread = threading.Thread(target=self._check_slave_loop)
            self.check_thread.start()
            self.pd_thread = threading.Thread(target=self._process_data_loop)
            self.pd_thread.start()

            self.master.send_processdata()
            self.master.receive_processdata(timeout=2000)

            self.master.write_state()

            op_state_flag = False
            for i in range(40):
                self.master.state_check(pysoem.OP_STATE, timeout=50_000)
                if self.master.state == pysoem.OP_STATE:
                    op_state_flag = True
                    break

            if op_state_flag:
                self.task_thread = threading.Thread(target=self._process_task_loop)
                self.task_thread.start()
        except Exception as e:
            self.app.on_log(f"[ERROR] EtherCAT runtime error: {e}")
        finally:
            self.disconnect()

    def disconnect(self):
        try:
            self.pd_stop_event.set()
            self.check_stop_event.set()

            self.check_thread.join()
            self.pd_thread.join()

            self.master.state = pysoem.INIT_STATE

            self.master.write_state()
            self.master.close()
        except Exception as e:
            self.app.on_log(f"[ERROR] EtherCAT disconnection error: {e}")

    def _process_data_loop(self):
        while not self.stop_event.is_set():
            self.master.send_processdata()
            self.recv = self.master.receive_processdata(timeout=100_000)
            if not self.rect == self.master.expect_wkc:
                self.app.on_log("[WARNING] incorrect wkc")

            time.sleep(ETHERCAT_DELAY)

    def _check_slave(self, slave, idx):
        if slave.state == (pysoem.SAFEOP_STATE + pysoem.STATE_ERROR):
            self.app.on_log(f"[ERROR] slave {idx} is in SAFE_OP + ERROR, attempting ack.")
            slave.state = pysoem.SAFEOP_STATE + pysoem.STATE_ACK
            slave.write_state()
        elif slave.state == pysoem.SAFEOP_STATE:
            self.app.on_log(f"[WARNING] slave {idx} is in SAFE_OP, try change to OPERATIONAL.")
            slave.state = pysoem.OP_STATE
            slave.write_state()
        elif slave.state > pysoem.NONE_STATE:
            if slave.reconfig():
                slave.is_lost = False
                self.app.on_log(f"[INFO] slave {idx} reconfigured")
        elif not slave.is_lost:
            slave.state_check(pysoem.OP_STATE)
            if slave.state == pysoem.NONE_STATE:
                slave.is_lost = True
                self.app.on_log(f"[ERROR] slave {idx} lost")

        if slave.is_lost:
            if slave.state == pysoem.NONE_STATE:
                if slave.recover():
                    slave.is_lost = False
                    self.app.on_log(f"[INFO] slave {idx} recovered")
            else:
                slave.is_lost = False
                self.app.on_log(f"[INFO] slave {idx} found")
    
    def _check_slave_loop(self):
        while not self.stop_event.is_set():
            if self.master.in_op and ((self._actual_wkc < self.master.expected_wkc) or self.master.do_check_state):
                self.master.do_check_state = False
                self.master.read_state()
                for i, slave in enumerate(self.master.slaves):
                    if slave.state != pysoem.OP_STATE:
                        self.master.do_check_state = True
                        self._check_slave(slave, i)
                if not self.master.do_check_state:
                    self.app.on_log("[INFO] OK : all slaves resumed OPERATIONAL.")
            time.sleep(ETHERCAT_DELAY)

    def _process_task_loop(self):
        self.master.in_op = True
        
        while not self.stop_event.is_set():
            while not self.tasks.empty():
                task = self.tasks.get()
                # todo: run task function

    # 서보 드라이브 셋업
    def setup_servo_drive(self, slave_pos):
        slave = self.master.slaves[slave_pos]
        try:
            # RxPDO(master -> slave) 설정
            rx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(SERVO_RX_MAP))]),
                len(SERVO_RX_MAP),
                *SERVO_RX_MAP
            )
            slave.sdo_write(index=0x1C12, subindex=0, data=rx_map_bytes, ca=True)

            rx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(SERVO_RX))]),
                len(SERVO_RX),
                *SERVO_RX
            )
            slave.sdo_write(index=SERVO_RX_MAP[0], subindex=0, data=rx_bytes, ca=True)

            # TxPDO(slave -> master) 설정
            tx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(SERVO_TX_MAP))]),
                len(SERVO_TX_MAP),
                *SERVO_TX_MAP
            )
            slave.sdo_write(index=0x1C13, subindex=0, data=tx_map_bytes, ca=True)

            tx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(SERVO_TX))]),
                len(SERVO_TX),
                *SERVO_TX
            )
            slave.sdo_write(index=SERVO_TX_MAP[0], subindex=0, data=tx_bytes, ca=True)

        except Exception as e:
            self.app.on_log(f"[ERROR] EtherCAT PDO setting error: {e}")

    # IO 모듈 셋업
    def setup_input_module(self, slave):
        try:
            # RxPDO(master -> slave) 설정
            rx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(IO_RX_MAP))]),
                len(IO_RX_MAP),
                *IO_RX_MAP
            )
            slave.sdo_write(index=0x1C12, subindex=0, data=rx_map_bytes, ca=True)

            rx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(IO_RX))]),
                len(IO_RX),
                *IO_RX
            )
            slave.sdo_write(index=IO_RX_MAP[0], subindex=0, data=rx_bytes, ca=True)

            # TxPDO(slave -> master) 설정
            tx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(IO_TX_MAP))]),
                len(IO_TX_MAP),
                *IO_TX_MAP
            )
            slave.sdo_write(index=0x1C13, subindex=0, data=tx_map_bytes, ca=True)

            tx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(IO_TX))]),
                len(IO_TX),
                *IO_TX
            )
            slave.sdo_write(index=IO_TX_MAP[0], subindex=0, data=tx_bytes, ca=True)

        except Exception as e:
            self.app.on_log(f"[ERROR] EtherCAT PDO setting error: {e}")

    def setup_output_module(self, slave):
        try:
            # RxPDO(master -> slave) 설정
            rx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(IO_RX_MAP))]),
                len(IO_RX_MAP),
                *IO_RX_MAP
            )
            slave.sdo_write(index=0x1C12, subindex=0, data=rx_map_bytes, ca=True)

            rx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(IO_RX))]),
                len(IO_RX),
                *IO_RX
            )
            slave.sdo_write(index=IO_RX_MAP[0], subindex=0, data=rx_bytes, ca=True)

            # TxPDO(slave -> master) 설정
            tx_map_bytes = struct.pack(
                "<Bx" + "".join(["H" for _ in range(len(IO_TX_MAP))]),
                len(IO_TX_MAP),
                *IO_TX_MAP
            )
            slave.sdo_write(index=0x1C13, subindex=0, data=tx_map_bytes, ca=True)

            tx_bytes = struct.pack(
                "<Bx" + "".join(["I" for _ in range(len(IO_TX))]),
                len(IO_TX),
                *IO_TX
            )
            slave.sdo_write(index=IO_TX_MAP[0], subindex=0, data=tx_bytes, ca=True)

        except Exception as e:
            self.app.on_log(f"[ERROR] EtherCAT PDO setting error: {e}")

    # 서보 기능
    # RxPDO 설정
    def _set_rx_pdo(self, slave, ctrl: int = 0, mode: int = 0, pos: int = 0, v: int = 0):
        buf = bytearray(11)
        buf = struct.pack("<H", ctrl) + struct.pack("b", mode) + struct.pack("<i", get_servo_modified_value(pos)) + struct.pack("<i", get_servo_modified_value(v))
        slave.output = bytes(buf)

    # 서보 on/off
    def servo_onoff(self, slave_id: int, onoff: bool):
        try:
            servo = self.slaves[slave_id]
            if onoff:
                self._set_rx_pdo(servo, 0x000F)
            else:
                self._set_rx_pdo(servo, 0x0107)
        except Exception as e:
            self.app.on_log(f"[ERROR] servo on/off failed: {e}")

    # # 위치 지정
    # def servo_position(self, slave_id: int, pos: float):
    #     servo = self.slaves[slave_id]
    #     ...

    # # 원점 지정
    # def servo_home(self, slave_id: int):
    #     self.servo_position(slave_id, 0)

    # 원점 복귀
    def servo_homing(self, slave_id: int):
        try:
            servo = self.slaves[slave_id]
            self._set_rx_pdo(servo, 0x001F, 6)
        except Exception as e:
            self.app.on_log(f"[ERROR] servo homing failed: {e}")

    # 절대 위치 이동
    def servo_move_absolute(self, slave_id: int, pos: float):
        try:
            servo = self.slaves[slave_id]
            cur_state = struct.unpack('<H', servo.input)[0]
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")
            
            self._set_rx_pdo(servo, 0x000F, 8, pos, 0)
        except Exception as e:
            self.app.on_log(f"[ERROR] servo CSP move failed: {e}")

    # 상대 위치 이동
    def servo_move_relative(self, slave_id: int, dist: float):
        servo = self.slaves[slave_id]
        ...

    # 속도 이동
    def servo_move_velocity(self, slave_id: int, v:float):
        try:
            servo = self.slaves[slave_id]
            cur_state = struct.unpack('<H', servo.input)[0]
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")

            self._set_rx_pdo(servo, 0x000F, 9, 0, v)

        except Exception as e:
            self.app.on_log(f"[ERROR] servo CSV move failed: {e}")

    # 정지(대기 상태로 전환)
    def servo_halt(self, slave_id: int):
        try:
            servo = self.slaves[slave_id]
            cur_state = struct.unpack('<H', servo.input)[0]
            if not check_mask(cur_state, STATUS_MASK.STATUS_READY_TO_SWITCH_ON):
                raise Exception("servo is not ready to work")

            self._set_rx_pdo(servo, 0x010F)

        except Exception as e:
            self.app.on_log(f"[ERROR] halt failed: {e}")

    # IO 기능
    # 비트 쓰기
    def io_write_bit(self, slave_id: int, offset: int, bit_offset: int, data: int):
        module = self.slaves[slave_id]
        ...

    # 읽기는 PDO에서 주기적으로 할 것이므로 별도 구현은 필요 없음
    # 사실 쓰기도 PDO로 하면 됨

# endregion