import subprocess
import os
import time
import logging

# Logging is configured in sample_code.py
logger = logging.getLogger(__name__)


class BreezeController:
    def __init__(self, shortcut_path=r"C:\Users\withwe\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Prediktera\Breeze\Breeze.lnk"):
        """
        Initialize BreezeController for controlling the Breeze application.

        :param shortcut_path: Path to the Breeze .lnk file.
        """
        self.shortcut_path = shortcut_path
        self.process = None

    def start(self):
        """Launch Breeze application."""
        if not os.path.exists(self.shortcut_path):
            logger.critical(f"Breeze shortcut not found at {self.shortcut_path}")
            raise FileNotFoundError(f"Breeze shortcut not found at {self.shortcut_path}")

        try:
            logger.info(f"Launching Breeze from {self.shortcut_path}")
            self.process = subprocess.Popen(
                self.shortcut_path,
                shell=True,  # Required for .lnk files on Windows
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            logger.info(f"Breeze launched with PID {self.process.pid}")

            # Check if process is still running
            if self.process.poll() is not None:
                error_output = self.process.stderr.read().decode() if self.process.stderr else "No error output"
                logger.error(f"Breeze process terminated prematurely. Exit code: {self.process.returncode}, Error: {error_output}")
                self.process = None
                raise RuntimeError("Breeze process failed to stay running")
            time.sleep(30)  # Brief wait to ensure process starts

            return True
        except Exception as e:
            logger.error(f"Failed to launch Breeze: {str(e)}")
            self.process = None
            raise

    def stop(self):
        """Terminate Breeze process if running."""
        if self.process and self.process.poll() is None:
            try:
                logger.info(f"Terminating Breeze process (PID: {self.process.pid})")
                self.process.terminate()
                self.process.wait(timeout=5)
                logger.info("Breeze process terminated successfully")
            except subprocess.TimeoutExpired:
                logger.warning("Breeze process did not terminate gracefully, forcing kill")
                self.process.kill()
            except Exception as e:
                logger.error(f"Error terminating Breeze process: {str(e)}")
            finally:
                self.process = None

    def is_running(self):
        """Check if Breeze process is still running."""
        return self.process is not None and self.process.poll() is None