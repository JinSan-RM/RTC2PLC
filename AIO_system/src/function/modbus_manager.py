from pymodbus.client import ModbusSerialClient
from typing import Any, Dict, List, Optional, Callable
import queue
import threading
import time

from src.utils.config_util import *
from src.utils.logger import log

class ModbusManager():
    _lock = threading.Lock()
    _initialized = False

    def __init__(self, app):
        if not self._initialized:
            self.app = app
            self.config = MODBUS_RTU_CONFIG

            self.stop_event = threading.Event()

            self.tasks: queue.Queue[Dict] = queue.Queue()
            
            # self.slave_ids = self.config['slave_ids']
            self.client = None
            
            self._initialized = True

    def connect(self):
        try:
            self.client = ModbusSerialClient(
                port = self.config['port'],
                baudrate = self.config['baudrate'],
                bytesize = self.config['bytesize'],
                parity = self.config['parity'],
                stopbits = self.config['stopbits'],
                timeout = self.config['timeout']
            )

            self.client.connect()

            # 연결된 슬레이브만 딕셔너리에 넣어서 사용
            self.slave_ids = {}
            for name, id in self.config['slave_ids'].items():
                try:
                    ret = self.client.read_holding_registers(0x0001, count=1, device_id=id)
                    if not ret.isError():
                        self.slave_ids[name] = id
                except:
                    continue

            self.run()
        except Exception as e:
            log(f"Modbus connection error: {e}")

    def run(self):
        try:
            # 시작 시 인버터들 설정 값 세팅
            for name, _ in self.slave_ids.items():
                _conf = self.app.config["inverter_config"][name]
                self.set_freq(name, _conf[0])
                self.set_acc(name, _conf[1])
                self.set_dec(name, _conf[2])

            self.process_thread = threading.Thread(target=self._process_task, daemon=True)
            self.process_thread.start()
        except Exception as e:
            log(f"error while process: {e}")

    def disconnect(self):
        try:
            self.stop_event.set()
            self.process_thread.join(timeout=5)
            if self.process_thread.is_alive():
                log("comm manager thread did not terminate properly")
            self.client.close()
            self.client = None
        except Exception as e:
            log(f"Modbus disconnection error: {e}")

    def _process_task(self):
        while not self.stop_event.is_set():
            self.read_monitor_values()
            with self._lock:
                while self.tasks:
                    task = self.tasks.get()
                    task[0](*task[1])

            time.sleep(0.033) # 60프레임 업데이트 해본다

