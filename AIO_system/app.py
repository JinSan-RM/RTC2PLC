from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
import sys

from src.ui.main_window import MainWindow
from src.function.modbus_manager import ModbusManager

class App():
    def __init__(self):
        
        self.qt_app = QApplication(sys.argv)
        
        # 글로벌 폰트 설정
        font = QFont("맑은 고딕", 10)
        self.qt_app.setFont(font)
        
        self.ui = MainWindow(self)
        self.manager = ModbusManager(self)
        self.manager.connect()
        
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_periodic_update)
        self.update_timer.start(100)

    def on_periodic_update(self):
        """주기적 업데이트"""
        self.ui.update_time()
    
    def on_update_monitor(self, _list):
        if hasattr(self.ui, 'monitoring_page'):
            self.ui.monitoring_page.update_values(_list)

    def on_set_freq(self, motor_id: str, value: float):
        self.ui.log(f"Setting frequency for {motor_id} to {value} Hz")
        self.manager.set_freq(motor_id, value)

    def on_set_acc(self, motor_id: str, value: float):
        self.ui.log(f"Setting acceleration time for {motor_id} to {value} sec")
        self.manager.set_acc(motor_id, value)

    def on_set_dec(self, motor_id: str, value: float):
        self.ui.log(f"Setting deceleration time for {motor_id} to {value} sec")
        self.manager.set_dec(motor_id, value)

    def motor_start(self, motor_id: str = 'inverter_001'):
        self.ui.log(f"Starting motor: {motor_id}")
        self.manager.motor_start(motor_id)

    def motor_stop(self, motor_id):
        self.ui.log(f"Stopping motor: {motor_id}")
        self.manager.motor_stop(motor_id)
        
    def custom_check(self, addr):
        self.manager.custom_check(addr)
    
    def custom_write(self, addr, value):
        self.manager.custom_write(addr, value)

    def on_log(self, msg):
        self.ui.log(msg)

    def run(self):
        """애플리케이션 실행"""
        self.ui.show()
        sys.exit(self.qt_app.exec_())
        # self.root.protocol("WM_DELETE_WINDOW", self.quit)
        # self.root.mainloop()

    def quit(self):
        """애플리케이션 종료"""
        self.manager.disconnect()
        self.qt_app.quit()
        # self.manager.disconnect()
        # self.root.destroy()

if __name__ == '__main__':
    app = App()
    app.run()