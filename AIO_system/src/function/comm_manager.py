"""통신 관리자"""
import socket
import json
import uuid
import threading
import time
import traceback
import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import cv2
import numpy as np

from src.utils.config_util import (
    HOST, COMMAND_PORT, EVENT_PORT, DATA_STREAM_PORT, WORKFLOW_PATH,
    CONVEYOR_SPEED, SCAN_LINE_TO_AIRSOL, USE_MIN_INTERVAL, MIN_INTERVAL,
    CLASS_MAPPING, PLASTIC_VALUE_MAPPING_LARGE, PLASTIC_VALUE_MAPPING_SMALL,
    PLASTIC_SIZE_MAPPING, STREAM_TYPE, MIN_PULSE_WIDTH,
    classify_object_size, calc_delay, get_border_coords
)
from src.utils.logger import log
from .XGT_run import XGTTester

SMALL_EVENT_TTL = 10.0
SMALL_EVENT_MATCH_WINDOW = 0.35
SMALL_EVENT_FALLBACK_WINDOW = 0.8


# region data classes
@dataclass
class CommSockets:
    """소켓 모음"""
    command_socket: socket.socket = None
    event_socket: socket.socket = None
    stream_socket: socket.socket = None


@dataclass
class Threads:
    """스레드 모음"""
    event_listener_thread: threading.Thread = None
    data_stream_listener_thread: threading.Thread = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    main_stop_event: threading.Event = field(default_factory=threading.Event)


@dataclass
class QueueAndLock:
    """큐와 락 모음"""
    # USE_MIN_INTERVAL = True일 때 사용하는 부분
    timestamp_queue: deque = None
    timestamp_lock: threading.Lock = field(default_factory=threading.Lock)
    # 분석 완료 대기 큐
    analysis_queue: deque = None
    queue_lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class Trackings:
    """Tracked object state."""
    tracked_objects: dict = field(default_factory=dict)
    obj_counter: int = 0
    tracking_lock: threading.Lock = field(default_factory=threading.Lock)
    small_events: deque = field(default_factory=deque)
    small_lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class ObjectInfo:
    """제품 정보"""
    obj_id: int = 0             # ID
    classification: str = ""    # 재질 분류
    plc_value: int = 0          # 재질/사이즈에 따른 PLC 주소
    size: str = ""              # 사이즈 (large/small)
    size_addr: int = 0          # 사이즈에 따른 배출 PLC 주소
    y_position: int = 0         # 제품 중심 y좌표
@dataclass
class SmallMaterialEvent:
    object_info: ObjectInfo
    detect_time: float
    expected_cross_time: float
# endregion data classes


# region Comm Manager
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
        # 스캔 라인에서 에어솔까지의 거리만 중요함
        # 객체 추적 (Y 좌표 기반)

        self.trackings = Trackings()

        self.xgt_tester = XGTTester(ip="192.168.1.3", port=2004)