# region r/w register
    # G100 인버터는 코일(비트) 읽기/쓰기는 지원하지 않으므로 해당하는 함수들은 구현하지 않음

    def read_holding_register(self, host_name: str, register_address: int) -> Optional[int]:
        """
            홀딩 레지스터 읽기

            Args:
                host_name: 슬레이브 명칭
                register_address: 레지스터 주소

            Returns:
                읽은 값 또는 None (오류시)
        """
        try:
            if host_name not in self.slave_ids:
                log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.read_holding_registers(register_address-1, count=1, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            value = ret.registers[0]
            # log(f"[{host_name}] Register {register_address} read: {value}")
            return value

        except Exception as e:
            log(f"read register failed (Name: {host_name}, Register: {register_address}): {e}")
            return None

    def write_holding_register(self, host_name: str, register_address: int, value: int) -> bool:
        """
            홀딩 레지스터 쓰기

            Args:
                host_name: 슬레이브 명칭
                register_address: 레지스터 주소
                value: 쓸 값

            Returns:
                성공 여부
        """
        try:
            if host_name not in self.slave_ids:
                log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.write_register(register_address-1, value, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            # log(f"[{host_name}] write value {value} on register {register_address} completed")
            return True

        except Exception as e:
            log(f"register writing failed (Name: {host_name}, Register: {register_address}, Value: {value}): {e}")
            return False

    def read_multiple_registers(self, host_name: str, start_address: int, count: int) -> Optional[List[int]]:
        """
            다중 레지스터 읽기

            Args:
                host_name: 슬레이브 명칭
                start_address: 시작 레지스터 주소
                count: 읽을 레지스터 개수

            Returns:
                읽은 값들의 리스트 또는 None (오류시)
        """
        try:
            if host_name not in self.slave_ids:
                log(f"can't find slave: {host_name}")
                return None

            slave_id = self.slave_ids[host_name]
            ret = self.client.read_holding_registers(start_address-1, count=count, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            values = ret.registers[:count]
            # log(f"[{host_name}] register {start_address}-{start_address+count-1} read: {values}")
            return values

        except Exception as e:
            log(f"reading multiple registers failed (Name: {host_name}, Start: {start_address}, Count: {count}): {e}")
            return None

    def write_multiple_registers(self, host_name: str, start_address: int, values: List[int]) -> bool:
        """
            다중 레지스터 쓰기

            Args:
                host_name: 슬레이브 명칭
                start_address: 시작 레지스터 주소
                values: 쓸 값의 리스트

            Returns:
                성공 여부
        """
        try:
            if host_name not in self.slave_ids:
                log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.write_registers(start_address-1, values, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            # log(f"[{host_name}] write values {values} on register {start_address}-{start_address+len(values)-1} completed")
            return True

        except Exception as e:
            log(f"multiple registers writing failed (Name: {host_name}, Start: {start_address}, Count: {len(values)}): {e}")
            return False
# endregion

# region functions
    def read_monitor_values(self):
        # 모니터링 값: 가속시간(0007, 0.1sec), 감속시간(0008, 0.1sec), 출력전류(0009, 0.1A), 출력주파수(000A, 0.01Hz), 출력전압(000B, 1V), DC Link 전압(000C, 1V), 출력파워(000D, 0.1kW), 운전상태6종(000E)
        # 운전 상태: 정지(B0), 정방향(B1), 역방향(B2), Fault(B3), 가속중(B4), 감속중(B5)
        _data = {}
        for _name, _ in self.slave_ids.items():
            ret = self.read_multiple_registers(_name, 0x0007, 8)
            if ret and len(ret) == 8:
                ret[0] = ret[0] * 0.1
                ret[1] = ret[1] * 0.1
                ret[2] = ret[2] * 0.1
                ret[3] = ret[3] * 0.01
                ret[6] = ret[6] * 0.1

                _data[_name] = ret

        self.app.on_update_inverter_status(_data)

    # 주파수 설정 함수
    def set_freq(self, motor_id:str = 'inverter_001', value: float = 0.0):
        """ 주파수 설정 """
        ret = self.write_holding_register(motor_id, 0x0005, int(value * 100))
        if ret:
            self.app.config["inverter_config"][motor_id][0] = value
            log(f"set Frequency to {value:.2f} Hz success")
            
    # 가속 시간 설정 함수
    def set_acc(self, motor_id:str = 'inverter_001', value: float = 0.0):
        """ 가속 시간 설정 """
        ret = self.write_holding_register(motor_id, 0x0007, int(value * 10))
        if ret:
            self.app.config["inverter_config"][motor_id][1] = value
            log(f"set acceleration time to {value:.1f} sec success")

    # 감속 시간 설정 함수
    def set_dec(self, motor_id:str = 'inverter_001', value: float = 0.0):
        """ 감속 시간 설정 """
        ret = self.write_holding_register(motor_id, 0x0008, int(value * 10))
        if ret:
            self.app.config["inverter_config"][motor_id][2] = value
            log(f"set Frequency to {value:.1f} sec success")
    
    # 모터 동작 함수
    def motor_start(self, motor_id: str = 'inverter_001'):
        """모터 운전 시작"""
        log(f"motor_start called: {motor_id}")
        
        if motor_id not in self.slave_ids:
            log(f"Unknown motor_id: {motor_id}")
            return
        
        ret = self.write_holding_register(motor_id, 0x0382, 0x0001)
        if ret:
            log(f"{motor_id} started")
        else:
            log("motor start failed")

    # 모터 정지 함수
    def motor_stop(self, motor_id: str):
        """모터 운전 정지"""
        log(f"motor_stop called: {motor_id}")
        
        if motor_id not in self.slave_ids:
            log(f"Unknown motor_id: {motor_id}")
            return
        
        ret = self.write_holding_register(motor_id, 0x0382, 0x0000)
        if ret:
            log(f"{motor_id} stopped")
        else:
            log("motor stop failed")

    # 자동 운전 시작
    def on_automode_start(self):
        log("auto mode started")
        for _name, _id in self.slave_ids.items():
            self.motor_start(_name)

    # 자동 운전 정지
    def on_automode_stop(self):
        log("auto mode stopped")
        for _name, _id in self.slave_ids.items():
            self.motor_stop(_name)

    # def custom_check(self, addr):
    #     ret = self.read_holding_register("inverter_001", addr - 1)
    #     if ret != None:
    #         log(f"read addr: {addr:X} value: {ret}")
    #     else:
    #         log(f"read addr: {addr:X} failed")

    # def custom_write(self, addr, value):
    #     ret = self.write_holding_register("inverter_001", addr - 1, value)
    #     if ret:
    #         log(f"write addr: {addr:X} value: {value}")
    #     else:
    #         log(f"write addr: {addr:X} failed")
# endregion