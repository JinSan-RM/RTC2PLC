"""
메인 앱
"""
import tkinter as tk
# import numpy as np

from src.comm_manager import CommManager
from src.main_ui import MainUI

class App():
    """메인 앱 클래스"""
    def __init__(self):
        self.root = tk.Tk()
        self.ui = MainUI(self)
        self.manager = CommManager(self)
        self.manager.start()

    def on_btn_clicked(self, pixel_format):
        """픽셀 형식 버튼 클릭"""
        self.manager.change_pixel_format(pixel_format)

    def on_blend_btn_clicked(self, onoff):
        """블렌드 버튼 클릭"""
        self.manager.set_visualization_blend(onoff)

    def on_pixel_line_data(self, info):
        """데이터를 UI로 전달 (메인 스레드에서 처리)"""
        self.root.after(0, self.ui.process_line, info)

    def on_obj_detected(self, info):
        """제품 감지 시 호출"""
        self.ui.overlay_info.append(info)

    def run(self):
        """메인 루프 실행"""
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.mainloop()

    def quit(self):
        """앱 종료"""
        self.manager.quit()
        self.manager.join(timeout=5)
        if self.manager.is_alive():
            print("comm manager thread did not terminate properly")
        self.root.destroy()

if __name__ == '__main__':
    app = App()
    app.run()