# region command client
    def _send_command(self, command_socket: socket.socket, command: dict):
        """카메라로 요청 전송"""
        command_id = uuid.uuid4().hex[:8]
        log(f"Sending command '{command.get('Command')}' with id {command_id}")
        command['Id'] = command_id
        message = json.dumps(command, separators=(',', ':')) + '\r\n'

        log(f"송신 Raw message: {message[:200]}")

        try:
            command_socket.sendall(message.encode('utf-8'))
            message_buffer = ""
            while True:
                try:
                    part = command_socket.recv(1024).decode('utf-8')
                    if not part:
                        log("[ERROR] No response from camera")
                        break
                    message_buffer += part
                    while '\r\n' in message_buffer:
                        full_response_str, message_buffer = message_buffer.split('\r\n', 1)
                        try:
                            response_json = json.loads(full_response_str.strip())
                            if response_json.get('Id') == command_id:
                                log(f"Received camera response for command {command_id}: {str(response_json)}")
                                return response_json
                        except json.JSONDecodeError:
                            log(f"[ERROR] Invalid JSON received: {full_response_str}")
                            continue
                except socket.timeout:
                    log("[ERROR] Camera request timed out")
                    return None
        except Exception as e:
            log(f"[ERROR] Error sending command: {str(e)}")
            return None
        return None

    def _handle_response(self, response):
        """카메라로부터의 응답"""
        if not response:
            log("[ERROR] No response or incorrect response ID received from camera")
            raise ValueError("No response or incorrect response ID received")
        message = response.get('Message', '')
        if not response.get("Success", False):
            log(f"[ERROR] Camera command not successful: {message}")
            raise RuntimeError(f"Command not successful: {message}")
        log(f"Id: {response.get('Id')} successfully received message body: '{message[:100]}'")

        return message

    def _start_command_client(self) -> socket.socket:
        """요청 클라이언트 시작"""
        log(f"Connecting to camera at {HOST}:{COMMAND_PORT}")
        try:
            soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            soc.connect((HOST, COMMAND_PORT))
            soc.settimeout(120)
            log("Camera connection successful")
            return soc
        except Exception as e:
            log(f"[ERROR] Camera connection failed: {str(e)}")
            raise

    def _command_client(self):
        # ==================== 설정 확인 ====================
        log("="*70)
        log("라인 스캔 카메라 타이밍 제어")
        log(f"  - 컨베이어 속도: {CONVEYOR_SPEED:.2f} cm/s")
        log(f"  - 스캔 라인 -> 에어솔 거리: {SCAN_LINE_TO_AIRSOL:.2f} cm")
        log("")
        log("  작동 방식:")
        log("  1. 객체가 스캔 라인을 지나가면 즉시 분석")
        log("  2. 지연 시간 후 PLC 신호 전송")
        log("  3. All objects use the same trigger timing")
        log("="*70)
        # =================================================

        try:
            # 소켓 인스턴스를 멤버 변수에 저장
            self.comm_sockets.command_socket = self._start_command_client()
            with self.comm_sockets.command_socket as command_socket:
                log("Sending InitializeCamera command")
                self._handle_response(
                    self._send_command(
                        command_socket,
                        {"Command": "InitializeCamera"}
                    )
                )

                log("Sending GetProperty command")
                self._handle_response(
                    self._send_command(
                        command_socket,
                        {"Command": "GetProperty", "Property": "WorkspacePath"}
                    )
                )

                workflow_path = WORKFLOW_PATH
                log(f"Loading workflow: {workflow_path}")
                workflow_json = self._handle_response(
                    self._send_command(
                        command_socket,
                        {"Command": "LoadWorkflow", "FilePath": workflow_path}
                    )
                )
                log(f"workflow: {workflow_json}")
                workflow_info = json.loads(workflow_json)
                obj_format = workflow_info.get("ObjectFormat", {}) or {}
                descriptors = obj_format.get("Descriptors", []) \
                    if isinstance(obj_format, dict) else []
                desc_info = descriptors[0] if descriptors else {}
                legend_info_list = desc_info.get("Classes", []) \
                    if isinstance(desc_info, dict) else []
                if not legend_info_list:
                    log("[WARNING] No legend class info in workflow")
                self.app.on_legend_info(legend_info_list)

                log("Starting prediction")
                self._handle_response(
                    self._send_command(
                        command_socket,
                        {"Command": "StartPredict", "IncludeObjectShape": True}
                    )
                )

                self.threads.event_listener_thread = threading.Thread(
                target=self._listen_for_events,
                daemon=True
                )
                self.threads.data_stream_listener_thread = threading.Thread(
                    target=self._listen_for_data_stream,
                    daemon=True
                )

                log("Starting event and data stream threads")
                self.threads.event_listener_thread.start()
                self.threads.data_stream_listener_thread.start()
        except Exception as e:
            log(f"{e}")
# endregion command client

