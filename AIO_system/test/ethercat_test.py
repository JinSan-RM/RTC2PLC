"""Toggles the state of a digital output on an EL1259.

Usage: python basic_example.py <adapter>

This example expects a physical slave layout according to _expected_slave_layout, seen below.
Timeouts are all given in us.
"""
import os
import sys
import struct
import time
import threading
from dataclasses import dataclass
import typing
import ctypes

import pysoem

LS_VENDOR_ID = 30101
L7NH_PRODUCT_CODE = 0x0001_0001

def _get_modified_value(val):
    gear_ratio = 524288 / 10000
    return int(val * gear_ratio)

@dataclass
class Device:
    name: str
    vendor_id: int
    product_code: int
    config_func: typing.Callable = None

class RxPDOData(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ('Controlword', ctypes.c_uint16), # 0x6040:00 컨트롤 워드
        ('OperationMode', ctypes.c_byte), # 0x6060:00 운전 모드
        ('TargetPosition', ctypes.c_int32), # 0x607A:00 목표 위치
        ('TargetVelocity', ctypes.c_int32), # 0x60FF:00 목표 속도
    ]

class TxPDOData(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ('ErrorCode', ctypes.c_uint16), # 0x2614:00 경고 코드
        ('Statusword', ctypes.c_uint16), # 0x6041:00 스테이터스 워드
        ('OperationMode', ctypes.c_byte), # 0x6061:00 운전 모드 표시
        ('PositionActualValue', ctypes.c_int32), # 0x6064:00 현재 위치
        ('VelocityActualValue', ctypes.c_int32), # 0x606C:00 현재 속도
    ]

