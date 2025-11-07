import socket
import json
import uuid
import threading
import time
import logging
from datetime import datetime, timedelta
from dateutil import tz
from XGT_run import XGTTester
from collections import deque
from calc import classify_object_size
# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('plc_actions.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Breeze Runtime 관련 설정
HOST = '169.254.188.53'
COMMAND_PORT = 2000
EVENT_PORT = 2500
DATA_STREAM_PORT = 3000
stop_event = threading.Event()

# 헬스체크 패킷용
check_time = 0

# ==================== 라인 스캔 타이밍 제어 설정 ====================
# 라인 스캔 카메라는 고정된 위치에서 촬영하므로 
# 스캔 라인 → 에어솔까지의 거리만 중요!

CONVEYOR_SPEED = 40.0           # cm/s - 실측 필요
SCAN_LINE_TO_AIRSOL = 40.0      # cm - 스캔 라인부터 에어솔까지 거리
LENGTH_PIXEL = 640              # px - 딜레이 계산할 때 사용할, 초분광 스캔 지점으로부터의 기준 거리
PX_CM_RATIO = 10.0              # px대 cm 비율

USE_MIN_INTERVAL = True

# 객체 추적 (Y 좌표 기반)
tracked_objects = {}
object_counter = 0
tracking_lock = threading.Lock()

# 분석 완료 대기 큐
analysis_queue = deque(maxlen=100)
queue_lock = threading.Lock()

def calc_delay(y_position):
    remain_px = LENGTH_PIXEL - y_position   # 객체 중심이 끝점 지나기까지 남은 거리(px)
    if remain_px < 0:
        return 0
    
    remain_cm = remain_px / PX_CM_RATIO     # cm 단위로 변환
    delay = remain_cm / CONVEYOR_SPEED      # 딜레이 초 단위로 구함
    return delay
# =====================================================================

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

# ==================== 라인 스캔용 타이밍 제어 ====================
MIN_INTERVAL = 0.1
timestamp_queue = deque()
timestamp_lock = threading.Lock()
def _process_interval():
    # 물체 간 최소 간격이 지난 데이터를 지워줌
    current_time = datetime.now()
    _interval = timedelta(seconds=MIN_INTERVAL)
    with timestamp_lock:
        while timestamp_queue:
            if current_time - timestamp_queue[0][1] > _interval:
                timestamp_queue.popleft()
            else:
                # deque 내부 원소들은 시간 순서로 쌓이므로, 더이상 지울 게 없으면 break
                break

def check_interval(address):
    current_time = datetime.now()
    _interval = timedelta(seconds=MIN_INTERVAL)
    with timestamp_lock:
        for addr, timestamp in timestamp_queue:
            if addr == address and current_time - timestamp <= _interval:
                # 0.5초 이내로 들어온 동일 재질-사이즈 물체는 무시
                if addr != 0x8C:
                    logging.info(f"주소 P{address:3X}로 {MIN_INTERVAL}초 간격 내 물체 진입 감지")
                return False

        timestamp_queue.append((address, current_time))
        return True

def schedule_plc_signal_delay(XGT, obj_id, classification, plc_value, size, size_addr, y_position, delay):
    """
    10ms 펄스로 신호 전송 (PLC에서 상승엣지 감지)
    """
    MIN_PULSE_WIDTH = 0.01  # 10ms - PLC 스캔 사이클 고려
    
    def send_signal(_id=obj_id, _class=classification, _plc=plc_value, _size=size, _size_addr=size_addr, _y=y_position):
        try:
            with tracking_lock:
                if _id in tracked_objects:
                    obj_data = tracked_objects[_id]
                    if obj_data['analysis_complete']:
                        # 재질 신호 직후 사이즈 신호
                        success1 = XGT.write_bit_packet(address=_plc, onoff=1)
                        success2 = XGT.write_bit_packet(address=_size_addr, onoff=1)
                        if success1 and success2:
                            # 재질 on-off 사이에 사이즈 on-off 가 들어갈 수 있도록 처리
                            XGT.schedule_bit_off(address=_size_addr, delay=MIN_PULSE_WIDTH)
                            XGT.schedule_bit_off(address=_plc, delay=MIN_PULSE_WIDTH)
                            logging.info(f"✓ [PLC펄스] ID={_id}, Y={_y}, 재질={_class}, size={_size}, 주소=P{_plc:3X}/P{_size_addr:3X}")
                        else:
                            logging.warning(f"✗ [PLC펄스] ID={_id} - 전송 실패")
                        
                        obj_data['status'] = 'completed'
                        threading.Timer(1.0, lambda: cleanup_object(_id)).start()
                    else:
                        logging.warning(f"⚠ [PLC펄스] ID={_id} - 분석 미완료")
                        obj_data['status'] = 'timeout'
                else:
                    logging.error(f"✗ [PLC펄스] ID={_id} - 객체 없음")
                    
        except Exception as e:
            logging.error(f"PLC 신호 전송 오류: {e}")
