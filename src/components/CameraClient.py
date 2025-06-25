import socket
import json
import uuid
import logging
import time
# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('camera_client.log'), logging.StreamHandler()]
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