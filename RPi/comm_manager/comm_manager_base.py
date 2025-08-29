import threading
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable

from common.consts import ConnectionStatus
from common.utils import IOResult, EventManager

class CommManagerBase(ABC):
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, event_manager: EventManager, config: Dict):
        if not self._initialized:
            self.config = config
            self.loop_interval = config['loop_interval']
            self.status = ConnectionStatus.DISCONNECTED
            self.event_manager = event_manager
            self.loop: Optional[asyncio.AbstractEventLoop] = None
            self.thread: Optional[threading.Thread] = None
            self._stop_event = asyncio.Event()
            self._status_callbacks = []
            self._data_callbacks = []
            self.logger = logging.getLogger(f"{self.__class__.__name__}")
            # self._initialized = True # 이건 상속받는 쪽에서 처리하도록 하자

    @abstractmethod
    async def _connect_impl(self) -> bool:
        pass

    @abstractmethod
    async def _disconnect_impl(self) -> bool:
        pass

    @abstractmethod
    async def _read_impl(self, target_info: Any, **kwargs) -> IOResult:
        pass

    @abstractmethod
    async def _write_impl(self, target_info: Any, value: Any, **kwargs) -> IOResult:
        pass

    def start(self):
        if self.thread and self.thread.is_alive():
            return

        self.thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"{self.config['type']} manager started")

    def stop(self):
        if self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._stop_event.set(), self.loop)

        if self.thread:
            self.thread.join(timeout=5.0)

        self.logger.info(f"manager stopped")

    def _run_async_loop(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._async_main())
        except Exception as e:
            self.logger.error(f"Network Error: {e}")
        finally:
            self.loop.close()

    async def _async_main(self):
        try:
            while not self._stop_event.is_set():
                await self._periodic_task()
                await asyncio.sleep(self.loop_interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Main loop error: {e}")
        finally:
            await self

    async def _periodic_task(self):
        pass

    async def connect(self) -> bool:
        if self.status == ConnectionStatus.CONNECTED:
            return True

        self._set_status(ConnectionStatus.CONNECTING)
        try:
            result = await self._connect_impl()
            if result:
                self._set_status(ConnectionStatus.CONNECTED)
                self.logger.info()
            else:
                self._set_status(ConnectionStatus.ERROR)
                self.logger.error()
            return result
        except Exception as e:
            self._set_status(ConnectionStatus.ERROR)
            self.logger.error(f"Connection error: {e}")
            return False

    async def disconnect(self) -> bool:
        try:
            result = await self._disconnect_impl()
            self._set_status(ConnectionStatus.DISCONNECTED)
            return result
        except Exception as e:
            self.logger.error(f"Disconnection error: {e}")
            return False
        
    def read_async(self, target_info: Any, **kwargs) -> asyncio.Future:
        if not self.loop:
            raise RuntimeError("Manager not started")
        return asyncio.run_coroutine_threadsafe(
            self._read_impl(target_info, **kwargs), self.loop
        )

    def write_async(self, target_info: Any, value: Any, **kwargs) -> asyncio.Future:
        if not self.loop:
            raise RuntimeError("Manager not started")
        return asyncio.run_coroutine_threadsafe(
            self._write_impl(target_info, value, **kwargs), self.loop
        )

    # 콜백 관리
    def add_status_callback(self, callback: Callable[[ConnectionStatus], None]):
        self._status_callbacks.append(callback)

    def add_data_callback(self, callback: Callable[[str, Any], None]):
        self._data_callbacks.append(callback)

    def _set_status(self, status: ConnectionStatus):
        if self.status != status:
            self.status = status
            for callback in self._status_callbacks:
                try:
                    callback(status)
                except Exception as e:
                    self.logger.error(f"Status callback error: {e}")

    def _notify_data(self, tag: str, data: Any):
        for callback in self._data_callbacks:
            try:
                callback(tag, data)
            except Exception as e:
                self.logger.error(f"Data callback error: {e}")