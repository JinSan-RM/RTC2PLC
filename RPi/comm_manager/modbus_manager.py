import asyncio
import queue
from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from typing import Any, Dict, List, Optional, Callable

from .comm_manager_base import CommManagerBase

from common.consts import MODBUS_TYPE
from common.utils import Message, IOResult, EventManager

class ModbusManager(CommManagerBase):
    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, event_manager: EventManager, config: Dict):
        if not self._initialized:
            super().__init__(event_manager=event_manager, config=config)

            self.tasks: queue.Queue[Message] = queue.Queue()
            self._initialized = True

    async def _connect_impl(self) -> bool:
        try:
            if MODBUS_TYPE == "RTU":
                self.client = ModbusSerialClient(
                    method = self.config['mode'],
                    port = self.config['port'],
                    baudrate = self.config['baudrate'],
                    bytesize = self.config['bytesize'],
                    parity = self.config['parity'],
                    stopbits = self.config['stopbits'],
                    timeout = self.config['timeout']
                )

                self.slave_ids = {}
                for name, id in self.config['slave_ids'].items():
                    self.slave_ids[name] = id

            elif MODBUS_TYPE == "TCP":
                self.clients: Dict[str, ModbusTcpClient] = {}
                for name, ip in self.config['hosts'].items():
                    self.clients[name] = ModbusTcpClient(
                        host = ip,
                        port = self.config['port'],
                        timeout = self.config['timeout']
                    )
        except Exception as e:
            self.logger.error(f"Modbus connection error: {e}")
            return False

    async def _disconnect_impl(self) -> bool:
        try:
            if MODBUS_TYPE == "RTU":
                self.client.close()
                self.client = None
            elif MODBUS_TYPE == "TCP":
                for _, client in self.clients.items():
                    client.close()
                self.clients.clear()
            return True
        except Exception as e:
            self.logger.error(f"Modbus disconnection error: {e}")
            return False

    async def _read_impl(self, target_info: Any, **kwargs) -> IOResult:
        pass

    async def _write_impl(self, target_info: Any, value: Any, **kwargs) -> IOResult:
        pass

    async def _periodic_task(self):
        if self.tasks:
            while self.tasks.not_empty:
                msg = self.tasks.get()
                msg.execute()

    """
        작업 예약

        Args:
            slave_id: 슬레이브 ID
            task_func: 작업에 사용할 함수
            args: task_func에 전달할 위치 변수
            kwargs: task_func에 전달할 키워드 변수
    """
    def reserve_task(self, host_name: str, task_func: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        if MODBUS_TYPE == "RTU":
            if host_name not in self.slave_ids:
                self.logger.error(f"can't find slave: {host_name}")
                return False
        elif MODBUS_TYPE == "TCP":
            if host_name not in self.clients:
                self.logger.error(f"can't find host: {host_name}")
                return False

        msg = Message(func=task_func, args=args, kwargs=kwargs)
        self.tasks.put(msg)
        return True

    """
        작업 실행

            예약 큐가 빌 때까지 실행
    """
    async def process_task(self):
        while self.tasks.not_empty:
            task = self.tasks.get()
            task.execute()

    """
        홀딩 레지스터 읽기

        Args:
            slave_id: 슬레이브 ID
            register_address: 레지스터 주소

        Returns:
            읽은 값 또는 None (오류시)
    """
    def read_holding_register(self, host_name: str, register_address: int) -> Optional[float]:
        try:
            if MODBUS_TYPE == "RTU":
                if host_name not in self.slave_ids:
                    self.logger.error(f"can't find slave: {host_name}")
                    return False

                slave_id = self.slave_ids[host_name]
                ret = self.client.read_holding_registers(register_address, count=1, device_id=slave_id)

            elif MODBUS_TYPE == "TCP":
                if host_name not in self.clients:
                    self.logger.error(f"can't find host: {host_name}")
                    return False

                client = self.clients[host_name]
                ret = client.read_holding_registers(register_address, count=1, device_id=1)

            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            value = ret.registers[0]

            self.logger.info(f"[{host_name}] Register {register_address} read: {value}")
            return value

        except Exception as e:
            self.logger.error(f"read register failed (Name: {host_name}, Register: {register_address}): {e}")
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
            if MODBUS_TYPE == "RTU":
                if host_name not in self.slave_ids:
                    self.logger.error(f"can't find slave: {host_name}")
                    return False

                slave_id = self.slave_ids[host_name]
                ret = self.client.write_register(register_address, value, device_id=slave_id)

            elif MODBUS_TYPE == "TCP":
                if host_name not in self.clients:
                    self.logger.error(f"can't find host: {host_name}")
                    return False

                client = self.clients[host_name]
                ret = client.write_register(register_address, value, device_id=1)

            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            self.logger.info(f"[{host_name}] write value {value} on register {register_address} completed")
            return True

        except Exception as e:
            self.logger.error(f"register writing failed (Name: {host_name}, Register: {register_address}, Value: {value}): {e}")
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
            if MODBUS_TYPE == "RTU":
                if host_name not in self.slave_ids:
                    self.logger.error(f"can't find slave: {host_name}")
                    return None

                slave_id = self.slave_ids[host_name]
                ret = self.client.read_holding_registers(start_address, count=count, device_id=slave_id)

            elif MODBUS_TYPE == "TCP":
                if host_name not in self.clients:
                    self.logger.error(f"can't find host: {host_name}")
                    return None

                client = self.clients[host_name]
                ret = client.read_holding_registers(start_address, count=count, device_id=1)

            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            values = ret.registers[:count]

            self.logger.info(f"[{host_name}] register {start_address}-{start_address+count-1} read: {values}")
            return values

        except Exception as e:
            self.logger.error(f"reading multiple registers failed (Name: {host_name}, Start: {start_address}, Count: {count}): {e}")
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
            if MODBUS_TYPE == "RTU":
                if host_name not in self.slave_ids:
                    self.logger.error(f"can't find slave: {host_name}")
                    return False

                slave_id = self.slave_ids[host_name]
                ret = self.client.write_registers(start_address, values, device_id=slave_id)

            elif MODBUS_TYPE == "TCP":
                if host_name not in self.clients:
                    self.logger.error(f"can't find host: {host_name}")
                    return False

                client = self.clients[host_name]
                ret = client.write_registers(start_address, values, device_id=1)

            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            self.logger.info(f"[{host_name}] write values {values} on register {start_address}-{start_address+len(values)-1} completed")
            return True

        except Exception as e:
            self.logger.error(f"multiple registers writing failed (Name: {host_name}, Start: {start_address}, Count: {len(values)}): {e}")
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
            if MODBUS_TYPE == "RTU":
                if host_name not in self.slave_ids:
                    self.logger.error(f"can't find slave: {host_name}")
                    return False

                slave_id = self.slave_ids[host_name]
                ret = self.client.read_coils(register_address, count=1, device_id=slave_id)

            elif MODBUS_TYPE == "TCP":
                if host_name not in self.clients:
                    self.logger.error(f"can't find host: {host_name}")
                    return False

                client = self.clients[host_name]
                ret = client.read_coils(register_address, count=1, device_id=1)

            if ret.isError():
                raise Exception(f"Modbus error: {ret}")
            
            value = ret.bits[0]

            self.logger.info(f"[{host_name}] Register {register_address} read: {value}")
            return value

        except Exception as e:
            self.logger.error(f"read bit failed (Name: {host_name}, Register: {register_address}): {e}")
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
            if MODBUS_TYPE == "RTU":
                if host_name not in self.slave_ids:
                    self.logger.error(f"can't find slave: {host_name}")
                    return False

                slave_id = self.slave_ids[host_name]
                ret = self.client.write_coil(register_address, value, device_id=slave_id)

            elif MODBUS_TYPE == "TCP":
                if host_name not in self.clients:
                    self.logger.error(f"can't find host: {host_name}")
                    return False

                client = self.clients[host_name]
                ret = client.write_coil(register_address, value, device_id=1)

            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            self.logger.info(f"[{host_name}] write value {value} on register {register_address} completed")
            return True

        except Exception as e:
            self.logger.error(f"register writing failed (Name: {host_name}, Register: {register_address}, Value: {value}): {e}")
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
            if MODBUS_TYPE == "RTU":
                if host_name not in self.slave_ids:
                    self.logger.error(f"can't find slave: {host_name}")
                    return False

                slave_id = self.slave_ids[host_name]
                ret = self.client.read_coils(start_address, count=count, device_id=slave_id)

            elif MODBUS_TYPE == "TCP":
                if host_name not in self.clients:
                    self.logger.error(f"can't find host: {host_name}")
                    return False

                client = self.clients[host_name]
                ret = client.read_coils(start_address, count=count, device_id=1)

            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            values = ret.bits[:count]

            self.logger.info(f"[{host_name}] register {start_address}-{start_address+count-1} read: {values}")
            return values

        except Exception as e:
            self.logger.error(f"reading multiple bits failed (Name: {host_name}, Start: {start_address}, Count: {count}): {e}")
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
            if MODBUS_TYPE == "RTU":
                if host_name not in self.slave_ids:
                    self.logger.error(f"can't find slave: {host_name}")
                    return False

                slave_id = self.slave_ids[host_name]
                ret = self.client.write_coils(start_address, values, device_id=slave_id)

            elif MODBUS_TYPE == "TCP":
                if host_name not in self.clients:
                    self.logger.error(f"can't find host: {host_name}")
                    return False

                client = self.clients[host_name]
                ret = client.write_coils(start_address, values, device_id=1)

            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            self.logger.info(f"[{host_name}] write bits {values} on register {start_address}-{start_address+len(values)-1} completed")
            return True

        except Exception as e:
            self.logger.error(f"multiple bits writing failed (Name: {host_name}, Start: {start_address}, Count: {len(values)}): {e}")
            return False