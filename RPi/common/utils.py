import threading
import time
import queue
import struct
from typing import Optional, Tuple, List, Dict, Callable, Any

from dataclasses import dataclass

from .consts import MessageType, LSDataType

@dataclass
class Message:
    msg_type: MessageType
    func: Callable
    args: Tuple = ()
    kwargs: Dict[str, Any] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}
        if self.timestamp is None:
            self.timestamp = time.time()

    def execute(self):
        return self.func(*self.args, **self.kwargs)

@dataclass
class IOResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    timestamp: Optional[float] = None

class EventManager:
    def __init__(self):
        self.queues: Dict[str, queue.Queue] = {}
        self.lock = threading.Lock()

    def create_queue(self, name: str, maxsize: int = 100):
        with self.lock:
            self.queues[name] = queue.Queue(maxsize=maxsize)

    def send_message(self, queue_name: str, message: Message):
        if queue_name in self.queues:
            try:
                self.queues[queue_name].put_nowait(message)
            except queue.Full:
                print(f"Queue {queue_name} is full, dropping message")

    def get_message(self, queue_name: str, timeout: float = None) -> Message:
        if queue_name in self.queues:
            try:
                return self.queues[queue_name].get(timeout=timeout)
            except queue.Empty:
                return None
        return None

# 비트 마스크가 2진수인 경우
def read_bit_mask_binary(target_byte: int, bit_mask: Dict[str, int]):
    ret = {}
    for bit_meaning, bit_position in bit_mask.items():
        ret[bit_meaning] = bool(target_byte & bit_position)
    return ret

# 비트 마스크가 10진수인 경우
def read_bit_mask_decimal(target_byte: int, bit_mask: Dict[str, int]):
    ret = {}
    for bit_meaning, bit_position in bit_mask.items():
        ret[bit_meaning] = bool(target_byte & (1 << bit_position))
    return ret

# 리틀 엔디언 방식으로 정렬
def read_little_endian(bytes: List[int]) -> int:
    ret = 0
    for i, byte in enumerate(bytes):
        ret |= (byte & 0xFF) << i * 8
    return ret

# 빅 엔디언 방식으로 정렬
def read_big_endian(bytes: List[int]) -> int:
    ret = 0
    for i, byte in enumerate(bytes):
        ret = (ret << 8) | (byte & 0xFF)
    return ret

# 딕셔너리들의 리스트 내에서 특정 키 - 값 쌍을 가진 딕셔너리를 뽑음
def find_dict(l: List[Dict], k: Any, v: Any):
    return next((d for d in l if d.get(k) == v), None)

# LS 산전 FEnet 패킷 파싱
def parse_FEnet_packet(msg: bytes):
    ### 헤더 ###
    header = msg[0:20]
    # company_id = header[0:8] # LSIS-XGT
    # [8:16] -> 무시
    size_of_body, = int.from_bytes(header[16:18], byteorder='little', signed=False)
    # [18:20] -> 무시
    ### 헤더 끝 ###

    ### 프레임 기본 ###
    body = msg[20:20+size_of_body]
    command, = int.from_bytes(body[0:2], byteorder='little', signed=False)
    data_type = int.from_bytes(body[2:4], byteorder='little', signed=False)
    # [4:6] -> 무시
    num_of_block = int.from_bytes(body[6:8], byteorder='little', signed=False)
    ### 프레임 기본 끝 ###

    ### 데이터 ###
    var_list = []
    offset = 8
    for _ in range(num_of_block):
        strlen = int.from_bytes(body[offset:offset + 2], byteorder='little', signed=False)
        offset += 2
        var_name = body[offset:offset + strlen]
        var_list.append(var_name.decode('ascii'))
        offset += strlen
    ### 데이터 끝 ###