# region event listener
    # ==================== 라인 스캔 타이밍 제어 ====================
    def _process_interval(self):
        # 물체 간 최소 간격만 지난 데이터만 유지
        current_time = datetime.now()
        _interval = timedelta(seconds=MIN_INTERVAL)
        with self.queue_n_lock.timestamp_lock:
            while self.queue_n_lock.timestamp_queue:
                if current_time - self.queue_n_lock.timestamp_queue[0][1] > _interval:
                    self.queue_n_lock.timestamp_queue.popleft()
                else:
                    # deque는 시간 순서로 쌓이므로 더 지울 항목이 없으면 break
                    break

    def _check_interval(self, address):
        current_time = datetime.now()
        _interval = timedelta(seconds=MIN_INTERVAL)
        with self.queue_n_lock.timestamp_lock:
            for addr, timestamp in self.queue_n_lock.timestamp_queue:
                if addr == address and current_time - timestamp <= _interval:
                    # 0.5초 이내 들어온 동일 재질-사이즈 물체는 무시
                    log(f"주소 P{address:03X}로 {MIN_INTERVAL:.2f}초 간격 내 물체 진입 감지")
                    return False

            self.queue_n_lock.timestamp_queue.append((address, current_time))
            return True

    def _cleanup_object(self, obj_id):
        """객체 정리"""
        with self.trackings.tracking_lock:
            if obj_id in self.trackings.tracked_objects:
                del self.trackings.tracked_objects[obj_id]
                log(f"객체 제거: ID={obj_id}")

    def _cleanup_small_events_locked(self, now: float):
        while self.trackings.small_events:
            event = self.trackings.small_events[0]
            age = now - event.detect_time
            if age > SMALL_EVENT_TTL:
                self.trackings.small_events.popleft()
            else:
                break

    def _remove_small_event(self, obj_id: int):
        with self.trackings.small_lock:
            if not self.trackings.small_events:
                return
            self.trackings.small_events = deque(
                event
                for event in self.trackings.small_events
                if event.object_info.obj_id != obj_id
            )

    def _queue_small_event(self, obj_info: ObjectInfo, detect_time: float, delay: float):
        expected_cross_time = detect_time + max(delay, 0.0)
        event = SmallMaterialEvent(
            object_info=obj_info,
            detect_time=detect_time,
            expected_cross_time=expected_cross_time,
        )
        with self.trackings.small_lock:
            self._cleanup_small_events_locked(detect_time)
            self.trackings.small_events.append(event)
            log(
                f"[SMALL인식] ID={obj_info.obj_id}, 재질={obj_info.classification}, "
                f"size={obj_info.size}, 주소=P{obj_info.plc_value:03X}/P{obj_info.size_addr:03X}"
            )

    def _pop_best_small_event(self, cross_time: float):
        with self.trackings.small_lock:
            self._cleanup_small_events_locked(cross_time)
            if not self.trackings.small_events:
                return None

            events = list(self.trackings.small_events)
            best_event = min(
                events,
                key=lambda event: abs(event.expected_cross_time - cross_time)
            )
            time_diff = abs(best_event.expected_cross_time - cross_time)

            if time_diff > SMALL_EVENT_FALLBACK_WINDOW:
                log(
                    f"[SMALL] no event in fallback window: "
                    f"buffer={len(self.trackings.small_events)}, diff={time_diff:.3f}s"
                )
                return None

            self.trackings.small_events.remove(best_event)

        level = "INFO" if time_diff <= SMALL_EVENT_MATCH_WINDOW else "WARNING"
        log(
            f"[{level}] [SMALL] matched event: obj_id={best_event.object_info.obj_id}, "
            f"class={best_event.object_info.classification}, diff={time_diff:.3f}s"
        )
        return best_event

    def _send_plc_pulse(self, _info: ObjectInfo):
        """10ms 펄스로 신호 전송 (PLC에서 상승엣지 감지)"""
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
            # 재질 on-off 사이에 사이즈 on-off가 들어가도록 처리
            self.xgt_tester.schedule_bit_off(
                address=_info.size_addr,
                delay=MIN_PULSE_WIDTH
            )
            self.xgt_tester.schedule_bit_off(
                address=_info.plc_value,
                delay=MIN_PULSE_WIDTH
            )
            log(f"[PLC펄스] ID={_info.obj_id}, Y={_info.y_position}, 재질={_info.classification}, size={_info.size}, 주소=P{_info.plc_value:03X}/P{_info.size_addr:03X}")
        else:
            log(f"[WARNING] [PLC펄스] ID={_info.obj_id} - 전송 실패")

    def _send_signal(self, _info: ObjectInfo):
        """PLC 신호 전송 전 객체 존재 여부 확인"""
        try:
            with self.trackings.tracking_lock:
                if _info.obj_id in self.trackings.tracked_objects:
                    obj_data = self.trackings.tracked_objects[_info.obj_id]
                    
                    if obj_data['analysis_complete']:
                        self._send_plc_pulse(_info)
                        obj_data['status'] = 'completed'
                        threading.Timer(1.0, lambda: self._cleanup_object(_info.obj_id)).start()
                    else:
                        log(f"[WARNING] PLC pulse skipped: ID={_info.obj_id} analysis incomplete")
                        obj_data['status'] = 'timeout'
                else:
                    log(f"[ERROR] [PLC펄스] ID={_info.obj_id} - 객체 없음")
        except Exception as e:
            log(f"[ERROR] PLC 신호 전송 오류: {str(e)}")

    def _schedule_plc_signal_delay(self, obj_info: ObjectInfo, delay: float):
        """고정 지연 시간 후 신호 전송"""
        timer = threading.Timer(delay, lambda: self._send_signal(obj_info))
        timer.daemon = True
        timer.start()

        # log(
        #     "[신호예약] ID=%d, Y=%d, 재질=%s, %.2f초 후 전송",
        #     obj_info.obj_id,
        #     obj_info.y_position,
        #     obj_info.classification,
        #     delay
        # )
    # ================================================================

    def _listen_for_events(self):
        """Listen for classification events from the camera."""
        log(f"Connecting to camera event port at {HOST}:{EVENT_PORT}")
        try:
            self.comm_sockets.event_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.comm_sockets.event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.comm_sockets.event_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.comm_sockets.event_socket.connect((HOST, EVENT_PORT))
            log("Event socket connected")
        except Exception as e:
            log(f"[ERROR] Failed to connect to event port: {str(e)}", )
            return

        message_buffer = ""

        while not self.threads.stop_event.is_set():
            # 0.5초 이내 들어오는 데이터들을 하나의 객체로 묶음
            # USE_MIN_INTERVAL = True    # default
            # 동작 여부 판단 로직은 현장 조건에 맞게 조정 필요
            if USE_MIN_INTERVAL:
                self._process_interval()

            # 생성된 비트 off 처리 - 매 루프마다 실행되어야 함
            self.xgt_tester.process_bit_off()

            self.comm_sockets.event_socket.settimeout(1)
            try:
                data = self.comm_sockets.event_socket.recv(1024)
                if not data:
                    log("[WARNING] No data received from camera")
                    break
                try:
                    decoded_data = data.decode('utf-8')
                except UnicodeDecodeError as e:
                    log(f"[ERROR] Unicode decode error: {str(e)}")
                    continue
                message_buffer += decoded_data

                # 메시지 버퍼 처리
                message_buffer = self._process_event_buffer(message_buffer)

            except socket.timeout:
                pass
            except Exception as e:
                log(f"[ERROR] Error in event loop: {str(e)}")
                continue

    def _process_event_buffer(self, message_buffer: str):
        """이벤트 메시지 처리"""
        while '\r\n' in message_buffer:
            message, message_buffer = message_buffer.split('\r\n', 1)
            try:
                message_json = json.loads(message)
                event = message_json.get('Event', '')
                inner_message = json.loads(message_json.get('Message', '{}'))

                if not getattr(self.app, "monitoring_enabled", True):
                    continue

                if event == "PredictionObject":
                    descriptors = inner_message.get('Descriptors', [])
                    try:
                        descriptor_value = int(descriptors[0]) if descriptors else 0
                    except (TypeError, ValueError, IndexError):
                        descriptor_value = 0
                    classification = CLASS_MAPPING.get(descriptor_value, "Unknown")

                    shape = inner_message.get('Shape', {})
                    center = shape.get('Center', [])

                    if not center:
                        log("[WARNING] No center position in shape data")
                    
                        continue
                    
                    # ==================== 라인 스캔 처리 ====================
                    # 라인 스캔이므로 X 좌표보다 Y 좌표로 객체를 구분
                    border = shape.get("Border", [])
                    x0, x1, y0, y1 = get_border_coords(border)
                    if abs(x1 - x0) < 15:
                        log("[INFO] ignoring thin object")
                        continue

                    y_position = center[1] if len(center) > 1 else center[0]
                    delay = calc_delay(y_position)
                    
                    if y_position >= 1000:
                        continue

                    # 일단 감지됐으므로 감지 신호 처리
                    size = classify_object_size(center[0])
                    plc_value = None
                    if size is None:
                        log("[가이드라인] 무시")
                        continue  # 다음 객체로 스킵

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

                    if not border:
                        log("[WARNING] No border coordinates in shape data")
                        continue

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
                    # log(
                    #     "[감지완료] Y=%d, 재질=%s, border=%s, start=%d, end=%d",
                    #     y_position,
                    #     classification,
                    #     str(border),
                    #     start_frame,
                    #     end_frame
                    # )

                    # 고정 지연 시간 후 PLC 신호 예약
                    if size == "large":
                        # 대형의 경우 즉시 펄스 신호 예약
                        self._schedule_plc_signal_delay(obj_info, delay)    
                    elif size == "small":
                        # 소형의 경우 큐에 저장
                        self._queue_small_event(obj_info, detection_time, delay)
                # else:
                #     log(f"event:{event}")
            except json.JSONDecodeError:
                log("[ERROR] Invalid JSON received from camera")
            except Exception as e:
                log(f"[ERROR] Error processing event: {str(e)}")
                traceback.print_exc()
        return message_buffer

    def on_small_material_cross_matched(self):
        """Handle small-material trigger using FIFO queue consumption."""
        now = time.time()
        with self.trackings.small_lock:
            self._cleanup_small_events_locked(now)
            if not self.trackings.small_events:
                return

            matched_event = self.trackings.small_events.popleft()

        if not matched_event:
            return

        obj_info = matched_event.object_info
        self._send_signal(obj_info)
    
    def on_small_material_cross(self):
        """Backward-compatible entrypoint for small-material line crossings."""
        self.on_small_material_cross_matched()
