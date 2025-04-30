import socket
import json
import uuid
import threading
import time
import logging
from datetime import datetime, timedelta
from dateutil import tz
import struct

# 로깅 설정
logging.basicConfig(filename='plc_actions.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# PLCController 클래스 정의
class PLCController:
    def __init__(self, ip="192.168.250.120", port=2004):
        self.ip = ip
        self.port = port
        self.group_3sec = {"PET", "HDPE"}
        self.group_5sec = {"PVC", "LDPE"}
        self.group_7sec = {"PP", "PS"}

    def get_category_action(self, material: str):
        material = material.upper().strip()
        if material in self.group_3sec:
            return 3, b'\x01\x01'
        elif material in self.group_5sec:
            return 5, b'\x02\x01'
        elif material in self.group_7sec:
            return 7, b'\x11\x01'
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

    def send_packet_to_plc(self, packet):
        print("Sending packet (hex):", packet.hex())
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.ip, self.port))
                s.sendall(packet)
                response = s.recv(1024)
                print("Received response (hex):", response.hex())
                return response
        except Exception as e:
            print(f"PLC communication error: {e}")
            return None

    def write_to_plc(self, material: str):
        try:
            delay_sec, data_to_send = self.get_category_action(material)
            db0_address = b'\x25\x44\x42\x30'
            packet_db0 = self.create_write_packet(db0_address, data_to_send)
            print(f"Writing data {data_to_send.hex()} to %DB0 for material {material}")
            self.send_packet_to_plc(packet_db0)

            db2_address = b'\x25\x44\x42\x33'
            data_one = struct.pack('<H', 1)
            print(f"Writing 1 to %DB2 for material {material}")
            self.send_packet_to_plc(packet_db2)

            return True
        except ValueError as ve:
            print(f"Error: {ve}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False

# Breeze Runtime 관련 설정
HOST = '192.168.1.185'
COMMAND_PORT = 2000
EVENT_PORT = 2500
DATA_STREAM_PORT = 3000
stop_event = threading.Event()

def start_command_client():
    soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    soc.connect((HOST, COMMAND_PORT))
    soc.settimeout(120)
    return soc

def send_command(command_socket, command):
    command_id = uuid.uuid4().hex[:8]
    print(f"Sending command '{command.get('Command')}' with id {command_id}")
    command['Id'] = command_id
    message = json.dumps(command, separators=(',', ':')) + '\r\n'

    command_socket.sendall(message.encode('utf-8'))

    message_buffer = ""
    while True:
        try:
            part = command_socket.recv(1024).decode('utf-8')
            if not part:
                break
            message_buffer += part

            while '\r\n' in message_buffer:
                full_response_str, message_buffer = message_buffer.split('\r\n', 1)
                try:
                    response_json = json.loads(full_response_str.strip())
                    if response_json.get('Id') == command_id:
                        return response_json
                except json.JSONDecodeError:
                    print(f"Invalid JSON received: {full_response_str}")
                    continue
        except socket.timeout:
            print("Request timed out")
            return None
    return None

def listen_for_events(plc_controller):
    CLASS_MAPPING = {
        0: "-",
        1: "PET Bottle",
        2: "PET sheet",
        3: "PET G",
        4: "PVC",
        5: "PC",
        6: "Background"
    }

    PLASTIC_MAPPING = {
        "PET Bottle": "PET",
        "PET sheet": "PET",
        "PET G": "PET",
        "PVC": "PVC",
        "PC": None,
        "Background": None,
        "-": None
    }

    plastic_groups = {
        "PET Bottle": [],
        "PET sheet": [],
        "PET G": [],
        "PVC": [],
        "PC": [],
        "Background": [],
        "-": []
    }

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as event_socket:
        event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        event_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        event_socket.connect((HOST, EVENT_PORT))

        message_buffer = ""
        while not stop_event.is_set():
            event_socket.settimeout(1)
            try:
                data = event_socket.recv(1024).decode('utf-8')
                if not data:
                    print("No data received")
                    break
                print(f"Raw data Received: {data}")
                message_buffer += data

                while '\r\n' in message_buffer:
                    message, message_buffer = message_buffer.split('\r\n', 1)
                    try:
                        message_json = json.loads(message)
                        event = message_json.get('Event', '')
                        inner_message = json.loads(message_json.get('Message', '{}'))
                        if event == "PredictionObject":
                            print("Full PredictionObject:", json.dumps(inner_message, indent=2))
                            descriptors = inner_message.get('Descriptors', [])
                            descriptor_value = int(descriptors[0]) if descriptors else 0
                            classification = CLASS_MAPPING.get(descriptor_value, "Unknown")

                            if classification in plastic_groups:
                                plastic_groups[classification].append(inner_message)
                            else:
                                print(f"Unknown classification: {classification}")

                            print(f"Classification: {classification}")

                            start_date = convert_ticks_to_datetime(inner_message.get('StartTime', 0))
                            end_date = convert_ticks_to_datetime(inner_message.get('EndTime', 0))
                            start_line = inner_message.get('StartLine', 0)
                            end_line = inner_message.get('EndLine', 0)
                            camera_id = inner_message.get('CameraId', 0)

                            print(
                                f"start line:{start_line} end line:{end_line} start time:{start_date} "
                                f"end time:{end_date} classification:{classification} cameraId:{camera_id}"
                            )

                            # PLC 동작
                            plc_material = PLASTIC_MAPPING.get(classification)
                            if plc_material:
                                print(f"Triggering PLC for material: {plc_material}")
                                success = plc_controller.write_to_plc(plc_material)
                                if success:
                                    print(f"PLC action successful for {plc_material}")
                                    logging.info(f"PLC action successful for {plc_material}")
                                    time.sleep(1)  # PLC 호출 간 딜레이
                                else:
                                    print(f"PLC action failed for {plc_material}")
                                    logging.error(f"PLC action failed for {plc_material}")
                            else:
                                print(f"Skipping PLC action for classification: {classification}")

                        else:
                            print(f"event:{event} message:{inner_message}")
                    except json.JSONDecodeError:
                        print("Invalid JSON received")
            except socket.timeout:
                continue

        print("\n=== Plastic Classification Groups ===")
        for plastic_type, events in plastic_groups.items():
            if events:
                print(f"\nGroup: {plastic_type} (Count: {len(events)})")
                for event in events:
                    start_date = convert_ticks_to_datetime(event.get('StartTime', 0))
                    end_date = convert_ticks_to_datetime(inner_message.get('EndTime', 0))
                    start_line = event.get('StartLine', 0)
                    end_line = event.get('EndLine', 0)
                    camera_id = event.get('CameraId', 0)
                    print(
                        f"  - Event ID: {event.get('Id')}, "
                        f"start line:{start_line}, end line:{end_line}, "
                        f"start time:{start_date}, end time:{end_date}, "
                        f"cameraId:{camera_id}"
                    )

def listen_for_data_stream():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream_socket:
        stream_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        stream_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        stream_socket.connect((HOST, DATA_STREAM_PORT))

        expected_header_size = 25
        while not stop_event.is_set():
            stream_socket.settimeout(1)
            try:
                header = b""
                while len(header) < expected_header_size:
                    chunk = stream_socket.recv(expected_header_size - len(header))
                    if not chunk:
                        break
                    header += chunk

                if len(header) != expected_header_size:
                    print("Incomplete header received")
                    continue
                
                stream_type = header[0]
                frame_number = int.from_bytes(header[1:9], byteorder='little', signed=True)
                timestamp = int.from_bytes(header[9:17], byteorder='little', signed=False)
                metadata_size = int.from_bytes(header[17:21], byteorder='little', signed=False)
                data_body_size = int.from_bytes(header[21:25], byteorder='little', signed=False)

                print(f"Stream Type: {stream_type}, Frame Number: {frame_number}, "
                      f"Timestamp: {timestamp}, Metadata Size: {metadata_size}, Data Body Size: {data_body_size}")

                stream_socket.recv(metadata_size)
                stream_socket.recv(data_body_size)
            except socket.timeout:
                continue

def convert_ticks_to_datetime(ticks):
    return (datetime(1, 1, 1) + timedelta(microseconds=ticks // 10)).replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())

def handle_response(response):
    if not response:
        raise ValueError(f"No response or incorrect response ID received: {response}")

    message = response.get('Message', '')
    if not response.get("Success", False):
        raise RuntimeError(f"Command not successful: {message}")

    print(f"Id: {response.get('Id')} successfully received message body: '{message[:100]}", end="")
    if len(message) > 100:
        print("...", end="")
    print("'")
    return message

def main():
    plc_controller = PLCController()
    with start_command_client() as command_socket:
        handle_response(send_command(command_socket, {"Command": "InitializeCamera"}))
        ws = handle_response(send_command(command_socket, {"Command": "GetProperty", "Property": "WorkspacePath"}))
        workflow_path = f"C:/Users/withwe/breeze/Data/Runtime/Plastic_Classification_1.xml"
        handle_response(send_command(command_socket, {"Command": "LoadWorkflow", "FilePath": workflow_path}))
        handle_response(send_command(command_socket, {"Command": "TakeDarkReference"}))
        handle_response(send_command(command_socket, {"Command": "TakeWhiteReference"}))
        handle_response(send_command(command_socket, {"Command": "StartPredict", "IncludeObjectShape": True}))

        event_listener_thread = threading.Thread(target=listen_for_events, args=(plc_controller,))
        data_stream_listener_thread = threading.Thread(target=listen_for_data_stream)

        event_listener_thread.start()
        data_stream_listener_thread.start()

        input("Press Enter to stop prediction...\n")
        try:
            response = send_command(command_socket, {"Command": "StopPredict"})
            handle_response(response)
        except (ValueError, RuntimeError) as e:
            print(f"Error during stop prediction: {e}")
        finally:
            stop_event.set()
            event_listener_thread.join()
            data_stream_listener_thread.join()

        print("Done")

if __name__ == '__main__':
    main()