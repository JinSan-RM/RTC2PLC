import socket
import json
import logging
import threading
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CAMController:
    def __init__(self, host, port, class_mapping):
        """
        Initialize the CAMController.

        :param host: The IP address of the camera.
        :param port: The port number for the camera's event stream.
        :param class_mapping: A dictionary mapping descriptor values to classifications.
        """
        self.host = host
        self.port = port
        self.class_mapping = class_mapping
        self.stop_event = threading.Event()

    def start_listening(self, callback):
        """
        Start listening for events from the camera in a separate thread.

        :param callback: A function to call with each classification (e.g., handle_classification).
        """
        def listen():
            while not self.stop_event.is_set():
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as event_socket:
                        event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        event_socket.connect((self.host, self.port))
                        logging.info("Event socket connected")

                        message_buffer = ""
                        while not self.stop_event.is_set():
                            event_socket.settimeout(1)
                            try:
                                data = event_socket.recv(1024).decode('utf-8')
                                if not data:
                                    logging.warning("No data received from camera")
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
                                            if descriptors:
                                                descriptor_value = int(descriptors[0])
                                                classification = self.class_mapping.get(descriptor_value, "Unknown")
                                                callback(classification)
                                    except json.JSONDecodeError:
                                        logging.error("Invalid JSON received from camera")
                            except socket.timeout:
                                continue
                            except Exception as e:
                                logging.error(f"Error processing camera event: {e}")
                except Exception as e:
                    logging.error(f"Error in listen loop: {e}")
                    time.sleep(5)  # Wait before retrying connection

        threading.Thread(target=listen, daemon=True).start()

    def stop_listening(self):
        """
        Stop the listening loop.
        """
        self.stop_event.set()