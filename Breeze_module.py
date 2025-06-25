import socket
import json
import uuid
import threading
import time
import logging
from datetime import datetime, timedelta
from dateutil import tz
from XGT_run import XGTTester

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('plc_actions.log'), logging.StreamHandler()]
)

class CameraClient:
    def __init__(self, host, port, timeout=120):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket = self._connect()

    def _connect(self):
        logging.info(f"Connecting to camera at {self.host}:{self.port}")
        soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        soc.connect((self.host, self.port))
        soc.settimeout(self.timeout)
        logging.info("Camera connection successful")
        return soc

    def send_command(self, command):
        command_id = uuid.uuid4().hex[:8]
        command['Id'] = command_id
        message = json.dumps(command, separators=(',', ':')) + '\r\n'
        try:
            self.socket.sendall(message.encode('utf-8'))
            message_buffer = ""
            while True:
                part = self.socket.recv(1024).decode('utf-8')
                if not part:
                    logging.error("No response from camera")
                    return None
                message_buffer += part
                while '\r\n' in message_buffer:
                    full_response_str, message_buffer = message_buffer.split('\r\n', 1)
                    response_json = json.loads(full_response_str.strip())
                    if response_json.get('Id') == command_id:
                        logging.debug(f"Received camera response: {response_json}")
                        return response_json
        except Exception as e:
            logging.error(f"Error sending command: {e}")
            return None

    def initialize_camera(self):
        response = self.send_command({"Command": "InitializeCamera"})
        return self._handle_response(response)

    def load_workflow(self, file_path):
        response = self.send_command({"Command": "LoadWorkflow", "FilePath": file_path})
        return self._handle_response(response)

    def start_predict(self, include_shape=True):
        response = self.send_command({"Command": "StartPredict", "IncludeObjectShape": include_shape})
        return self._handle_response(response)

    def stop_predict(self):
        response = self.send_command({"Command": "StopPredict"})
        return self._handle_response(response)

    def _handle_response(self, response):
        if not response or not response.get("Success", False):
            logging.error(f"Command failed: {response.get('Message', '')}")
            raise RuntimeError("Command not successful")
        return response.get('Message', '')

    def close(self):
        if self.socket:
            self.socket.close()
            logging.info("Camera socket closed")

class EventListener:
    CLASS_MAPPING = {0: "_", 1: "PP", 2: "HDPE", 3: "PS", 4: "LDPE", 5: "ABS"}
    PLASTIC_VALUE_MAPPING = {"PP": 1, "HDPE": 1, "PS": 2, "LDPE": 3, "ABS": 3, "Background": None}

    def __init__(self, host, port, xgt, stop_event):
        self.host = host
        self.port = port
        self.xgt = xgt
        self.stop_event = stop_event
        self.socket = None

    def start_listening(self):
        logging.info(f"Connecting to event port at {self.host}:{self.port}")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.socket.connect((self.host, self.port))
        logging.info("Event socket connected")

        message_buffer = ""
        while not self.stop_event.is_set():
            self.socket.settimeout(1)
            try:
                data = self.socket.recv(1024)
                if not data:
                    logging.warning("No data received from camera")
                    break
                message_buffer += data.decode('utf-8')
                while '\r\n' in message_buffer:
                    message, message_buffer = message_buffer.split('\r\n', 1)
                    self.process_event(json.loads(message))
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Error in event loop: {e}")

    def process_event(self, message_json):
        event = message_json.get('Event', '')
        if event == "PredictionObject":
            inner_message = json.loads(message_json.get('Message', '{}'))
            descriptors = inner_message.get('Descriptors', [])
            descriptor_value = int(descriptors[0]) if descriptors else 0
            classification = self.CLASS_MAPPING.get(descriptor_value, "Unknown")
            plc_value = self.PLASTIC_VALUE_MAPPING.get(classification)

            shape = inner_message.get('Shape', {})
            border = shape.get('Border', [])
            pos = self.calculate_shape_metrics(border)
            logging.info(f"Classification: {classification}, Pos: {pos}")

            if plc_value is not None and 20 < pos['width'] < 800 and 20 < pos['height'] < 2000:
                try:
                    success = self.xgt.write_d_and_set_m300(plc_value)
                    logging.info(f"PLC action {'successful' if success else 'failed'} for value {plc_value}")
                except Exception as e:
                    logging.error(f"PLC write exception: {e}")
            else:
                logging.info(f"Skipping PLC action for classification: {classification}")

    def calculate_shape_metrics(self, border):
        if not border or len(border) < 2:
            return {"width": 0, "height": 0, "center_x": 0, "center_y": 0}
        x_coords = [point[0] for point in border]
        y_coords = [point[1] for point in border]
        return {
            "width": max(x_coords) - min(x_coords),
            "height": max(y_coords) - min(y_coords),
            "center_x": (max(x_coords) + min(x_coords)) / 2,
            "center_y": (max(y_coords) + min(y_coords)) / 2
        }

    def stop(self):
        if self.socket:
            self.socket.close()
            logging.info("Event socket closed")

class Application:
    def __init__(self, config):
        self.stop_event = threading.Event()
        self.camera_client = CameraClient(config['camera_host'], config['command_port'])
        self.event_listener = EventListener(config['camera_host'], config['event_port'], 
                                         XGTTester(config['plc_ip'], config['plc_port']), self.stop_event)
        self.data_stream_listener = DataStreamListener(config['camera_host'], config['data_stream_port'], 
                                                    self.stop_event, config['throttle_interval'])

    def start(self):
        self.camera_client.initialize_camera()
        self.camera_client.load_workflow("C:/Users/withwe/Breeze/Data/Runtime/PP_PS_HDPE_Classification.xml")
        self.camera_client.start_predict()
        
        self.event_thread = threading.Thread(target=self.event_listener.start_listening)
        self.stream_thread = threading.Thread(target=self.data_stream_listener.start_listening)
        self.event_thread.daemon = True
        self.stream_thread.daemon = True
        self.event_thread.start()
        self.stream_thread.start()

    def stop(self):
        self.stop_event.set()
        self.camera_client.stop_predict()
        self.camera_client.close()
        self.event_listener.stop()
        self.data_stream_listener.stop()
        self.event_thread.join(timeout=5)
        self.stream_thread.join(timeout=5)
        logging.info("Program terminated")

    def run(self):
        self.start()
        print("Program is running. Press Enter to stop...")
        input()
        self.stop()

if __name__ == "__main__":
    config = {
        'camera_host': '192.168.250.130',
        'command_port': 2000,
        'event_port': 2500,
        'data_stream_port': 3000,
        'plc_ip': '192.168.250.120',
        'plc_port': 2004,
        'throttle_interval': 1.0
    }
    app = Application(config)
    app.run()