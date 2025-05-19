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
import queue  # queue.Empty를 위해 추가
from threading import Lock
from collections import defaultdict

logger = logging.getLogger(__name__)

class CAMController:
    def __init__(self, host='127.0.0.1', command_port=2000, event_port=2500, data_stream_port=3000, class_mapping=None):
        """
        Initialize the CAMController for interacting with a Specim FX17 camera.

        :param host: The IP address of the camera.
        :param command_port: Port for sending commands (default: 2000).
        :param event_port: Port for receiving events (default: 2500).
        :param data_stream_port: Port for receiving data stream (default: 3000).
        :param class_mapping: Dictionary mapping descriptor values to classifications (e.g., {1: 'PET Bottle', 2: 'PET sheet'}).
        """
        self.host = host
        self.command_port = command_port
        self.event_port = event_port
        self.data_stream_port = data_stream_port
        self.class_mapping = class_mapping or {}
        self.stop_event = threading.Event()
        self.command_socket = None
        self._lock = threading.Lock()
        self.prediction_queue = Queue()
        self.queue_lock = Lock()

    def start_command_client(self):
        """Initialize and connect the command socket, then simulate Enter key press."""
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
        """Close the command socket."""
        with self._lock:
            if self.command_socket:
                self.command_socket.close()
                self.command_socket = None
                logger.info("Command socket closed")

    def send_command(self, command):
        """
        Send a command to the camera and return the response.

        :param command: Dictionary with the command details (e.g., {"Command": "InitializeCamera"}).
        :return: Response dictionary or None if failed.
        """
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
        """Process a command response and return the message."""
        if not response:
            raise ValueError(f"No response received: {response}")
        message = response.get('Message', '')
        if not response.get("Success", False):
            raise RuntimeError(f"Command not successful: {message}")
        return message

    def process_predictions_batch(self, interval, callback):
        """
        Process predictions in batches over a specified time interval and return the most frequent classification.

        :param interval: Time interval (in seconds) to collect predictions (e.g., 1.0 for 1 second).
        :param callback: Function to call with the most frequent classification and its details.
        """
        def batch_processor():
            while not self.stop_event.is_set():
                try:
                    predictions = []
                    start_time = time.time()
                    # Collect predictions for the specified interval
                    while time.time() - start_time < interval:
                        try:
                            prediction = self.prediction_queue.get(timeout=0.1)
                            predictions.append(prediction)
                        except queue.Empty:
                            continue
                    if predictions:
                        # Group by classification
                        class_counts = defaultdict(list)
                        for classification, details in predictions:
                            class_counts[classification].append(details)
                        if class_counts:
                            # Select the most frequent classification
                            dominant_class = max(class_counts, key=lambda k: len(class_counts[k]))
                            dominant_details = class_counts[dominant_class][0]  # Use first details as representative
                            count = len(class_counts[dominant_class])
                            # Log summary
                            summary = {cls: [d['start_line'] for d in details] for cls, details in class_counts.items()}
                            logger.info(f"Batch processed {len(predictions)} predictions over {interval}s, dominant: {dominant_class} ({count} occurrences), Summary: {summary}")
                            # Call callback with dominant classification
                            callback(dominant_class, dominant_details)
                        else:
                            logger.debug(f"No valid classifications in {interval}s batch")
                    else:
                        logger.debug(f"No predictions collected in {interval}s batch")
                    time.sleep(0.1)  # Prevent tight loop
                except Exception as e:
                    logger.error(f"Error in batch_processor: {e}")
                    time.sleep(1)  # Prevent rapid error loops

        threading.Thread(target=batch_processor, daemon=True).start()

    def start_listening(self, callback, batch_interval=1.0):
        """
        Start listening for events from the camera in a separate thread, processing predictions in batches.

        :param callback: Function to call with the most frequent classification (e.g., handle_classification(classification, details)).
        :param batch_interval: Time interval (in seconds) for batch processing (default: 1.0).
        """
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
                                                logger.debug(f"Received classification: {classification}, StartLine: {details['start_line']}, Details: {details}")
                                    except json.JSONDecodeError:
                                        logger.error("Invalid JSON received from camera")
                            except socket.timeout:
                                continue
                            except Exception as e:
                                logger.error(f"Error processing camera event: {e}")
                except Exception as e:
                    logger.error(f"Error in event listen loop: {e}")
                    time.sleep(5)

        # Start listening thread
        threading.Thread(target=listen, daemon=True).start()
        # Start batch processing thread
        self.process_predictions_batch(batch_interval, callback)

    def start_data_stream(self):
        """Start listening for data stream in a separate thread."""
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
        """Convert ticks to a timezone-aware datetime."""
        return (datetime(1, 1, 1) + timedelta(microseconds=ticks // 10)).replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())

    def initialize_and_start(self, workflow_path, callback, batch_interval=1.0):
        """
        Initialize the camera, load workflow, and start prediction with batch processing.

        :param workflow_path: Path to the workflow XML file.
        :param callback: Function to handle classification results.
        :param batch_interval: Time interval (in seconds) for batch processing (default: 1.0).
        """
        try:
            self.start_command_client()
            self.send_command({"Command": "InitializeCamera"})
            self.send_command({"Command": "LoadWorkflow", "FilePath": workflow_path})
            self.send_command({"Command": "TakeDarkReference"})
            self.send_command({"Command": "TakeWhiteReference"})
            self.send_command({"Command": "StartPredict", "IncludeObjectShape": True})
            time.sleep(5)
            pyautogui.press('enter')
            self.start_listening(callback, batch_interval)
            self.start_data_stream()
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.close_command_client()
            raise

    def stop(self):
        """Stop prediction and all listening threads."""
        try:
            if self.command_socket:
                self.send_command({"Command": "StopPredict"})
        except Exception as e:
            logger.error(f"Error stopping prediction: {e}")
        finally:
            self.stop_event.set()
            self.close_command_client()
            logger.info("CAMController stopped")