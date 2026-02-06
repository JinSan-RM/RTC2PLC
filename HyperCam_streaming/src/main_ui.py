"""UI"""
import time
# import socket
# import threading
import traceback
from collections import deque
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk, scrolledtext
from PIL import Image, ImageTk
# import cv2

import numpy as np

from .config_util import (
    GUIDELINE_MAX_X, GUIDELINE_MIN_X, MAX_IMG_LINES, UI_UPDATE_INTERVAL
)


@dataclass
class ImageData:
    """이미지 버퍼 관련 모음"""
    max_lines: int
    line_buffer: deque = None
    canvas_image_id: int | None = None
    current_line: int = 0
    overlay_info: deque = None


@dataclass
class ChildrenWidget:
    """UI 업데이트용 자식 위젯 모음"""
    format_var: tk.StringVar = None
    blend_var: tk.StringVar = None
    canvas: tk.Canvas = None
    legend_frame: tk.Frame = None
    rgb_canvas: tk.Canvas = None
    stats_frame: ttk.LabelFrame = None
    log_text: scrolledtext.ScrolledText = None


@dataclass
class StatisticsData:
    """통계용 데이터 모음"""
    count_dict: dict = {}
    label_dict: dict = {}
    line_count: int = 0
    last_time: float = 0.0
    fps: float = 0.0


@dataclass
class UIConfig:
    """UI 설정값 모음"""
    last_update_time: float = 0.0
    update_interval: float = 0.0


