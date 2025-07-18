import lgpio
import rgpio
import threading
import time

from common.config import DeviceRole, PinRole

class GPIOController:
    def __init__(self, slave_ip = None, slave_port = None):
        self.master_handle = lgpio.gpiochip_open(0)
        if self.master_handle < 0:
            raise RuntimeError(f"MASTER GPIO open error. errorcode: {self.master_handle}")
        self.master_initialized = set()

        if slave_ip:
            # timeout = 30
            # start_time = time.time()
            # while time.time() - start_time < timeout:
            #     try:
            #         self.slave_handle = rgpio.gpiochip_open(slave_ip, slave_port)
            #         if self.slave_handle >= 0:
            #             return True
            #     except:
            #         pass
            self.slave_handle = rgpio.gpiochip_open(slave_ip, slave_port)
            if self.slave_handle < 0:
                raise RuntimeError(f"SLAVE GPIO open error. errorcode: {self.slave_handle}")
            self.slave_initialized = set()

    def _get_gpio(self, target: DeviceRole):
        if target == DeviceRole.MASTER:
            return self.master_handle, self.master_initialized
        elif target == DeviceRole.SLAVE:
            return self.slave_handle, self.slave_initialized
        else:
            raise ValueError("GPIO target must be MASTER or SLAVE")

    def setup_pin(self, target: DeviceRole, pin, mode: PinRole):
        handle, initialized = self._get_gpio(target)

        key = (pin, mode)
        if key not in initialized:
            initialized.add(key)
            ret = 0
            if target == DeviceRole.MASTER:
                if mode == PinRole.INPUT:
                    ret = lgpio.gpio_claim_input(handle, pin)
                elif mode == PinRole.OUTPUT:
                    ret = lgpio.gpio_claim_output(handle, pin, 0)
                else:
                    raise ValueError("GPIO mode must be INPUT or OUTPUT")

                if ret < 0:
                    raise RuntimeError(f"MASTER GPIO {pin} {mode.name} error. errorcode: {ret}")
            elif target == DeviceRole.SLAVE:
                if mode == PinRole.INPUT:
                    ret = rgpio.gpio_claim_input(handle, pin)
                elif mode == PinRole.OUTPUT:
                    ret = rgpio.gpio_claim_output(handle, pin, 0)
                else:
                    raise ValueError("GPIO mode must be INPUT or OUTPUT")

                if ret < 0:
                    raise RuntimeError(f"SLAVE GPIO {pin} {mode.name} error. errorcode: {ret}")
            else:
                raise ValueError("GPIO target must be MASTER or SLAVE")

    def write_pin(self, target: DeviceRole, pin, value):
        self.setup_pin(target, pin, PinRole.OUTPUT)
        handle, _ = self._get_gpio(target)
        ret = 0
        if target == DeviceRole.MASTER:
            ret = lgpio.gpio_write(handle, pin, value)
        elif target == DeviceRole.SLAVE:
            ret = rgpio.gpio_write(handle, pin, value)
        else:
            raise ValueError("GPIO target must be MASTER or SLAVE")
        
        if ret < 0:
            raise RuntimeError(f"{target.name} GPIO {pin} write error. errorcode: {ret}")

    def read_pin(self, target: DeviceRole, pin):
        self.setup_pin(target, pin, PinRole.INPUT)
        handle, _ = self._get_gpio(target)
        ret = 0
        if target == DeviceRole.MASTER:
            ret = lgpio.gpio_read(handle, pin)
        elif target == DeviceRole.SLAVE:
            ret = rgpio.gpio_read(handle, pin)
        else:
            raise ValueError("GPIO target must be MASTER or SLAVE")
        
        if ret < 0:
            raise RuntimeError(f"{target.name} GPIO {pin} read error. errorcode: {ret}")
        return ret

    def toggle(self, target: DeviceRole, pin):
        self.setup_pin(target, pin, PinRole.OUTPUT)
        handle, _ = self._get_gpio(target)
        if target == DeviceRole.MASTER:
            current = lgpio.gpio_read(handle, pin)
            if current < 0:
                raise RuntimeError(f"{target.name} GPIO {pin} read error. errorcode: {current}")
            lgpio.gpio_write(pin, not current)
        elif target == DeviceRole.SLAVE:
            current = rgpio.gpio_read(handle, pin)
            if current < 0:
                raise RuntimeError(f"{target.name} GPIO {pin} read error. errorcode: {current}")
            rgpio.gpio_write(pin, not current)
        else:
            raise ValueError("GPIO target must be MASTER or SLAVE")

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
        if hasattr(self, "slave_handle"):
            for pin, mode in self.slave_initialized:
                try:
                    if mode == PinRole.OUTPUT:
                        rgpio.gpio_write(self.master_handle, pin, 0)
                    rgpio.gpio_free(self.master_handle, pin)
                except Exception as e:
                    print(f"SLAVE GPIO {pin} free error: {e}")
            self.slave_initialized.clear()
            rgpio.gpiochip_close(self.slave_handle)

        for pin, mode in self.master_initialized:
            try:
                if mode == PinRole.OUTPUT:
                    lgpio.gpio_write(self.master_handle, pin, 0)
                lgpio.gpio_free(self.master_handle, pin)
            except Exception as e:
                print(f"MASTER GPIO {pin} free error: {e}")
        self.master_initialized.clear()
        lgpio.gpiochip_close(self.master_handle)