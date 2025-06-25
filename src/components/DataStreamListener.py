import socket
import threading
import time
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DataStreamListener:
    def __init__(self, host, port, stop_event, throttle_interval=1.0):
        self.host = host
        self.port = port
        self.stop_event = stop_event
        self.throttle_interval = throttle_interval
        self.last_processed_time = 0
        self.socket = None

    def start_listening(self):
        logging.info(f"Connecting to data stream at {self.host}:{self.port}")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.socket.connect((self.host, self.port))
        logging.info("Data stream connected")

        expected_header_size = 25
        while not self.stop_event.is_set():
            self.socket.settimeout(1)
            try:
                header = b""
                while len(header) < expected_header_size:
                    chunk = self.socket.recv(expected_header_size - len(header))
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
                    chunk = self.socket.recv(metadata_size - len(metadata))
                    if not chunk:
                        logging.warning("Incomplete metadata received")
                        break
                    metadata += chunk

                data_body = b""
                while len(data_body) < data_body_size:
                    chunk = self.socket.recv(data_body_size - len(data_body))
                    if not chunk:
                        logging.warning("Incomplete data body received")
                        break
                    data_body += chunk

                current_time = time.time()
                if current_time - self.last_processed_time >= self.throttle_interval:
                    self.last_processed_time = current_time
                    self.process_data(stream_type, frame_number, timestamp, metadata, data_body)
                else:
                    logging.debug(f"Skipping frame {frame_number} due to throttle limit")

            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Error in data stream: {e}")
                continue

    def process_data(self, stream_type, frame_number, timestamp, metadata, data_body):
        logging.info(f"Stream type: {stream_type}, Frame: {frame_number}, Timestamp: {timestamp}")
        # 추가적인 데이터 처리 로직이 필요하면 여기에 구현
        # 예: logging.info(f"Metadata (hex): {metadata.hex()}, Data body (hex): {data_body.hex()}")

    def stop(self):
        if self.socket:
            self.socket.close()
            logging.info("Data stream socket closed")