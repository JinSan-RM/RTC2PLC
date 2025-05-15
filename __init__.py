from .conf import HOST, EVENT_PORT, CLASS_MAPPING, PLASTIC_MAPPING
import socket
import json
import logging
import threading
import time


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class CAMController:
    def __init__(self):
        self.host = HOST
        self.event_port = EVENT_PORT
        self.class_mapping = CLASS_MAPPING
        self.plastic_mapping = PLASTIC_MAPPING

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as event_socket:
            event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                event_socket.connect((HOST, EVENT_PORT))
                logging.info("Event socket connected")
            except Exception as e:
            
            message_buffer = ""
            while not stop_event.is_set():
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
                                descriptor_value = int(descriptors[0]) if descriptors else 0
                                
                                classification = CLASS_MAPPING.get(descriptor_value, "Unknown")
                                logging.info(f"Classification: {classification}")
                                
                                # 플라스틱 타입으로 변환하여 PLC에 전송
                                plc_material = PLASTIC_MAPPING.get(classification)
                                if plc_material:
                                    logging.info(f"Triggering PLC for material: {plc_material}")
                                    success = plc_controller.write_to_plc(plc_material)
                                    if success:
                                        logging.info(f"PLC action successful for {plc_material}")
                                        time.sleep(1)  # 다음 이벤트 처리 전 대기
                                    else:
                                        logging.error(f"PLC action failed for {plc_material}")
                                else:
                                    logging.info(f"Skipping PLC action for classification: {classification}")
                        except json.JSONDecodeError:
                            logging.error("Invalid JSON received from camera")
                except socket.timeout:
                    continue
                except Exception as e:
                    logging.error(f"Error processing camera event: {e}")

    def stop(self):
        stop_event = threading.Event()
        stop_event.set()
    


def listen_for_events(plc_controller):
    # 클래스 매핑 정의
    CLASS_MAPPING = {
        0: "-",
        1: "PET Bottle",
        2: "PET sheet",
        3: "PET G",
        4: "PVC",
        5: "PC",
        6: "Background"
    }
    
    # 플라스틱 타입 매핑
    PLASTIC_MAPPING = {
        "PET Bottle": "PET",
        "PET sheet": "PET",
        "PET G": "PET",
        "PVC": "PVC",
        "PC": None,
        "Background": None,
        "-": None
    }
    
    logging.info(f"Connecting to camera event port at {HOST}:{EVENT_PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as event_socket:
        event_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            event_socket.connect((HOST, EVENT_PORT))
            logging.info("Event socket connected")
        except Exception as e:
            logging.error(f"Failed to connect to event port: {e}")
            return

        message_buffer = ""
        while not stop_event.is_set():
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
                            descriptor_value = int(descriptors[0]) if descriptors else 0
                            
                            classification = CLASS_MAPPING.get(descriptor_value, "Unknown")
                            logging.info(f"Classification: {classification}")
                            
                            # 플라스틱 타입으로 변환하여 PLC에 전송
                            plc_material = PLASTIC_MAPPING.get(classification)
                            if plc_material:
                                logging.info(f"Triggering PLC for material: {plc_material}")
                                success = plc_controller.write_to_plc(plc_material)
                                if success:
                                    logging.info(f"PLC action successful for {plc_material}")
                                    time.sleep(1)  # 다음 이벤트 처리 전 대기
                                else:
                                    logging.error(f"PLC action failed for {plc_material}")
                            else:
                                logging.info(f"Skipping PLC action for classification: {classification}")
                    except json.JSONDecodeError:
                        logging.error("Invalid JSON received from camera")
            except socket.timeout:
                continue
            except Exception as e:
                logging.error(f"Error processing camera event: {e}")

def main():
    logging.info("Starting PLC-Camera integration")
    plc_controller = PLCController()
    
    # 카메라 이벤트 리스너 스레드 시작
    event_thread = threading.Thread(target=listen_for_events, args=(plc_controller,))
    event_thread.daemon = True
    event_thread.start()
    
    try:
        logging.info("System running. Press Ctrl+C to stop...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping system...")
    finally:
        stop_event.set()
        event_thread.join(timeout=5)
        logging.info("System stopped")

if __name__ == "__main__":
    main()
