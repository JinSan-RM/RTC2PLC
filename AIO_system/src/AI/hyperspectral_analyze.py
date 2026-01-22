import threading
import socket
import json
import time
import uuid
from datetime import datetime, timedelta
from dateutil import tz
from src.utils.logger import log

# Breeze Runtime 관련 설정
HOST = '192.168.250.130'  # 카메라 IP, 실제 IP로 변경 필요
COMMAND_PORT = 2000
EVENT_PORT = 2500
DATA_STREAM_PORT = 3000
stop_event = threading.Event()

def start_command_client():
    log(f"Connecting to camera at {HOST}:{COMMAND_PORT}")
    try:
        soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        soc.connect((HOST, COMMAND_PORT))
        soc.settimeout(120)
        log("Camera connection successful")
        return soc
    except Exception as e:
        log(f"Camera connection failed: {e}")
        raise

def send_command(command_socket, command):
    command_id = uuid.uuid4().hex[:8]
    log(f"Sending command '{command.get('Command')}' with id {command_id}")
    command['Id'] = command_id
    message = json.dumps(command, separators=(',', ':')) + '\r\n'
    try:
        command_socket.sendall(message.encode('utf-8'))
        message_buffer = ""
        while True:
            try:
                part = command_socket.recv(1024).decode('utf-8')
                if not part:
                    log("No response from camera")
                    break
                message_buffer += part
                while '\r\n' in message_buffer:
                    full_response_str, message_buffer = message_buffer.split('\r\n', 1)
                    try:
                        response_json = json.loads(full_response_str.strip())
                        if response_json.get('Id') == command_id:
                            log(f"Received camera response for command {command_id}: {response_json}")
                            return response_json
                    except json.JSONDecodeError:
                        log(f"Invalid JSON received: {full_response_str}")
                        continue
            except socket.timeout:
                log("Camera request timed out")
                return None
    except Exception as e:
        log(f"Error sending command: {e}")
        return None
    return None

