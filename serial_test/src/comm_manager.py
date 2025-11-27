from pymodbus.client import ModbusSerialClient
from typing import Any, Dict, List, Optional, Callable
import queue
import threading

from .config_util import *

class ModbusManager():
    _lock = threading.Lock()
    _initialized = False

    def __init__(self, app):
        if not self._initialized:
            self.app = app
            self.config = MODBUS_RTU_CONFIG

            self.stop_event = threading.Event()

            self.tasks: queue.Queue[Dict] = queue.Queue()
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

            self.slave_ids = {}
            for name, id in self.config['slave_ids'].items():
                self.slave_ids[name] = id

            self.run()
        except Exception as e:
            self.app.on_log(f"Modbus connection error: {e}")

    def run(self):
        try:
            self.process_thread = threading.Thread(target=self._process_task, daemon=True)
            self.process_thread.start()
        except Exception as e:
            self.app.on_log(f"error while process: {e}")

    def disconnect(self):
        try:
            self.stop_event.set()
            self.process_thread.join()
            if self.process_thread.is_alive():
                self.on_log("comm manager thread did not terminate properly")
            self.client.close()
            self.client = None
        except Exception as e:
            self.app.on_log(f"Modbus disconnection error: {e}")

    def _process_task(self):
        while not self.stop_event.is_set():
            while not self.tasks.empty():
                task = self.tasks.get()
                task['func']()

# region r/w register
    """
        홀딩 레지스터 읽기

        Args:
            slave_id: 슬레이브 ID
            register_address: 레지스터 주소

        Returns:
            읽은 값 또는 None (오류시)
    """
    def read_holding_register(self, host_name: str, register_address: int) -> Optional[int]:
        try:
            if host_name not in self.slave_ids:
                self.app.on_log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.read_holding_registers(register_address, count=1, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            value = ret.registers[0]
            self.app.on_log(f"[{host_name}] Register {register_address} read: {value}")
            return value

        except Exception as e:
            self.app.on_log(f"read register failed (Name: {host_name}, Register: {register_address}): {e}")
            return None

    """
        홀딩 레지스터 쓰기

        Args:
            slave_id: 슬레이브 ID
            register_address: 레지스터 주소
            value: 쓸 값

        Returns:
            성공 여부
    """
    def write_holding_register(self, host_name: str, register_address: int, value: int) -> bool:
        try:
            if host_name not in self.slave_ids:
                self.app.on_log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.write_register(register_address, value, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            self.app.on_log(f"[{host_name}] write value {value} on register {register_address} completed")
            return True

        except Exception as e:
            self.app.on_log(f"register writing failed (Name: {host_name}, Register: {register_address}, Value: {value}): {e}")
            return False

    """
        다중 레지스터 읽기

        Args:
            slave_id: 슬레이브 ID
            start_address: 시작 레지스터 주소
            count: 읽을 레지스터 개수

        Returns:
            읽은 값들의 리스트 또는 None (오류시)
    """
    def read_multiple_registers(self, host_name: str, start_address: int, count: int) -> Optional[List[int]]:
        try:
            if host_name not in self.slave_ids:
                self.app.on_log(f"can't find slave: {host_name}")
                return None

            slave_id = self.slave_ids[host_name]
            ret = self.client.read_holding_registers(start_address, count=count, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            values = ret.registers[:count]
            self.app.on_log(f"[{host_name}] register {start_address}-{start_address+count-1} read: {values}")
            return values

        except Exception as e:
            self.app.on_log(f"reading multiple registers failed (Name: {host_name}, Start: {start_address}, Count: {count}): {e}")
            return None

    """
        다중 레지스터 쓰기

        Args:
            slave_id: 슬레이브 ID
            start_address: 시작 레지스터 주소
            values: 쓸 값의 리스트

        Returns:
            성공 여부
    """
    def write_multiple_registers(self, host_name: str, start_address: int, values: List[int]) -> bool:
        try:
            if host_name not in self.slave_ids:
                self.app.on_log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.write_registers(start_address, values, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            self.app.on_log(f"[{host_name}] write values {values} on register {start_address}-{start_address+len(values)-1} completed")
            return True

        except Exception as e:
            self.app.on_log(f"multiple registers writing failed (Name: {host_name}, Start: {start_address}, Count: {len(values)}): {e}")
            return False

    """
        코일(비트) 읽기

        Args:
            slave_id: 슬레이브 ID
            register_address: 레지스터 주소

        Returns:
            0, 1 또는 None (오류시)
    """
    def read_bit(self, host_name: str, register_address: int) -> Optional[int]:
        try:
            if host_name not in self.slave_ids:
                self.app.on_log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.read_coils(register_address, count=1, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")
            
            value = ret.bits[0]
            self.app.on_log(f"[{host_name}] Register {register_address} read: {value}")
            return value

        except Exception as e:
            self.app.on_log(f"read bit failed (Name: {host_name}, Register: {register_address}): {e}")
            return None

    """
        코일(비트) 쓰기

        Args:
            slave_id: 슬레이브 ID
            register_address: 레지스터 주소
            value: 쓸 값

        Returns:
            성공 여부
    """
    def write_coil(self, host_name: str, register_address: int, value: bool) -> bool:
        try:
            if host_name not in self.slave_ids:
                self.app.on_log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.write_coil(register_address, value, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            self.app.on_log(f"[{host_name}] write value {value} on register {register_address} completed")
            return True

        except Exception as e:
            self.app.on_log(f"register writing failed (Name: {host_name}, Register: {register_address}, Value: {value}): {e}")
            return False

    """
        다중 코일(비트) 읽기

        Args:
            slave_id: 슬레이브 ID
            start_address: 시작 레지스터 주소
            count: 읽을 비트 개수

        Returns:
            읽은 값들의 리스트 또는 None (오류시)
    """
    def read_multiple_bits(self, host_name: str, start_address: int, count: int) -> Optional[List[int]]:
        try:
            if host_name not in self.slave_ids:
                self.app.on_log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.read_coils(start_address, count=count, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            values = ret.bits[:count]
            self.app.on_log(f"[{host_name}] register {start_address}-{start_address+count-1} read: {values}")
            return values

        except Exception as e:
            self.app.on_log(f"reading multiple bits failed (Name: {host_name}, Start: {start_address}, Count: {count}): {e}")
            return None

    """
        다중 비트(코일) 쓰기

        Args:
            slave_id: 슬레이브 ID
            start_address: 시작 레지스터 주소
            values: 쓸 값의 리스트

        Returns:
            성공 여부
    """
    def write_multiple_coils(self, host_name: str, start_address: int, values: List[bool]) -> bool:
        try:
            if host_name not in self.slave_ids:
                self.app.on_log(f"can't find slave: {host_name}")
                return False

            slave_id = self.slave_ids[host_name]
            ret = self.client.write_coils(start_address, values, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            self.app.on_log(f"[{host_name}] write bits {values} on register {start_address}-{start_address+len(values)-1} completed")
            return True

        except Exception as e:
            self.app.on_log(f"multiple bits writing failed (Name: {host_name}, Start: {start_address}, Count: {len(values)}): {e}")
            return False
# endregion

# region functions
    def check_inverter_model(self):
        ret = self.read_holding_register("inverter_001", 0x0000)
        if ret:
            self.app.on_log(f"result: {ret:2X}")
# endregion