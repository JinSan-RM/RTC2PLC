import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font
from PIL import Image, ImageTk

import os
from pathlib import Path
from typing import Optional

from cammanager.cammanager import CamManager
from common.config import APP_NAME, WINDOW_WIDTH, WINDOW_HEIGHT, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT, FPS_VALUE, IMG_FORMAT, save_config
from common.utils import smart_path_display, resize_image_proportional

class MainUI:
    def __init__(self, app, root: Optional[tk.Tk], cammanager: Optional[CamManager]):
        self.app = app
        self.root = root
        self.cammanager = cammanager
        self.setup_ui()

    def setup_ui(self):
        # 앱 기본 설정
        self.root.title(APP_NAME)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        # 창 열리는 좌표 중앙으로 고정
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        app_x = (screen_width - WINDOW_WIDTH) // 2
        app_y = (screen_height - WINDOW_HEIGHT) // 2
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{app_x}+{app_y}")
        
        # 각 위젯에서 사용할 스타일 등 설정
        btn_style = ttk.Style()
        btn_style.configure("Btn.TButton", padding=10, font=("System", 20, "bold"))

        self.txt_font = font.Font(family="System", size=16)

        self.root.option_add("*TCombobox*Listbox.font", ("System", 16))

        # 영상 프레임 설정
        self.delay = round(1000 / FPS_VALUE)
        self.current_frame = None

        # 위젯 배치
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        cam_frame = ttk.Frame(main_frame)
        cam_frame.place(anchor=tk.NW, relwidth=0.75, relheight=0.85)
        self.canvas = tk.Canvas(cam_frame)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.thumbnail_id = None
        mgmt_frame = ttk.Frame(main_frame)
        mgmt_frame.place(relx=0.75, relwidth=0.25, relheight=0.85)
        self.canvas_thumbnail = tk.Canvas(mgmt_frame)
        self.canvas_thumbnail.pack(fill=tk.BOTH, expand=True)
        listbox_frame = ttk.Frame(mgmt_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox = tk.Listbox(listbox_frame, width=30, height=15, font=self.txt_font, yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.show_thumbnail)
        scrollbar.config(command=self.listbox.yview)
        btn_delete = ttk.Button(mgmt_frame, text="삭제", style="Btn.TButton", command=self.delete_selected)
        btn_delete.pack(pady=5)
        self.update_file_list()

        self.listbox.selection_set(tk.END)
        self.listbox.see(tk.END)
        self.show_thumbnail(None)

        self.btn_frame = ttk.Frame(main_frame)
        self.btn_frame.pack(side=tk.BOTTOM, fill=tk.X)
        capture_btn = ttk.Button(self.btn_frame, text="캡처", style="Btn.TButton", command=self.on_capture_btn)
        capture_btn.pack(side=tk.LEFT, padx=(0, 5))
        config_btn = ttk.Button(self.btn_frame, text="설정", style="Btn.TButton", command=self.open_config)
        config_btn.pack(side=tk.LEFT, padx=(0, 5))
        quit_btn = ttk.Button(self.btn_frame, text="종료", style="Btn.TButton", command=self.app.quit)
        quit_btn.pack(side=tk.RIGHT, padx=(0, 5))

        self.root.update()
        btn_frame_height = self.btn_frame.winfo_height()
        cam_frame.config(height=cam_frame.winfo_height() - btn_frame_height)

        self.update_cam_screen()

        self.root.bind("<Configure>", self.on_resize)

    def update_cam_screen(self):
        frame, frame2 = self.cammanager.read_cam()
        if frame is not None:
            self.current_frame = frame
            
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            image = Image.fromarray(frame2)
            image = resize_image_proportional(image, canvas_width, canvas_height)
            self.photo = ImageTk.PhotoImage(image=image)
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

        self.root.after(self.delay, self.update_cam_screen)

    def on_resize(self, event):
        self.canvas.config(width=event.width, height=event.height - self.btn_frame.winfo_height())

    def on_capture_btn(self):
        if self.current_frame is None:
            messagebox.showerror("오류", "현재 재생되고 있는 프레임이 없습니다.")
            return
        
        ret, e = self.cammanager.capture_img(self.current_frame, self.app.config_data["SAVE_FORMAT"])
        if ret:
            messagebox.showinfo("Success", f"[{e}] 파일을 생성했습니다.")
            self.update_file_list()
        else:
            messagebox.showerror("Error", f"파일을 생성할 수 없습니다: [{e}]")

    def open_config(self):
        popup = tk.Toplevel(self.root)
        popup.title("설정")

        self.save_path = self.app.config_data["SAVE_PATH"]
        self.format_select = self.app.config_data["SAVE_FORMAT"]

        dir_frame = ttk.Frame(popup, padding=10)
        dir_frame.pack(anchor=tk.NW)
        dir_label = ttk.Label(dir_frame, text="저장 위치: ", font=self.txt_font)
        dir_label.pack(side=tk.LEFT)
        self.dir_text = ttk.Label(dir_frame, text=smart_path_display(self.save_path, 40), font=self.txt_font)
        self.dir_text.pack(side=tk.LEFT)
        dir_btn = ttk.Button(dir_frame, text="변경", style="Btn.TButton", command=self.change_directory)
        dir_btn.pack(side=tk.RIGHT)

        format_frame = ttk.Frame(popup, padding=10)
        format_frame.pack(anchor=tk.SW)
        keys = list(IMG_FORMAT.keys())
        format_option = ttk.Combobox(format_frame, values=keys, state="readonly")
        format_option.set(self.format_select)
        format_option.config(font=("System", 16))
        format_option.pack(side=tk.LEFT)

        def on_format_select(event):
            self.format_select = format_option.get()
            format_label.config(text=f"파일 형식: {self.format_select}")

        format_option.bind("<<ComboboxSelected>>", on_format_select)
        format_label = ttk.Label(format_frame, text=f"파일 형식: {self.format_select}", font=self.txt_font)
        format_label.pack(side=tk.LEFT)

        btn_frame = ttk.Frame(popup, padding=10)
        btn_frame.pack(anchor=tk.SE)
        cancel_btn = ttk.Button(btn_frame, text="취소", style="Btn.TButton", command=popup.destroy)
        cancel_btn.pack(side=tk.RIGHT)
        save_btn = ttk.Button(btn_frame, text="저장", style="Btn.TButton", command=self.save_option)
        save_btn.pack(side=tk.RIGHT)

        popup.update_idletasks()

        popup_width = popup.winfo_reqwidth()
        popup_height = popup.winfo_reqheight()
        popup.geometry(f"{popup_width}x{popup_height}")

    def change_directory(self):
        get_dir = filedialog.askdirectory(title="폴더 선택", initialdir=self.save_path)
        if get_dir:
            self.save_path = get_dir
            self.dir_text.config(text=smart_path_display(self.save_path, 40))

    def save_option(self):
        self.app.config_data["SAVE_PATH"] = self.dir_text
        self.app.config_data["SAVE_FORMAT"] = IMG_FORMAT[self.format_select]
        save_config(self.app.config_data)

    def update_file_list(self):
        self.listbox.delete(0, tk.END)
        for file in os.listdir(self.app.config_data["SAVE_PATH"]):
            if file.endswith((".png", ".jpg", ".jpeg")):
                self.listbox.insert(tk.END, file)

    def show_thumbnail(self, event):
        selection = self.listbox.curselection()
        if selection:
            filename = self.listbox.get(selection[0])
            filepath = Path(self.app.config_data["SAVE_PATH"]).joinpath(filename)
            try:
                if self.thumbnail_id:
                    self.canvas_thumbnail.delete(self.thumbnail_id)

                image = Image.open(filepath)
                image = resize_image_proportional(image, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
                self.photo_thumbnail = ImageTk.PhotoImage(image=image)

                canvas_width = self.canvas_thumbnail.winfo_width()
                canvas_height = self.canvas_thumbnail.winfo_height()
                if canvas_width <= 1 or canvas_height <= 1:
                    canvas_width = THUMBNAIL_WIDTH
                    canvas_height = THUMBNAIL_HEIGHT

                img_width, img_height = image.size
                x = (canvas_width - img_width) // 2
                y = (canvas_height - img_height) // 2

                self.thumbnail_id = self.canvas_thumbnail.create_image(x, y, image=self.photo_thumbnail, anchor=tk.NW)
            except Exception as e:
                messagebox.showerror("Error", f"이미지를 불러올 수 없습니다: [{e}]")
        else:
            self.canvas_thumbnail.create_rectangle(2, 2, THUMBNAIL_WIDTH - 8, THUMBNAIL_HEIGHT - 3, outline="black", width=1)

    def delete_selected(self):
        selection = self.listbox.curselection()
        if selection:
            filename = self.listbox.get(selection[0])
            filepath = Path(self.app.config_data["SAVE_PATH"]).joinpath(filename)
            if messagebox.askyesno("Confirm", f"[{filename}] 파일을 삭제하시겠습니까?"):
                try:
                    os.remove(filepath)
                    self.update_file_list()
                    self.canvas_thumbnail.delete(self.thumbnail_id)
                    self.show_thumbnail(None)
                    messagebox.showinfo("Success", f"[{filename}] 파일을 삭제했습니다.")
                except Exception as e:
                    messagebox.showerror("Error", f"파일을 삭제할 수 없습니다: [{e}]")