def listen_for_events(plc_controller):
    CLASS_MAPPING = {
        0: "HDPE",
        1: "HDPE",
        2: "PET sheet",
        3: "PET G",
        4: "PVC",
        5: "PC",
        6: "Background"
    }
    PLASTIC_MAPPING = {
        "HDPE": "PET",
        "PET sheet": "PET",
        "PET G": "PET",
        "PVC": "PVC",
        "PC": None,
        "Background": None,
        "-": None
    }
    plastic_groups = {
        "PET Bottle": [], "PET sheet": [], "PET G": [], "PVC": [], "PC": [], "Background": [], "-": []
    }

    log(f"Connecting to camera event port at {HOST}:{EVENT_PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as event_socket:
        event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        event_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            event_socket.connect((HOST, EVENT_PORT))
            log("Event socket connected")
        except Exception as e:
            log(f"Failed to connect to event port: {e}")
            return

        message_buffer = ""
        while not stop_event.is_set():
            event_socket.settimeout(1)
            try:
                data = event_socket.recv(1024).decode('utf-8')
                if not data:
                    log("No data received from camera")
                    break
                log(f"Raw camera data received: {data}")
                message_buffer += data
                while '\r\n' in message_buffer:
                    message, message_buffer = message_buffer.split('\r\n', 1)
                    try:
                        message_json = json.loads(message)
                        event = message_json.get('Event', '')
                        inner_message = json.loads(message_json.get('Message', '{}'))
                        if event == "PredictionObject":
                            log("Full PredictionObject: %s", json.dumps(inner_message, indent=2))
                            descriptors = inner_message.get('Descriptors', [])
                            descriptor_value = int(descriptors[0]) if descriptors else 0
                            classification = CLASS_MAPPING.get(descriptor_value, "Unknown")
                            if classification in plastic_groups:
                                plastic_groups[classification].append(inner_message)
                            else:
                                log(f"Unknown classification: {classification}")
                            log(f"Classification: {classification}")
                            start_date = convert_ticks_to_datetime(inner_message.get('StartTime', 0))
                            end_date = convert_ticks_to_datetime(inner_message.get('EndTime', 0))
                            start_line = inner_message.get('StartLine', 0)
                            end_line = inner_message.get('EndLine', 0)
                            camera_id = inner_message.get('CameraId', 0)
                            log(
                                f"start line:{start_line} end line:{end_line} start time:{start_date} "
                                f"end time:{end_date} classification:{classification} cameraId:{camera_id}"
                            )
                            plc_material = PLASTIC_MAPPING.get(classification)
                            if plc_material:
                                log(f"Triggering PLC for material: {plc_material}")
                                success = plc_controller.write_to_plc(plc_material)
                                if success:
                                    log(f"PLC action successful for {plc_material}")
                                    time.sleep(1)
                                else:
                                    log(f"PLC action failed for {plc_material}")
                            else:
                                log(f"Skipping PLC action for classification: {classification}")
                        else:
                            log(f"event:{event} message:{inner_message}")
                    except json.JSONDecodeError:
                        log("Invalid JSON received from camera")
            except socket.timeout:
                continue

        log("\n=== Plastic Classification Groups ===")
        for plastic_type, events in plastic_groups.items():
            if events:
                log(f"\nGroup: {plastic_type} (Count: {len(events)})")
                for event in events:
                    start_date = convert_ticks_to_datetime(event.get('StartTime', 0))
                    end_date = convert_ticks_to_datetime(event.get('EndTime', 0))
                    start_line = event.get('StartLine', 0)
                    end_line = event.get('EndLine', 0)
                    camera_id = event.get('CameraId', 0)
                    log(
                        f"  - Event ID: {event.get('Id')}, "
                        f"start line:{start_line}, end line:{end_line}, "
                        f"start time:{start_date}, end time:{end_date}, "
                        f"cameraId:{camera_id}"
                    )

def listen_for_data_stream():
    log(f"Connecting to data stream at {HOST}:{DATA_STREAM_PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream_socket:
        stream_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        stream_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            stream_socket.connect((HOST, DATA_STREAM_PORT))
            log("Data stream connected")
        except Exception as e:
            log(f"Failed to connect to data stream: {e}")
            return

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
                    log.warning("Incomplete header received")
                    continue
                stream_type = header[0]
                frame_number = int.from_bytes(header[1:9], byteorder='little', signed=True)
                timestamp = int.from_bytes(header[9:17], byteorder='little', signed=False)
                metadata_size = int.from_bytes(header[17:21], byteorder='little', signed=False)
                data_body_size = int.from_bytes(header[21:25], byteorder='little', signed=False)
                #log.debug(f"Stream Type: {stream_type}, Frame Number: {frame_number}, "
                #              f"Timestamp: {timestamp}, Metadata Size: {metadata_size}, Data Body Size: {data_body_size}")
                stream_socket.recv(metadata_size)
                stream_socket.recv(data_body_size)
            except socket.timeout:
                continue

def convert_ticks_to_datetime(ticks):
    return (datetime(1, 1, 1) + timedelta(microseconds=ticks // 10)).replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())

def handle_response(response):
    if not response:
        log("No response or incorrect response ID received from camera")
        raise ValueError("No response or incorrect response ID received")
    message = response.get('Message', '')
    if not response.get("Success", False):
        log(f"Camera command not successful: {message}")
        raise RuntimeError(f"Command not successful: {message}")
    log.debug(f"Id: {response.get('Id')} successfully received message body: '{message[:100]}'")
    return message

def main():
    log("Starting main function")
    global event_socket, stream_socket
    event_socket = None
    stream_socket = None
    try:
        with start_command_client() as command_socket:
            log("Sending InitializeCamera command")
            handle_response(send_command(command_socket, {"Command": "InitializeCamera"}))
            
            log("Sending GetProperty command")
            ws = handle_response(send_command(command_socket, {"Command": "GetProperty", "Property": "WorkspacePath"}))
            
            # workflow_path = f"C:/Users/withwe/breeze/Data/Runtime/Plastic_Classification_1.xml"
            workflow_path = f"C:/Users/withwe/Breeze/Data/Runtime/plastic.xml"
            log(f"Loading workflow: {workflow_path}")
            handle_response(send_command(command_socket, {"Command": "LoadWorkflow", "FilePath": workflow_path}))
            
            log("Taking Dark Reference")
            handle_response(send_command(command_socket, {"Command": "TakeDarkReference"}))
            
            log("Taking White Reference")
            handle_response(send_command(command_socket, {"Command": "TakeWhiteReference"}))
            
            log("Starting prediction")
            handle_response(send_command(command_socket, {"Command": "StartPredict", "IncludeObjectShape": True}))

            data_stream_listener_thread = threading.Thread(target=listen_for_data_stream)
            
            data_stream_listener_thread.daemon = True  # 메인 스레드 종료 시 자동 종료

            log("Starting event and data stream threads")
            data_stream_listener_thread.start()

            # 사용자 입력 대기
            print("Program is running. Press Enter to stop...")
            input()
            
            log("Stopping prediction")
            try:
                response = send_command(command_socket, {"Command": "StopPredict"})
                handle_response(response)
            except (ValueError, RuntimeError) as e:
                log.error(f"Error during stop prediction: {e}")

    except KeyboardInterrupt:
        log("Keyboard interrupt detected")
    except Exception as e:
        log(f"Main function error: {e}")
    finally:
        # 종료 처리
        log("Cleaning up resources...")
        stop_event.set()
        
        # 소켓 강제 종료
        try:
            if event_socket:
                event_socket.shutdown(socket.SHUT_RDWR)
                event_socket.close()
        except Exception as e:
            log(f"Error closing event socket: {e}")
            
        try:
            if stream_socket:
                stream_socket.shutdown(socket.SHUT_RDWR)
                stream_socket.close()
        except Exception as e:
            log(f"Error closing stream socket: {e}")
                
        if 'data_stream_listener_thread' in locals():
            log("Waiting for data stream thread to terminate...")
            data_stream_listener_thread.join(timeout=5)
            if data_stream_listener_thread.is_alive():
                log("Data stream thread did not terminate properly")
        
        log("Program terminated")