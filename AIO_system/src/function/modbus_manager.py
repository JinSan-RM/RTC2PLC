"""
시리얼 통신 매니저
"""
import queue
import threading
import time

from pymodbus.client import ModbusSerialClient

from src.utils.config_util import MODBUS_RTU_CONFIG
from src.utils.logger import log

class ModbusManager:
    """
    시리얼 통신 매니저
    """
    _lock = threading.Lock()
    _initialized = False

    def __init__(self, app):
        if not self._initialized:
            self.app = app
            self.config = MODBUS_RTU_CONFIG

            self.process_thread = None
            self.stop_event = threading.Event()
            self.tasks: queue.Queue[dict] = queue.Queue()
            self.client = None

            self._initialized = True

    def connect(self):
        """시리얼 통신 연결"""
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
        """
        시리얼 통신 시작
        
        :param self: Description
        """
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
        """시리얼 통신 종료"""
        log("Modbus disconnect start")
        try:
            self.stop_event.set()
            self.process_thread.join(timeout=5)
            if self.process_thread.is_alive():
                log("comm manager thread did not terminate properly")
            self.client.close()
            self.client = None
            log("Modbus disconnect completed")
        except Exception as e:
            log(f"Modbus disconnection error: {e}")

    def _process_task(self):
        while not self.stop_event.is_set():
            self.read_monitor_values()
            with self._lock:
                while not self.tasks.empty():
                    task = self.tasks.get()
                    ret = task['task_func'](*task['args'])
                    task['callback_func'](ret, *task['args'])

            time.sleep(0.033) # 60프레임 업데이트 해본다

