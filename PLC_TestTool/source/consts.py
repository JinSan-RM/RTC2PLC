from enum import Enum

class LSDataType(Enum):
    BIT = 0x00      # X
    BYTE = 0x01     # B
    WORD = 0x02     # W
    DWORD = 0x03    # D
    LWORD = 0x04    # L
    BLOCK = 0x14

HOST_IP = "0.0.0.0"
TCP_PORT = 2004