# endregion event listener

# region data stream listener
    def _listen_for_data_stream(self):
        """Listen for line-scan data stream frames."""
        log(f"Connecting to data stream at {HOST}:{DATA_STREAM_PORT}")
        try:
            self.comm_sockets.stream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.comm_sockets.stream_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.comm_sockets.stream_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.comm_sockets.stream_socket.connect((HOST, DATA_STREAM_PORT))
            log("Data stream connected")
        except Exception as e:
            log(f"[ERROR] Failed to connect to data stream: {str(e)}")
            return

        expected_header_size = 25
        last_processed_time = 0
        # UI 스트리밍은 30fps로 제한
        throttle_interval = 1.0 / 30.0

        while not self.threads.stop_event.is_set():
            self.comm_sockets.stream_socket.settimeout(1)
            try:
                header = b""
                while len(header) < expected_header_size:
                    chunk = self.comm_sockets.stream_socket.recv(expected_header_size - len(header))
                    if not chunk:
                        log("[WARNING] No data received from stream")
                        break
                    header += chunk
                if len(header) != expected_header_size:
                    log("[WARNING] Incomplete header received")
                    continue

                stream_type_idx = header[0]
                if stream_type_idx >= len(STREAM_TYPE):
                    log(f"[WARNING] Unknown stream type index: {stream_type_idx}")
                    continue
                stream_type = STREAM_TYPE[stream_type_idx]
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
                        log("[WARNING] Incomplete metadata received")
                        break
                    metadata += chunk

                # 중요: data body 전체를 먼저 수신
                data_body = b""
                while len(data_body) < data_body_size:
                    chunk = self.comm_sockets.stream_socket.recv(data_body_size - len(data_body))
                    if not chunk:
                        log("[WARNING] Incomplete data body received")
                        break
                    data_body += chunk

                # if stream_type != "Raw":
                #     print(f"""header : {header} \n
                #         metadata : {metadata} \n
                #         data_body : {data_body}""")
                # print(f"stream_type: {stream_type}\ndata_body; {data_body}")
                # data body 전체를 모두 받은 경우에만 처리
                if len(data_body) != data_body_size:
                    continue

                current_time = time.time()
                if current_time - last_processed_time < throttle_interval:
                    continue
                last_processed_time = current_time

                if not getattr(self.app, "monitoring_enabled", True):
                    continue

                info = {
                    "frame_number": frame_number,
                    "data_body": data_body
                }
                self.app.on_pixel_line_data(info)

            except socket.timeout:
                continue
            except Exception as e:
                log(f"[ERROR] Error in data stream: {str(e)}")
                continue
