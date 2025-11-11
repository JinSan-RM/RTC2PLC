import tkinter as tk
import numpy as np

from src.comm_manager import CommManager
from src.main_ui import MainUI

class App():
    def __init__(self):
        self.root = tk.Tk()
        self.ui = MainUI(self)
        self.manager = CommManager(self)
        self.manager.start()

    def on_btn_clicked(self, pixel_format):
        self.manager.change_pixel_format(pixel_format)

    def on_blend_btn_clicked(self, onoff):
        self.manager.set_visualization_blend(onoff)

    def on_pixel_line_data(self, info):
        """데이터를 UI로 전달 (메인 스레드에서 처리)"""
        self.root.after(0, self.ui.process_line, info)
    
    def on_obj_detected(self, info):
        self.ui.overlay_info.append(info)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.mainloop()

    def quit(self):
        self.manager.quit()
        self.manager.join(timeout=5)
        if self.manager.is_alive():
            print(f"comm manager thread did not terminate properly")
        self.root.destroy()

if __name__ == '__main__':
    app = App()
    app.run()