import socket
import time
import struct
import logging

logger = logging.getLogger(__name__)

class XGTController:
    def __init__(self, ip="192.168.250.120", port=2004):
        """XGT 통신 초기화"""
        self.ip = ip
        self.port = port
        self.timeout = 30
          # 타임아웃 5초로 조정
        self.sock = None
        self.connected = False
        
    def connect(self):
        """PLC Connect"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.ip, self.port))
            self.connected = True
            logger.info(f"PLC {self.ip}:{self.port}에 연결되었습니다.")
            return True
        except Exception as e:
            logger.error(f"PLC 연결 실패: {str(e)}")
            self.connected = False
            return False
    
    def disconnect(self):
        """PLC Connect close"""
        if self.sock:
            self.sock.close()
        self.connected = False
        logger.info("PLC 연결이 종료되었습니다.")
    
    def send_packet_to_plc(self, packet, description="", max_retries=3):
        for attempt in range(max_retries):
            if not self.connected:
                if not self.connect():
                    time.sleep(0.5)
                    continue
            try:
                # TX: safe hex logging
                if isinstance(packet, (bytes, bytearray)):
                    logger.debug(f"{description}: 전송 패킷 (hex): {packet.hex()}")
                else:
                    logger.debug(f"{description}: 전송 패킷 (non‐bytes): {packet!r}")
                    # 잘못된 타입은 보내지 않고 에러 처리
                    return False, None

                self.sock.send(packet)
                response = self.sock.recv(1024)

                # RX: safe hex logging
                if isinstance(response, (bytes, bytearray)):
                    logger.debug(f"{description}: 응답 패킷 (hex): {response.hex()}")
                else:
                    logger.debug(f"{description}: 응답 패킷 (non‐bytes): {response!r}")
                    return False, None

                if len(response) >= 28:
                    status = response[26:28]
                    if status == b'\x00\x00':
                        logger.info(f"{description}: 통신 성공")
                        return True, response
                    else:
                        logger.error(f"{description}: 실패, 상태 코드: {status.hex()}")
                        return False, response
                else:
                    logger.error(f"{description}: 응답 부족 (길이: {len(response)})")
                    return False, response

            except Exception as e:
                # Exception 자체에 .hex()를 쓰지 않음
                logger.error(f"{description}: 통신 오류 (시도 {attempt + 1}/{max_retries}): {str(e)}")
                self.connected = False
                if attempt < max_retries - 1:
                    time.sleep(0.5)

        logger.error(f"{description}: 최대 재시도 실패")
        return False, None

    
    def create_write_packet(self, address_ascii, data_bytes, data_type=0x02):
        """Packet creation function"""
        packet = bytearray()
        packet.extend(b'LSIS-XGT')
        packet.extend(b'\x00\x00')
        packet.extend(b'\x00\x00')
        packet.append(0xB0)
        packet.append(0x33)
        packet.extend(b'\x00\x00')
        packet.extend(b'\x12\x00')
        packet.append(0x00)
        packet.append(0x00)
        packet.extend(b'\x58\x00')       # Command: Write
        packet.extend(struct.pack('<H', data_type))  # Data Type
        packet.extend(b'\x00\x00')
        packet.extend(b'\x01\x00')
        packet.extend(struct.pack('<H', len(address_ascii)))
        packet.extend(address_ascii)
        # 데이터 길이
        if data_type == 0x01:  # 비트
            packet.extend(b'\x01\x00')
        else:  # 워드
            packet.extend(b'\x02\x00')
        packet.extend(data_bytes)
        return packet
    
    def write_d_value(self, value):
        """D00000에 값 쓰기"""
        d_address = b'\x25\x44\x42\x30'  # %DB0
        data_bytes = struct.pack('<H', value)
        packet = self.create_write_packet(d_address, data_bytes)
        logger.info(f"D00000에 값 {value} 쓰기 시도")
        success, response = self.send_packet_to_plc(packet, f"D00000에 값 {value} 쓰기")
        if success:
            logger.info(f"D00000에 값 {value} 쓰기 성공")
            return True
        logger.error(f"D00000에 값 {value} 쓰기 실패")
        return False

    def write_mx_bit(self, address, value):
        """MX 비트 값 쓰기"""
        packet = bytearray()
        packet.extend(b'LSIS-XGT')
        packet.extend(b'\x00\x00\x00\x00')
        packet.append(0xB0)
        packet.append(0x33)
        packet.extend(b'\x00\x00')
        packet.extend(b'\x13\x00')
        packet.extend(b'\x00\x00')
        packet.extend(b'\x58\x00')       # 쓰기 명령
        packet.extend(b'\x00\x00')       # 비트 타입
        packet.extend(b'\x00\x00')
        packet.extend(b'\x01\x00')
        
        device_name = f'%MX{address}'.encode('ascii')
        packet.extend(bytes([len(device_name), 0x00]))  # 변수명 길이
        packet.extend(device_name)
        
        packet.extend(b'\x01\x01')       # 데이터 타입 및 길이
        packet.append(value)
        logger.info(f"[TX] M{address} {'ON' if value else 'OFF'} 패킷(hex): {packet.hex()}")
        success, response = self.send_packet_to_plc(packet, f"%MX{address} 비트 값 {value} 쓰기")
        if success:
            immediate_value = self.read_mx_bit(address)
            logger.info(f"즉시 확인: %MX{address} = {immediate_value}, {response}")
        return success
    
    def read_mx_bit(self, address):
        """MX 비트 값 읽기"""
        packet = bytearray()
        packet.extend(b'LSIS-XGT')
        packet.extend(b'\x00\x00\x00\x00')
        packet.append(0xB0)
        packet.append(0x33)
        packet.extend(b'\x00\x00')
        packet.extend(b'\x10\x00')
        packet.extend(b'\x00\x00')
        packet.extend(b'\x54\x00')       # 읽기 명령
        packet.extend(b'\x00\x00')       # 비트 타입
        packet.extend(b'\x00\x00')
        packet.extend(b'\x01\x00')
        
        device_name = f'%MX{address}'.encode('ascii')
        packet.extend(bytes([len(device_name), 0x00]))  # 변수명 길이
        packet.extend(device_name)
        
        success, response = self.send_packet_to_plc(packet, f"%MX{address} 비트 값 읽기")
        if success and len(response) >= 30:
            bit_value = response[29]
            logger.info(f"%MX{address} 현재 값: {bit_value} ({'ON' if bit_value else 'OFF'})")
            return bit_value
        return None
    
    # def write_mx_bit(self, address, value):
    #     """MX 비트 값 쓰기"""
    #     packet = bytearray()
    #     packet.extend(b'LSIS-XGT')
    #     packet.extend(b'\x00\x00\x00\x00')
    #     packet.append(0xB0)
    #     packet.append(0x33)
    #     packet.extend(b'\x00\x00')
    #     packet.extend(b'\x13\x00')
    #     packet.extend(b'\x00\x00')
    #     packet.extend(b'\x58\x00')       # 쓰기 명령
    #     packet.extend(b'\x00\x00')       # 비트 타입
    #     packet.extend(b'\x00\x00')
    #     packet.extend(b'\x01\x00')
        
    #     device_name = f'%MX{address}'.encode('ascii')
    #     packet.extend(bytes([len(device_name), 0x00]))  # 변수명 길이
    #     packet.extend(device_name)
        
    #     packet.extend(b'\x01\x01')       # 데이터 타입 및 길이
    #     packet.append(value)
        
    #     success, response = self.send_packet_to_plc(packet, f"%MX{address} 비트 값 {value} 쓰기")
    #     if success:
    #         immediate_value = self.read_mx_bit(address)
    #         logger.info(f"즉시 확인: %MX{address} = {immediate_value}")
    #     return success
    
    # def read_mx_bit(self, address):
    #     """MX 비트 값 읽기"""
    #     packet = bytearray()
    #     packet.extend(b'LSIS-XGT')
    #     packet.extend(b'\x00\x00\x00\x00')
    #     packet.append(0xB0)
    #     packet.append(0x33)
    #     packet.extend(b'\x00\x00')
    #     packet.extend(b'\x10\x00')
    #     packet.extend(b'\x00\x00')
    #     packet.extend(b'\x54\x00')       # 읽기 명령
    #     packet.extend(b'\x00\x00')       # 비트 타입
    #     packet.extend(b'\x00\x00')
    #     packet.extend(b'\x01\x00')
        
    #     device_name = f'%MX{address}'.encode('ascii')
    #     packet.extend(bytes([len(device_name), 0x00]))  # 변수명 길이
    #     packet.extend(device_name)
        
    #     success, response = self.send_packet_to_plc(packet, f"%MX{address} 비트 값 읽기")
    #     if success and len(response) >= 30:
    #         bit_value = response[29]
    #         logger.info(f"%MX{address} 현재 값: {bit_value} ({'ON' if bit_value else 'OFF'})")
    #         return bit_value
    #     return None
    
    def write_d_and_set_m300(self, d_value):
        """D00000에 값을 쓰고 성공하면 M300 비트를 ON으로 설정"""
        logger.info(f"D00000에 {d_value} 쓰고 M300 비트 ON")
        # 1. M300 초기 상태 확인
        initial_m = self.read_mx_bit(300)
        logger.debug(f"Initial M300: {initial_m}")
        
        # 2. D00000에 값 쓰기
        d_success = self.write_d_value(d_value)
        if not d_success:
            logger.error("D00000 쓰기 실패, M300 설정 건너뜀")
            return False
        
        # 3. M300 비트 ON
        logger.info(f"D00000에 {d_value} 쓰기 성공, M300 비트 ON 설정")
        m_success = self.write_mx_bit(300, 1)
        if not m_success:
            logger.error("M300 비트 설정 실패")
            return False
        logger.info("M300 비트 설정 성공")
        return True