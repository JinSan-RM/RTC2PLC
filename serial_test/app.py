import tkinter as tk

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
import sys

from src.ui.main_window import MainWindow
from src.main_ui import MainUI
from src.function.comm_manager import ModbusManager

class App():
    def __init__(self):
        
        self.qt_app = QApplication(sys.argv)
        
        # 글로벌 폰트 설정
        font = QFont("맑은 고딕", 10)
        self.qt_app.setFont(font)
        
        self.root = tk.Tk()
        self.ui_old = MainUI(self)
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
        self.root.after(0, self.ui_old.update_monitor, _list)

    def on_set_freq(self, value):
        self.manager.set_freq(value)

    def on_set_acc(self, value):
        self.manager.set_acc(value)

    def on_set_dec(self, value):
        self.manager.set_dec(value)

    def motor_start(self, motor_id):
        self.manager.motor_start(motor_id)

    def motor_stop(self, motor_id):
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