# endregion data stream listener

# region run, start, stop, quit
    def blow_block(self):
        """블로우 배출구 막힘 해소"""
        # 현재 사용 주소: size=0x80, sol=0x8B
        # 대체 주소 예시: size=0x81, sol=0x8F
        size_addr = 0x80
        sol_addr = 0x8B
        success1 = self.xgt_tester.write_bit_packet(
            address=sol_addr,
            onoff=1
        )
        success2 = self.xgt_tester.write_bit_packet(
            address=size_addr,
            onoff=1
        )
        if success1 and success2:
            # 재질 on-off 사이에 사이즈 on-off가 들어가도록 처리
            self.xgt_tester.schedule_bit_off(
                address=size_addr,
                delay=MIN_PULSE_WIDTH
            )
            self.xgt_tester.schedule_bit_off(
                address=sol_addr,
                delay=MIN_PULSE_WIDTH
            )
            log("블로우 배출구 air 동작 성공")
        else:
            log("블로우 배출구 air 동작 실패")

    def _cleanup_old_objects(self):
        """오래된 객체 자동 정리"""
        current_time = time.time()

        with self.trackings.tracking_lock:
            to_remove = []
            for obj_id, obj_data in self.trackings.tracked_objects.items():
                age = current_time - obj_data['detect_time']
                if age > 10:  # 10초 이상
                    to_remove.append(obj_id)
                    log(f"[타임아웃] ID={obj_id} (상태={obj_data['status']})")

            for obj_id in to_remove:
                del self.trackings.tracked_objects[obj_id]

    def run(self):
        """Main loop started by start()."""
        log("Starting comm manager")

        try:
            while not self.threads.main_stop_event.is_set():
                # PLC 상태 통신 점검
                self.xgt_tester.status_check()

                # 오래된 객체 정리
                self._cleanup_old_objects()

                time.sleep(1)

        except Exception as e:
            log(f"[ERROR] Main function error: {str(e)}")

    def start_hypercam(self):
        """초분광 카메라 연결 및 감지 시작"""
        self.threads.stop_event.clear()
        try:
            # 초분광 카메라 시작
            self._command_client()
        except Exception as e:
            log(f"[ERROR] start command thread error: {str(e)}")

    def stop_hypercam(self):
        """초분광 카메라 정지"""
        # 1. stop 이벤트 설정
        self.threads.stop_event.set()

        # 1. event_listener, data_stream 스레드 종료 대기
        if self.threads.event_listener_thread is not None and \
            self.threads.event_listener_thread.is_alive():
            log("Waiting for event listener thread to terminate...")
            self.threads.event_listener_thread.join(timeout=5)
            if self.threads.event_listener_thread.is_alive():
                log("[WARNING] Event listener thread did not terminate properly")
        self.threads.event_listener_thread = None

        if self.threads.data_stream_listener_thread is not None and \
            self.threads.data_stream_listener_thread.is_alive():
            log("Waiting for data stream thread to terminate...")
            self.threads.data_stream_listener_thread.join(timeout=5)
            if self.threads.data_stream_listener_thread.is_alive():
                log("[WARNING] Data stream thread did not terminate properly")
        self.threads.data_stream_listener_thread = None

        # 2. event, stream 소켓 닫기
        try:
            if self.comm_sockets.event_socket:
                self.comm_sockets.event_socket.shutdown(socket.SHUT_RDWR)
                self.comm_sockets.event_socket.close()
        except Exception as e:
            log(f"Error closing event socket: {str(e)}")

        try:
            if self.comm_sockets.stream_socket:
                self.comm_sockets.stream_socket.shutdown(socket.SHUT_RDWR)
                self.comm_sockets.stream_socket.close()
        except Exception as e:
            log(f"Error closing stream socket: {str(e)}")

        # 3. 예측 종료 및 카메라 연결 끊기
        try:
            if self.comm_sockets.command_socket:
                with self.comm_sockets.command_socket as command_socket:
                    log("Stopping prediction")
                    self._handle_response(
                        self._send_command(
                            command_socket,
                            {"Command": "StopPredict"}
                        )
                    )

                    log("Disconnect camera")
                    self._handle_response(
                        self._send_command(
                            command_socket,
                            {"Command": "DisconnectCamera"}
                        )
                    )
        except Exception as e:
            log(f"[ERROR] Error during stop prediction: {str(e)}")

        # 4. command 소켓 닫기
        try:
            if self.comm_sockets.command_socket:
                self.comm_sockets.command_socket.close()
        except Exception as e:
            log(f"Error closing command socket: {str(e)}")

    def quit(self):
        """통신 관리자 종료"""
        self.stop_hypercam()
        self.threads.main_stop_event.set()

        log("Program terminated")
