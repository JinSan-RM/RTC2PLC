from enum import Enum, IntEnum, auto

class Priority(IntEnum):
    GPIO = 1      # 최고 우선순위
    ETHERCAT = 2  # 중간 우선순위
    MODBUS = 3    # 최저 우선순위

class PinRole(Enum):
    INPUT = auto()
    OUTPUT = auto()