import tkinter as tk
from tkinter import messagebox

from source.mainui import MainUI
from source.comm_manager import CommManager

class App():
    def __init__(self):
        self.root = tk.Tk()
        self.comm_manager = CommManager(self)
        self.ui = MainUI(self, self.root, None)

    def run(self):
        self.root.mainloop()

    def quit(self):
        self.comm_manager.stop()
        self.root.quit()

if __name__ == '__main__':
    app = App()
    app.run()