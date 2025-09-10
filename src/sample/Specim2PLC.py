import socket
import struct
import time
import logging
import json
import threading

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class PLCController:
    def __init__(self, ip="192.168.250.120", port=2004):
        self.ip = ip
        self.port = port
        self.group_3sec = {"PET", "HDPE"}
        self.group_5sec = {"PVC", "LDPE"}
        self.group_7sec = {"PP", "PS"}
        logging.info(f"PLCController initialized with IP: {ip}, Port: {port}")

    def get_category_action(self, material: str):
        material = material.upper().strip()
        if material in self.group_3sec:
            return 3, b'\x01\x01'  # 257 (0x0101)
        elif material in self.group_5sec:
            return 5, b'\x02\x01'  # 258 (0x0102)
        elif material in self.group_7sec:
            return 7, b'\x11\x01'  # 273 (0x0111)
        else:
            raise ValueError(f"Unknown or unsupported material: {material}")

    def create_write_packet(self, address_ascii: bytes, data_bytes: bytes):
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
        packet.extend(b'\x58\x00')
        packet.extend(b'\x02\x00')
        packet.extend(b'\x00\x00')
        packet.extend(b'\x01\x00')
        packet.extend(struct.pack('<H', len(address_ascii)))
        packet.extend(address_ascii)
        packet.extend(b'\x02\x00')
        packet.extend(data_bytes)
        return packet

    def send_packet_to_plc(self, packet, retries=3):
        logging.debug(f"Sending packet (hex): {packet.hex()}")
        for attempt in range(1, retries + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(10)
                    s.connect((self.ip, self.port))
                    s.sendall(packet)
                    response = s.recv(1024)
                    logging.debug(f"Received response (hex): {response.hex()}")
                    return response
            except Exception as e:
                logging.error(f"Attempt {attempt}/{retries} - PLC communication error: {e}")
                if attempt == retries:
                    return None
                time.sleep(2)
        return None

    def write_to_plc(self, material: str):
        try:
            delay_sec, data_to_send = self.get_category_action(material)
            int_value = int.from_bytes(data_to_send, byteorder='little')
            
            logging.info(f"Processing material: {material}, Group: {delay_sec}초, Data: 0x{data_to_send.hex()} ({int_value})")
            
            # Step 1: Send data to %DB0
            db0_address = b'\x25\x44\x42\x30'
            packet_db0 = self.create_write_packet(db0_address, data_to_send)
            logging.info(f"Writing data {data_to_send.hex()} to %DB0")
            response = self.send_packet_to_plc(packet_db0)
            if response is None:
                logging.error(f"Failed to write to %DB0 for material {material}")
                return False
                
            # Step 2: Send value 1 to %DB2
            db2_address = b'\x25\x44\x42\x32'
            data_one = struct.pack('<H', 1)
            packet_db2 = self.create_write_packet(db2_address, data_one)
            logging.info(f"Writing 1 to %DB2")
            response = self.send_packet_to_plc(packet_db2)
            if response is None:
                logging.error(f"Failed to write to %DB2 for material {material}")
                return False
                
            logging.info(f"PLC write successful for material {material}")
            return True
        except ValueError as ve:
            logging.error(f"Error: {ve}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            return False

# 카메라 이벤트 리스너 설정
HOST = '192.168.250.130'  # 카메라 IP 주소
EVENT_PORT = 2500
stop_event = threading.Event()

def listen_for_events(plc_controller):
    # 클래스 매핑 정의
    CLASS_MAPPING = {
        0: "-",
        1: "PET Bottle",
        2: "PET sheet",
        3: "PET G",
        4: "PVC",
        5: "PC",
        6: "Background"
    }
    # 플라스틱 타입 매핑
    PLASTIC_MAPPING = {
        "PET Bottle": "PET",
        "PET sheet": "PET",
        "PET G": "PET",
        "PVC": "PVC",
        "PC": None,
        "Background": None,
        "-": None
    }
    
    logging.info(f"Connecting to camera event port at {HOST}:{EVENT_PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as event_socket:
        event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            event_socket.connect((HOST, EVENT_PORT))
            logging.info("Event socket connected")
        except Exception as e:
            logging.error(f"Failed to connect to event port: {e}")
            return

        message_buffer = ""
        while not stop_event.is_set():
            event_socket.settimeout(1)
            try:
                data = event_socket.recv(1024).decode('utf-8')
                if not data:
                    logging.warning("No data received from camera")
                    break
                
                message_buffer += data
                while '\r\n' in message_buffer:
                    message, message_buffer = message_buffer.split('\r\n', 1)
                    try:
                        message_json = json.loads(message)
                        event = message_json.get('Event', '')
                        
                        if event == "PredictionObject":
                            inner_message = json.loads(message_json.get('Message', '{}'))
                            descriptors = inner_message.get('Descriptors', [])
                            descriptor_value = int(descriptors[0]) if descriptors else 0
                            
                            classification = CLASS_MAPPING.get(descriptor_value, "Unknown")
                            logging.info(f"Classification: {classification}")
                            
                            # 플라스틱 타입으로 변환하여 PLC에 전송
                            plc_material = PLASTIC_MAPPING.get(classification)
                            if plc_material:
                                logging.info(f"Triggering PLC for material: {plc_material}")
                                success = plc_controller.write_to_plc(plc_material)
                                if success:
                                    logging.info(f"PLC action successful for {plc_material}")
                                    time.sleep(1)  # 다음 이벤트 처리 전 대기
                                else:
                                    logging.error(f"PLC action failed for {plc_material}")
                            else:
                                logging.info(f"Skipping PLC action for classification: {classification}")
                    except json.JSONDecodeError:
                        logging.error("Invalid JSON received from camera")
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Error processing camera event: {e}")

def main():
    logging.info("Starting PLC-Camera integration")
    plc_controller = PLCController()
    
    # 카메라 이벤트 리스너 스레드 시작
    event_thread = threading.Thread(target=listen_for_events, args=(plc_controller,))
    event_thread.daemon = True
    event_thread.start()
    
    try:
        logging.info("System running. Press Ctrl+C to stop...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping system...")
    finally:
        stop_event.set()
        event_thread.join(timeout=5)
        logging.info("System stopped")

if __name__ == "__main__":
    main()
