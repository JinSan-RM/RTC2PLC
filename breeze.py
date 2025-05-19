import subprocess
import os
import time
import logging
import pyautogui

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('breeze.log')  # Separate log for Breeze
    ]
)

class BreezeController:
    def __init__(self, breeze_path=r"C:\Users\withwe\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Prediktera\Breeze\Breeze.lnk"):
        """
        Initialize BreezeController.

        :param breeze_path: Path to Breeze .lnk file.
        """
        self.breeze_path = breeze_path
        self.process = None

    def start(self):
        """Launch Breeze and simulate Enter key press."""
        # Validate file existence
        if not os.path.exists(self.breeze_path):
            logging.critical(f"Breeze shortcut not found at {self.breeze_path}")
            raise FileNotFoundError(f"Breeze shortcut not found at {self.breeze_path}")

        try:
            # Launch Breeze
            logging.info(f"Launching Breeze from {self.breeze_path}")
            self.process = subprocess.Popen(
                self.breeze_path,
                shell=True,  # Required for .lnk files on Windows
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            logging.info(f"Breeze launched with PID {self.process.pid}")

            # Wait for Breeze to initialize
            time.sleep(5)  # Adjust as needed

            # Simulate Enter key press
            logging.info("Simulating Enter key press to establish connection")
            pyautogui.press('enter')
            logging.info("Enter key press simulated")

            # Verify process is running
            if self.process.poll() is not None:
                error_output = self.process.stderr.read().decode() if self.process.stderr else "No error output"
                logging.error(f"Breeze process terminated prematurely. Exit code: {self.process.returncode}, Error: {error_output}")
                self.process = None
                raise RuntimeError("Breeze process failed to stay running")

        except Exception as e:
            logging.error(f"Failed to launch Breeze or simulate Enter key press: {str(e)}")
            self.process = None
            raise

    def stop(self):
        """Terminate Breeze process if running."""
        if self.process and self.process.poll() is None:
            try:
                logging.info(f"Terminating Breeze process (PID: {self.process.pid})")
                self.process.terminate()
                self.process.wait(timeout=5)
                logging.info("Breeze process terminated successfully")
            except subprocess.TimeoutExpired:
                logging.warning("Breeze process did not terminate gracefully, forcing kill")
                self.process.kill()
            except Exception as e:
                logging.error(f"Error terminating Breeze process: {str(e)}")
            finally:
                self.process = None

    def is_running(self):
        """Check if Breeze process is running."""
        return self.process is not None and self.process.poll() is None

# if __name__ == "__main__":
#     # Test BreezeController standalone
#     controller = BreezeController()
#     try:
#         controller.start()
#         input("Press Enter to stop Breeze...\n")
#     except Exception as e:
#         logging.critical(f"Error during Breeze test: {str(e)}")
#     finally:
#         controller.stop()