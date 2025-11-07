import socket
import time
import struct
from typing import Optional
from enum import Enum

class XGTTester:
    def __init__(self, ip="192.168.250.120", port=2004):
        """XGT 통신 테스터 초기화"""
        self.ip = ip
        self.port = port
        self.timeout = 10
        self.sock = None
        self.connected = False
        
    def connect(self):
        """PLC 연결"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.ip, self.port))
            self.connected = True
            print(f"✅ PLC {self.ip}:{self.port}에 연결되었습니다.")
            return True
        except Exception as e:
            print(f"❌ PLC 연결 실패: {str(e)}")
            self.connected = False
            return False
    
    def disconnect(self):
        """PLC 연결 종료"""
        if self.sock:
            self.sock.close()
        self.connected = False
        print("PLC 연결이 종료되었습니다.")
    
    def send_packet_to_plc(self, packet, description=""):
        """패킷 전송 및 응답 수신"""
        if not self.connected:
            if not self.connect():
                return False, None
        
        try:
            # if description:
                # print(f"\n===== {description} =====")
            # print(f"전송 패킷 (hex): {packet.hex()}")
            self.sock.send(packet)
            response = self.sock.recv(1024)
            # print(f"응답 패킷 (hex): {response.hex()}")
            
            # 응답 상태 확인
            if len(response) >= 28:
                status = response[26:28]
                if status == b'\x00\x00':
                    # print("✅ 성공! 통신이 정상적으로 이루어졌습니다.")
                    return True, response
                else:
                    # print(f"❌ 실패! 상태 코드: {status.hex()}")
                    return False, response
            else:
                print("❌ 응답이 충분하지 않음")
                return False, response
        except Exception as e:
            print(f"❌ 통신 오류: {str(e)}")
            self.connected = False
            return False, None
    
    def create_write_packet(self, address_ascii, data_bytes, data_type=0x02):
        """패킷 생성 함수"""
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
        """D00000에 값 쓰기 (첫 번째 코드 블록 참조)"""
        d_address = b'\x25\x44\x42\x30'  # %DB0 형식 사용
        data_bytes = struct.pack('<H', value)  # 리틀 엔디안 형식으로 변환
        
        packet = self.create_write_packet(d_address, data_bytes)
        # print(f"D00000에 값 {value} 쓰기 시도 중...")
        success, response = self.send_packet_to_plc(packet, f"D00000에 값 {value} 쓰기")
        
        if success:
            # print(f"D00000에 값 {value} 쓰기 성공!")
            return True
        else:
            # print(f"D00000에 값 쓰기 실패!")
            return False
    
    def write_mx_bit(self, address, value):
        """MX 비트 값 쓰기 (두 번째 코드 블록 참조)"""
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
        
        success, response = self.send_packet_to_plc(packet, f"%MX{address} 비트 값 {value} 쓰기")
        return success
    
    def read_mx_bit(self, address):
        """MX 비트 값 읽기 (두 번째 코드 블록 참조)"""
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
            # print(f"%MX{address} 현재 값: {bit_value} ({'ON' if bit_value else 'OFF'})")
            return bit_value
        return None
    
    def write_d_and_set_m300(self, d_value):
        """D00000에 값을 쓰고 성공하면 M300 비트를 ON으로 설정"""
        # print("\n========== D00000 및 M300 통합 테스트 시작 ==========")
        # print(f"1. D00000에 {d_value} 값을 쓰고")
        # print("2. M300 비트를 ON(1)으로 설정합니다.")
        # print("=================================================")
        
        # 1. M300 초기 상태 확인
        initial_m = self.read_mx_bit(300)
        # print(f'initial_m ;{initial_m}')
        
        # 2. D00000에 값 쓰기
        d_success = self.write_d_value(d_value)
        if not d_success:
            print("D00000 쓰기 실패! M300 비트 설정을 건너뜁니다.")
            return False
        
        # 3. M300 비트 ON
        print(f"\nD00000에 값 {d_value} 쓰기 성공! M300 비트 ON 설정 시작...")
        m_success = self.write_mx_bit(300, 1)  # M301에서 M300으로 변경
        if not m_success:
            print("M300 비트 설정 실패!")
            return False
        
        # 4. 충분한 대기 시간 설정
        # print("비트 설정 후 2초 대기...")
        
        # 5. 비트 상태 확인
        # final_m = self.read_mx_bit(300)  # M301에서 M300으로 변경
        # print(f'final_m ; {final_m}')
        # if final_m == 1:`
        #     print("\n✅✅✅ 테스트 성공! D00000에 값을 쓰고 M300 비트가 ON 되었습니다!")
        #     return True
        # else:
        #     print("\n❌ M300 비트 ON 상태가 아닙니다.")
        #     return False`
    
    def write_set_d_and_set_m300(self, d_set, d_value):
        """D00000에 값을 쓰고 성공하면 M300 비트를 ON으로 설정"""
        # print("\n========== D00000 및 M300 통합 테스트 시작 ==========")
        # print(f"1. D00000에 {d_value} 값을 쓰고")
        # print("2. M300 비트를 ON(1)으로 설정합니다.")
        # print("=================================================")
        
        # 1. M300 초기 상태 확인
        initial_m = self.read_mx_bit(300)
        # print(f'initial_m ;{initial_m}')
        
        # 2. D00000에 값 쓰기
        d_success = self.write_set_d_value(d_set, d_value)
        if not d_success:
            print("D00000 쓰기 실패! M300 비트 설정을 건너뜁니다.")
            return False
        
        # 3. M300 비트 ON
        print(f"\nD00000에 값 {d_value} 쓰기 성공! M300 비트 ON 설정 시작...")
        m_success = self.write_mx_bit(300, 1)  # M301에서 M300으로 변경
        if not m_success:
            print("M300 비트 설정 실패!")
            return False
        
    def write_set_d_value(self, d_address=None, value=0):
        """D00000에 값 쓰기 (첫 번째 코드 블록 참조)"""
        d_address = b'\x25\x44\x42\x30'  # %DB0 형식 사용
        data_bytes = struct.pack('<H', value)  # 리틀 엔디안 형식으로 변환
        
        packet = self.create_write_packet(d_address, data_bytes)
        # print(f"D00000에 값 {value} 쓰기 시도 중...")
        success, response = self.send_packet_to_plc(packet, f"D00000에 값 {value} 쓰기")
        
        if success:
            # print(f"D00000에 값 {value} 쓰기 성공!")
            return True
        else:
            # print(f"D00000에 값 쓰기 실패!")
            return False

    def create_bit_packet(self, address: int, onoff: Optional[bool]) -> bytearray:
        var_name = f"%PX{address:d}".encode('ascii')
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
        packet.extend(struct.pack('<H', 0x00))   # Data Type
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
    
    def create_status_packet(self):
        packet = bytearray()
        packet.extend(b'LSIS-XGT')  # 고정
        packet.extend(b'\x00\x00')  # Reserved (무시)
        packet.extend(b'\x00\x00')  # PLC Info (무시)
        packet.append(0xB0)         # CPU Info
        packet.append(0x33)         # Source of Frame (PC to PLC: 0x33, PLC to PC: 0x11)
        packet.extend(b'\x00\x00')  # Invoke ID (무시?)
        packet.extend(b'\x06\x00')  # 바디 부분 바이트 크기
        packet.append(0x00)         # FEnet Position (무시)
        packet.append(0x00)         # Reserved2 (무시)

        packet.extend(b'\xB0\x00')  # status request 명령어
        packet.extend(b'\x00\x00')  # Data Type (무시)
        packet.extend(b'\x00\x00')  # Reserved (무시)

        return packet

    def status_check(self):
        packet = self.create_status_packet()
        ret, response = self.send_packet_to_plc(packet)
        if ret and len(response) == 54:
            sys_state = response[28:36]
            print(f"시스템 상태: {sys_state}")
        else:
            print("❌ 응답이 충분하지 않음")
    
    def read_bit_packet(self, address: int) -> Optional[int]:
        packet = self.create_bit_packet(address, None)
        ret, response = self.send_packet_to_plc(packet)
        if ret and len(response) >= 30:
            bit_value = response[29]
            return bit_value
        elif not response:
            print("PLC에서 연결을 종료했습니다.")
            self.disconnect()
        return None

    def write_bit_packet(self, address: int, onoff) -> bool:
        packet = self.create_bit_packet(address, onoff)
        ret, response = self.send_packet_to_plc(packet)
        if not response:
            print("PLC에서 연결을 종료했습니다.")
            self.disconnect()
        return ret
    
    pending_tasks = {}
    def schedule_bit_off(self, address: int, delay: float = 0.1):
        execute_time = time.perf_counter() + delay
        self.pending_tasks[address] = execute_time

    def process_bit_off(self):
        if not self.pending_tasks:
            return

        current_time = time.perf_counter()
        for address, execute_time in list(self.pending_tasks.items()):
            if current_time >= execute_time:
                try:
                    success = self.write_bit_packet(address, 0)
                    if success:
                        del self.pending_tasks[address]
                except Exception as e:
                    del self.pending_tasks[address]
            else:
                pass # 아직 시간 안됨

    def plush_bit_off(self):
        if not self.pending_tasks:
            return
        
        for address in self.pending_tasks:
            try:
                success = self.write_bit_packet(address, 0)
                if not success:
                    pass
            except Exception as e:
                pass
        
        if self.pending_tasks:
            self.plush_bit_off()
