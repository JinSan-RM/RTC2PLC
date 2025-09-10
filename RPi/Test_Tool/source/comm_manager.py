import asyncio
import time
import threading
from collections import deque
from queue import Queue, Empty
from typing import Dict, Callable

import lgpio
import pysoem
from pymodbus.client import ModbusSerialClient, ModbusTcpClient

from .consts import Priority, PinRole

class CommManager:
    _instance = None
    _initialized = False
    _running = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, app):
        if not self._initialized:
            self.app = app

            # GPIO
            self.gpio_handle = lgpio.gpiochip_open(0)
            if self.gpio_handle < 0:
                raise RuntimeError(f"GPIO open error. errorcode: {self.gpio_handle}")
            self.pin_initialized = set()

            # EtherCAT
            # self.ethercat_master = pysoem.Master()
            # self.ethercat_master.open("eth1")
            # if self.ethercat_master.config_init() > 0:
            #     self.ethercat_slaves = []
            #     for slave in self.master.slaves:
            #         self.ethercat_slaves.append(slave)

            # Modbus-RTU
            self.modbus_client = ModbusSerialClient(
                port='/dev/ttyUSB0',
                baudrate=19200,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=0.5
            )
            self.modbus_client.connect()
    
    # ============= GPIO =============
    def _get_gpio(self):
        self.gpio_handle, self.pin_initialized

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

    def _write_gpio_pin(self, pin: int, value: int):
        self.setup_pin(pin, PinRole.OUTPUT)
        handle, _ = self._get_gpio()
        ret = lgpio.gpio_write(handle, pin, value)
        if ret < 0:
            raise RuntimeError(f"GPIO {pin} write error. errorcode: {ret}")
    
    def gpio_test(self):
        def _task():
            self._write_gpio_pin(17, 1)
            time.sleep(1)
            self._write_gpio_pin(17, 0)
        threading.Thread(target=_task, daemon=True).start()

    # ============= EtherCAT =============
    def write_CoE(self, index, sub_index, value):
        device = self.ethercat_slaves[0]
        device.sdo_write(index, sub_index, value)


    def ethercat_test(self):
        for device in self.ethercat_slaves:
            print(device.name)

    # ============= Modbus =============
    def write_holding_register(self, register_address: int, value: int) -> bool:
        try:
            slave_id = 1
            ret = self.modbus_client.write_register(register_address, value, device_id=slave_id)

            if ret.isError():
                raise Exception(f"Modbus error: {ret}")

            print(f"write value {value} on register {register_address} completed")
            return True

        except Exception as e:
            print(f"register writing failed (Register: {register_address}, Value: {value}): {e}")
            return False
    
    def modbus_test(self):
        def _task():
            self.write_holding_register(0x0382, 0x03)
            time.sleep(5)
            self.write_holding_register(0x0382, 0x00)
        threading.Thread(target=_task, daemon=True).start()