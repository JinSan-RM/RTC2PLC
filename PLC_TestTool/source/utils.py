import struct
from typing import Dict, Optional

from .consts import LSDataType, DATA_TYPE_INITIAL

def get_variable_name(device_type: str, data_type: LSDataType, address: int):
    return f"%{device_type}{DATA_TYPE_INITIAL[data_type]}{address:d}".encode('ascii')

def _get_packet_body_size(data_dict: Dict[str, bytes], data_type: LSDataType):
    count = len(data_dict)      # 변수 개수
    if data_type == LSDataType.BLOCK:   # 데이터 타입이 Block인 경우 연속 쓰기이며, 이 때엔 변수 개수를 0x0001로만 사용 가능
        count = 1

    if data_type == LSDataType.BIT or data_type == LSDataType.BYTE:
        data_size = 1
    elif data_type == LSDataType.WORD or data_type == LSDataType.BLOCK:
        data_size = 2
    elif data_type == LSDataType.DWORD:
        data_size = 4
    elif data_type == LSDataType.LWORD:
        data_size = 8

    body_size = ((data_size + 2) * count) + 8
    for var_name in data_dict:
        body_size += (len(var_name) + 2)

    return count, data_size, body_size

def create_write_packet(data_dict: Dict[str, bytes], data_type: LSDataType):
    count, data_size, body_size = _get_packet_body_size(data_dict, data_type)

    """ 헤더 """
    packet = bytearray()
    packet.extend(b'LSIS-XGT')  # 고정
    packet.extend(b'\x00\x00')  # Reserved (무시)
    packet.extend(b'\x00\x00')  # PLC Info (무시)
    packet.append(0xB0)         # CPU Info
    packet.append(0x33)         # Source of Frame (PC to PLC: 0x33, PLC to PC: 0x11)
    packet.extend(b'\x00\x00')  # Invoke ID (무시?)
    packet.extend(struct.pack('<H', body_size))  # 바디 부분 바이트 크기
    packet.append(0x00)         # FEnet Position (무시)
    packet.append(0x00)         # Reserved2 (무시)
    """ 헤더 끝 """

    """ 바디 시작 """
    packet.extend(b'\x58\x00')  # 명령어 (Write: 0x58, Read: 0x54)
    packet.extend(struct.pack('<H', data_type.value))   # Data Type
    packet.extend(b'\x00\x00')  # Reserved (무시)

    packet.extend(struct.pack('<H', count))

    for var_name in data_dict:  # 변수 이름 길이 + 변수 이름 쌍
        packet.extend(bytes([len(var_name), 0x00]))
        packet.extend(var_name)

    for data_bytes in data_dict.values():   # 변수 타입별 사이즈 + 실제 변수 값 쌍
        packet.extend(bytes([data_size, 0x00]))
        packet.extend(data_bytes)
    """ 바디 끝 """

    return packet

def create_bit_packet(address: int, onoff: Optional[bool]):
    var_name = get_variable_name("P", LSDataType.BIT, address)
    if onoff is None:
        body_size = 10 + len(var_name)
    else:
        body_size = 13 + len(var_name)

    """ 헤더 """
    packet = bytearray()
    packet.extend(b'LSIS-XGT')  # 고정
    packet.extend(b'\x00\x00')  # Reserved (무시)
    packet.extend(b'\x00\x00')  # PLC Info (무시)
    packet.append(0xB0)         # CPU Info
    packet.append(0x33)         # Source of Frame (PC to PLC: 0x33, PLC to PC: 0x11)
    packet.extend(b'\x00\x00')  # Invoke ID (무시?)
    packet.extend(struct.pack('<H', body_size))  # 바디 부분 바이트 크기
    packet.append(0x00)         # FEnet Position (무시)
    packet.append(0x00)         # Reserved2 (무시)
    """ 헤더 끝 """

    """ 바디 시작 """
    if onoff is None:
        packet.extend(b'\x54\x00')
    else:
        packet.extend(b'\x58\x00')  # 명령어 (Write: 0x58, Read: 0x54)
    packet.extend(struct.pack('<H', LSDataType.BIT.value))   # Data Type
    packet.extend(b'\x00\x00')  # Reserved (무시)
    packet.extend(b'\x01\x00')  # 개수 1개

    # 변수 이름 길이 + 변수 이름 쌍
    packet.extend(bytes([len(var_name), 0x00]))
    packet.extend(var_name)

    # 변수 타입별 사이즈 + 실제 변수 값 쌍
    if onoff is not None:
        packet.extend(b'\x01\x00')
        packet.append(onoff)

    return packet