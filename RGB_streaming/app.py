import tkinter as tk

from ui.mainui import MainUI
from cammanager.cammanager import CamManager

from common.config import load_config, save_config

class App():
    def __init__(self):
        self.config_data = load_config()
        self.root = tk.Tk()
        self.cammanager = CamManager(self)
        self.ui = MainUI(self, self.root, self.cammanager)

    def run(self):
        self.root.mainloop()

    def quit(self):
        self.cammanager.quit()
        self.root.quit()
        save_config(self.config_data)

if __name__ == '__main__':
    app = App()
    app.run()