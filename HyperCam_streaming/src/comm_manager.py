"""통신 관리자"""
import socket
import json
import uuid
import threading
import time
import logging
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .config_util import (
    HOST, COMMAND_PORT, EVENT_PORT, DATA_STREAM_PORT, WORKFLOW_PATH,
    CONVEYOR_SPEED, SCAN_LINE_TO_AIRSOL, USE_MIN_INTERVAL, MIN_INTERVAL,
    CLASS_MAPPING, PLASTIC_VALUE_MAPPING_LARGE, PLASTIC_VALUE_MAPPING_SMALL,
    PLASTIC_SIZE_MAPPING, STREAM_TYPE, MIN_PULSE_WIDTH
)
from .calc import classify_object_size, calc_delay, get_border_coords
from .XGT_run import XGTTester

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('plc_actions.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


@dataclass
class CommSockets:
    """소켓 모음"""
    command_socket: socket.socket = None
    event_socket: socket.socket = None
    stream_socket: socket.socket = None


@dataclass
class Threads:
    """스레드 모음"""
    cleanup_thread: threading.Thread = None
    event_listener_thread: threading.Thread = None
    data_stream_listener_thread: threading.Thread = None
    stop_event: threading.Event = threading.Event()
    check_time: float = 0


@dataclass
class QueueAndLock:
    """큐와 락 모음"""
    # USE_MIN_INTERVAL = True일 때 사용할 부분
    timestamp_queue: deque = None
    timestamp_lock = threading.Lock()
    # 분석 완료 대기 큐
    analysis_queue: deque = None
    queue_lock = threading.Lock()


@dataclass
class Trackings:
    """제품 트래킹 관리"""
    tracked_objects: dict = field(default_factory=dict)
    obj_counter: int = 0
    tracking_lock = threading.Lock()


@dataclass
class ObjectInfo:
    """제품 정보"""
    obj_id: int = 0             # ID
    classification: str = ""    # 재질 분류
    plc_value: int = 0          # 재질 - 사이즈 에 따른 에어 분사 관련 PLC 주소
    size: str = ""              # 사이즈(large/small)
    size_addr: int = 0          # 사이즈에 따른 배출 알림 PLC 주소
    y_position: int = 0         # 제품 중심 y좌표


# pylint: disable=broad-exception-caught
class CommManager(threading.Thread):
    """통신 관리자"""
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.comm_sockets = CommSockets()
        self.threads = Threads()

        # ==================== 라인 스캔 타이밍 제어 설정 ====================
        self.queue_n_lock = QueueAndLock()
        self.queue_n_lock.timestamp_queue = deque(maxlen=1000)  # 최대 크기 제한
        self.queue_n_lock.analysis_queue = deque(maxlen=100)
        # =================================================================
        # 라인 스캔 카메라는 고정된 위치에서 촬영하므로
        # 스캔 라인 → 에어솔까지의 거리만 중요!
        # 객체 추적 (Y 좌표 기반)

        self.trackings = Trackings()

        self.xgt_tester = XGTTester()

    def start_command_client(self) -> socket.socket:
        """요청 관리자 시작"""
        logging.info("Connecting to camera at %s:%d", HOST, COMMAND_PORT)
        try:
            soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            soc.connect((HOST, COMMAND_PORT))
            soc.settimeout(120)
            logging.info("Camera connection successful")
            return soc
        except Exception as e:
            logging.error("Camera connection failed: %s", str(e))
            raise

    def send_command(self, command_socket: socket.socket, command: dict):
        """카메라로 요청 전송"""
        command_id = uuid.uuid4().hex[:8]
        logging.debug("Sending command '%s' with id %s", command.get('Command'), command_id)
        command['Id'] = command_id
        message = json.dumps(command, separators=(',', ':')) + '\r\n'

        logging.info("📝 Raw message: %s", message[:200])

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
                                logging.debug(
                                    "Received camera response for command %s: %s",
                                    command_id,
                                    str(response_json)
                                )
                                return response_json
                        except json.JSONDecodeError:
                            logging.error("Invalid JSON received: %s", full_response_str)
                            continue
                except socket.timeout:
                    logging.error("Camera request timed out")
                    return None
        except Exception as e:
            logging.error("Error sending command: %s", str(e))
            return None
        return None

    def handle_response(self, response):
        """카메라로부터의 응답"""
        if not response:
            logging.error("No response or incorrect response ID received from camera")
            raise ValueError("No response or incorrect response ID received")
        message = response.get('Message', '')
        if not response.get("Success", False):
            logging.error("Camera command not successful: %s", message)
            raise RuntimeError(f"Command not successful: {message}")
        logging.debug(
            "Id: %s successfully received message body: '%s'",
            response.get('Id'),
            message[:100]
        )

        return message

    def _process_interval(self):
        # 물체 간 최소 간격이 지난 데이터를 지워줌
        current_time = datetime.now()
        _interval = timedelta(seconds=MIN_INTERVAL)
        with self.queue_n_lock.timestamp_lock:
            while self.queue_n_lock.timestamp_queue:
                if current_time - self.queue_n_lock.timestamp_queue[0][1] > _interval:
                    self.queue_n_lock.timestamp_queue.popleft()
                else:
                    # deque 내부 원소들은 시간 순서로 쌓이므로, 더이상 지울 게 없으면 break
                    break

    def _check_interval(self, address):
        current_time = datetime.now()
        _interval = timedelta(seconds=MIN_INTERVAL)
        with self.queue_n_lock.timestamp_lock:
            for addr, timestamp in self.queue_n_lock.timestamp_queue:
                if addr == address and current_time - timestamp <= _interval:
                    # 0.5초 이내로 들어온 동일 재질-사이즈 물체는 무시
                    logging.info("주소 P%03X로 %.2f초 간격 내 물체 진입 감지", address, MIN_INTERVAL)
                    return False

            self.queue_n_lock.timestamp_queue.append((address, current_time))
            return True

    # ==================== 라인 스캔용 타이밍 제어 ====================
    def schedule_plc_signal_delay(self, obj_info: ObjectInfo, delay: float):
        """
        10ms 펄스로 신호 전송 (PLC에서 상승엣지 감지)
        """
        def _send_signal(_info=obj_info):
            try:
                with self.trackings.tracking_lock:
                    if _info.obj_id in self.trackings.tracked_objects:
                        obj_data = self.trackings.tracked_objects[_info.obj_id]
                        if obj_data['analysis_complete']:
                            # 재질 신호 직후 사이즈 신호
                            success1 = self.xgt_tester.write_bit_packet(
                                address=_info.plc_value,
                                onoff=1
                            )
                            success2 = self.xgt_tester.write_bit_packet(
                                address=_info.size_addr,
                                onoff=1
                            )
                            if success1 and success2:
                                # 재질 on-off 사이에 사이즈 on-off 가 들어갈 수 있도록 처리
                                self.xgt_tester.schedule_bit_off(
                                    address=_info.size_addr,
                                    delay=MIN_PULSE_WIDTH
                                )
                                self.xgt_tester.schedule_bit_off(
                                    address=_info.plc_value,
                                    delay=MIN_PULSE_WIDTH
                                )
                                logging.info(
                                    "✓ [PLC펄스] ID=%d, Y=%d, 재질=%s, size=%s, 주소=P%03X/P%03X",
                                    _info.obj_id,
                                    _info.y_position,
                                    _info.classification,
                                    _info.size,
                                    _info.plc_value,
                                    _info.size_addr
                                )
                            else:
                                logging.warning("✗ [PLC펄스] ID=%d - 전송 실패", _info.obj_id)

                            obj_data['status'] = 'completed'
                            threading.Timer(1.0, lambda: self.cleanup_object(_info.obj_id)).start()
                        else:
                            logging.warning("⚠ [PLC펄스] ID=%d - 분석 미완료", _info.obj_id)
                            obj_data['status'] = 'timeout'
                    else:
                        logging.error("✗ [PLC펄스] ID=%d - 객체 없음", _info.obj_id)

            except Exception as e:
                logging.error("PLC 신호 전송 오류: %s", str(e))

        # 고정 지연 시간 후 신호 전송
        timer = threading.Timer(delay, _send_signal)
        timer.daemon = True
        timer.start()

        # logging.info(
        #     "→ [신호예약] ID=%d, Y=%d, 재질=%s, %.2f초 후 전송",
        #     obj_info.obj_id,
        #     obj_info.y_position,
        #     obj_info.classification,
        #     delay
        # )

    def cleanup_object(self, obj_id):
        """객체 정리"""
        with self.trackings.tracking_lock:
            if obj_id in self.trackings.tracked_objects:
                del self.trackings.tracked_objects[obj_id]
                logging.debug("객체 제거: ID=%d", obj_id)

    def cleanup_old_objects(self):
        """오래된 객체 자동 정리"""
        while not self.threads.stop_event.is_set():
            time.sleep(5)
            current_time = time.time()

            with self.trackings.tracking_lock:
                to_remove = []
                for obj_id, obj_data in self.trackings.tracked_objects.items():
                    age = current_time - obj_data['detect_time']
                    if age > 10:  # 10초 이상
                        to_remove.append(obj_id)
                        logging.debug("타임아웃: ID=%d (상태=%s)", obj_id, obj_data['status'])

                for obj_id in to_remove:
                    del self.trackings.tracked_objects[obj_id]
    # ================================================================

# region event listener
    def _listen_for_events(self):
        """제품 감지 이벤트"""
        logging.info("Connecting to camera event port at %s:%d", HOST, EVENT_PORT)
        try:
            self.comm_sockets.event_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.comm_sockets.event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.comm_sockets.event_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.comm_sockets.event_socket.connect((HOST, EVENT_PORT))
            logging.info("Event socket connected")
        except Exception as e:
            logging.error("Failed to connect to event port: %s", str(e))
            return

        message_buffer = ""

        while not self.threads.stop_event.is_set():
            # 0.5초 이내 들어오는 데이터들을 하나로 객체 묶음
            # USE_MIN_INTERVAL = True    # default
            # 동작 유무 판단 시 320줄, 380줄 주석 처리 필요
            if USE_MIN_INTERVAL:
                self._process_interval()

            current_time = time.perf_counter()
            if current_time - self.threads.check_time >= 1:
                self.xgt_tester.status_check()
                self.threads.check_time = current_time

            # 활성화 된 비트들 off 처리 - 각 프레임마다 프로세스 진행해야 함
            self.xgt_tester.process_bit_off()

            self.comm_sockets.event_socket.settimeout(1)
            try:
                data = self.comm_sockets.event_socket.recv(1024)
                if not data:
                    logging.warning("No data received from camera")
                    break
                try:
                    decoded_data = data.decode('utf-8')
                except UnicodeDecodeError as e:
                    logging.error("Unicode decode error: %s", str(e))
                    continue
                message_buffer += decoded_data

                # 메시지 버퍼 처리
                self._process_event_buffer(message_buffer)

            except socket.timeout:
                pass
            except Exception as e:
                logging.error("Error in event loop: %s", str(e))
                continue

    def _process_event_buffer(self, message_buffer: str):
        """이벤트 메시지 처리"""
        while '\r\n' in message_buffer:
            message, message_buffer = message_buffer.split('\r\n', 1)
            try:
                message_json = json.loads(message)
                event = message_json.get('Event', '')
                inner_message = json.loads(message_json.get('Message', '{}'))

                if event == "PredictionObject":
                    descriptors = inner_message.get('Descriptors', [])
                    descriptor_value = int(descriptors[0]) if descriptors else 0
                    classification = CLASS_MAPPING.get(descriptor_value, "Unknown")

                    shape = inner_message.get('Shape', {})
                    center = shape.get('Center', [])
                    if not center:
                        logging.warning("No center position in shape data")
                        continue

                    # ==================== 라인 스캔 처리 ====================
                    # 라인 스캔이므로 X 좌표는 무의미, Y 좌표로 객체 구분
                    y_position = center[1] if len(center) > 1 else center[0]
                    delay = calc_delay(y_position)
                    if y_position >= 4800:
                        continue

                    # 일단 감지했으므로 감지 신호 보냄
                    size = classify_object_size(center[0])
                    plc_value = None
                    if size is None:
                        logging.debug("⊗ [가이드라인] 무시")
                        continue  # ← 다음 객체로 스킵!

                    if size == "large":
                        plc_value = PLASTIC_VALUE_MAPPING_LARGE.get(classification)
                    elif size == "small":
                        plc_value = PLASTIC_VALUE_MAPPING_SMALL.get(classification)

                    size_addr = PLASTIC_SIZE_MAPPING[size]
                    if not plc_value or not size_addr:
                        continue

                    detection_time = time.time()

                    with self.trackings.tracking_lock:
                        obj_id = self.trackings.obj_counter
                        self.trackings.obj_counter += 1

                        obj_info = ObjectInfo(
                            obj_id=obj_id,
                            classification=classification,
                            plc_value=plc_value,
                            size=size,
                            size_addr=size_addr,
                            y_position=y_position
                        )

                        # 객체 정보 저장
                        self.trackings.tracked_objects[obj_id] = {
                            'object_info': obj_info,
                            'detect_time': detection_time,
                            'analysis_complete': True,  # 분석 즉시 완료
                            'status': 'scheduled'
                        }

                    border = shape.get("Border", [])
                    x0, x1, y0, y1 = get_border_coords(border)
                    start_frame = inner_message.get("StartLine", 0)
                    end_frame = inner_message.get("EndLine", 0)
                    info = {
                        "x0": x0,
                        "x1": x1,
                        "y0": y0,
                        "y1": y1,
                        "start_frame": start_frame,
                        "end_frame": end_frame
                    }
                    self.app.on_obj_detected(info, classification)
                    # logging.info(
                    #     "★ [감지완료] Y=%d, 재질=%s, border=%s, start=%d, end=%d",
                    #     y_position,
                    #     classification,
                    #     str(border),
                    #     start_frame,
                    #     end_frame
                    # )

                    # 고정 지연 시간 후 PLC 신호 예약
                    self.schedule_plc_signal_delay(obj_info, delay)
                else:
                    logging.debug("event:%s", event)
            except json.JSONDecodeError:
                logging.error("Invalid JSON received from camera")
            except Exception as e:
                logging.error("Error processing event: %s", str(e))
                traceback.print_exc()
# endregion

# region data stream listener
    def _listen_for_data_stream(self):
        """카메라 라인 스캔 데이터 스트림"""
        logging.info("Connecting to data stream at %s:%d", HOST, DATA_STREAM_PORT)
        try:
            self.comm_sockets.stream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.comm_sockets.stream_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.comm_sockets.stream_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.comm_sockets.stream_socket.connect((HOST, DATA_STREAM_PORT))
            logging.info("Data stream connected")
        except Exception as e:
            logging.error("Failed to connect to data stream: %s", str(e))
            return

        expected_header_size = 25
        last_processed_time = 0
        throttle_interval = 1.0

        while not self.threads.stop_event.is_set():
            self.comm_sockets.stream_socket.settimeout(1)
            try:
                header = b""
                while len(header) < expected_header_size:
                    chunk = self.comm_sockets.stream_socket.recv(expected_header_size - len(header))
                    if not chunk:
                        logging.warning("No data received from stream")
                        break
                    header += chunk
                if len(header) != expected_header_size:
                    logging.warning("Incomplete header received")
                    continue

                stream_type = STREAM_TYPE[header[0]]
                if not stream_type or stream_type == "None":
                    continue

                frame_number = int.from_bytes(header[1:9], byteorder='little', signed=True)
                timestamp = int.from_bytes(header[9:17], byteorder='little', signed=False)
                metadata_size = int.from_bytes(header[17:21], byteorder='little', signed=False)
                data_body_size = int.from_bytes(header[21:25], byteorder='little', signed=False)
                metadata = b""
                while len(metadata) < metadata_size:
                    chunk = self.comm_sockets.stream_socket.recv(metadata_size - len(metadata))
                    if not chunk:
                        logging.warning("Incomplete metadata received")
                        break
                    metadata += chunk

                # ✓ 수정: 완전한 데이터를 받은 후에 한 번만 호출
                data_body = b""
                while len(data_body) < data_body_size:
                    chunk = self.comm_sockets.stream_socket.recv(data_body_size - len(data_body))
                    if not chunk:
                        logging.warning("Incomplete data body received")
                        break
                    data_body += chunk

                # if stream_type != "Raw":
                #     print(f"""header : {header} \n
                #         metadata : {metadata} \n
                #         data_body : {data_body}""")
                # print(f"stream_type: {stream_type}\ndata_body; {data_body}")
                # 완전한 데이터를 받은 후에 한 번만 호출
                if len(data_body) == data_body_size:
                    info = {
                        "frame_number": frame_number,
                        "data_body": data_body
                    }
                    self.app.on_pixel_line_data(info)

                current_time = time.time()
                if current_time - last_processed_time >= throttle_interval:
                    last_processed_time = current_time
                else:
                    logging.debug("Skipping frame %d due to throttle limit", frame_number)

            except socket.timeout:
                continue
            except Exception as e:
                logging.error("Error in data stream: %s", str(e))
                continue
# endregion

    def change_pixel_format(self, pixel_format):
        """pixel 형식 변경"""
        # logging.info(f"Set Visualize Select to {pixel_format}")
        # self.handle_response(self.send_command(self.comm_sockets.command_socket, {
        #     "Command": "SetProperty",  # GetProperty가 아닌 SetProperty 사용
        #     "Property": "VisualizationVariable",
        #     "Value": pixel_format
        #     # "Raw", "Reflectance", "Absorbance" 또는 "기타 Descriptor 이름" 중 선택
        # }))
        res = self.handle_response(self.send_command(
            self.comm_sockets.command_socket, {
                "Command": "GetProperty",
                "Property": "Fields",
                "NodeID": "7200e406"
            }
        ))
        logging.info("Fields: %s", str(res))

    def set_visualization_blend(self, onoff: bool):
        """블렌드 사용할 것인가"""
        logging.info("Set Visualize Blend %s", onoff)
        self.handle_response(self.send_command(
            self.comm_sockets.command_socket, {
                "Command": "SetProperty",  # GetProperty가 아닌 SetProperty 사용
                "Property": "VisualizationBlend", 
                "Value": onoff
                # "Raw", "Reflectance", "Absorbance" 또는 "기타 Descriptor 이름" 중 선택
            }
        ))

    def run(self):
        """스레드의 메인 함수 - 여기서 카메라 초기화 및 실행"""
        logging.info("Starting main function")
        # ==================== 설정 확인 ====================
        logging.info("="*70)
        logging.info("🎯 라인 스캔 카메라 타이밍 제어")
        logging.info("  - 컨베이어 속도: %.2f cm/s", CONVEYOR_SPEED)
        logging.info("  - 스캔라인 → 에어솔 거리: %.2f cm", SCAN_LINE_TO_AIRSOL)
        logging.info("")
        logging.info("  작동 방식:")
        logging.info("  1. 객체가 스캔 라인을 지나가면 즉시 분석")
        logging.info("  2. 딜레이(초) 후 PLC 신호 전송")
        logging.info("  3. 모든 객체가 동일한 타이밍에 신호 전송됨")
        logging.info("="*70)
        # =================================================

        self.threads.cleanup_thread = threading.Thread(
            target=self.cleanup_old_objects, daemon=True
        )
        self.threads.cleanup_thread.start()

        try:
            # 소켓을 인스턴스 변수에 저장
            self.comm_sockets.command_socket = self.start_command_client()
            with self.comm_sockets.command_socket as command_socket:
                logging.info("Sending InitializeCamera command")
                self.handle_response(
                    self.send_command(
                        command_socket,
                        {"Command": "InitializeCamera"}
                    )
                )

                logging.info("Sending GetProperty command")
                self.handle_response(
                    self.send_command(
                        command_socket,
                        {"Command": "GetProperty", "Property": "WorkspacePath"}
                    )
                )

                workflow_path = WORKFLOW_PATH
                logging.info("Loading workflow: %s", workflow_path)
                workflow_json = self.handle_response(
                    self.send_command(
                        command_socket,
                        {"Command": "LoadWorkflow", "FilePath": workflow_path}
                    )
                )
                logging.info("workflow: %s", workflow_json)
                workflow_info = json.loads(workflow_json)
                obj_format = workflow_info.get("ObjectFormat", '')
                desc_info = obj_format.get("Descriptors", [])[0]
                legend_info_list = desc_info.get("Classes", [])
                self.app.on_legend_info(legend_info_list)

                # logging.info(f"Visualization Variable setting")
                # self.handle_response(self.send_command(command_socket, {
                #     "Command": "GetProperty",  # GetProperty가 아닌 SetProperty 사용
                #     "Property": "VisualizationVariable",
                #     "Value": "plastic classification"
                #     # 또는 "Reflectance", "Absorbance", "Descriptor names" 중 선택
                # }))

                # logging.info(f"blend pixel setting")
                # self.handle_response(self.send_command(command_socket, {
                #     "Command": "GetProperty",
                #     "Property": "VisualizationBlend",
                #     "Value": True  # 또는 "False"
                # }))

                logging.info("Starting prediction")
                self.handle_response(
                    self.send_command(
                        command_socket,
                        {"Command": "StartPredict", "IncludeObjectShape": True}
                    )
                )

                # 스레드 시작
                self.threads.event_listener_thread = threading.Thread(
                    target=self._listen_for_events,
                    daemon=True
                )
                self.threads.data_stream_listener_thread = threading.Thread(
                    target=self._listen_for_data_stream,
                    daemon=True
                )

                logging.info("Starting event and data stream threads")
                self.threads.event_listener_thread.start()
                self.threads.data_stream_listener_thread.start()

                print("\n" + "="*70)
                print("✓ 프로그램 실행 중")
                print("✓ 실시간 로그: plc_actions.log 파일 확인")
                print("="*70 + "\n")

                # 스레드가 종료될 때까지 대기
                while not self.threads.stop_event.is_set():
                    time.sleep(0.1)

        except Exception as e:
            logging.error("Main function error: %s", e)
            traceback.print_exc()

    def quit(self):
        """통신 관리자 종료"""
        logging.info("Stopping prediction")
        try:
            if self.comm_sockets.command_socket:
                response = self.send_command(
                    self.comm_sockets.command_socket, {"Command": "StopPredict"}
                )
                self.handle_response(response)
        except Exception as e:
            logging.error("Error during stop prediction: %s", str(e))

        # 1. stop 이벤트 설정
        self.threads.stop_event.set()

        # 2. 스레드 종료 대기 (먼저!)
        if self.threads.event_listener_thread is not None and \
            self.threads.event_listener_thread.is_alive():
            logging.info("Waiting for event listener thread to terminate...")
            self.threads.event_listener_thread.join(timeout=5)
            if self.threads.event_listener_thread.is_alive():
                logging.warning("Event listener thread did not terminate properly")

        if self.threads.data_stream_listener_thread is not None and \
            self.threads.data_stream_listener_thread.is_alive():
            logging.info("Waiting for data stream thread to terminate...")
            self.threads.data_stream_listener_thread.join(timeout=5)
            if self.threads.data_stream_listener_thread.is_alive():
                logging.warning("Data stream thread did not terminate properly")

        # 3. 그 다음 소켓 닫기
        try:
            if self.comm_sockets.command_socket:
                self.comm_sockets.command_socket.close()
        except Exception as e:
            logging.debug("Error closing command socket: %s", str(e))

        try:
            if self.comm_sockets.event_socket:
                self.comm_sockets.event_socket.shutdown(socket.SHUT_RDWR)
                self.comm_sockets.event_socket.close()
        except Exception as e:
            logging.debug("Error closing event socket: %s", str(e))

        try:
            if self.comm_sockets.stream_socket:
                self.comm_sockets.stream_socket.shutdown(socket.SHUT_RDWR)
                self.comm_sockets.stream_socket.close()
        except Exception as e:
            logging.debug("Error closing stream socket: %s", str(e))

        logging.info("Program terminated")