# def schedule_plc_signal_delay(XGT, obj_id, classification, plc_value, y_position, delay):
#     """
#     10ms 펄스로 신호 전송 (PLC에서 상승엣지 감지)
#     """
#     MIN_PULSE_WIDTH = 0.01  # 10ms - PLC 스캔 사이클 고려
    
#     def send_signal(_id=obj_id, _class=classification, _val=plc_value, _y=y_position):
#         try:
#             with tracking_lock:
#                 if _id in tracked_objects:
#                     obj_data = tracked_objects[_id]
                    
#                     if obj_data['analysis_complete']:
#                         success = XGT.write_bit_packet(address=_val, onoff=1)
#                         if success:
#                             # 10ms 후 OFF (PLC 상승엣지 감지용)
#                             XGT.schedule_bit_off(address=_val, delay=MIN_PULSE_WIDTH)
#                             logging.info(f"✓ [PLC펄스] ID={_id}, Y={_y}, 재질={_class}, 주소=P{_val:3X}")
#                         else:
#                             logging.warning(f"✗ [PLC펄스] ID={_id} - 전송 실패")
                        
#                         obj_data['status'] = 'completed'
#                         threading.Timer(1.0, lambda: cleanup_object(_id)).start()
#                     else:
#                         logging.warning(f"⚠ [PLC펄스] ID={_id} - 분석 미완료")
#                         obj_data['status'] = 'timeout'
#                 else:
#                     logging.error(f"✗ [PLC펄스] ID={_id} - 객체 없음")
                    
#         except Exception as e:
#             logging.error(f"PLC 신호 전송 오류: {e}")
# def schedule_plc_signal_delay(XGT, obj_id, classification, plc_value, y_position, delay):
#     """
#     라인 스캔 감지 후 고정된 시간 뒤에 PLC 신호 전송
#     """
#     def send_signal(_id=obj_id, _class=classification, _val=plc_value, _y=y_position):
#         try:
#             with tracking_lock:
#                 if _id in tracked_objects:
#                     obj_data = tracked_objects[_id]
                    
#                     # 분석이 완료되었는지 확인
#                     if obj_data['analysis_complete']:
#                         success = XGT.write_bit_packet(address=_val, onoff=1)
#                         if success:
#                             XGT.schedule_bit_off(address=_val, delay=0)
#                             logging.info(f"✓ [PLC신호] ID={_id}, Y={_y}, 재질={_class}, 주소=P{_val:3X}")
#                         else:
#                             logging.warning(f"✗ [PLC신호] ID={_id} - 전송 실패")
                         
#                         # 완료 후 제거
#                         obj_data['status'] = 'completed'
#                         threading.Timer(1.0, lambda: cleanup_object(_id)).start()
#                     else:
#                         # 분석이 아직 안 끝남
#                         logging.warning(f"⚠ [PLC신호] ID={_id} - 분석 미완료 (스킵)")
#                         obj_data['status'] = 'timeout'
#                 else:
#                     logging.error(f"✗ [PLC신호] ID={_id} - 객체 찾을 수 없음")
                    
#         except Exception as e:
#             logging.error(f"PLC 신호 전송 오류: {e}")
    
    # 고정 지연 시간 후 신호 전송
    timer = threading.Timer(delay, send_signal)
    timer.daemon = True
    timer.start()
    
    # logging.info(f"→ [신호예약] ID={obj_id}, Y={y_position}, 재질={classification}, {delay:.2f}초 후 전송")

def cleanup_object(obj_id):
    """객체 정리"""
    with tracking_lock:
        if obj_id in tracked_objects:
            del tracked_objects[obj_id]
            logging.debug(f"객체 제거: ID={obj_id}")

def cleanup_old_objects():
    """오래된 객체 자동 정리"""
    while not stop_event.is_set():
        time.sleep(5)
        current_time = time.time()
        
        with tracking_lock:
            to_remove = []
            for obj_id, obj_data in tracked_objects.items():
                age = current_time - obj_data['detect_time']
                if age > 10:  # 10초 이상
                    to_remove.append(obj_id)
                    logging.debug(f"타임아웃: ID={obj_id} (상태={obj_data['status']})")
            
            for obj_id in to_remove:
                del tracked_objects[obj_id]
