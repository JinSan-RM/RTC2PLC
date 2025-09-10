import socket
import threading
import time
from queue import Queue, Empty
from typing import Dict, Callable, Optional

from .consts import LSDataType
from .utils import get_variable_name, create_write_packet, create_bit_packet

class CommManager:
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, app, ip: str, port: int):
        if not self._initialized:
            self.app = app
            self.ip = ip
            self.port = port
            self.timeout = 3.0
            self.sock = None
            self._connected = False
            self._running = False

            self.comm_thread: threading.Thread = None

            self.send_queue: Queue[Dict] = Queue()

            self._initialized = True

    def start(self):
        if self.comm_thread and self.comm_thread.is_alive():
            return False

        self._running = True
        self.comm_thread = threading.Thread(target=self._comm_loop, daemon=True)
        self.comm_thread.start()
        return True

    def stop(self):
        self._running = False
        if self.comm_thread:
            self.comm_thread.join(timeout=2.0)
        self.disconnect()

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.ip, self.port))
            self._connected = True
            print(f"✅ PLC {self.ip}:{self.port}에 연결되었습니다.")
            return True
        except Exception as e:
            print(f"❌ PLC 연결 실패: {str(e)}")
            self._connected = False
            return False
        
    def _comm_loop(self):
        while self._running:
            if not self._connected:
                if not self.connect():
                    time.sleep(1)
                    continue

            try:
                self._handle_sending()
                time.sleep(0.01)
            except Exception as e:
                print(f"통신 오류: {e}")
                self.disconnect()
                time.sleep(1)

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = None
        self._connected = False
        print("PLC 연결이 종료되었습니다.")

    def send_command_async(self, address: int, var_type: LSDataType, value: Optional[int], callback: Callable):
        if not self._connected:
            return None

        req_data = {
            'address': address,
            'type': var_type,
            'value': value,
            'callback': callback
        }

        self.send_queue.put(req_data)

    def _handle_sending(self):
        try:
            req_data = self.send_queue.get_nowait()
            address = req_data['address']
            var_type = req_data['type']
            value: Optional[int] = req_data['value']
            callback = req_data['callback']

            if var_type == LSDataType.BIT:
                packet = create_bit_packet(address, value)
            else:
                data_dict = {}
                var_name = get_variable_name("P", var_type, address)
                if value is not None:
                    data_dict[var_name] = value.to_bytes(2, byteorder='little')
                packet = create_write_packet(data_dict, var_type)

            ret, response = self.send_write_packet(packet)
            if ret and callback:
                callback(ret)
            else:
                print(f"패킷 오류: {response}")
        except Empty:
            pass
        except Exception as e:
            print(f"❌ 통신 오류 1: {e}")
            raise

    def send_write_packet(self, packet: bytearray):
        """패킷 전송 및 응답 수신"""
        if not self._connected:
            if not self.connect():
                return False, None

        try:
            self.sock.send(packet)
            response = self.sock.recv(1024)

            if len(response) >= 28:
                status = response[26:28]
                if status == b'\x00\x00':
                    return True, response
                else:
                    return False, response
            else:
                print("❌ 응답이 충분하지 않음")
                return False, response
        except Exception as e:
            print(f"❌ 통신 오류 2: {e}")
            self._connected = False
            return False, None