"""
프로세스 간 공유 메모리 관리자
"""
from multiprocessing import shared_memory
import numpy as np

from src.utils.config_util import SHARED_MEMORY_DTYPE
from src.utils.logger import log


class SharedMemoryManager:
    """
    프로세스 간 공유 메모리 관리자
    """
    def __init__(self, mem_name: str = "COMM_SHM", create: bool = True):
        self.mem_dtype = SHARED_MEMORY_DTYPE

        if create:
            try:
                old_mem = shared_memory.SharedMemory(name=mem_name)
                if old_mem:
                    old_mem.close()
                    old_mem.unlink()
            except: pass

            self.shm = shared_memory.SharedMemory(
                name=mem_name,
                create=True,
                size=self.mem_dtype.itemsize
            )
        else:
            self.shm = shared_memory.SharedMemory(name=mem_name)

        self.data = np.frombuffer(self.shm.buf, dtype=self.mem_dtype)[0]
        log("SharedMemoryManager initialized")

    def close(self):
        """
        메모리 매니저 종료
        
        :param self: Description
        """
        if hasattr(self, 'data'):
            del self.data

        if hasattr(self, 'shm'):
            self.shm.close()
            try:
                self.shm.unlink()
            except: pass
        log("SharedMemoryManager closed")
