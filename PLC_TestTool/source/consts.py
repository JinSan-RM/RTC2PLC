from enum import Enum

class LSDataType(Enum):
    BIT = 0x00      # X
    BYTE = 0x01     # B
    WORD = 0x02     # W
    DWORD = 0x03    # D
    LWORD = 0x04    # L
    BLOCK = 0x14

DATA_TYPE_INITIAL = {
    LSDataType.BIT: "X",
    LSDataType.BYTE: "B",
    LSDataType.WORD: "W",
    LSDataType.DWORD: "D",
    LSDataType.LWORD: "L",
}

HOST_IP = "192.168.250.120"
TCP_PORT = 2004