import socket
import json
import uuid
import threading
import time
import logging
from datetime import datetime, timedelta
from dateutil import tz
from XGT_run import XGTTester
from calc import calculate_shape_metrics
# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('plc_actions.log'),
        logging.StreamHandler()
    ]
)

# Breeze Runtime 관련 설정
HOST = '192.168.250.130'  # 카메라 IP, 실제 IP로 변경 필요
COMMAND_PORT = 2000
EVENT_PORT = 2500
DATA_STREAM_PORT = 3000
stop_event = threading.Event()

def start_command_client():
    logging.info(f"Connecting to camera at {HOST}:{COMMAND_PORT}")
    try:
        soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        soc.connect((HOST, COMMAND_PORT))
        soc.settimeout(120)
        logging.info("Camera connection successful")
        return soc
    except Exception as e:
        logging.error(f"Camera connection failed: {e}")
        raise

def send_command(command_socket, command):
    command_id = uuid.uuid4().hex[:8]
    logging.debug(f"Sending command '{command.get('Command')}' with id {command_id}")
    command['Id'] = command_id
    message = json.dumps(command, separators=(',', ':')) + '\r\n'
    try:
        command_socket.sendall(message.encode('utf-8'))
        message_buffer = ""
        while True:
            try:
                part = command_socket.recv(1024).decode('utf-8')
                if not part:
                    logging.error("No response from camera")
                    break
                message_buffer += part
                while '\r\n' in message_buffer:
                    full_response_str, message_buffer = message_buffer.split('\r\n', 1)
                    try:
                        response_json = json.loads(full_response_str.strip())
                        if response_json.get('Id') == command_id:
                            logging.debug(f"Received camera response for command {command_id}: {response_json}")
                            return response_json
                    except json.JSONDecodeError:
                        logging.error(f"Invalid JSON received: {full_response_str}")
                        continue
            except socket.timeout:
                logging.error("Camera request timed out")
                return None
    except Exception as e:
        logging.error(f"Error sending command: {e}")
        return None
    return None

