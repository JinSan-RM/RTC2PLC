import logging
import threading

from CameraClient import CameraClient
from EventListener import EventListener
from DataStreamListener import DataStreamListener
from XGTClient import XGTTester

class Application:
    def __init__(self, config):
        self.stop_event = threading.Event()
        self.camera_client = CameraClient(config['camera_host'], config['command_port'])
        self.event_listener = EventListener(config['camera_host'], config['event_port'], XGTTester(config['plc_ip'], config['plc_port']), self.stop_event)
        self.data_stream_listener = DataStreamListener(config['camera_host'], config['data_stream_port'], self.stop_event, config['throttle_interval'])

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