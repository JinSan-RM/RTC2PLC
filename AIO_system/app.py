from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
import sys

from src.ui.main_window import MainWindow
from src.function.modbus_manager import ModbusManager
from src.function.ethercat_manager import EtherCATManager
from src.utils.logger import log

class App():
    def __init__(self):
        
        self.qt_app = QApplication(sys.argv)
        
        # 글로벌 폰트 설정
        font = QFont("맑은 고딕", 10)
        self.qt_app.setFont(font)
        
        self.ui = MainWindow(self)
        self.modbus_manager = ModbusManager(self)
        self.modbus_manager.connect()

        self.ethercat_manager = EtherCATManager(self)
        self.ethercat_manager.connect()
        
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_periodic_update)
        self.update_timer.start(100)

    def on_periodic_update(self):
        """주기적 업데이트"""
        self.ui.update_time()

    def on_update_monitor(self, _list):
        if hasattr(self.ui, 'monitoring_page'):
            self.ui.monitoring_page.update_values(_list)

# region inverter control
    def on_update_inverter_status(self, _data):
        if hasattr(self.ui, 'settings_page') and self.ui.pages.currentIndex() == 2:
            tab_index = self.ui.settings_page.tabs.currentIndex()
            if tab_index == 1 or tab_index == 2:
                self.ui.settings_page.tabs.widget(tab_index).update_values(_data)

    def on_set_freq(self, motor_id: str, value: float):
        log(f"Setting frequency for {motor_id} to {value} Hz")
        self.modbus_manager.set_freq(motor_id, value)

    def on_set_acc(self, motor_id: str, value: float):
        log(f"Setting acceleration time for {motor_id} to {value} sec")
        self.modbus_manager.set_acc(motor_id, value)

    def on_set_dec(self, motor_id: str, value: float):
        log(f"Setting deceleration time for {motor_id} to {value} sec")
        self.modbus_manager.set_dec(motor_id, value)

    def motor_start(self, motor_id: str = 'inverter_001'):
        log(f"Starting motor: {motor_id}")
        self.modbus_manager.motor_start(motor_id)

    def motor_stop(self, motor_id):
        log(f"Stopping motor: {motor_id}")
        self.modbus_manager.motor_stop(motor_id)
        
    def custom_check(self, addr):
        self.modbus_manager.custom_check(addr)
    
    def custom_write(self, addr, value):
        self.modbus_manager.custom_write(addr, value)
# endregion

# region servo control
    def on_update_servo_status(self, _data):
        if hasattr(self.ui, 'settings_page') and self.ui.pages.currentIndex() == 2:
            tab_index = self.ui.settings_page.tabs.currentIndex()
            if tab_index == 0:
                self.ui.settings_page.tabs.widget(tab_index).update_values(_data)

    def servo_on(self, servo_id: int):
        self.ethercat_manager.servo_onoff(servo_id, True)
    
    def servo_off(self, servo_id: int):
        self.ethercat_manager.servo_onoff(servo_id, False)

    def servo_reset(self, servo_id: int):
        self.ethercat_manager.servo_reset(servo_id)

    def servo_stop(self, servo_id: int):
        self.ethercat_manager.servo_halt(servo_id)
    
    def servo_homing(self, servo_id: int):
        self.ethercat_manager.servo_homing(servo_id)

    def servo_set_origin(self, servo_id: int):
        self.ethercat_manager.servo_set_home(servo_id)

    def servo_move_to_position(self, servo_id: int, pos: int):
        self.ethercat_manager.servo_move_absolute(servo_id, pos)

    def servo_jog_move(self, servo_id: int, v: int):
        self.ethercat_manager.servo_move_velocity(servo_id, v)

    def servo_inch_move(self, servo_id: int, dist: int):
        self.ethercat_manager.servo_move_relative(servo_id, dist)
# endregion

# region I/O
    def on_update_io_status(self, input_data, output_data):
        if hasattr(self.ui, 'logs_page') and self.ui.pages.currentIndex() == 3:
            tab_index = self.ui.logs_page.tabs.currentIndex()
            if tab_index == 0:
                self.ui.logs_page.tabs.widget(tab_index).update_io_status(input_data, output_data)

    def airknife_on(self, air_num: int, on_term: int):
        self.ethercat_manager.airknife_onoff(0, air_num, on_term)

    def on_airknife_off(self, air_num: int):
        if hasattr(self, 'settings_page'):
            self.ui.settings_page.tabs.widget(3).on_airknife_off(air_num)
# endregion

    def on_log(self, msg):
        self.ui.log(msg)

    def run(self):
        """애플리케이션 실행"""
        self.ui.show()
        sys.exit(self.qt_app.exec())
        # self.root.protocol("WM_DELETE_WINDOW", self.quit)
        # self.root.mainloop()

    def quit(self):
        """애플리케이션 종료"""
        self.modbus_manager.disconnect()
        self.ethercat_manager.disconnect()
        # self.qt_app.quit()
        # self.manager.disconnect()
        # self.root.destroy()

if __name__ == '__main__':
    app = App()
    app.run()