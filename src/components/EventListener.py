import json
import logging
import socket
from XGTClient import XGTTester

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('plc_actions.log'), logging.StreamHandler()]
)
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
