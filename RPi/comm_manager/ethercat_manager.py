import threading
import asyncio
import time
import queue
import pysoem
from typing import Any, Dict
from concurrent.futures import ThreadPoolExecutor

from .comm_manager_base import CommManagerBase

from common.consts import ETHERNET_IP_DEF
from common.utils import Message, IOResult, EventManager, read_bit_mask_binary, read_little_endian, find_dict

class EtherCATManager(CommManagerBase):
    def __init__(self, event_manager: EventManager, config: Dict):
        if not self._initialized:
            super().__init__(event_manager=event_manager, config=config)

            self.tasks = queue.Queue[Message] = queue.Queue()
            self._initialized = True

    async def _connect_impl(self):
        self.master = pysoem.Master()
        self.master.open(self.config["if_name"])

        if self.master.config_init() > 0:
            self.slaves = []
            for slave in self.master.slaves:
                self.slaves.append(slave)

    async def _disconnect_impl(self) -> bool:
        try:
            self.master.close()
            return True
        except Exception as e:
            self.logger.error(f"EtherCAT disconnection error: {e}")
            return False

    async def _read_impl(self, target_info: Any, **kwargs) -> IOResult:
        pass

    async def _write_impl(self, target_info: Any, value: Any, **kwargs) -> IOResult:
        pass

    async def _periodic_task(self):
        pass