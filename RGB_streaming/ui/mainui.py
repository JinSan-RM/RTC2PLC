import cv2
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

from datetime import datetime
from typing import Optional

from cammanager.cammanager import CamManager

from common.config import APP_NAME, WINDOW_SIZE, FPS_VALUE, IMG_FORMAT, save_config

class MainUI:
    def __init__(self, app, root: Optional[tk.Tk], cammanager: Optional[CamManager]):
        self.app = app
        self.root = root
        self.cammanager = cammanager
        self.setup_ui()

    def setup_ui(self):
        self.root.title(APP_NAME)
        self.root.geometry(WINDOW_SIZE)
        self.root.resizable(False, False)
        
        self.delay = round(1000 / FPS_VALUE)
        self.current_frame = None

        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        cam_frame = ttk.Frame(main_frame)
        cam_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(cam_frame)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.btn_frame = ttk.Frame(main_frame)
        self.btn_frame.pack(side=tk.BOTTOM, fill=tk.X)
        capture_btn = ttk.Button(self.btn_frame, text="캡처", command=self.on_capture_btn)
        capture_btn.pack(side=tk.LEFT, padx=(0, 5))
        config_btn = ttk.Button(self.btn_frame, text="설정", command=self.open_config)
        config_btn.pack(side=tk.LEFT, padx=(0, 5))
        quit_btn = ttk.Button(self.btn_frame, text="종료", command=self.app.quit)
        quit_btn.pack(side=tk.RIGHT, padx=(0, 5))

        self.root.update()
        btn_frame_height = self.btn_frame.winfo_height()
        cam_frame.config(height=cam_frame.winfo_height() - btn_frame_height)

        self.update_cam_screen()

        self.root.bind("<Configure>", self.on_resize)

    def update_cam_screen(self):
        frame = self.cammanager.read_cam()
        if frame is not None:
            self.current_frame = frame
            
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame)
            image = self.resize_to_screen(image, canvas_width, canvas_height)
            self.photo = ImageTk.PhotoImage(image=image)
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

        self.root.after(self.delay, self.update_cam_screen)

    def resize_to_screen(self, image, target_width, target_height):
        origin_width, origin_height = image.size
        img_ratio = origin_width / origin_height
        target_ratio = target_width / target_height

        if img_ratio > target_ratio:
            # 이미지가 캔버스보다 넓은 경우
            new_width = target_width
            new_height = int(target_width / img_ratio)
        else:
            # 이미지가 캔버스보다 높은 경우
            new_height = target_height
            new_width = int(target_height * img_ratio)

        if new_width == 0 or new_height == 0:
            return image
        
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def on_resize(self, event):
        self.canvas.config(width=event.width, height=event.height - self.btn_frame.winfo_height())

    def on_capture_btn(self):
        if self.current_frame is None:
            messagebox.showerror("오류", "현재 재생되고 있는 프레임이 없습니다.")
            return
        
        self.cammanager.capture_img(self.current_frame, self.app.config_data["SAVE_FORMAT"])

    def open_config(self):
        popup = tk.Toplevel()
        popup.title("설정")
        popup.geometry("1280x720")

        dir_frame = ttk.Frame(popup, padding=10)
        dir_frame.pack(anchor=tk.NW)
        dir_label = ttk.Label(dir_frame, text="저장 위치: ")
        dir_label.pack(side=tk.LEFT)
        self.dir_text = ttk.Label(dir_frame, text=self.app.config_data["SAVE_PATH"])
        self.dir_text.pack(side=tk.LEFT)
        dir_btn = ttk.Button(dir_frame, text="변경", command=self.change_directory)
        dir_btn.pack(side=tk.RIGHT)

        format_frame = ttk.Frame(popup, padding=10)
        format_frame.pack(anchor=tk.SW)
        format_label = ttk.Label(format_frame, text="파일 형식: ")
        format_label.pack(side=tk.LEFT)
        keys = list(IMG_FORMAT.keys())
        self.format_select = tk.StringVar(format_frame, keys[0])
        tk.OptionMenu(format_frame, self.format_select, *keys).pack(side=tk.LEFT)

        btn_frame = ttk.Frame(popup, padding=10)
        btn_frame.pack(anchor=tk.SE)
        cancel_btn = ttk.Button(btn_frame, text="취소", command=popup.destroy)
        cancel_btn.pack(side=tk.RIGHT)
        save_btn = ttk.Button(btn_frame, text="저장", command=self.save_option)
        save_btn.pack(side=tk.RIGHT)

    def change_directory(self):
        save_path = filedialog.askdirectory(title="폴더 선택")
        if save_path:
            self.dir_text.config(text=save_path)

    def save_option(self):
        self.app.config_data["SAVE_PATH"] = self.dir_text
        self.app.config_data["SAVE_FORMAT"] = IMG_FORMAT[self.format_select]
        save_config(self.app.config_data)