# region r/w register
    # G100 인버터는 코일(비트) 읽기/쓰기는 지원하지 않으므로 해당하는 함수들은 구현하지 않음
    def read_holding_register(self,
                              inverter_name: str,
                              register_address: int) -> int | None:
        """
        홀딩 레지스터 읽기

        Args:
            inverter_name: 슬레이브 명칭
            register_address: 레지스터 주소

        Returns:
            읽은 값 또는 None (오류시)
        """
        try:
            if inverter_name not in self.slave_ids:
                log(f"can't find slave: {inverter_name}")
                return False

            slave_id = self.slave_ids[inverter_name]
            ret = self.client.read_holding_registers(
                register_address-1,
                count=1,
                device_id=slave_id
            )
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            value = ret.registers[0]
            return value

        except Exception as e:
            log(f"""
                read register failed (Name: {inverter_name}, Register: {register_address}): {e}
                """)
            return None

    def write_holding_register(self,
                               inverter_name: str,
                               register_address: int,
                               value: int) -> bool:
        """
        홀딩 레지스터 쓰기

        Args:
            inverter_name: 슬레이브 명칭
            register_address: 레지스터 주소
            value: 쓸 값

        Returns:
            성공 여부
        """
        try:
            if inverter_name not in self.slave_ids:
                log(f"can't find slave: {inverter_name}")
                return False

            slave_id = self.slave_ids[inverter_name]
            ret = self.client.write_register(register_address-1, value, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            return True

        except Exception as e:
            log(f"""
                register writing failed 
                (Name: {inverter_name}, Register: {register_address}, Value: {value}): {e}
                """)
            return False

    def read_multiple_registers(self,
                                inverter_name: str,
                                start_address: int,
                                count: int) -> list[int] | None:
        """
        다중 레지스터 읽기

        Args:
            inverter_name: 슬레이브 명칭
            start_address: 시작 레지스터 주소
            count: 읽을 레지스터 개수

        Returns:
            읽은 값들의 리스트 또는 None (오류시)
        """
        try:
            if inverter_name not in self.slave_ids:
                log(f"can't find slave: {inverter_name}")
                return None

            slave_id = self.slave_ids[inverter_name]
            ret = self.client.read_holding_registers(
                start_address-1,
                count=count,
                device_id=slave_id
            )
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            values = ret.registers[:count]
            return values

        except Exception as e:
            log(f"""
                reading multiple registers failed 
                (Name: {inverter_name}, Start: {start_address}, Count: {count}): {e}
                """)
            return None

    def write_multiple_registers(self,
                                 inverter_name: str,
                                 start_address: int,
                                 values: list[int]) -> bool:
        """
        다중 레지스터 쓰기

        Args:
            inverter_name: 슬레이브 명칭
            start_address: 시작 레지스터 주소
            values: 쓸 값의 리스트

        Returns:
            성공 여부
        """
        try:
            if inverter_name not in self.slave_ids:
                log(f"can't find slave: {inverter_name}")
                return False

            slave_id = self.slave_ids[inverter_name]
            ret = self.client.write_registers(start_address-1, values, device_id=slave_id)
            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            return True

        except Exception as e:
            log(f"""
                multiple registers writing failed 
                (Name: {inverter_name}, Start: {start_address}, Count: {len(values)}): {e}
                """)
            return False
# endregion

# region functions
    def read_monitor_values(self):
        """
        인버터 상태 UI 업데이트

        # 모니터링 값 #
        가속시간(0007, 0.1sec), 감속시간(0008, 0.1sec),
        출력전류(0009, 0.1A), 출력주파수(000A, 0.01Hz), 출력전압(000B, 1V),
        DC Link 전압(000C, 1V), 출력파워(000D, 0.1kW), 운전상태6종(000E)

        # 운전 상태 #
        정지(B0), 정방향(B1), 역방향(B2), Fault(B3), 가속중(B4), 감속중(B5)
        """
        _data = {}
        for _name, _ in self.slave_ids.items():
            ret = self.read_multiple_registers(_name, 0x0007, 8)
            if ret and len(ret) == 8:
                ret[0] = ret[0] * 0.1
                ret[1] = ret[1] * 0.1
                ret[2] = ret[2] * 0.1
                ret[3] = ret[3] * 0.01
                ret[4] = ret[4] * 0.1

                _data[_name] = ret

        self.app.on_update_inverter_status(_data)

# pylint: disable=unused-argument
    # 주파수 설정 함수
    def set_freq(self, inverter_name: str = 'inverter_001', value: float = 0.0):
        """주파수 설정"""
        task = {
            'task_func': self.write_holding_register,
            'callback_func': self.callback_set_freq,
            'args': [ inverter_name, 0x0005, int(value * 100) ]
        }
        self.tasks.put(task)

    def callback_set_freq(self, ret, inverter_name: str, addr: int, value: int):
        """주파수 설정 콜백"""
        if ret:
            f_value = value * 0.01
            self.app.config["inverter_config"][inverter_name][0] = f_value
            log(f"set frequency to {f_value:.2f} Hz success")
        else:
            log(f"{inverter_name} set frequency failed")

    # 가속 시간 설정 함수
    def set_acc(self, inverter_name: str = 'inverter_001', value: float = 0.0):
        """가속 시간 설정"""
        task = {
            'task_func': self.write_holding_register,
            'callback_func': self.callback_set_acc,
            'args': [ inverter_name, 0x0007, int(value * 10) ]
        }
        self.tasks.put(task)

    def callback_set_acc(self, ret, inverter_name: str, addr: int, value: int):
        """가속 시간 설정 콜백"""
        if ret:
            f_value = value * 0.1
            self.app.config["inverter_config"][inverter_name][1] = f_value
            log(f"set acceleration time to {f_value:.1f} sec success")
        else:
            log(f"{inverter_name} set acceleration time failed")

    # 감속 시간 설정 함수
    def set_dec(self, inverter_name: str = 'inverter_001', value: float = 0.0):
        """감속 시간 설정"""
        task = {
            'task_func': self.write_holding_register,
            'callback_func': self.callback_set_dec,
            'args': [ inverter_name, 0x0008, int(value * 10) ]
        }
        self.tasks.put(task)

    def callback_set_dec(self, ret, inverter_name: str, addr: int, value: int):
        """감속 시간 설정 콜백"""
        if ret:
            f_value = value * 0.1
            self.app.config["inverter_config"][inverter_name][2] = f_value
            log(f"set deceleration time to {f_value:.1f} sec success")
        else:
            log(f"{inverter_name} set deceleration time failed")

    # 모터 동작 함수
    def motor_start(self, inverter_name: str = 'inverter_001'):
        """모터 운전 시작"""
        log(f"motor_start called: {inverter_name}")

        task = {
            'task_func': self.write_holding_register,
            'callback_func': self.callback_motor_start,
            'args': [ inverter_name, 0x0382, 0x0001 ]
        }
        self.tasks.put(task)

    def callback_motor_start(self, ret, inverter_name: str, addr: int, value: int):
        """모터 운전 시작 콜백"""
        if ret:
            log(f"{inverter_name} started")
        else:
            log(f"{inverter_name} start failed")

    # 모터 정지 함수
    def motor_stop(self, inverter_name: str):
        """모터 운전 정지"""
        log(f"motor_stop called: {inverter_name}")

        task = {
            'task_func': self.write_holding_register,
            'callback_func': self.callback_motor_stop,
            'args': [ inverter_name, 0x0382, 0x0000 ]
        }
        self.tasks.put(task)

    def callback_motor_stop(self, ret, inverter_name: str, addr: int, value: int):
        """모터 운전 정지 콜백"""
        if ret:
            log(f"{inverter_name} stopped")
        else:
            log(f"{inverter_name} stop failed")
# pylint: enable=unused-argument

    # 자동 운전 시작
    def on_automode_start(self):
        """인버터 전체 운전 시작"""
        for _name, _ in self.slave_ids.items():
            self.motor_start(_name)

    # 자동 운전 정지
    def on_automode_stop(self):
        """인버터 전체 정지"""
        for _name, _ in self.slave_ids.items():
            self.motor_stop(_name)

    def custom_read(self, slave_id: int, addr: int):
        """
        원하는 주소의 값 읽기
        
        :param self: Description
        :param slave_id: Description
        :type slave_id: int
        :param addr: Description
        :type addr: int
        """
        inverter_name = f"inverter_00{slave_id}"
        task = {
            'task_func': self.read_holding_register,
            'callback_func': self.callback_custom_read,
            'args': [ inverter_name, addr ]
        }
        self.tasks.put(task)

    def callback_custom_read(self, ret, inverter_name: str, addr: int):
        """ 원하는 주소의 값 읽기 콜백 """
        if ret:
            log(f"{inverter_name}read addr: {addr:X} value: {ret}")
        else:
            log(f"{inverter_name} read addr: {addr:X} failed")

    def custom_write(self, slave_id: int, addr: int, value: int):
        """
        원하는 주소에 값 쓰기
        
        :param self: Description
        :param slave_id: Description
        :type slave_id: int
        :param addr: Description
        :type addr: int
        :param value: Description
        :type value: int
        """
        inverter_name = f"inverter_00{slave_id}"
        task = {
            'task_func': self.write_holding_register,
            'callback_func': self.callback_custom_write,
            'args': [ inverter_name, addr, value ]
        }
        self.tasks.put(task)

    def callback_custom_write(self, ret, inverter_name: str, addr: int, value: int):
        """ 원하는 주소에 값 쓰기 콜백 """
        if ret:
            log(f"{inverter_name} write addr: {addr:X} value: {value}")
        else:
            log(f"{inverter_name} write addr: {addr:X} failed")
# endregion