# ================================================================

"""
    sol 매칭
    0x88: 대형#1
    0x89: 대형#2
    0x8A: 대형#3
    0x8B: 대형#4

    0x8C: 소형#1
    0x8D: 소형#2
    0x8E: 소형#3
    0x8F: 소형#4

    0x90: 대형#1-1
    0x91: 대형#2-1
    0x92: 대형#3-1
    0x93: 미사용
    
    0x94: 소형#1-1
    0x95: 소형#2-1
    0x96: 소형#3-1
    0x97: 미사용
"""
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
    
    PLASTIC_VALUE_MAPPING_LARGE = {
        "PP": 0x88,
        "ABS": 0x89,
        "HDPE": 0x8A,
        "PS": 0x88,
        "LDPE": 0x89,
        "PET": 0x88,
        # "_": 0x88,
    }
    PLASTIC_VALUE_MAPPING_SMALL = {
        "PP": 0x8C,
        "ABS": 0x8D,
        "HDPE": 0x8E,
        "PS": 0x8C,
        "LDPE": 0x8D,
        "PET": 0x8C,
        # "_": 0x88,
    }
    # PLASTIC_VALUE_MAPPING_LARGE = {
    #     "HDPE": 0x8E,
    #     "PS": 0x8E,
    #     "PP": 0x8E,
    #     "LDPE": 0x8E,
    #     "ABS": 0x83,
    #     "PET": 0x8E,
    #     # "_": 0x88,
    # }

    PLASTIC_SIZE_MAPPING = {
        "large": 0x80,
        "small": 0x81
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
        global object_counter, check_time

        while not stop_event.is_set():
            # 0.5초 이내 들어오는 데이터들을 하나로 객체 묶음
            """
            USE_MIN_INTERVAL = True    # default
            동작 유무 판단 시 320줄, 380줄 주석 처리 필요
            """
            if USE_MIN_INTERVAL:
                _process_interval()
            
            current_time = time.perf_counter()
            if current_time - check_time >= 1:
                XGT.status_check()
                check_time = time.perf_counter()

            XGT.process_bit_off() # 활성화 된 비트 off 처리는 무조건 각 프레임마다 프로세스 돌아야 한다.
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
                        event = message_json.get('Event', '')
                        inner_message = json.loads(message_json.get('Message', '{}'))
                        
                        if event == "PredictionObject":
                            descriptors = inner_message.get('Descriptors', [])
                            descriptor_value = int(descriptors[0]) if descriptors else 0
                            classification = CLASS_MAPPING.get(descriptor_value, "Unknown")
                            if classification == 'PS':
                                continue
                            # plc_value = PLASTIC_VALUE_MAPPING_LARGE.get(classification)

                            shape = inner_message.get('Shape', {})
                            center = shape.get('Center', [])
                            # print(f"center : {center} \n shape : {shape}")
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
                            if size is None:
                                logging.debug(f"⊗ [가이드라인] 무시")
                                continue  # ← 다음 객체로 스킵!
                            elif size == "large":
                                plc_value = PLASTIC_VALUE_MAPPING_LARGE.get(classification)
                            elif size == "small":
                                plc_value = PLASTIC_VALUE_MAPPING_SMALL.get(classification)
                            
                            # size = "small"  # 추후 소형 대형 구분 필요
                            size_addr = PLASTIC_SIZE_MAPPING[size]
                            
                            ####### 오인식 제거 임시 처리 ###################
                            if not plc_value or not size_addr:
                                continue

                            if classification =='ABS' and size == 'small':
                                continue
                            ##############################################

                            # 재질-사이즈 가 동일하며 0.5초 간격 이내에 들어온 경우에 대한 처리
                            # if USE_MIN_INTERVAL and not check_interval(plc_value):
                            #     continue
                                
                            # 지금 현재 이부분에서 write_bit_packet을 하는 이유는? 뒤에 한번 더 보내는데?
                            # success = XGT.write_bit_packet(address=size_addr, onoff=1)
                            # if success:
                            #     XGT.schedule_bit_off(address=size_addr, delay=0.01)
                            #     logging.info(f"✓ [PLC신호] size={size}, 주소=P{size_addr:3X}")
                            # else:
                            #     logging.warning(f"✗ [PLC신호] size={size} - 전송 실패")
                            
                            
                            detection_time = time.time()
                            
                            with tracking_lock:
                                obj_id = object_counter
                                object_counter += 1
                                
                                # 객체 정보 저장
                                tracked_objects[obj_id] = {
                                    'id': obj_id,
                                    'detect_time': detection_time,
                                    'y_position': y_position,
                                    'classification': classification,
                                    'plc_value': plc_value,
                                    'size': size,
                                    'size_address': size_addr,
                                    'analysis_complete': True,  # 분석 즉시 완료
                                    'status': 'scheduled'
                                }
                                
                                # logging.info(f"★ [감지완료] ID={obj_id}, Y={y_position}, 재질={classification}")

                            # 고정 지연 시간 후 PLC 신호 예약
                            # schedule_plc_signal_delay(
                            #     XGT,
                            #     obj_id,
                            #     classification,
                            #     plc_value,
                            #     y_position,
                            #     delay
                            # )
                            schedule_plc_signal_delay(
                                XGT,
                                obj_id,
                                classification,
                                plc_value,
                                size,
                                size_addr,
                                y_position,
                                delay
                            )
                            # ====================================================
                            
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
        throttle_interval = 1.0

        while not stop_event.is_set():
            stream_socket.settimeout(1)
            try:
                header = b""
                while len(header) < expected_header_size:
                    chunk = stream_socket.recv(expected_header_size - len(header))
                    # print(f"chunk : {chunk}")
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
                    chunk = stream_socket.recv(metadata_size - len(metadata))
                    if not chunk:
                        logging.warning("Incomplete metadata received")
                        break
                    metadata += chunk

                data_body = b""
                while len(data_body) < data_body_size:
                    chunk = stream_socket.recv(data_body_size - len(data_body))
                    if not chunk:
                        logging.warning("Incomplete data body received")
                        break
                    data_body += chunk
                
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
    
    XGT = XGTTester(ip='192.168.1.3', port=2004)
    global event_socket, stream_socket
    event_socket = None
    stream_socket = None
    
    # 객체 정리 스레드 시작
    cleanup_thread = threading.Thread(target=cleanup_old_objects)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    try:
        with start_command_client() as command_socket:
            logging.info("Sending InitializeCamera command")
            handle_response(send_command(command_socket, {"Command": "InitializeCamera"}))
            
            logging.info("Sending GetProperty command")
            ws = handle_response(send_command(command_socket, {"Command": "GetProperty", "Property": "WorkspacePath"}))
            
            # logging.info("Set Visualize Select to Raw")
            # handle_response(send_command(command_socket, {
            #     "Command": "SetProperty",  # GetProperty가 아닌 SetProperty 사용
            #     "Property": "VisualizationVariable", 
            #     "Value": "Raw"  # 또는 "Reflectance", "Absorbance", "Descriptor names" 중 선택
            # }))

            # # 필요한 경우 blend 설정도 추가
            # logging.info("Set Visualization Blend")
            # handle_response(send_command(command_socket, {
            #     "Command": "SetProperty",
            #     "Property": "VisualizationBlend",
            #     "Value": "True"  # 또는 "False"
            # }))
            # SetProperty("Property" = "VisualizationVariable", "Value" = "<Raw | Reflectance | Absorbance | Descriptor names>")
            # SetProperty("Property" = "VisualizationBlend",    "Value" = "True or False")

            workflow_path = f"C:/Users/USER/Breeze/Data/Runtime/1029_test.xml"
            logging.info(f"Loading workflow: {workflow_path}")
            handle_response(send_command(command_socket, {"Command": "LoadWorkflow", "FilePath": workflow_path}))
            
            logging.info("Starting prediction")
            handle_response(send_command(command_socket, {"Command": "StartPredict", "IncludeObjectShape": True}))

            # 스레드 시작
            event_listener_thread = threading.Thread(target=listen_for_events, args=(XGT,), daemon=True)
            data_stream_listener_thread = threading.Thread(target=listen_for_data_stream, daemon=True)

            logging.info("Starting event and data stream threads")
            event_listener_thread.start()
            data_stream_listener_thread.start()

            # 사용자 입력 대기
            print("\n" + "="*70)
            print("✓ 프로그램 실행 중")
            print("✓ 실시간 로그: plc_actions.log 파일 확인")
            print("✓ 종료: Enter 키")
            print("="*70 + "\n")
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
        logging.info("Cleaning up resources...")
        stop_event.set()
        
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

        XGT.plush_bit_off() # 프로그램 종료 시 PLC측의 off처리 안된 모든 비트들을 off처리 해주도록 한다.
        
        logging.info("Program terminated")

if __name__ == '__main__':
    main()