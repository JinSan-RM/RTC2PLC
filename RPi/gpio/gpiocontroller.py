import lgpio
import rgpio
import threading
import time
import logging
from typing import Dict

from common.consts import DeviceRole, PinRole, MessageType
from common.utils import EventManager

class GPIOController():
    _instance = None
    _initialized = False
    _running = False

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, event_manager: EventManager):
        self.logger = logging.getLogger(__name__)
        if not self._initialized:
            self.event_manager = event_manager
            self.master_handle = lgpio.gpiochip_open(0)
            if self.master_handle < 0:
                raise RuntimeError(f"MASTER GPIO open error. errorcode: {self.master_handle}")
            self.pin_initialized = set()

            self._initialized = True

    def run(self):
        self._running = True

        while self._running:
            msg = self.event_manager.get_message("gpio_queue", timeout=0.1)
            if msg and msg.msg_type == MessageType.GPIO_COMMAND:
                msg.execute()

            time.sleep(0.01)

    def stop(self):
        self._running = False
        self.cleanup()

    def _get_gpio(self):
        self.master_handle, self.pin_initialized

    def setup_pin(self, pin: int, mode: PinRole):
        handle, initialized = self._get_gpio()

        key = (pin, mode)
        if key not in initialized:
            initialized.add(key)
            ret = 0
            if mode == PinRole.INPUT:
                ret = lgpio.gpio_claim_input(handle, pin)
            elif mode == PinRole.OUTPUT:
                ret = lgpio.gpio_claim_output(handle, pin, 0)
            else:
                raise ValueError("GPIO mode must be INPUT or OUTPUT")

            if ret < 0:
                raise RuntimeError(f"GPIO {pin} {mode.name} error. errorcode: {ret}")

    def write_pin(self, pin: int, value: int):
        self.setup_pin(pin, PinRole.OUTPUT)
        handle, _ = self._get_gpio()
        ret = lgpio.gpio_write(handle, pin, value)
        if ret < 0:
            raise RuntimeError(f"GPIO {pin} write error. errorcode: {ret}")

    def read_pin(self, pin: int):
        self.setup_pin(pin, PinRole.INPUT)
        handle, _ = self._get_gpio()
        ret = lgpio.gpio_read(handle, pin)
        if ret < 0:
            raise RuntimeError(f"GPIO {pin} read error. errorcode: {ret}")
        return ret

    def toggle(self, pin: int):
        self.setup_pin(pin, PinRole.OUTPUT)
        handle, _ = self._get_gpio()
        current = lgpio.gpio_read(handle, pin)
        if current < 0:
            raise RuntimeError(f"GPIO {pin} read error. errorcode: {current}")
        lgpio.gpio_write(pin, not current)

    def pulse(self, pin: int, delay = 0, duration = 0):
        def _task():
            if delay > 0:
                time.sleep(delay)
            self.write_pin(pin, 1)
            if duration > 0:
                time.sleep(duration)
            self.write_pin(pin, 0)
        threading.Thread(target=_task, daemon=True).start()

    def cleanup(self):
        for pin, mode in self.pin_initialized:
            try:
                if mode == PinRole.OUTPUT:
                    lgpio.gpio_write(self.master_handle, pin, 0)
                lgpio.gpio_free(self.master_handle, pin)
            except Exception as e:
                self.logger.error(f"GPIO {pin} free error: {e}")

        self.pin_initialized.clear()
        lgpio.gpiochip_close(self.master_handle)