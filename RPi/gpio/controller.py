import pigpio
import threading
import time

class GPIOController:
    def __init__(self, pins):  # GPIO 컨트롤러 생성 시 핀 번호는 BCM 기준(내부 번호)
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio 데몬이 실행되고 있지 않습니다.")
        
        self.pins = pins
        # 초기값 off 처리
        for pin in self.pins:
            self.pi.set_mode(pin, pigpio.OUTPUT)
            self.pi.write(pin, 0)

    def set_high(self, pin):
        if pin in self.pins:
            self.pi.write(pin, 1)

    def set_low(self, pin):
        if pin in self.pins:
            self.pi.write(pin, 0)

    def toggle(self, pin):
        if pin in self.pins:
            current = self.pi.read(pin)
            self.pi.write(pin, not current)

    def pulse(self, pin, delay = 0, duration = 0):
        def _task():
            if delay > 0:
                time.sleep(delay)
            self.set_high(pin)
            if duration > 0:
                time.sleep(duration)
            self.set_low(pin)
        threading.Thread(target = _task, daemon = True).start()
                
    def cleanup(self):
        for pin in self.pins:
            self.pi.write(pin, 0)
        self.pi.stop()