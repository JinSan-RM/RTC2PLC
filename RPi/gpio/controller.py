import pigpio
import threading
import time

from common.config import DeviceRole

class GPIOController:
    def __init__(self, slave_ip = None):
        self.master_pi = pigpio.pi()
        if not self.master_pi.connected:
            raise RuntimeError("pigpio 데몬이 실행되고 있지 않습니다.")
        self.master_initialized = set()
        
        if slave_ip:
            self.slave_pi = pigpio.pi(slave_ip)
            if not self.slave_pi.connected:
                raise RuntimeError("슬레이브의 pigpio 데몬이 실행되고 있지 않습니다.")
        self.slave_initialized = set()

    def _get_pi(self, target: DeviceRole):
        if target == DeviceRole.MASTER:
            return self.master_pi, self.master_initialized
        elif target == DeviceRole.SLAVE:
            return self.slave_pi, self.slave_initialized
        else:
            raise ValueError("target은 'master' 또는 'slave' 이어야 합니다")
        
    def setup_pin(self, target: DeviceRole, pin, mode):
        pi, initialized = self._get_pi(target)

        key = (pin, mode)
        if key not in initialized:
            pi.set_mode(pin, mode)
            initialized.add(key)

    def write_pin(self, target: DeviceRole, pin, value):
        self.setup_pin(target, pin, pigpio.OUTPUT)
        pi, _ = self._get_pi(target)
        pi.write(pin, value)

    def read_pin(self, target: DeviceRole, pin):
        self.setup_pin(target, pin, pigpio.INPUT)
        pi, _ = self._get_pi(target)
        return pi.read(pin)

    def toggle(self, target: DeviceRole, pin):
        self.setup_pin(target, pin, pigpio.OUTPUT)
        pi, _ = self._get_pi(target)
        current = pi.read(pin)
        self.pi.write(pin, not current)

    def pulse(self, target: DeviceRole, pin, delay = 0, duration = 0):
        def _task():
            if delay > 0:
                time.sleep(delay)
            self.write_pin(target, pin, 1)
            if duration > 0:
                time.sleep(duration)
            self.write_pin(target, pin, 0)
        threading.Thread(target = _task, daemon = True).start()
                
    def cleanup(self):
        self.master_pi.stop()
        self.slave_pi.stop()