class BasicExample:
    def __init__(self, ifname):
        self._ifname = ifname
        self._pd_thread_stop_event = threading.Event()
        self._ch_thread_stop_event = threading.Event()
        self._actual_wkc = 0
        self._master = pysoem.Master()
        self._master.in_op = False
        self._master.do_check_state = False
        self._expected_slave_layout = {
            0: Device("L7NH", LS_VENDOR_ID, L7NH_PRODUCT_CODE, self.l7nh_setup)
        }
        self._rx_pdo_struct = RxPDOData()
        self._tx_pdo_struct = TxPDOData()
        self.cycle_time = 0.01

    def l7nh_setup(self, slave_pos):
        """Config function that will be called when transitioning from PreOP state to SafeOP state."""
        slave = self._master.slaves[slave_pos]

        # slave.sdo_write(0x1011, 1, struct.pack("I", 0x64616F6C)) # 전체 초기화 코드

        # slave.sdo_write(index=0x6099, subindex=1, data=struct.pack('<i', 2621440)) # 호밍 속도(탐색)
        # slave.sdo_write(index=0x6099, subindex=2, data=struct.pack('<i', 524288)) # 호밍 속도(제로 근처)

        # 기어비: (motor resolution) / (shaft resolution) -> 전원재투입 필요
        # res = [
        #     1,
        #     1
        # ]
        # res_bytes = struct.pack(
        #     "<Bx" + "".join(["I" for _ in range(len(res))]), len(res), *res)
        # slave.sdo_write(index=0x6091, subindex=0, data=res_bytes, ca=True)
        # slave.sdo_write(index=0x60B1, subindex=0, data=struct.pack("<i", 0))
        # slave.sdo_write(index=0x6060, subindex=0, data=struct.pack('b', 8))
        slave.sdo_write(index=0x6065, subindex=0, data=struct.pack("<I", _get_modified_value(100_000)))
        slave.sdo_write(index=0x6098, subindex=0, data=struct.pack("b", 33)) # 33->역방향호밍 34->정방향호밍
        # slave.sdo_write(index=0x2005, subindex=0, data=struct.pack("<H", 0)) # absolute encoder 설정

        # 송수신 PDO 할당
        rx_map_obj = [
            0x1601,
        ]
        rx_map_obj_bytes = struct.pack(
            "<Bx" + "".join(["H" for _ in range(len(rx_map_obj))]), len(rx_map_obj), *rx_map_obj)
        slave.sdo_write(index=0x1C12, subindex=0, data=rx_map_obj_bytes, ca=True)
        rx_obj = [
            0x60400010, # 컨트롤 워드
            0x60600008, # 운전 모드
            0x607A0020, # 목표 위치
            0x60FF0020, # 목표 속도
            # 0x60710010,
        ]
        rx_obj_bytes = struct.pack(
            "<Bx" + "".join(["I" for _ in range(len(rx_obj))]), len(rx_obj), *rx_obj)
        slave.sdo_write(index=0x1601, subindex=0, data=rx_obj_bytes, ca=True)

        tx_map_obj = [
            0x1A01,
        ]
        tx_map_obj_bytes = struct.pack(
            "<Bx" + "".join(["H" for _ in range(len(tx_map_obj))]), len(tx_map_obj), *tx_map_obj)
        slave.sdo_write(index=0x1C13, subindex=0, data=tx_map_obj_bytes, ca=True)
        tx_obj = [
            0x603F0010, # 에러 코드
            0x60410010, # 스테이터스 워드
            0x60610008, # 운전 모드 표시
            0x60640020, # 현재 위치
            0x606C0020, # 현재 속도
        ]
        tx_obj_bytes = struct.pack(
            "<Bx" + "".join(["I" for _ in range(len(tx_obj))]), len(tx_obj), *tx_obj)
        slave.sdo_write(index=0x1A01, subindex=0, data=tx_obj_bytes, ca=True)

        # slave.sdo_write(index=0x6040, subindex=0, data=struct.pack("<H", 0x0006))

    def _processdata_thread(self):
        slave = self._master.slaves[0]
        """Background thread that sends and receives the process-data frame in a 10ms interval."""
        while not self._pd_thread_stop_event.is_set():
            # self._set_rx_pdo(slave)
            self._master.send_processdata()
            self._actual_wkc = self._master.receive_processdata(timeout=100_000)
            if not self._actual_wkc == self._master.expected_wkc:
                print("incorrect wkc")
            
            time.sleep(self.cycle_time)

    def _pdo_update_loop(self):
        self._master.in_op = True

        slave = self._master.slaves[0]

        self.servo_off(slave)

        # self.servo_homing(slave)

        def check_bit(tgt):
            low_bit = tgt & 0x00FF
            mask = 0b00100001
            return (low_bit & mask) == mask
    
        try:
            while True:
                if self._actual_wkc > 0:
                    self._print_tx_pdo(slave)
                    if check_bit(self._tx_pdo_struct.Statusword):
                        self._set_rx_pdo(slave, 0x000F, 9, 50_000, 10_000)
                    # self._print_rx_pdo(slave)

                    # self._print_output_sync_data(slave)
                
                time.sleep(1)

        except KeyboardInterrupt:
            # ctrl-C abort handling
            print("stopped")
        except Exception as e:
            print(f"{e}")

    def run(self):
        self._master.open(self._ifname)

        if not self._master.config_init() > 0:
            self._master.close()
            raise BasicExampleError("no slave found")

        for i, slave in enumerate(self._master.slaves):
            if not ((slave.man == self._expected_slave_layout[i].vendor_id) and
                    (slave.id == self._expected_slave_layout[i].product_code)):
                self._master.close()
                raise BasicExampleError(f"unexpected slave layout: vendor id[{slave.man}] product code[{slave.id:X}]")
            slave.config_func = self._expected_slave_layout[i].config_func
            slave.is_lost = False

        self._master.config_map()

        if self._master.state_check(pysoem.SAFEOP_STATE, timeout=50_000) != pysoem.SAFEOP_STATE:
            self._master.close()
            raise BasicExampleError("not all slaves reached SAFEOP state")

        # for slave in self._master.slaves:
        #     slave.dc_sync(act=True, sync0_cycle_time=self.cycle_time*(10**9))  # time is given in ns -> 10,000,000ns = 10ms

        self._master.state = pysoem.OP_STATE

        # send one valid process data to make outputs in slaves happy
        self._master.send_processdata()
        self._master.receive_processdata(timeout=2000)

        # request OP state for all slaves
        self._master.write_state()

        all_slaves_reached_op_state = False
        for i in range(40):
            self._master.state_check(pysoem.OP_STATE, timeout=50_000)
            if self._master.state == pysoem.OP_STATE:
                all_slaves_reached_op_state = True
                break

        check_thread = threading.Thread(target=self._check_thread)
        check_thread.start()
        proc_thread = threading.Thread(target=self._processdata_thread)
        proc_thread.start()

        if all_slaves_reached_op_state:
            self._pdo_update_loop()

        # self._master.slaves[0].sdo_write(index=0x6040, subindex=0, data=struct.pack("<H", 0x010F))
        # self._rx_pdo_struct.Controlword = 0x010F
        # ctypes.memmove(
        #     slave.output,
        #     ctypes.addressof(self._rx_pdo_struct),
        #     ctypes.sizeof(self._rx_pdo_struct)
        # )
        self._set_rx_pdo(self._master.slaves[0], 0x010F)
        
        self._master.send_processdata()
        self._master.receive_processdata(timeout=2000)

        self._pd_thread_stop_event.set()
        self._ch_thread_stop_event.set()
        proc_thread.join()
        check_thread.join()
        self._master.state = pysoem.INIT_STATE
        # request INIT state for all slaves
        self._master.write_state()
        self._master.close()

        if not all_slaves_reached_op_state:
            raise BasicExampleError("not all slaves reached OP state")

    @staticmethod
    def _check_slave(slave, pos):
        if slave.state == (pysoem.SAFEOP_STATE + pysoem.STATE_ERROR):
            print(f"ERROR : slave {pos} is in SAFE_OP + ERROR, attempting ack.")
            slave.state = pysoem.SAFEOP_STATE + pysoem.STATE_ACK
            slave.write_state()
        elif slave.state == pysoem.SAFEOP_STATE:
            print(f"WARNING : slave {pos} is in SAFE_OP, try change to OPERATIONAL.")
            slave.state = pysoem.OP_STATE
            slave.write_state()
        elif slave.state > pysoem.NONE_STATE:
            if slave.reconfig():
                slave.is_lost = False
                print(f"MESSAGE : slave {pos} reconfigured")
        elif not slave.is_lost:
            slave.state_check(pysoem.OP_STATE)
            if slave.state == pysoem.NONE_STATE:
                slave.is_lost = True
                print(f"ERROR : slave {pos} lost")
        if slave.is_lost:
            if slave.state == pysoem.NONE_STATE:
                if slave.recover():
                    slave.is_lost = False
                    print(f"MESSAGE : slave {pos} recovered")
            else:
                slave.is_lost = False
                print(f"MESSAGE : slave {pos} found")

    def _check_thread(self):
        while not self._ch_thread_stop_event.is_set():
            if self._master.in_op and ((self._actual_wkc < self._master.expected_wkc) or self._master.do_check_state):
                self._master.do_check_state = False
                self._master.read_state()
                for i, slave in enumerate(self._master.slaves):
                    if slave.state != pysoem.OP_STATE:
                        self._master.do_check_state = True
                        BasicExample._check_slave(slave, i)
                if not self._master.do_check_state:
                    print("OK : all slaves resumed OPERATIONAL.")
            time.sleep(self.cycle_time)

    def servo_off(self, slave):
        # self._rx_pdo_struct.Controlword = 0x0006
        # ctypes.memmove(
        #     slave.output,
        #     ctypes.addressof(self._rx_pdo_struct),
        #     ctypes.sizeof(self._rx_pdo_struct)
        # )
        self._set_rx_pdo(slave, 0x0006)

    # 1:Profile Position 3:Profile Velocity 4:Profile Torque 6:Homing 8:Cyclic Sync Position 9: Cyclic Sync Velocity 10: Cyclic Sync Torque
    def servo_homing(self, slave):
        self.homing_started = True
        if self._tx_pdo_struct.PositionActualValue >= 0:
            slave.sdo_write(index=0x6098, subindex=0, data=struct.pack("b", 33))
        else:
            slave.sdo_write(index=0x6098, subindex=0, data=struct.pack("b", 34))

        # slave.sdo_write(index=0x6040, subindex=0, data=struct.pack("<H", 0x001F))
        # slave.sdo_write(index=0x6060, subindex=0, data=struct.pack("b", 6))

        self._set_rx_pdo(slave, 0x001F, 6)
    
    def _set_rx_pdo(self, slave, ctrl = 0, mode = 0, pos = 0, v = 0):
        # slave.sdo_write(index=0x6040, subindex=0, data=struct.pack("<H", 0x000F))
        # slave.sdo_write(index=0x6060, subindex=0, data=struct.pack("b", 9))
        # slave.sdo_write(index=0x607A, subindex=0, data=struct.pack("<i", _get_modified_value(50_000)))
        # slave.sdo_write(index=0x60FF, subindex=0, data=struct.pack("<i", _get_modified_value(10_000)))

        # self._rx_pdo_struct.Controlword = 0x000F
        # self._rx_pdo_struct.OperationMode = 0x09
        # self._rx_pdo_struct.TargetPosition = _get_modified_value(0)
        # self._rx_pdo_struct.TargetVelocity = _get_modified_value(v)
        # ctypes.memmove(
        #     slave.output,
        #     ctypes.addressof(self._rx_pdo_struct),
        #     ctypes.sizeof(self._rx_pdo_struct)
        # )

        buf = bytearray(11)
        buf = struct.pack("<H", ctrl) + struct.pack("b", mode) + struct.pack("<i", _get_modified_value(pos)) + struct.pack("<i", _get_modified_value(v))
        slave.output = bytes(buf)
    
    def _print_tx_pdo(self, slave):
        raw_input_data = slave.input
        ctypes.memmove(
            ctypes.addressof(self._tx_pdo_struct),
            raw_input_data,
            ctypes.sizeof(self._tx_pdo_struct)
        )
        error_code = self._tx_pdo_struct.ErrorCode
        status_word = self._tx_pdo_struct.Statusword
        cur_mode = self._tx_pdo_struct.OperationMode
        cur_pos = self._tx_pdo_struct.PositionActualValue
        cur_vel = self._tx_pdo_struct.VelocityActualValue
        print(f"status:{status_word:016b}, mode:{cur_mode}, pos:{cur_pos}, v:{cur_vel}, err:{error_code}")

    def _print_rx_pdo(self, slave):
        ctrl = struct.unpack('<H', slave.sdo_read(0x6040, 0, 2))[0]
        mode = struct.unpack('b', slave.sdo_read(0x6060, 0, 1))[0]
        pos = struct.unpack('<i',slave.sdo_read(0x607A, 0, 4))[0]
        v = struct.unpack('<i',slave.sdo_read(0x60FF, 0, 4))[0]
        print(f"ctrl:{ctrl:016b}, mode:{mode}, pos:{pos}, v:{v}")

    def _print_output_sync_data(self, slave):
        output_sync_mode = struct.unpack("<H", slave.sdo_read(0x1C32, 1, 2))[0]
        output_cycle_time = struct.unpack("<I", slave.sdo_read(0x1C32, 2, 4))[0]
        output_shift_time = struct.unpack("<I", slave.sdo_read(0x1C32, 3, 4))[0]
        output_delay_time = struct.unpack("<I", slave.sdo_read(0x1C32, 9, 4))[0]
        output_sync0_time = struct.unpack("<I", slave.sdo_read(0x1C32, 10, 4))[0]
        output_exceeded_cnt = struct.unpack("<H", slave.sdo_read(0x1C32, 11, 2))[0]
        output_event_missed = struct.unpack("<H", slave.sdo_read(0x1C32, 12, 2))[0]
        output_too_short = struct.unpack("<H", slave.sdo_read(0x1C32, 13, 2))[0]
        output_error = struct.unpack("b", slave.sdo_read(0x1C32, 32, 1))[0]
        print(f"output: {output_sync_mode} / {output_cycle_time} / {output_shift_time} / {output_delay_time} / {output_sync0_time} / {output_exceeded_cnt} / {output_event_missed} / {output_too_short} / {output_error}")

class BasicExampleError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message

if __name__ == "__main__":
    try:
        BasicExample('\\Device\\NPF_{82D71BA4-0710-4E4A-9ED2-4FD7DA4F0FD3}').run()
    except BasicExampleError as err:
        print(f"{os.path.basename(__file__)} failed: {err.message}")
        sys.exit(1)