import socket
import json
import uuid
import threading
import logging
from datetime import datetime, timedelta
from dateutil import tz
import time
import pyautogui
from queue import Queue
import queue
from threading import Lock
from collections import defaultdict

logger = logging.getLogger(__name__)

class CAMController:
    def __init__(self, host='127.0.0.1', command_port=2000, event_port=2500, data_stream_port=3000, class_mapping=None):
        self.host = host
        self.command_port = command_port
        self.event_port = event_port
        self.data_stream_port = data_stream_port
        self.class_mapping = class_mapping or {}
        self.stop_event = threading.Event()
        self.command_socket = None
        self._lock = threading.Lock()
        self.prediction_queue = Queue(maxsize=1000)
        self.queue_lock = Lock()
        self.class_priority = {'PET sheet': 2, 'PVC': 1, 'PET Bottle': 0, 'PET G': 0, 'PC': 0, 'Background': -1, '-': -1}

    def start_command_client(self):
        try:
            soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            soc.connect((self.host, self.command_port))
            soc.settimeout(120)
            self.command_socket = soc
            logger.info("Command socket connected")
            logger.info("Waiting 5 seconds for Breeze to initialize connection")
            time.sleep(30)
            logger.info("Simulating Enter key press to activate camera connection")
            pyautogui.press('enter')
            logger.info("Enter key press simulated")
        except Exception as e:
            logger.error(f"Failed to connect command socket or simulate Enter key press: {e}")
            raise

    def close_command_client(self):
        with self._lock:
            if self.command_socket:
                self.command_socket.close()
                self.command_socket = None
                logger.info("Command socket closed")

    def send_command(self, command):
        if not self.command_socket:
            raise RuntimeError("Command socket not initialized")
        command_id = uuid.uuid4().hex[:8]
        command['Id'] = command_id
        message = json.dumps(command, separators=(',', ':')) + '\r\n'
        with self._lock:
            try:
                self.command_socket.sendall(message.encode('utf-8'))
                message_buffer = ""
                while True:
                    part = self.command_socket.recv(1024).decode('utf-8')
                    if not part:
                        logger.warning("Socket closed by server")
                        break
                    
                    message_buffer += part
                    while '\r\n' in message_buffer:
                        full_response_str, message_buffer = message_buffer.split('\r\n', 1)
                        try:
                            response_json = json.loads(full_response_str.strip())
                            if response_json.get('Id') == command_id:
                                return self._handle_response(response_json)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON received: {full_response_str}")
                            continue
            except socket.timeout:
                logger.error("Command request timed out")
                return None
            except Exception as e:
                logger.error(f"Error sending command: {e}")
                return None
        return None

    def _handle_response(self, response):
        if not response:
            raise ValueError(f"No response received: {response}")
        message = response.get('Message', '')
        if not response.get("Success", False):
            raise RuntimeError(f"Command not successful: {message}")
        return message

    def process_predictions_batch(self, interval, callback, min_predictions=3):
        def batch_processor():
            while not self.stop_event.is_set():
                try:
                    predictions = []
                    start_time = time.time()
                    while time.time() - start_time < interval:
                        try:
                            prediction = self.prediction_queue.get(timeout=0.1)
                            predictions.append(prediction)
                        except queue.Empty:
                            continue
                    if predictions:
                        class_counts = defaultdict(list)
                        for classification, details in predictions:
                            class_counts[classification].append(details)
                        if class_counts:
                            dominant_class = max(
                                class_counts,
                                key=lambda k: (len(class_counts[k]), self.class_priority.get(k, 0))
                            )
                            count = len(class_counts[dominant_class])
                            if count >= min_predictions:
                                dominant_details = class_counts[dominant_class][0]
                                summary = {cls: [d['start_line'] for d in details] for cls, details in class_counts.items()}
                                logger.info(
                                    f"Batch processed {len(predictions)} predictions over {interval}s, "
                                    f"dominant: {dominant_class} ({count} occurrences), Summary: {summary}"
                                )
                                callback(dominant_class, dominant_details)
                            else:
                                logger.debug(
                                    f"Batch skipped: {len(predictions)} predictions, "
                                    f"dominant: {dominant_class} ({count} < {min_predictions})"
                                )
                        else:
                            logger.debug(f"No valid classifications in {interval}s batch")
                    else:
                        logger.debug(f"No predictions collected in {interval}s batch")
                    if self.prediction_queue.qsize() > 800:
                        logger.warning(f"Queue size high: {self.prediction_queue.qsize()}")
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error in batch_processor: {e}")
                    time.sleep(1)

        threading.Thread(target=batch_processor, daemon=True).start()

    def start_listening(self, callback, batch_interval=1.0, min_predictions=3):
        def listen():
            while not self.stop_event.is_set():
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as event_socket:
                        event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        event_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        event_socket.connect((self.host, self.event_port))
                        logger.info("Event socket connected")
                        message_buffer = ""
                        while not self.stop_event.is_set():
                            event_socket.settimeout(1)
                            try:
                                data = event_socket.recv(1024).decode('utf-8')
                                if not data:
                                    logger.warning("No data received from camera")
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
                                            details = {
                                                'start_line': inner_message.get('StartLine', 0),
                                                'end_line': inner_message.get('EndLine', 0),
                                                'start_time': self._convert_ticks_to_datetime(inner_message.get('StartTime', 0)),
                                                'end_time': self._convert_ticks_to_datetime(inner_message.get('EndTime', 0)),
                                                'camera_id': inner_message.get('CameraId', 0),
                                                'shape': inner_message.get('Shape', {})
                                            }
                                            if descriptors:
                                                descriptor_value = int(descriptors[0])
                                                classification = self.class_mapping.get(descriptor_value, "Unknown")
                                                with self.queue_lock:
                                                    self.prediction_queue.put((classification, details))
                                                logger.debug(
                                                    f"Received classification: {classification}, "
                                                    f"StartLine: {details['start_line']}, Details: {details}"
                                                )
                                    except json.JSONDecodeError:
                                        logger.error("Invalid JSON received from camera")
                            except socket.timeout:
                                continue
                            except Exception as e:
                                logger.error(f"Error processing camera event: {e}")
                except Exception as e:
                    logger.error(f"Error in event listen loop: {e}")
                    time.sleep(5)

        threading.Thread(target=listen, daemon=True).start()
        self.process_predictions_batch(batch_interval, callback, min_predictions)

    def start_data_stream(self):
        def listen():
            while not self.stop_event.is_set():
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream_socket:
                        stream_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        stream_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        stream_socket.connect((self.host, self.data_stream_port))
                        logger.info("Data stream socket connected")
                        expected_header_size = 25
                        while not self.stop_event.is_set():
                            stream_socket.settimeout(1)
                            try:
                                header = b""
                                while len(header) < expected_header_size:
                                    chunk = stream_socket.recv(expected_header_size - len(header))
                                    if not chunk:
                                        break
                                    header += chunk
                                if len(header) != expected_header_size:
                                    logger.warning("Incomplete header received")
                                    continue
                                stream_type = header[0]
                                frame_number = int.from_bytes(header[1:9], byteorder='little', signed=True)
                                timestamp = int.from_bytes(header[9:17], byteorder='little', signed=False)
                                metadata_size = int.from_bytes(header[17:21], byteorder='little', signed=False)
                                data_body_size = int.from_bytes(header[21:25], byteorder='little', signed=False)
                                stream_socket.recv(metadata_size)
                                stream_socket.recv(data_body_size)
                            except socket.timeout:
                                continue
                            except Exception as e:
                                logger.error(f"Error processing data stream: {e}")
                except Exception as e:
                    logger.error(f"Error in data stream listen loop: {e}")
                    time.sleep(5)

        threading.Thread(target=listen, daemon=True).start()

    def _convert_ticks_to_datetime(self, ticks):
        return (datetime(1, 1, 1) + timedelta(microseconds=ticks // 10)).replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())

    def initialize_and_start(self, workflow_path, callback, batch_interval=1.0, min_predictions=3):
        try:
            self.start_command_client()
            self.send_command({"Command": "InitializeCamera"})
            self.send_command({"Command": "LoadWorkflow", "FilePath": workflow_path})
            self.send_command({"Command": "TakeDarkReference"})
            self.send_command({"Command": "TakeWhiteReference"})
            self.send_command({"Command": "StartPredict", "IncludeObjectShape": True})
            time.sleep(5)
            pyautogui.press('enter')
            self.start_listening(callback, batch_interval, min_predictions)
            self.start_data_stream()
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.close_command_client()
            raise

    def stop(self):
        try:
            if self.command_socket:
                self.send_command({"Command": "StopPredict"})
        except Exception as e:
            logger.error(f"Error stopping prediction: {e}")
        finally:
            self.stop_event.set()
            self.close_command_client()
            logger.info("CAMController stopped")