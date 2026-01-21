"""
프로세스 간 공유 메모리 관리자
"""
from multiprocessing import shared_memory
import numpy as np

from src.utils.config_util import SHM_DTYPE
from src.utils.logger import log


class SharedMemoryManager:
    """프로세스 간 공유 메모리 관리자"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, mem_name: str = "COMM_SHM", create: bool = True):
        if hasattr(self, '_initialized'):
            return

        self.mem_dtype = SHM_DTYPE

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

        self._data = np.frombuffer(self.shm.buf, dtype=self.mem_dtype)[0]
        log("SharedMemoryManager initialized")

        self._initialized = True

    @property
    def data(self):
        """공유 메모리 뷰 getter"""
        return self._data

    def close(self):
        """메모리 매니저 종료"""
        if hasattr(self, '_data'):
            del self._data

        if hasattr(self, 'shm'):
            self.shm.close()
            try:
                self.shm.unlink()
            except: pass
        log("SharedMemoryManager closed")
