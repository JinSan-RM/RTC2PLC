import tkinter as tk

from src.main_ui import MainUI
from src.comm_manager import ModbusManager

class App():
    def __init__(self):
        self.root = tk.Tk()
        self.ui = MainUI(self)
        self.manager = ModbusManager(self)
        self.manager.connect()

    def on_btn_clicked(self):
        self.manager.check_inverter_model()

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