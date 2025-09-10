import threading
import asyncio
import time
import queue
from eeip.eipclient import EEIPClient, RealTimeFormat, ConnectionType
from typing import Any, Dict
from concurrent.futures import ThreadPoolExecutor

from .comm_manager_base import CommManagerBase

from common.consts import ETHERNET_IP_DEF
from common.utils import Message, IOResult, EventManager, read_bit_mask_binary, read_little_endian, find_dict

class EthernetIPManager(CommManagerBase):
    def __init__(self, event_manager: EventManager, config: Dict):
        if not self._initialized:
            super().__init__(event_manager=event_manager, config=config)

            self.implicit_input_def = find_dict(
                ETHERNET_IP_DEF['Implicit']['Input'],
                "Instance",
                self.config['input_instance']
            )

            self.explicit_tasks: queue.Queue[Message] = queue.Queue()
            self._initialized = True

    async def _connect_impl(self):
        self.tcp_port = self.config['tcp_port']
        self.udp_port = self.config['udp_port']

        self.clients: Dict[str, EEIPClient] = {}
        loop = asyncio.get_event_loop()
        for name, ip in self.config['hosts']:
            await loop.run_in_executor(None, self.add_client, name, ip)

    async def _disconnect_impl(self) -> bool:
        try:
            for _, client in self.clients.items():
                client.forward_close()
                client.unregister_session()
            self.clients.clear()
            return True
        except Exception as e:
            self.logger.error(f"EtherNet/IP disconnection error: {e}")
            return False

    async def _read_impl(self, target_info: Any, **kwargs) -> IOResult:
        pass

    async def _write_impl(self, target_info: Any, value: Any, **kwargs) -> IOResult:
        pass

    async def _periodic_task(self):
        if self.clients:
            for _, client in self.clients.items():
                parse_result = self.parse_implicit_input()
                # todo: parse_result를 통해 현재 인버터 상태나 모터 속도 등을 모니터링 가능하도록 UI에 보여주는 처리 필요
            
            while self.explicit_tasks.not_empty:
                msg = self.explicit_tasks.get()
                msg.execute()

    async def add_client(self, host_name: str, host_ip: str):
        try:
            client = EEIPClient()
            client.register_session(host_ip)

            # Parameters from Originator -> Target
            client.o_t_instance_id = self.config["output_instance"]
            client.o_t_length = 4
            client.o_t_requested_packet_rate = self.loop_interval * (10 ** 6) # loop_interval은 s, packet_rate는 μs
            client.o_t_realtime_format = RealTimeFormat.HEADER32BIT
            client.o_t_owner_redundant = False
            client.o_t_variable_length = False
            client.o_t_connection_type = ConnectionType.POINT_TO_POINT

            # Parameters from Target -> Originator
            client.t_o_instance_id = self.config["input_instance"]
            client.t_o_length = 16
            client.t_o_requested_packet_rate = self.loop_interval * (10 ** 6)
            client.t_o_realtime_format = RealTimeFormat.MODELESS
            client.t_o_owner_redundant = False
            client.t_o_variable_length = False
            client.t_o_connection_type = ConnectionType.MULTICAST

            client.forward_open()

        except Exception as e:
            self.logger.error(f"EtherNet/IP connection error: {e}")

        self.clients[host_name] = client

    async def get_attribute_single(self, host_name: str, class_id: int, instance_id: int, attribute_id: int):
        if host_name not in self.clients:
            self.logger.error(f"can't find host: {host_name}")
            return None

        client = self.clients[host_name]
        try:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                ret = await loop.run_in_executor(executor, client.get_attribute_single, class_id, instance_id, attribute_id)
        except Exception as e:
            self.logger.error(f"get attribute failed: {e}")
            return None

        return ret

    async def set_attribute_single(self, host_name: str, class_id: int, instance_id: int, attribute_id: int, value: Any) -> bool:
        if host_name not in self.clients:
            self.logger.error(f"can't find host: {host_name}")
            return False

        client = self.clients[host_name]
        try:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(executor, client.set_attribute_single, class_id, instance_id, attribute_id, value)
        except Exception as e:
            self.logger.error(f"set attribute failed: {e}")
            return False

        return True

    def get_attribute_all(self, class_id: int, instance_id: int):
        pass

    def set_attribute_all(self, class_id: int, instance_id: int, value: Any):
        pass

    def parse_implicit_input(self, client: EEIPClient):
        bytes_info_list = self.implicit_input_def["Bytes"]
        ret = {}
        for i, d in enumerate(bytes_info_list):
            ind = i * 2 + 8 # EEIPClient API에 따르면 인덱스 8부터 input 데이터 첫 바이트가 시작됨
            if d == "Mask":
                mask = self.implicit_input_def["Mask"]
                status_dict = read_bit_mask_binary(client.t_o_iodata[ind], mask)
                ret["Status"] = status_dict
            elif isinstance(d, str):
                int_val = read_little_endian(client.t_o_iodata[ind:ind + 1])
                ret[d] = int_val

        return ret