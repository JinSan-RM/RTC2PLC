import tkinter as tk
from tkinter import ttk, scrolledtext
import socket
import threading
import cv2
from PIL import Image, ImageTk
import numpy as np
import time

from .config_util import GUIDELINE_MAX_X, GUIDELINE_MIN_X

class MainUI:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.root.title("Vision Viewer")
        self.root.geometry("1600x900")

        # 연결 상태
        self.connected = False
        self.running = False
        self.sock = None
        self.receive_thread = None

        # ✓ 수정: 이미지 버퍼를 deque로 변경 (FIFO)
        from collections import deque
        self.max_lines = 480  # 화면에 표시할 라인 수
        self.line_buffer = deque(maxlen=self.max_lines)  # 자동으로 오래된 라인 제거
        self.canvas_image_id = None
        self.current_line = 0
        
        # UI 업데이트 빈도 제한
        self.last_update_time = 0
        self.update_interval = 0.033  # ~30fps로 제한

        # 물체 감지 overlay
        self.overlay_info = deque()

        # 통계용
        self.count_dict = {}
        self.label_dict = {}

        # UI 구성
        self.setup_ui()

    def setup_ui(self):
        # # 데이터 형식 프레임
        # format_frame = ttk.LabelFrame(self.root, text="데이터 형식", padding=10)
        # format_frame.pack(fill=tk.X, padx=10, pady=5)

        # ttk.Label(format_frame, text="출력 형식:").grid(row=0, column=0, sticky=tk.W, padx=5)
        # self.format_var = tk.StringVar(value="Raw")
        # # formats = [("Grayscale (1 byte/pixel)", "Raw"),
        # #            ("RGB (3 bytes/pixel)", "Rgb")]
        # formats = [("Raw", "Raw"),
        #            ("Reflectance", "Reflectance"),
        #            ("Absorbance", "Absorbance")]
        # for i, (text, value) in enumerate(formats):
        #     ttk.Radiobutton(format_frame, text=text, variable=self.format_var, 
        #                   value=value, command=self.change_pixel_format).grid(row=0, column=i+1, padx=5)
        
        # ttk.Label(format_frame, text="블렌드 적용:").grid(row=1, column=0, sticky=tk.W, padx=5)
        # self.blend_var = tk.StringVar(value="Off")
        # for i in range(0, 2):
        #     val = "Off" if i == 0 else "On"
        #     ttk.Radiobutton(format_frame, text=val, variable=self.format_var, 
        #                   value=val, command=self.set_blend).grid(row=1, column=i+1, padx=5)

        # 2개의 스트림 프레임의 외부 프레임
        view_frame = ttk.Frame(self.root, relief=tk.FLAT, borderwidth=0)
        view_frame.pack(fill=tk.BOTH, padx=10, pady=5)

        # 초분광 스트림 프레임
        hyper_frame = ttk.LabelFrame(view_frame, text="초분광 카메라", padding=10)
        hyper_frame.pack(fill=tk.BOTH, side=tk.LEFT, expand=True, padx=(0, 5), pady=5)

        # Canvas for image display
        self.canvas = tk.Canvas(hyper_frame, width=640, height=480, bg="black")
        self.canvas.pack(side=tk.LEFT)

        # 분류 별 색상 표시
        self.legend_frame = tk.Frame(hyper_frame, width=100, height=480)
        self.legend_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # RGB 스트림 프레임
        rgb_frame = ttk.LabelFrame(view_frame, text="RGB 카메라", padding=10)
        rgb_frame.pack(fill=tk.BOTH, side=tk.LEFT, expand=True, padx=(5, 0), pady=5)

        # Canvas for image display
        self.rgb_canvas = tk.Canvas(rgb_frame, width=640, height=480, bg="black")
        self.rgb_canvas.pack()

        # 통계 프레임
        self.stats_frame = ttk.LabelFrame(self.root, text="통계", padding=10)
        self.stats_frame.pack(fill=tk.BOTH, padx=10, pady=5)

        # self.stats_label = ttk.Label(self.stats_frame, text="FPS: 0.0")
        # self.stats_label.pack()

        # 로그 프레임
        log_frame = ttk.LabelFrame(self.root, text="로그", padding=10)
        log_frame.pack(fill=tk.BOTH, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 통계 변수
        self.line_count = 0
        self.last_time = time.time()
        self.fps = 0.0

    def log(self, message):
        """로그 메시지 추가"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def change_pixel_format(self):
        selected = self.format_var.get()
        # 형식 변경 시 버퍼 초기화
        # self.line_buffer.clear()
        self.app.on_btn_clicked(selected)
    
    def set_blend(self):
        selected = self.blend_var.get()
        onoff = True if selected == "On" else False
        self.app.on_blend_btn_clicked(onoff)

    def process_line(self, info):
        """라인 데이터 처리"""
        # pixel_format = self.format_var.get()
        line_data = info["data_body"]

        try:
            line_array = np.frombuffer(line_data, dtype=np.uint8)
            if len(line_array) == 640:
                # ✓ 수정: Grayscale 640픽셀
                # ✓ 수정: 색상 반전 (검정↔흰색) + 밝기 증폭
                line_array = 255 - (line_array * 36)  # 0→255, 7→3 (반전 후 증폭)
                line_array = np.clip(line_array, 0, 255).astype(np.uint8)
                # 이 줄만 쓰면 픽셀 변환 그대로
                line_rgb = np.stack([line_array, line_array, line_array], axis=1)
            elif len(line_array) == 640*3:
                # RGB 640*3픽셀
                line_rgb = line_array.reshape(640, 3)
            else:
                self.log(f"⚠️ 잘못된 라인 크기: {len(line_array)} (예상: 640 또는 1920)")
                return

            # ✓ 수정: deque에 라인 추가 (자동으로 오래된 라인 제거)
            self.line_buffer.append(line_rgb)
            self.current_line = info["frame_number"]

            # 통계 업데이트
            # self.line_count += 1
            current_time = time.time()
            # if current_time - self.last_time >= 1.0:
            #     self.fps = self.line_count / (current_time - self.last_time)
            #     self.last_time = current_time
            #     self.line_count = 0
            #     self.update_stats()

            # 이미지 업데이트 (30fps 제한)
            if current_time - self.last_update_time >= self.update_interval:
                self.update_image()
                self.update_overlay()
                self.last_update_time = current_time

        except Exception as e:
            import traceback
            self.log(f"라인 처리 오류: {str(e)}")
            self.log(traceback.format_exc())

    # def update_stats(self):
    #     """통계 업데이트"""
    #     self.stats_label.config(text=f"수신된 라인: {self.current_line} | FPS: {self.fps:.1f}")

    def update_image(self):
        """이미지 표시 업데이트 - 스크롤 효과"""
        try:
            if len(self.line_buffer) == 0:
                return

            # ✓ 수정: deque → numpy array (최신 라인이 아래로)
            img_data = np.array(list(self.line_buffer), dtype=np.uint8)
            
            # ✓ 수정: 라인이 480개 미만이면 위쪽을 검은색으로 채움
            if len(img_data) < self.max_lines:
                padding = np.zeros((self.max_lines - len(img_data), 640, 3), dtype=np.uint8)
                img_data = np.vstack([padding, img_data])
            
            #가이드라인 영역을 빨간색으로 표시
            img_data[:, GUIDELINE_MIN_X:GUIDELINE_MAX_X, :] = [255, 0, 0]
            # PIL Image로 변환
            img = Image.fromarray(img_data)
            
            # 크기 조정
            img = img.resize((640, 480), Image.NEAREST)
            
            photo = ImageTk.PhotoImage(img)
            
            # Canvas 업데이트
            if self.canvas_image_id is None:
                self.canvas_image_id = self.canvas.create_image(
                    0, 0, anchor=tk.NW, image=photo
                )
            else:
                self.canvas.itemconfig(self.canvas_image_id, image=photo)
                
            self.canvas.image = photo  # 참조 유지

        except Exception as e:
            import traceback
            self.log(f"이미지 업데이트 오류: {str(e)}")
            self.log(traceback.format_exc())

    def update_overlay(self):
        # 영상 출력 범위 지나간 물체 오버레이 정보 제거
        while self.overlay_info:
            info = self.overlay_info[0]
            if self.current_line > info["end_frame"] + self.max_lines:
                self.overlay_info.popleft()
            else:
                break

        self.canvas.delete("overlay")
        for info in self.overlay_info:
            if self.current_line < info["start_frame"]:
                continue

            y0 = self.max_lines - (self.current_line - info["start_frame"])
            y1 = y0 + (info["end_frame"] - info["start_frame"] + 1)

            self.canvas.create_rectangle(
                info["x0"], y0, info["x1"], y1,
                outline="white", width=2, tags="overlay", dash=(5, 5)
            )

    def set_legend(self, info_list):
        for i, info in enumerate(info_list):
            name = info["Name"]
            color = info["Color"]
            
            # 초분광 범례 생성
            color_canvas = tk.Canvas(self.legend_frame, width=20, height=20, bg=color, highlightthickness=0)
            color_canvas.pack(pady=2)
            class_label = tk.Label(self.legend_frame, text=name, font=("Arial", 8), justify=tk.LEFT)
            class_label.pack(pady=1)

            # 통계 생성
            row = 0 if i % 2 == 0 else 1
            col = (i // 2) * 3
            color_lbl = tk.Label(self.stats_frame, bg=color, width=3)
            color_lbl.grid(row=row, column=col, padx=(0, 5), pady=2, sticky=tk.W)
            class_lbl = tk.Label(self.stats_frame, text=name, font=("Arial", 8))
            class_lbl.grid(row=row, column=col+1, padx=(0, 10), pady=2, sticky=tk.W)
            count_lbl = tk.Label(self.stats_frame, text="0", font=("Arial", 8, "bold"), width=5, anchor=tk.E)
            count_lbl.grid(row=row, column=col+2, pady=2, sticky=tk.E)

            self.count_dict[name] = 0
            self.label_dict[name] = count_lbl

    def update_legend_count(self, name):
        self.count_dict[name] += 1
        self.label_dict[name].config(text=str(self.count_dict[name]))

        self.log(self.count_dict)