def listen_for_events(XGT, size_event=False):
    CLASS_MAPPING = {
        0: "_",
        1: "PP",
        2: "HDPE",
        3: "PS",
        4: "LDPE",
        5: "ABS",
        6: "PET"
    }
    PLASTIC_VALUE_MAPPING = {
        "HDPE": 0x88,
        "PS": 0x89,
        "PP": 0x8A,
        "LDPE": 0x8B,
        "ABS": 0x8C,
        "PET": 0x8D
    }

    logging.info(f"Connecting to camera event port at {HOST}:{EVENT_PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as event_socket:
        event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        event_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
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
                data = event_socket.recv(1024)
                if not data:
                    logging.warning("No data received from camera")
                    break
                try:
                    decoded_data = data.decode('utf-8')
                except UnicodeDecodeError as e:
                    logging.error(f"Unicode decode error: {e}")
                    continue
                message_buffer += decoded_data
                while '\r\n' in message_buffer:
                    message, message_buffer = message_buffer.split('\r\n', 1)
                    try:
                        message_json = json.loads(message)
                        print(f"message_json received: {message_json}")
                        event = message_json.get('Event', '')
                        print(f"Event received: {event}")
                        inner_message = json.loads(message_json.get('Message', '{}'))
                        print(f"inner_message received: {inner_message}")
                        if event == "PredictionObject":
                            descriptors = inner_message.get('Descriptors', [])
                            descriptor_value = int(descriptors[0]) if descriptors else 0
                            classification = CLASS_MAPPING.get(descriptor_value, "Unknown")
                            plc_value = PLASTIC_VALUE_MAPPING.get(classification)
                            logging.info(f'Descriptors {descriptors}  descriptor_value {descriptor_value}\n classfication {classification}')

                            shape = inner_message.get('Shape', {})
                            center, border = shape.get('Center', []), shape.get('Border', [])
                            pos = calculate_shape_metrics(border)
                            logging.info(f'pos data {pos}')
                            # Event 가 발생하고 Noise를 잡기 위해서
                            if plc_value is not None and (pos['width'] > 20 and pos['width'] < 800 ) and (pos['height'] > 20 and pos['height'] < 2000):
                                try:
                                    if size_event:
                                        if pos['size_category'] == "small":
                                            plc_value = 1  # 1번 블로우
                                            success = XGT.create_bit_packet(address=plc_value, onoff=1)  # 1번 블로우
                                            
                                        elif pos['size_category'] == "medium":
                                            plc_value = 2  # 1번 블로우
                                            success = XGT.create_bit_packet(address=plc_value, onoff=1)  # 1번 블로우
                                        else:
                                            plc_value = 3  # 1번 블로우
                                            success = XGT.create_bit_packet(address=plc_value, onoff=1)  # 2번 블로우
                                    else:
                                        success = XGT.XGT.create_bit_packet(address=plc_value, onoff=1)  # 1번 블로우
                                    
                                    if success:
                                        logging.info(f"PLC action successful for value {plc_value}")
                                    else:
                                        logging.error(f"PLC action failed for value {plc_value}")
                                except Exception as e:
                                    logging.error(f"PLC write exception: {e}")
                            else:
                                logging.info(f"Skipping PLC action for classification: {classification}")
                        else:
                            logging.debug(f"event:{event} message:{inner_message}")
                    except json.JSONDecodeError:
                        logging.error("Invalid JSON received from camera")
            except socket.timeout:
                pass
            except Exception as e:
                logging.error(f"Error in event loop: {e}")
                continue


def listen_for_data_stream():
    logging.info(f"Connecting to data stream at {HOST}:{DATA_STREAM_PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream_socket:
        stream_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        stream_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            stream_socket.connect((HOST, DATA_STREAM_PORT))
            logging.info("Data stream connected")
        except Exception as e:
            logging.error(f"Failed to connect to data stream: {e}")
            return

        expected_header_size = 25
        last_processed_time = 0
        throttle_interval = 1.0  # 1초 간격

        while not stop_event.is_set():
            stream_socket.settimeout(1)
            try:
                header = b""
                while len(header) < expected_header_size:
                    chunk = stream_socket.recv(expected_header_size - len(header))
                    if not chunk:
                        logging.warning("No data received from stream")
                        break
                    header += chunk
                if len(header) != expected_header_size:
                    logging.warning("Incomplete header received")
                    continue

                stream_type = header[0]
                frame_number = int.from_bytes(header[1:9], byteorder='little', signed=True)
                timestamp = int.from_bytes(header[9:17], byteorder='little', signed=False)
                metadata_size = int.from_bytes(header[17:21], byteorder='little', signed=False)
                data_body_size = int.from_bytes(header[21:25], byteorder='little', signed=False)
                # logging.info(f'stream_type {stream_type} \n frame_number {frame_number} \n timestamp {timestamp} \n metadata_size {metadata_size} data_body_size {data_body_size}')

                # 메타데이터 수신
                metadata = b""
                while len(metadata) < metadata_size:
                    chunk = stream_socket.recv(metadata_size - len(metadata))
                    if not chunk:
                        logging.warning("Incomplete metadata received")
                        break
                    metadata += chunk
                # logging.info(f'metadata (hex): {metadata.hex()}')

                # 데이터 본문 수신
                data_body = b""
                while len(data_body) < data_body_size:
                    chunk = stream_socket.recv(data_body_size - len(data_body))
                    if not chunk:
                        logging.warning("Incomplete data body received")
                        break
                    data_body += chunk
                # logging.info(f'data_body (hex): {data_body.hex()}')

                current_time = time.time()
                if current_time - last_processed_time >= throttle_interval:
                    last_processed_time = current_time
                else:
                    logging.debug(f"Skipping frame {frame_number} due to throttle limit")

            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Error in data stream: {e}")
                continue



def convert_ticks_to_datetime(ticks):
    return (datetime(1, 1, 1) + timedelta(microseconds=ticks // 10)).replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())

def handle_response(response):
    if not response:
        logging.error("No response or incorrect response ID received from camera")
        raise ValueError("No response or incorrect response ID received")
    message = response.get('Message', '')
    if not response.get("Success", False):
        logging.error(f"Camera command not successful: {message}")
        raise RuntimeError(f"Command not successful: {message}")
    logging.debug(f"Id: {response.get('Id')} successfully received message body: '{message[:100]}'")
    return message

def main():
    logging.info("Starting main function")
    XGT = XGTTester(ip="192.168.250.120", port=2004)
    global event_socket, stream_socket
    event_socket = None
    stream_socket = None
    try:
        with start_command_client() as command_socket:
            logging.info("Sending InitializeCamera command")
            handle_response(send_command(command_socket, {"Command": "InitializeCamera"}))
            
            logging.info("Sending GetProperty command")
            ws = handle_response(send_command(command_socket, {"Command": "GetProperty", "Property": "WorkspacePath"}))
            
            workflow_path = f"C:/Users/withwe/Breeze/Data/Runtime/PP_PS_HDPE_Classification.xml"
            logging.info(f"Loading workflow: {workflow_path}")
            handle_response(send_command(command_socket, {"Command": "LoadWorkflow", "FilePath": workflow_path}))
            
            logging.info("Starting prediction")
            handle_response(send_command(command_socket, {"Command": "StartPredict", "IncludeObjectShape": True}))

            # 스레드 시작
            event_listener_thread = threading.Thread(target=listen_for_events, args=(XGT,))
            data_stream_listener_thread = threading.Thread(target=listen_for_data_stream)
            
            event_listener_thread.daemon = True  # 메인 스레드 종료 시 자동 종료
            data_stream_listener_thread.daemon = True  # 메인 스레드 종료 시 자동 종료

            logging.info("Starting event and data stream threads")
            event_listener_thread.start()
            data_stream_listener_thread.start()

            # 사용자 입력 대기
            print("Program is running. Press Enter to stop...")
            input()
            
            logging.info("Stopping prediction")
            try:
                response = send_command(command_socket, {"Command": "StopPredict"})
                handle_response(response)
            except (ValueError, RuntimeError) as e:
                logging.error(f"Error during stop prediction: {e}")

    except KeyboardInterrupt:
        logging.info("Keyboard interrupt detected")
    except Exception as e:
        logging.error(f"Main function error: {e}")
    finally:
        # 종료 처리
        logging.info("Cleaning up resources...")
        stop_event.set()
        
        # 소켓 강제 종료
        try:
            if event_socket:
                event_socket.shutdown(socket.SHUT_RDWR)
                event_socket.close()
        except Exception as e:
            logging.debug(f"Error closing event socket: {e}")
            
        try:
            if stream_socket:
                stream_socket.shutdown(socket.SHUT_RDWR)
                stream_socket.close()
        except Exception as e:
            logging.debug(f"Error closing stream socket: {e}")
        
        # 스레드 종료 대기
        if 'event_listener_thread' in locals():
            logging.info("Waiting for event listener thread to terminate...")
            event_listener_thread.join(timeout=5)
            if event_listener_thread.is_alive():
                logging.warning("Event listener thread did not terminate properly")
                
        if 'data_stream_listener_thread' in locals():
            logging.info("Waiting for data stream thread to terminate...")
            data_stream_listener_thread.join(timeout=5)
            if data_stream_listener_thread.is_alive():
                logging.warning("Data stream thread did not terminate properly")
        
        logging.info("Program terminated")

if __name__ == '__main__':
    main()