import threading
import time
import queue
from typing import Optional, Tuple, List, Dict, Callable, Any

from dataclasses import dataclass

from .consts import MessageType

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
    
def read_bit_mask(target_byte: int, bit_mask: Dict[str, int]):
    ret = {}
    for bit_meaning, bit_position in bit_mask.items():
        ret[bit_meaning] = bool(target_byte & bit_position)
    return ret

def read_little_endian(bytes: List[int]) -> int:
    ret = 0
    for i, byte in enumerate(bytes):
        ret |= (byte & 0xFF) << i * 8
    return ret

def read_big_endian(bytes: List[int]) -> int:
    ret = 0
    for i, byte in enumerate(bytes):
        ret = (ret << 8) | (byte & 0xFF)
    return ret

def find_dict(l: List, k: Any, v: Any):
    return next((d for d in l if d.get(k) == v), None)