# pylint: disable=broad-exception-caught
class MainUI:
    """UI"""
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.root.title("Vision Viewer")
        self.root.geometry("1600x900")

        # ✓ 수정: 이미지 버퍼를 deque로 변경 (FIFO)
        self.img_data = ImageData(max_lines=MAX_IMG_LINES) # 화면에 표시할 라인 수
        self.img_data.line_buffer = deque(maxlen=self.img_data.max_lines)  # 자동으로 오래된 라인 제거

        # 물체 감지 overlay
        self.img_data.overlay_info = deque()

        # UI 업데이트 빈도 제한
        self.ui_config = UIConfig()
        self.ui_config.update_interval = UI_UPDATE_INTERVAL  # ~30fps로 제한

        # 통계 변수
        self.statistics_data = StatisticsData()
        self.statistics_data.last_time = time.time()

        # UI 구성
        self.children_widget = ChildrenWidget()
        self._setup_ui()

    def _setup_ui(self):
        """UI 구성"""
        # # 데이터 형식 프레임
        # format_frame = ttk.LabelFrame(self.root, text="데이터 형식", padding=10)
        # format_frame.pack(fill=tk.X, padx=10, pady=5)

        # ttk.Label(format_frame, text="출력 형식:").grid(row=0, column=0, sticky=tk.W, padx=5)
        # self.children_widget.format_var = tk.StringVar(value="Raw")
        # # formats = [("Grayscale (1 byte/pixel)", "Raw"),
        # #            ("RGB (3 bytes/pixel)", "Rgb")]
        # formats = [("Raw", "Raw"),
        #            ("Reflectance", "Reflectance"),
        #            ("Absorbance", "Absorbance")]
        # for i, (text, value) in enumerate(formats):
        #     ttk.Radiobutton(
        #         format_frame,
        #         text=text, variable=self.children_widget.format_var,
        #         value=value, command=self._change_pixel_format
        #     ).grid(row=0, column=i+1, padx=5)

        # ttk.Label(format_frame, text="블렌드 적용:").grid(row=1, column=0, sticky=tk.W, padx=5)
        # self.children_widget.blend_var = tk.StringVar(value="Off")
        # for i in range(0, 2):
        #     val = "Off" if i == 0 else "On"
        #     ttk.Radiobutton(
        #         format_frame,
        #         text=val, variable=self.children_widget.format_var,
        #         value=val, command=self._set_blend
        #     ).grid(row=1, column=i+1, padx=5)

        # 2개의 스트림 프레임의 외부 프레임
        view_frame = ttk.Frame(self.root, relief=tk.FLAT, borderwidth=0)
        view_frame.pack(fill=tk.BOTH, padx=10, pady=5)

        # 초분광 스트림 프레임
        hyper_frame = ttk.LabelFrame(view_frame, text="초분광 카메라", padding=10)
        hyper_frame.pack(fill=tk.BOTH, side=tk.LEFT, expand=True, padx=(0, 5), pady=5)

        # Canvas for image display
        self.children_widget.canvas = tk.Canvas(hyper_frame, width=640, height=480, bg="black")
        self.children_widget.canvas.pack(side=tk.LEFT)

        # 분류 별 색상 표시
        self.children_widget.legend_frame = tk.Frame(hyper_frame, width=100, height=480)
        self.children_widget.legend_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # RGB 스트림 프레임
        rgb_frame = ttk.LabelFrame(view_frame, text="RGB 카메라", padding=10)
        rgb_frame.pack(fill=tk.BOTH, side=tk.LEFT, expand=True, padx=(5, 0), pady=5)

        # Canvas for image display
        self.rgb_canvas = tk.Canvas(rgb_frame, width=640, height=480, bg="black")
        self.rgb_canvas.pack()

        # 통계 프레임
        self.stats_frame = ttk.LabelFrame(self.root, text="통계", padding=10)
        self.stats_frame.pack(fill=tk.BOTH, padx=10, pady=5)

        # self.children_widget.stats_label = ttk.Label(self.stats_frame, text="FPS: 0.0")
        # self.children_widget.stats_label.pack()

        # 로그 프레임
        log_frame = ttk.LabelFrame(self.root, text="로그", padding=10)
        log_frame.pack(fill=tk.BOTH, padx=10, pady=5)

        self.children_widget.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, state=tk.DISABLED
        )
        self.children_widget.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message):
        """로그 메시지 추가"""
        self.children_widget.log_text.config(state=tk.NORMAL)
        self.children_widget.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.children_widget.log_text.see(tk.END)
        self.children_widget.log_text.config(state=tk.DISABLED)

    def _change_pixel_format(self):
        selected = self.children_widget.format_var.get()
        # 형식 변경 시 버퍼 초기화
        # self.line_buffer.clear()
        self.app.on_btn_clicked(selected)

    def _set_blend(self):
        selected = self.children_widget.blend_var.get()
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
            self.img_data.line_buffer.append(line_rgb)
            self.img_data.current_line = info["frame_number"]

            # 통계 업데이트
            # self.statistics_data.line_count += 1
            current_time = time.time()
            # if current_time - self.statistics_data.last_time >= 1.0:
            #     self.statistics_data.fps = \
            #     self.statistics_data.line_count / (current_time - self.statistics_data.last_time)
            #     self.statistics_data.last_time = current_time
            #     self.statistics_data.line_count = 0
            #     self.update_stats()

            # 이미지 업데이트 (30fps 제한)
            if current_time - self.ui_config.last_update_time >= self.ui_config.update_interval:
                self.update_image()
                self.update_overlay()
                self.ui_config.last_update_time = current_time

        except Exception as e:
            self.log(f"라인 처리 오류: {str(e)}")
            self.log(traceback.format_exc())

    # def update_stats(self):
    #     """통계 업데이트"""
    #     self.stats_label.config(
    #         text=f"수신된 라인: {self.img_data.current_line} | FPS: {self.statistics_data.fps:.1f}"
    #     )

    def update_image(self):
        """이미지 표시 업데이트 - 스크롤 효과"""
        try:
            if len(self.img_data.line_buffer) == 0:
                return

            # ✓ 수정: deque → numpy array (최신 라인이 아래로)
            img_data = np.array(list(self.img_data.line_buffer), dtype=np.uint8)

            # ✓ 수정: 라인이 480개 미만이면 위쪽을 검은색으로 채움
            if len(img_data) < self.img_data.max_lines:
                padding = np.zeros(
                    (self.img_data.max_lines - len(img_data), 640, 3),
                    dtype=np.uint8
                )
                img_data = np.vstack([padding, img_data])

            #가이드라인 영역을 빨간색으로 표시
            img_data[:, GUIDELINE_MIN_X:GUIDELINE_MAX_X, :] = [255, 0, 0]
            # PIL Image로 변환
            img = Image.fromarray(img_data)
            # 크기 조정
            img = img.resize((640, 480), Image.NEAREST) # pylint: disable=no-member

            photo = ImageTk.PhotoImage(img)

            # Canvas 업데이트
            if self.img_data.canvas_image_id is None:
                self.img_data.canvas_image_id = self.children_widget.canvas.create_image(
                    0, 0, anchor=tk.NW, image=photo
                )
            else:
                self.children_widget.canvas.itemconfig(self.img_data.canvas_image_id, image=photo)

            self.children_widget.canvas.image = photo  # 참조 유지

        except Exception as e:
            self.log(f"이미지 업데이트 오류: {str(e)}")
            self.log(traceback.format_exc())

    def update_overlay(self):
        """물체 감지 오버레이"""
        # 영상 출력 범위 지나간 물체 오버레이 정보 제거
        while self.img_data.overlay_info:
            info = self.img_data.overlay_info[0]
            if self.img_data.current_line > info["end_frame"] + self.img_data.max_lines:
                self.img_data.overlay_info.popleft()
            else:
                break

        self.children_widget.canvas.delete("overlay")
        for info in self.img_data.overlay_info:
            if self.img_data.current_line < info["start_frame"]:
                continue

            y0 = self.img_data.max_lines - (self.img_data.current_line - info["start_frame"])
            y1 = y0 + (info["end_frame"] - info["start_frame"] + 1)

            self.children_widget.canvas.create_rectangle(
                info["x0"], y0, info["x1"], y1,
                outline="white", width=2, tags="overlay", dash=(5, 5)
            )

    def set_legend(self, info_list):
        """재질 별 범례 설정"""
        for i, info in enumerate(info_list):
            name = info["Name"]
            color = info["Color"]

            # 초분광 범례 생성
            color_canvas = tk.Canvas(
                self.children_widget.legend_frame,
                width=20, height=20,
                bg=color, highlightthickness=0
            )
            color_canvas.pack(pady=2)
            class_label = tk.Label(
                self.children_widget.legend_frame,
                text=name, font=("Arial", 8),
                justify=tk.LEFT
            )
            class_label.pack(pady=1)

            # 통계 생성
            row = 0 if i % 2 == 0 else 1
            col = (i // 2) * 3
            color_lbl = tk.Label(
                self.stats_frame,
                bg=color, width=3
            )
            color_lbl.grid(
                row=row, column=col,
                padx=(0, 5), pady=2, sticky=tk.W
            )
            class_lbl = tk.Label(
                self.stats_frame,
                text=name, font=("Arial", 8)
            )
            class_lbl.grid(
                row=row, column=col+1,
                padx=(0, 10), pady=2, sticky=tk.W
            )
            count_lbl = tk.Label(
                self.stats_frame,
                text="0", font=("Arial", 8, "bold"),
                width=5, anchor=tk.E
            )
            count_lbl.grid(row=row, column=col+2, pady=2, sticky=tk.E)

            self.statistics_data.count_dict[name] = 0
            self.statistics_data.label_dict[name] = count_lbl

    def update_legend_count(self, name):
        """재질 별 카운트 업데이트"""
        self.statistics_data.count_dict[name] += 1
        self.statistics_data.label_dict[name].config(
            text=str(self.statistics_data.count_dict[name])
        )
