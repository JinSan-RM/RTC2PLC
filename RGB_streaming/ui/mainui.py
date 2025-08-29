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
        # 색상 팔레트
        colors = {
            'bg': '#f8f9fa',
            'primary': '#007bff', 
            'secondary': '#6c757d',
            'success': '#28a745',
            'danger': '#dc3545',
            'warning': '#ffc107',
            'card': '#ffffff',
            'dark': '#343a40'
        }
        
        # 앱 기본 설정
        self.root.title("🎥 RGB 카메라 뷰어")
        self.root.configure(bg=colors['bg'])
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        # 창 열리는 좌표 중앙으로 고정
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        app_x = (screen_width - WINDOW_WIDTH) // 2
        app_y = (screen_height - WINDOW_HEIGHT) // 2
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{app_x}+{app_y}")
        
        # 폰트 설정
        title_font = font.Font(family="Segoe UI", size=20, weight="bold")
        subtitle_font = font.Font(family="Segoe UI", size=14, weight="bold")
        btn_font = font.Font(family="Segoe UI", size=12, weight="bold")
        self.txt_font = font.Font(family="Segoe UI", size=11)

        # 스타일 설정
        style = ttk.Style()
        style.theme_use('clam')
        
        # 커스텀 스타일 정의
        style.configure("Primary.TButton",
                       background=colors['primary'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       padding=(15, 8),
                       font=btn_font)
        
        style.map("Primary.TButton",
                 background=[('active', '#0056b3')])
        
        style.configure("Success.TButton",
                       background=colors['success'],
                       foreground='white',
                       borderwidth=0,
                       padding=(15, 8),
                       font=btn_font)
        
        style.map("Success.TButton",
                 background=[('active', '#1e7e34')])
        
        style.configure("Danger.TButton",
                       background=colors['danger'],
                       foreground='white',
                       borderwidth=0,
                       padding=(15, 8),
                       font=btn_font)
        
        style.map("Danger.TButton",
                 background=[('active', '#c82333')])
        
        style.configure("Card.TFrame",
                       background=colors['card'],
                       relief='solid',
                       borderwidth=1,
                       lightcolor='#dee2e6',
                       darkcolor='#dee2e6')

        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 11))

        # 영상 프레임 설정
        self.delay = round(1000 / FPS_VALUE)
        self.current_frame = None

        # 메인 컨테이너
        main_container = tk.Frame(self.root, bg=colors['bg'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 헤더
        header_frame = tk.Frame(main_container, bg=colors['bg'])
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = tk.Label(
            header_frame,
            text="📹 RGB 카메라 뷰어",
            font=title_font,
            bg=colors['bg'],
            fg=colors['primary']
        )
        title_label.pack(side=tk.LEFT)
        
        status_frame = tk.Frame(header_frame, bg=colors['bg'])
        status_frame.pack(side=tk.RIGHT)
        
        status_label = tk.Label(
            status_frame,
            text="🟢 카메라 연결됨",
            font=self.txt_font,
            bg=colors['bg'],
            fg=colors['success']
        )
        status_label.pack()

        # 콘텐츠 영역
        content_frame = tk.Frame(main_container, bg=colors['bg'])
        content_frame.pack(fill=tk.BOTH, expand=True)

        # 왼쪽: 카메라 뷰 카드
        cam_card = ttk.Frame(content_frame, style="Card.TFrame", padding=15)
        cam_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        cam_header = tk.Label(
            cam_card,
            text="📹 실시간 미리보기",
            font=subtitle_font,
            bg=colors['card'],
            fg=colors['secondary']
        )
        cam_header.pack(pady=(0, 10))
        
        self.canvas = tk.Canvas(
            cam_card,
            bg='#2c3e50',
            highlightthickness=2,
            highlightcolor=colors['primary'],
            relief='flat'
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 오른쪽: 파일 관리 카드
        file_card = ttk.Frame(content_frame, style="Card.TFrame", padding=15)
        file_card.pack(side=tk.RIGHT, fill=tk.Y, ipadx=15)  # ipadx 증가
        
        file_header = tk.Label(
            file_card,
            text="📁 저장된 이미지",
            font=subtitle_font,
            bg=colors['card'],
            fg=colors['secondary']
        )
        file_header.pack(pady=(0, 10))
        
        # 썸네일 영역
        thumbnail_container = tk.Frame(file_card, bg=colors['card'])
        thumbnail_container.pack(fill=tk.X, pady=(0, 15))
        
        self.canvas_thumbnail = tk.Canvas(
            thumbnail_container,
            height=220,  # 높이 증가
            bg='#34495e',
            highlightthickness=1,
            highlightcolor='#95a5a6',
            relief='flat'
        )
        self.canvas_thumbnail.pack(fill=tk.X, padx=5, pady=5)  # 패딩 추가
        self.thumbnail_id = None
        
        # 파일 리스트
        listbox_container = tk.Frame(file_card, bg=colors['card'])
        listbox_container.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        scrollbar = ttk.Scrollbar(listbox_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.listbox = tk.Listbox(
            listbox_container,
            width=25,
            height=12,
            font=self.txt_font,
            yscrollcommand=scrollbar.set,
            bg='#f8f9fa',
            fg='#495057',
            selectbackground=colors['primary'],
            selectforeground='white',
            relief='flat',
            borderwidth=1,
            highlightthickness=1,
            highlightcolor=colors['primary']
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.show_thumbnail)
        scrollbar.config(command=self.listbox.yview)
        
        # 삭제 버튼
        btn_delete = ttk.Button(
            file_card,
            text="🗑️ 삭제",
            style="Danger.TButton",
            command=self.delete_selected
        )
        btn_delete.pack(fill=tk.X)

        # 초기 파일 리스트 업데이트
        self.update_file_list()
        self.listbox.selection_set(tk.END)
        self.listbox.see(tk.END)
        self.show_thumbnail(None)

        # 하단 버튼 영역
        self.btn_frame = tk.Frame(main_container, bg=colors['bg'])
        self.btn_frame.pack(fill=tk.X, pady=(20, 0))
        
        # 왼쪽 버튼들
        left_buttons = tk.Frame(self.btn_frame, bg=colors['bg'])
        left_buttons.pack(side=tk.LEFT)
        
        capture_btn = ttk.Button(
            left_buttons,
            text="📸 캡처",
            style="Success.TButton",
            command=self.on_capture_btn
        )
        capture_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        config_btn = ttk.Button(
            left_buttons,
            text="⚙️ 설정",
            style="Primary.TButton",
            command=self.open_config
        )
        config_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 오른쪽 버튼들
        right_buttons = tk.Frame(self.btn_frame, bg=colors['bg'])
        right_buttons.pack(side=tk.RIGHT)
        
        quit_btn = ttk.Button(
            right_buttons,
            text="❌ 종료",
            style="Danger.TButton",
            command=self.app.quit
        )
        quit_btn.pack(side=tk.RIGHT, padx=(0, 5))

        # 초기화
        self.root.update()  # UI 업데이트를 먼저 수행
        self.root.after(100, self.update_cam_screen)  # 100ms 후에 카메라 업데이트 시작
        self.root.bind("<Configure>", self.on_resize)

    def update_cam_screen(self):
        frame, frame2 = self.cammanager.read_cam()
        if frame is not None:
            self.current_frame = frame
            
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # 캔버스 크기가 유효하지 않은 경우 기본값 사용
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = 800  # 기본 너비
                canvas_height = 600  # 기본 높이

            image = Image.fromarray(frame)
            image = resize_image_proportional(image, canvas_width, canvas_height)
            self.photo = ImageTk.PhotoImage(image=image)
            self.canvas.delete("all")  # 이전 이미지 삭제
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        else:
            print("[WARN] Failed to read frame from camera")
            # Optionally show a warning to the user after repeated failures
            if not hasattr(self, 'frame_failure_count'):
                self.frame_failure_count = 0
            self.frame_failure_count += 1
            if self.frame_failure_count > 10:  # Show warning after 10 failures
                messagebox.showwarning("Camera Warning", "Failed to capture camera frames. Check camera connection and settings.")
                self.frame_failure_count = 0  # Reset counter

        self.root.after(self.delay, self.update_cam_screen)

    def on_resize(self, event):
        # 리사이즈 이벤트는 기존과 동일하게 유지
        pass

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
        # 색상 팔레트 (설정 창용)
        colors = {
            'bg': '#f8f9fa',
            'primary': '#007bff',
            'card': '#ffffff'
        }
        
        popup = tk.Toplevel(self.root)
        popup.title("⚙️ 설정")
        popup.configure(bg=colors['bg'])
        popup.resizable(False, False)

        self.save_path = self.app.config_data["SAVE_PATH"]
        self.format_select = self.app.config_data["SAVE_FORMAT"]

        # 메인 컨테이너
        main_popup_frame = tk.Frame(popup, bg=colors['bg'])
        main_popup_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 제목
        title_label = tk.Label(
            main_popup_frame,
            text="⚙️ 카메라 설정",
            font=font.Font(family="Segoe UI", size=16, weight="bold"),
            bg=colors['bg'],
            fg=colors['primary']
        )
        title_label.pack(pady=(0, 20))

        # 저장 위치 설정 카드
        dir_card = tk.Frame(main_popup_frame, bg=colors['card'], relief='solid', bd=1)
        dir_card.pack(fill=tk.X, pady=(0, 15))
        
        dir_frame = tk.Frame(dir_card, bg=colors['card'])
        dir_frame.pack(fill=tk.X, padx=15, pady=15)
        
        dir_label = tk.Label(
            dir_frame, 
            text="📁 저장 위치:", 
            font=self.txt_font,
            bg=colors['card']
        )
        dir_label.pack(anchor=tk.W, pady=(0, 5))
        
        dir_display_frame = tk.Frame(dir_frame, bg=colors['card'])
        dir_display_frame.pack(fill=tk.X)
        
        self.dir_text = tk.Label(
            dir_display_frame,
            text=smart_path_display(self.save_path, 40),
            font=self.txt_font,
            bg='#f8f9fa',
            fg='#495057',
            relief='solid',
            bd=1,
            padx=10,
            pady=5
        )
        self.dir_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        dir_btn = ttk.Button(
            dir_display_frame,
            text="📂 변경",
            style="Primary.TButton",
            command=self.change_directory
        )
        dir_btn.pack(side=tk.RIGHT)

        # 파일 형식 설정 카드
        format_card = tk.Frame(main_popup_frame, bg=colors['card'], relief='solid', bd=1)
        format_card.pack(fill=tk.X, pady=(0, 20))
        
        format_frame = tk.Frame(format_card, bg=colors['card'])
        format_frame.pack(fill=tk.X, padx=15, pady=15)
        
        format_label_title = tk.Label(
            format_frame,
            text="🖼️ 파일 형식:",
            font=self.txt_font,
            bg=colors['card']
        )
        format_label_title.pack(anchor=tk.W, pady=(0, 5))
        
        format_option_frame = tk.Frame(format_frame, bg=colors['card'])
        format_option_frame.pack(fill=tk.X)
        
        keys = list(IMG_FORMAT.keys())
        format_option = ttk.Combobox(
            format_option_frame,
            values=keys,
            state="readonly",
            font=("Segoe UI", 11),
            width=20
        )
        format_option.set(self.format_select)
        format_option.pack(side=tk.LEFT, padx=(0, 10))

        format_label = tk.Label(
            format_option_frame,
            text=f"현재: {self.format_select}",
            font=self.txt_font,
            bg=colors['card'],
            fg='#6c757d'
        )
        format_label.pack(side=tk.LEFT)

        def on_format_select(event):
            self.format_select = format_option.get()
            format_label.config(text=f"현재: {self.format_select}")

        format_option.bind("<<ComboboxSelected>>", on_format_select)

        # 버튼 영역
        btn_frame = tk.Frame(main_popup_frame, bg=colors['bg'])
        btn_frame.pack(fill=tk.X)
        
        cancel_btn = ttk.Button(
            btn_frame,
            text="❌ 취소",
            style="Danger.TButton",
            command=popup.destroy
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        save_btn = ttk.Button(
            btn_frame,
            text="💾 저장",
            style="Success.TButton",
            command=lambda: self.save_option(popup)
        )
        save_btn.pack(side=tk.RIGHT)

        # 창 크기 조정 및 중앙 배치
        popup.update_idletasks()
        popup_width = max(500, popup.winfo_reqwidth())
        popup_height = popup.winfo_reqheight()
        
        # 부모 창 중앙에 배치
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        
        x = parent_x + (parent_width - popup_width) // 2
        y = parent_y + (parent_height - popup_height) // 2
        
        popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")

    def change_directory(self):
        get_dir = filedialog.askdirectory(title="폴더 선택", initialdir=self.save_path)
        if get_dir:
            self.save_path = get_dir
            self.dir_text.config(text=smart_path_display(self.save_path, 40))

    def save_option(self, popup):
        self.app.config_data["SAVE_PATH"] = self.save_path
        self.app.config_data["SAVE_FORMAT"] = IMG_FORMAT[self.format_select]
        save_config(self.app.config_data)
        popup.destroy()
        messagebox.showinfo("설정 저장", "설정이 성공적으로 저장되었습니다!")

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
                
                # 캔버스 실제 크기 가져오기
                self.canvas_thumbnail.update_idletasks()
                canvas_width = self.canvas_thumbnail.winfo_width()
                canvas_height = self.canvas_thumbnail.winfo_height()
                
                # 캔버스 크기가 유효하지 않은 경우 기본값 사용
                if canvas_width <= 1:
                    canvas_width = 300
                if canvas_height <= 1:
                    canvas_height = 220
                
                # 여백을 고려한 실제 사용 가능한 크기
                usable_width = canvas_width - 10  # 좌우 여백 5px씩
                usable_height = canvas_height - 10  # 상하 여백 5px씩
                
                image = resize_image_proportional(image, usable_width, usable_height)
                self.photo_thumbnail = ImageTk.PhotoImage(image=image)

                img_width, img_height = image.size
                x = (canvas_width - img_width) // 2
                y = (canvas_height - img_height) // 2

                self.thumbnail_id = self.canvas_thumbnail.create_image(x, y, image=self.photo_thumbnail, anchor=tk.NW)
            except Exception as e:
                messagebox.showerror("Error", f"이미지를 불러올 수 없습니다: [{e}]")
        else:
            if self.thumbnail_id:
                self.canvas_thumbnail.delete(self.thumbnail_id)
            # 캔버스 크기 다시 확인
            self.canvas_thumbnail.update_idletasks()
            canvas_width = self.canvas_thumbnail.winfo_width()
            canvas_height = self.canvas_thumbnail.winfo_height()
            if canvas_width <= 1:
                canvas_width = 300
            if canvas_height <= 1:
                canvas_height = 220
            # 빈 썸네일 표시 (여백 고려)
            self.canvas_thumbnail.create_rectangle(5, 5, canvas_width - 5, canvas_height - 5, outline="gray", width=1, fill="#2c3e50")

    def delete_selected(self):
        selection = self.listbox.curselection()
        if selection:
            filename = self.listbox.get(selection[0])
            filepath = Path(self.app.config_data["SAVE_PATH"]).joinpath(filename)
            if messagebox.askyesno("파일 삭제 확인", f"🗑️ [{filename}] 파일을 삭제하시겠습니까?"):
                try:
                    os.remove(filepath)
                    self.update_file_list()
                    if self.thumbnail_id:
                        self.canvas_thumbnail.delete(self.thumbnail_id)
                    self.show_thumbnail(None)
                    messagebox.showinfo("삭제 완료", f"✅ [{filename}] 파일을 삭제했습니다.")
                except Exception as e:
                    messagebox.showerror("삭제 오류", f"❌ 파일을 삭제할 수 없습니다: [{e}]")