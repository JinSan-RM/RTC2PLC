import tkinter as tk

from src.main_ui import MainUI
from src.comm_manager import ModbusManager

class App():
    def __init__(self):
        self.root = tk.Tk()
        self.ui = MainUI(self)
        self.manager = ModbusManager(self)
        self.manager.connect()

    def on_update_monitor(self, _list):
        self.root.after(0, self.ui.update_monitor, _list)

    def on_set_freq(self, value):
        self.manager.set_freq(value)

    def on_set_acc(self, value):
        self.manager.set_acc(value)

    def on_set_dec(self, value):
        self.manager.set_dec(value)

    def on_start_clicked(self):
        self.manager.motor_start()

    def on_stop_clicked(self):
        self.manager.motor_stop()

    def custom_check(self, addr):
        self.manager.custom_check(addr)
    
    def custom_write(self, addr, value):
        self.manager.custom_write(addr, value)

    def on_log(self, msg):
        self.ui.log(msg)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.mainloop()

    def quit(self):
        self.manager.disconnect()
        self.root.destroy()

if __name__ == '__main__':
    app = App()
    app.run()