# endregion run, start, stop, quit
# endregion Comm Manager


# region LineScanSimulator
class LineScanSimulator(threading.Thread):
    """
    라인 스캔 테스트용 시뮬레이터
    """

    legend_list = [
        { "Name": "PET" , "Color": "#258FD0" },
        {"Name": "PE", "Color": "#1CB786" },
        { "Name" : "PP", "Color": "#E43C3C" },
        { "Name" : "PS", "Color": "#F5A50F" },
        { "Name" : "PVC", "Color": "#BE5EC3" },
        { "Name" : "Others", "Color": "#878787" }
    ]

    def __init__(self, app, width=640):
        super().__init__(daemon=True)
        self.app = app # 메인 앱 참조

        self.width = width # 초분광 카메라용 UI 캔버스 너비
        self.frame_number = 0 # 현재 생성된 프레임(라인) 번호
        self.canvas_height = 2000 # 캔버스 높이
        self.canvas = np.zeros(
            (self.canvas_height, self.width, 3),
            dtype=np.uint8
        ) # 가상 오브젝트를 생성할 캔버스
        self.objects_metadata = [] # 오브젝트 좌표 정보를 담아둘 리스트
        self.current_y = 0 # 초분광 카메라 이벤트 시점을 흉내내기 위한 Y 좌표
        self._generate_new_objects()

        self._thread = None
        self.stop_event = threading.Event()
        self.main_stop_event = threading.Event()

    def _generate_new_objects(self):
        """가상의 오브젝트 생성"""
        self.canvas.fill(15) # 일단 어두운 색으로 채워둠
        self.objects_metadata = []

        scan_ratio = 1

        for _ in range(random.randint(5, 10)):
            _ind = random.randint(0, len(self.legend_list) - 1)
            _info = self.legend_list[_ind]
            classification = _info["Name"]
            color_txt = _info["Color"]
            color = tuple(int(color_txt[i:i+2], 16) for i in (1, 3, 5))

            w = random.randint(40, 100)
            h = int(random.randint(60, 150) * scan_ratio)
            x_min = random.randint(0, self.width - w)
            y_min_relative = random.randint(100, self.canvas_height - h - 100)

            # 다각형 생성
            pts = np.array([
                [
                    x_min + random.randint(0, w),
                    y_min_relative + random.randint(0, h)
                ]
                for _ in range(5)
            ], np.int32)

            cv2.fillPoly(self.canvas, [pts], color)

            # 오브젝트의 실제 경계값(Bounding Box) 계산
            self.objects_metadata.append({
                "classification": classification,
                "x_min": int(np.min(pts[:, 0])),
                "x_max": int(np.max(pts[:, 0])),
                "y_min_rel": int(np.min(pts[:, 1])),
                "y_max_rel": int(np.max(pts[:, 1])),
                "start_frame": None,
                "end_frame": None,
                "sent": False # 전송 여부 플래그
            })

    def _get_next_data(self):
        """다음 라인 데이터와 완료된 이벤트 데이터를 반환"""
        y_idx = self.current_y
        line_data = self.canvas[y_idx, :, :].tobytes()

        current_frame = self.frame_number

        # 현재 라인(y_idx)이 물체의 하단(y_max)에 도달하면 이벤트 발생
        # 실제 카메라 처리 흐름의 종료 시점을 흉내냄
        event_data = None
        classification = None
        for obj in self.objects_metadata:
            # 1. 물체의 시작 지점을 지나면 시작 프레임 기록
            if obj["start_frame"] is None and y_idx >= obj["y_min_rel"]:
                obj["start_frame"] = current_frame

            # 2. 물체의 끝 지점을 지나면 종료 프레임 기록 및 이벤트 생성
            if not obj["sent"] and y_idx >= obj["y_max_rel"]:
                obj["end_frame"] = current_frame

                event_data = {
                    "x0": obj["x_min"],
                    "x1": obj["x_max"],
                    "y0": obj["y_min_rel"],
                    "y1": obj["y_max_rel"],
                    "start_frame": obj["start_frame"],
                    "end_frame": obj["end_frame"]
                }
                obj["sent"] = True
                classification = obj["classification"]
                break

        info = {
            "frame_number": current_frame,
            "data_body": line_data
        }

        self.current_y += 1
        self.frame_number += 1

        if self.current_y >= self.canvas_height:
            self.current_y = 0
            self._generate_new_objects()

        return info, event_data, classification

    def _pseudo_linescan_loop(self):
        """소켓 없이 데이터 스트림을 흉내내는 루프"""
        log("Starting pseudo data stream simulator")

        self.app.on_legend_info(self.legend_list)

        last_processed_time = 0
        throttle_interval = 1.0 / 30.0

        while not self.stop_event.is_set():
            info, event_info, classification = self._get_next_data()

            # 1. 이미지 데이터 전송 (기존 로직)
            current_time = time.time()
            if current_time - last_processed_time >= throttle_interval:
                self.app.on_pixel_line_data(info)
                last_processed_time = current_time

            # 2. 이벤트 데이터 전송 (추가 로직)
            if event_info:
                # 실제 이벤트 처리 핸들러만 호출
                self.app.on_obj_detected(event_info, classification)

            time.sleep(0.01)

    def blow_block(self):
        """블로우 배출구 막힘 해소"""
        log("블로우 배출구 air 동작")

    def on_small_material_cross(self):
        """소형 재질 선통과 감지 및 처리"""
        log("선통과 감지")

    def run(self):
        while not self.main_stop_event.is_set():
            time.sleep(0.1)

    def start_hypercam(self):
        """시뮬레이터 루프 시작"""
        log("start pseudo hypercam")
        self.stop_event.clear()
        self._thread = threading.Thread(target=self._pseudo_linescan_loop, daemon=True)
        self._thread.start()

    def stop_hypercam(self):
        """시뮬레이터 루프 정지"""
        log("stop pseudo hypercam")
        self.stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def quit(self):
        """종료"""
        self.stop_hypercam()
        self.main_stop_event.set()

    def on_small_material_cross_matched(self):
        """Compatibility shim for the simulator path."""
        self.on_small_material_cross()

# endregion LineScanSimulator



