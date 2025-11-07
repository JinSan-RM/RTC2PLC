import socket
import json
import uuid
import threading
import time
import logging
import tkinter as tk
from collections import deque
from datetime import datetime, timedelta

from .config_util import *
from .calc import classify_object_size, calc_delay

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('plc_actions.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class CommManager(threading.Thread):

    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.command_socket = None
        self.event_socket = None
        self.stream_socket = None
        self.stop_event = threading.Event()

        # ==================== 라인 스캔 타이밍 제어 설정 ====================

        # USE_MIN_INTERVAL = True일 때 사용할 부분
        self.timestamp_queue = deque(maxlen=1000)  # 최대 크기 제한
        self.timestamp_lock = threading.Lock()
        # 분석 완료 대기 큐
        self.analysis_queue = deque(maxlen=100)
        self.queue_lock = threading.Lock()
        # =================================================================
        # 라인 스캔 카메라는 고정된 위치에서 촬영하므로 
        # 스캔 라인 → 에어솔까지의 거리만 중요!
        # 객체 추적 (Y 좌표 기반)

        self.tracked_objects = {}
        self.object_counter = 0
        

    # def start_command_client(self):
    #     logging.info(f"Connecting to camera at {HOST}:{COMMAND_PORT}")
    #     try:
    #         soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #         soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    #         soc.connect((HOST, COMMAND_PORT))
    #         soc.settimeout(10)
    #         logging.info("Camera connection successful")
    #         return soc
    #     except Exception as e:
    #         logging.error(f"Camera connection failed: {e}")
    #         raise

    def send_command(self, command_socket, command):
        command_id = uuid.uuid4().hex[:8]
        logging.debug(f"Sending command '{command.get('Command')}' with id {command_id}")
        command['Id'] = command_id
        message = json.dumps(command, separators=(',', ':')) + '\r\n'

        logging.info(f"📝 Raw message: {message[:200]}")

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

    def handle_response(self, response):
        if not response:
            logging.error("No response or incorrect response ID received from camera")
            raise ValueError("No response or incorrect response ID received")
        message = response.get('Message', '')
        if not response.get("Success", False):
            logging.error(f"Camera command not successful: {message}")
            raise RuntimeError(f"Command not successful: {message}")
        logging.debug(f"Id: {response.get('Id')} successfully received message body: '{message[:100]}'")
        return message

    def _process_interval(self):
        # 물체 간 최소 간격이 지난 데이터를 지워줌
        current_time = datetime.now()
        _interval = timedelta(seconds=MIN_INTERVAL)
        with self.timestamp_lock:
            while self.timestamp_queue:
                if current_time - self.timestamp_queue[0][1] > _interval:
                    self.timestamp_queue.popleft()
                else:
                    # deque 내부 원소들은 시간 순서로 쌓이므로, 더이상 지울 게 없으면 break
                    break

    def check_interval(self, address):
        current_time = datetime.now()
        _interval = timedelta(seconds=MIN_INTERVAL)
        with self.timestamp_lock:
            for addr, timestamp in self.timestamp_queue:
                if addr == address and current_time - timestamp <= _interval:
                    # 0.5초 이내로 들어온 동일 재질-사이즈 물체는 무시
                    logging.info(f"주소 P{address:3X}로 {MIN_INTERVAL}초 간격 내 물체 진입 감지")
                    return False

            self.timestamp_queue.append((address, current_time))
            return True

    # ================================================================

    def listen_for_events(self, size_event=False):
        logging.info(f"Connecting to camera event port at {HOST}:{EVENT_PORT}")
        try:
            self.event_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.event_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.event_socket.connect((HOST, EVENT_PORT))
            logging.info("Event socket connected")
        except Exception as e:
            logging.error(f"Failed to connect to event port: {e}")
            return

        message_buffer = ""

        while not self.stop_event.is_set():
            if USE_MIN_INTERVAL:
                self._process_interval()

            self.event_socket.settimeout(1)
            try:
                data = self.event_socket.recv(1024)
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
                        event = message_json.get('Event', '')
                        inner_message = json.loads(message_json.get('Message', '{}'))
                        
                        if event == "PredictionObject":
                            descriptors = inner_message.get('Descriptors', [])
                            descriptor_value = int(descriptors[0]) if descriptors else 0

                        else:
                            logging.debug(f"event:{event}")

                    except json.JSONDecodeError:
                        logging.error("Invalid JSON received from camera")
                    except Exception as e:
                        logging.error(f"Error processing event: {e}")
                        import traceback
                        traceback.print_exc()

            except socket.timeout:
                pass
            except Exception as e:
                logging.error(f"Error in event loop: {e}")
                continue

    def listen_for_data_stream(self):
        logging.info(f"Connecting to data stream at {HOST}:{DATA_STREAM_PORT}")
        try:
            self.stream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.stream_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.stream_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.stream_socket.connect((HOST, DATA_STREAM_PORT))
            logging.info("Data stream connected")
        except Exception as e:
            logging.error(f"Failed to connect to data stream: {e}")
            return

        expected_header_size = 25
        last_processed_time = 0
        throttle_interval = 1.0

        while not self.stop_event.is_set():
            self.stream_socket.settimeout(1)
            try:
                header = b""
                while len(header) < expected_header_size:
                    chunk = self.stream_socket.recv(expected_header_size - len(header))
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
                metadata = b""
                while len(metadata) < metadata_size:
                    chunk = self.stream_socket.recv(metadata_size - len(metadata))
                    if not chunk:
                        logging.warning("Incomplete metadata received")
                        break
                    metadata += chunk

                # ✓ 수정: 완전한 데이터를 받은 후에 한 번만 호출
                data_body = b""
                while len(data_body) < data_body_size:
                    chunk = self.stream_socket.recv(data_body_size - len(data_body))
                    if not chunk:
                        logging.warning("Incomplete data body received")
                        break
                    data_body += chunk

                print(f"header : {header} \n metadata : {metadata} \n data_body : {data_body}")
                # 완전한 데이터를 받은 후에 한 번만 호출
                if len(data_body) == data_body_size:
                    self.app.on_pixel_line_data(data_body)

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

    def change_pixel_format(self, pixel_format):
        logging.info(f"Set Visualize Select to {pixel_format}")
        self.handle_response(self.send_command({
            "Command": "SetProperty",  # GetProperty가 아닌 SetProperty 사용
            "Property": "VisualizationVariable", 
            "Value": "Raw"  # 또는 "Reflectance", "Absorbance", "Descriptor names" 중 선택
        }))

    def start_command_client(self):
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


    def run(self):
        """스레드의 메인 함수 - 여기서 카메라 초기화 및 실행"""
        logging.info("Starting main function")
        # ==================== 설정 확인 ====================
        logging.info("="*70)
        logging.info("🎯 라인 스캔 카메라 타이밍 제어")
        logging.info(f"  - 컨베이어 속도: {CONVEYOR_SPEED} cm/s")
        logging.info(f"  - 스캔라인 → 에어솔 거리: {SCAN_LINE_TO_AIRSOL} cm")
        logging.info("")
        logging.info("  작동 방식:")
        logging.info("  1. 객체가 스캔 라인을 지나가면 즉시 분석")
        logging.info("  2. 딜레이(초) 후 PLC 신호 전송")
        logging.info("  3. 모든 객체가 동일한 타이밍에 신호 전송됨")
        logging.info("="*70)
        # =================================================

        try:
            # ✓ 수정: with 문 없이 소켓을 인스턴스 변수에 저장
            # self.command_socket = self.start_command_client()
            with self.start_command_client() as command_socket:
            
                logging.info("Sending InitializeCamera command")
                self.handle_response(self.send_command(command_socket, {"Command": "InitializeCamera"}))

                logging.info("Sending GetProperty command")
                ws = self.handle_response(self.send_command(command_socket, {"Command": "GetProperty", "Property": "WorkspacePath"}))

                workflow_path = f"C:/Users/USER/Breeze/Data/Runtime/1029_test.xml"
                logging.info(f"Loading workflow: {workflow_path}")
                self.handle_response(self.send_command(command_socket, {"Command": "LoadWorkflow", "FilePath": workflow_path}))

                logging.info("Starting prediction")
                self.handle_response(self.send_command(command_socket, {"Command": "StartPredict", "IncludeObjectShape": True}))

                # 스레드 시작
                self.event_listener_thread = threading.Thread(target=self.listen_for_events, daemon=True)
                self.data_stream_listener_thread = threading.Thread(target=self.listen_for_data_stream, daemon=True)

                logging.info("Starting event and data stream threads")
                self.event_listener_thread.start()
                self.data_stream_listener_thread.start()

                print("\n" + "="*70)
                print("✓ 프로그램 실행 중")
                print("✓ 실시간 로그: plc_actions.log 파일 확인")
                print("="*70 + "\n")
                
                # 스레드가 종료될 때까지 대기
                while not self.stop_event.is_set():
                    time.sleep(0.1)
                
        except Exception as e:
            logging.error(f"Main function error: {e}")
            import traceback
            traceback.print_exc()

    def quit(self):
        logging.info("Stopping prediction")
        try:
            if self.command_socket:
                response = self.send_command(self.command_socket, {"Command": "StopPredict"})
                self.handle_response(response)
        except Exception as e:
            logging.error(f"Error during stop prediction: {e}")
        
        # 1. stop 이벤트 설정
        self.stop_event.set()
        
        # 2. 스레드 종료 대기 (먼저!)
        if hasattr(self, 'event_listener_thread') and self.event_listener_thread.is_alive():
            logging.info("Waiting for event listener thread to terminate...")
            self.event_listener_thread.join(timeout=5)
            if self.event_listener_thread.is_alive():
                logging.warning("Event listener thread did not terminate properly")
        
        if hasattr(self, 'data_stream_listener_thread') and self.data_stream_listener_thread.is_alive():
            logging.info("Waiting for data stream thread to terminate...")
            self.data_stream_listener_thread.join(timeout=5)
            if self.data_stream_listener_thread.is_alive():
                logging.warning("Data stream thread did not terminate properly")
        
        # 3. 그 다음 소켓 닫기
        try:
            if self.command_socket:
                self.command_socket.close()
        except Exception as e:
            logging.debug(f"Error closing command socket: {e}")
            
        try:
            if self.event_socket:
                self.event_socket.shutdown(socket.SHUT_RDWR)
                self.event_socket.close()
        except Exception as e:
            logging.debug(f"Error closing event socket: {e}")
        
        try:
            if self.stream_socket:
                self.stream_socket.shutdown(socket.SHUT_RDWR)
                self.stream_socket.close()
        except Exception as e:
            logging.debug(f"Error closing stream socket: {e}")
        
        
        logging.info("Program terminated")