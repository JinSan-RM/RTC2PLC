import time
import logging
import queue
import threading
import signal
import sys
from CAMController import CAMController
from PLCController import XGTController
import conf

# Configure logging (single configuration)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('system.log')
    ]
)

# Inverse class mapping
INV_CLASS_MAPPING = {v: k for k, v in conf.CLASS_MAPPING.items()}

# PLC write queue
plc_queue = queue.Queue()

# Global variables for resource management
plc = None
cam = None
breeze = None

def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) to ensure clean shutdown."""
    logging.info("Received Ctrl+C (SIGINT), shutting down...")
    cleanup()
    sys.exit(0)

def cleanup():
    """Clean up all resources."""
    logging.info("Shutting down system")
    if cam:
        cam.stop()
    if plc:
        plc.disconnect()
    if breeze:
        breeze.stop()
    logging.info("System stopped")

def process_plc_queue():
    while True:
        try:
            class_id, plastic_type, details = plc_queue.get(timeout=1)
            logging.info(
                f"Processing queued PLC write: class_id={class_id} (Plastic: {plastic_type}), "
                f"StartLine={details['start_line']}, StartTime={details['start_time']}"
            )
            success = plc.write_d_and_set_m300(class_id)
            if success:
                logging.info(f"Successfully wrote class_id={class_id} to D00000 and set M300")
            else:
                logging.error(f"Failed to write class_id={class_id} to PLC")
            plc_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logging.error(f"Error processing PLC queue: {str(e)}")

# Start queue processor
threading.Thread(target=process_plc_queue, daemon=True).start()

def handle_classification(classification, details):
    logging.debug(
        f"Received classification: {classification}, Details: "
        f"StartLine={details['start_line']}, EndLine={details['end_line']}, "
        f"StartTime={details['start_time']}, EndTime={details['end_time']}, "
        f"CameraID={details['camera_id']}"
    )

    class_id = INV_CLASS_MAPPING.get(classification, None)
    if class_id is None:
        logging.warning(f"Unknown classification: {classification}, skipping PLC write")
        return

    plastic_type = conf.PLASTIC_MAPPING.get(classification, None)
    if plastic_type is None:
        logging.info(f"No PLC action required for classification: {classification} (Plastic: {plastic_type})")
        return

    logging.info(f"Queueing PLC write for class_id={class_id} (Plastic: {plastic_type})")
    plc_queue.put((class_id, plastic_type, details))

def main():
    logging.info("Starting Camera-PLC integration system")

    # Register SIGINT handler
    signal.signal(signal.SIGINT, signal_handler)

    # Initialize Breeze
    global breeze
    from breeze import BreezeController
    breeze = BreezeController()
    try:
        breeze.start()
    except Exception as e:
        logging.critical(f"Failed to start Breeze: {str(e)}")
        cleanup()
        return

    # Initialize PLC
    global plc
    plc = XGTController(conf.PLC_IP, conf.PLC_PORT)
    try:
        if not plc.connect():
            logging.critical("Failed to connect to PLC. Exiting.")
            cleanup()
            return
    except Exception as e:
        logging.critical(f"PLC connection failed: {str(e)}")
        cleanup()
        return

    # Initialize Camera
    global cam
    cam = CAMController(
        host=conf.HOST,
        command_port=2000,
        event_port=conf.EVENT_PORT,
        data_stream_port=3000,
        class_mapping=conf.CLASS_MAPPING
    )

    try:
        cam.initialize_and_start(conf.WORKFLOW_PATH, handle_classification)
        logging.info("Camera initialized and listening for events")
    except Exception as e:
        logging.critical(f"Camera initialization failed: {str(e)}")
        cleanup()
        return

    # Main loop
    try:
        while True:
            time.sleep(1)
            if not plc.connected:
                logging.warning("PLC disconnected. Attempting to reconnect...")
                plc.connect()
            if not breeze.is_running():
                logging.critical("Breeze process stopped unexpectedly. Exiting.")
                break
    except Exception as e:
        logging.error(f"Unexpected error in main loop: {str(e)}")
    finally:
        cleanup()

if __name__ == "__main__":
    main()