import socket
import threading
import asyncio
import queue
import time
import logging
from typing import Optional, Callable

from common.utils import parse_FEnet_packet

class TCPServer(threading.Thread):
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
            self, host: str,
            port: int,
            handler_func: Optional[Callable[[bytes], None]] = None,
            disconnect_func: Optional[Callable[[], None]] = None
        ):
        if not self._initialized:
            self.host = host
            self.port = port
            self.logger = logging.getLogger(__name__)
            self.socket = None

            self.message_handler = handler_func
            self.disconnect_handler = disconnect_func

            self.send_queue = queue.Queue()

            self._connected = False
            self.connect_event = threading.Event()

            self._running = False
            self._initialized = True

    def run(self):
        self._running = True
        while self._running:
            try:
                self._connect()
                if self._connected:
                    self._handle_communication()
            except Exception as e:
                self.logger.error(f"TCP Client Error: {e}")
                self._disconnect()
                if self._running:
                    time.sleep(5) # 재연결 대기

    def _connect(self):
        if self._connected:
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0) # 연결 타임아웃
            self.socket.connect((self.host, self.port))
            self.socket.settimeout(1.0) # 통신 타임아웃

            self._connected = True
            self.connect_event.set()
            self.logger.info(f"TCP Connected to {self.host}:{self.port}")

        except Exception as e:
            self.logger.error(f"TCP Connection failed: {e}")
            self._disconnect()

    def _disconnect(self):
        self._connected = False
        self.connect_event.clear()

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        if self.disconnect_handler:
            self.disconnect_handler()

    # 통신 처리 (송수신)
    def _handle_communication(self):
        while self._running and self._connected:
            try:
                self._process_send_queue() # 메시지 전송 처리
                self._receive_messages() # 메시지 수신 처리
            except socket.timeout:
                continue # 타임아웃은 정상적인 흐름
            except Exception as e:
                self.logger.error(f"TCP Communication error: {e}")
                break

    # 전송 큐에서 메시지 처리
    def _process_send_queue(self):
        try:
            while not self.send_queue.empty():
                message = self.send_queue.get_nowait()
                self.socket.send(message)
        except queue.Empty:
            pass
        except Exception as e:
            raise e

    # 메시지 수신
    def _receive_messages(self):
        try:
            msg = self.socket.recv(1024)
            if msg:
                if self.message_handler:
                    self.message_handler(msg)
            else:
                raise ConnectionError("Connection closed by server") # 연결이 종료됨
        except socket.timeout:
            pass # 정상적인 타임아웃

    # 메시지 전송
    def send_message(self, message: bytes) -> bool:
        if not self._connected:
            return False

        try:
            self.send_queue.put(message, timeout=1.0)
            return True
        except queue.Full:
            return False

    # 연결 대기
    def wait_for_connection(self, timeout: float = 10.0) -> bool:
        return self.connect_event.wait(timeout)

    def stop(self):
        self._running = False
        self._disconnect()

        if self.is_alive():
            self.join(timeout=2.0)