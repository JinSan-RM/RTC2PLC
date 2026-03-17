"""
모니터링 페이지 - 카메라 스트림
"""
import traceback
import sys
import time

from collections import deque
from dataclasses import dataclass

import numpy as np
import cv2
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QComboBox,
    QLineEdit, QSizePolicy,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem
)
from PySide6.QtCore import Qt, QTimer, QRegularExpression
from PySide6.QtGui import (
    QPixmap, QImage, QRegularExpressionValidator, QPen, QColor
)

# from PIL import Image, ImageTk

# from src.AI.predict_AI import AIPlasticDetectionSystem
# from src.AI.cam.camera_thread_old import CameraThread
from src.AI.cam.camera_thread import CameraThread
from src.AI.AI_manager import BatchAIManager
from src.utils.logger import log
from src.utils.config_util import (
    UI_PATH, MAX_IMG_LINES
)


@dataclass
class HyperSpectralWidget:
    """초분광 관련 PySide 위젯"""
    view: QGraphicsView = None
    img_item: QGraphicsPixmapItem = None
    scene: QGraphicsScene = None


@dataclass
class HyperSpectralData:
    """초분광 관련 속성"""
    max_lines: int
    line_buffer: deque = None
    current_line: int = 0
    last_update_time: float = 0.0
    update_interval: float = 0.0
    overlay_items: list = None
    overlay_info: deque = None


# pylint: disable=broad-exception-caught
class CameraView(QFrame):
    """카메라 뷰 위젯"""
    def __init__(
        self, camera_id, camera_name, camera_index,
        app, ai_manager=None, is_hyperspectral=False
    ):
        super().__init__()
        self.app = app
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.camera_index = camera_index
        self.ai_manager = ai_manager
        self.is_hyperspectral = is_hyperspectral
        if self.is_hyperspectral:
            self.img_data = HyperSpectralData(max_lines=MAX_IMG_LINES)
            self.img_data.line_buffer = deque(maxlen=self.img_data.max_lines)
            self.img_data.overlay_info = deque(maxlen=self.img_data.max_lines * 10)
            self.img_data.overlay_items = []
            self.img_data.update_interval = 0.033
        else:
            self.img_data = None
        self.image_label = None
        self.detector = None
        self.detector_frame_generator = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

        self.camera_thread = None
        # 카메라 동작 상태
        self.is_running = False

        self._init_ui()

    def _init_ui(self):
        """UI 초기화"""
        self.setObjectName("camera_view")
        self.setMinimumSize(350, 1000)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 헤더
        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignLeft)

        # 카메라 이름
        title = QLabel(self.camera_name)
        title.setObjectName("camera_title")
        header_layout.addWidget(title)

        header_layout.addSpacing(15)

        # 상태 표시
        self.status = QLabel("🟢 연결됨")
        self.status.setObjectName("camera_status")
        header_layout.addWidget(self.status)

        layout.addLayout(header_layout)

        layout.addSpacing(15)

        # 카메라 화면
        if not self.is_hyperspectral:
            # 스크롤 영역으로 감싸기
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(False)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setStyleSheet("""
                QScrollArea {
                    border: 1px solid #E2E2E2;
                    border-radius: 7px;
                    background-color: #FAFAFA;
                }
                QScrollBar:vertical {
                    border: none;
                    background: #F3F4F6;
                    width: 8px;
                    margin: 2px;
                }
                QScrollBar::handle:vertical {
                    background: #C0C0C0;
                    min-height: 30px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #A0A0A0;
                }
            """)

            self.image_label = QLabel()
            self.image_label.setObjectName("camera_frame")
            self.image_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            self.image_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.image_label.setText("📷 카메라 대기 중...")
            self.image_label.setStyleSheet(
                """
                background-color: #FAFAFA;
                color: #B9B9B9;
                font-size: 14px;
                font-weight: medium;
                """
            )

            scroll_area.setWidget(self.image_label)
            layout.addWidget(scroll_area)
        else:
            self.hyper_widget = HyperSpectralWidget()
            self.hyper_widget.scene = QGraphicsScene(0, 0, 640, 480, self)
            self.hyper_widget.img_item = QGraphicsPixmapItem()
            self.hyper_widget.scene.addItem(self.hyper_widget.img_item)

            self.hyper_widget.view = QGraphicsView(self.hyper_widget.scene, self)
            self.hyper_widget.view.setObjectName("camera_frame")
            self.hyper_widget.view.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.hyper_widget.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self.hyper_widget.view)

        # 하단 정보
        info_layout = QHBoxLayout()

        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setStyleSheet(
            """
            color: #989898;
            font-size: 12px;
            font-weight: normal;
            margin-left: 10px;
            margin-bottom: 25px;
            """
        )
        info_layout.addWidget(self.fps_label)

        info_layout.addStretch()

        self.resolution = QLabel("해상도: 1920x1080")
        self.resolution.setStyleSheet(
            """
            color: #989898;
            font-size: 12px;
            font-weight: normal;
            margin-right: 10px;
            margin-bottom: 25px;
            """
        )
        info_layout.addWidget(self.resolution)

        layout.addLayout(info_layout)

        layout.addStretch()

    def start_camera(self):
        """카메라 시작"""
        if self.is_running:
            log(f"{self.camera_name} 이미 실행 중")
            return

        try:
            log(f"{self.camera_name} 시작 (인덱스: {self.camera_index})")

            # 하이퍼스펙트럴은 CommManager 스트림으로만 수신한다.
            if self.is_hyperspectral:
                self.is_running = True
                self.update_status(True)
                log(f"{self.camera_name} 시작 완료 (CommManager 수신 대기)")
                return

            # CameraThread 생성
            self.camera_thread = CameraThread(
                camera_index=self.camera_index,
                airknife_callback=self.app.airknife_on,
                app=self.app,
                ai_manager=self.ai_manager,
            )

            # 시그널 연결
            self.camera_thread.frame_ready.connect(self.update_frame)
            self.camera_thread.error_occurred.connect(self.on_error)

            # 스레드 시작
            self.camera_thread.start()

            self.is_running = True
            self.update_status(True)
            log(f"{self.camera_name} 시작 완료")

        except Exception as e:
            log(f"카메라 시작 오류: {e}")
            traceback.print_exc()
            self.is_running = False
            self.update_status(False)

    def stop_camera(self):
        """카메라 정지"""
        if not self.is_running:
            return

        try:
            log(f"{self.camera_name} 정지 중...")

            if self.camera_thread:
                self.camera_thread.stop()
                self.camera_thread.wait(5000)  # 최대 5초 대기

                if self.camera_thread.isRunning():
                    log(f"{self.camera_name} 강제 종료")
                    self.camera_thread.terminate()
                    self.camera_thread.wait(1000)

            if self.is_hyperspectral:
                if self.hyper_widget and self.hyper_widget.img_item:
                    self.hyper_widget.img_item.setPixmap(QPixmap())
                if self.img_data:
                    for item in self.img_data.overlay_items:
                        if self.hyper_widget and self.hyper_widget.scene:
                            self.hyper_widget.scene.removeItem(item)
                    self.img_data.overlay_items.clear()
                    self.img_data.overlay_info.clear()
                    self.img_data.line_buffer.clear()
            else:
                self.image_label.setText("📷 카메라 대기 중...")
                self.image_label.setPixmap(QPixmap())

            self.is_running = False
            self.update_status(False)
            log(f"{self.camera_name} 정지 완료")

        except Exception as e:
            log(f"카메라 정지 오류: {e}")

    def update_frame(self, frame):
        """프레임 업데이트 (시그널로 호출됨)"""
        try:
            # pylint: disable=no-member
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)

            if not self.is_hyperspectral:
                # RGB 카메라: 부모 영역에 맞춰 fit
                parent_size = self.image_label.parent().size()
                available_width = parent_size.width() - 20   # 여백
                available_height = parent_size.height() - 20

                scaled_pixmap = pixmap.scaled(
                    available_width, available_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                self.image_label.setFixedSize(
                    scaled_pixmap.width(),
                    scaled_pixmap.height()
                )
                self.image_label.setPixmap(scaled_pixmap)
            else:
                if self.hyper_widget and self.hyper_widget.img_item and self.hyper_widget.view:
                    scaled_pixmap = pixmap.scaled(
                        self.hyper_widget.view.viewport().size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.hyper_widget.img_item.setPixmap(scaled_pixmap)

            if self.camera_thread:
                fps = self.camera_thread.current_fps
                self.fps_label.setText(f"FPS: {fps}")

        except Exception as e:
            log(f"프레임 업데이트 오류: {e}")

    def update_status(self, connected):
        """상태 업데이트"""
        if connected:
            self.status.setText("🟢 연결됨")
            self.status.setStyleSheet("color: #3fb950; font-size: 12px; font-weight: bold;")
        else:
            self.status.setText("🔴 연결 끊김")
            self.status.setStyleSheet("color: #f85149; font-size: 12px; font-weight: bold;")

    def on_error(self, error_msg):
        """에러 처리"""
        log(f"{self.camera_name} 오류: {error_msg}")
        if self.is_hyperspectral:
            if self.hyper_widget and self.hyper_widget.img_item:
                self.hyper_widget.img_item.setPixmap(QPixmap())
        else:
            self.image_label.setText(f"오류:\n{error_msg}")
        self.is_running = False
        self.update_status(False)

    def process_hyperspectral_line(self, info):
        """라인 데이터 처리"""
        # pixel_format = self.format_var.get()
        if self.img_data is None:
            return

        cur_line = info["frame_number"]
        line_data = info["data_body"]
        prev_line = self.img_data.current_line

        if prev_line != 0:
            line_gap = cur_line - prev_line - 1
            if 0 < line_gap < 500:
                padding_line = self.img_data.line_buffer[-1] \
                    if self.img_data.line_buffer else np.zeros((640, 3), dtype=np.uint8)
                for _ in range(line_gap):
                    self.img_data.line_buffer.append(padding_line)

        try:
            line_array = np.frombuffer(line_data, dtype=np.uint8)
            if len(line_array) == 640:
                # Grayscale 640픽셀
                # 색상 반전 (검정↔흰색) + 밝기 증폭
                line_array = 255 - (line_array * 36)  # 0→255, 7→3 (반전 후 증폭)
                line_array = np.clip(line_array, 0, 255).astype(np.uint8)
                # 이 줄만 쓰면 픽셀 변환 그대로
                line_rgb = np.stack([line_array, line_array, line_array], axis=1)
            elif len(line_array) == 640*3:
                # RGB 640*3픽셀
                line_rgb = line_array.reshape(640, 3)
            else:
                log(f"⚠️ 잘못된 라인 크기: {len(line_array)} (예상: 640 또는 1920)")
                return

            # ✓ 수정: deque에 라인 추가 (자동으로 오래된 라인 제거)
            self.img_data.line_buffer.append(line_rgb)
            self.img_data.current_line = cur_line

            current_time = time.time()

            # 이미지 업데이트 (30fps 제한)
            if current_time - self.img_data.last_update_time >= self.img_data.update_interval:
                self.update_hyperspectral_image()
                self.update_hyperspectral_overlay()
                self.img_data.last_update_time = current_time

        except Exception as e:
            log(f"라인 처리 오류: {str(e)}")
            log(traceback.format_exc())

    # def update_stats(self):
    #     """통계 업데이트"""
    #     self.stats_label.config(
    #         text=f"수신된 라인: {self.img_data.current_line} | FPS: {self.statistics_data.fps:.1f}"
    #     )

    def update_hyperspectral_image(self):
        """이미지 표시 업데이트 - 스크롤 효과"""
        try:
            if len(self.img_data.line_buffer) == 0:
                return

            # deque → numpy array (최신 라인이 아래로)
            img_data = np.array(list(self.img_data.line_buffer), dtype=np.uint8)

            # 라인이 480개 미만이면 위쪽을 검은색으로 채움
            if len(img_data) < self.img_data.max_lines:
                padding = np.zeros(
                    (self.img_data.max_lines - len(img_data), 640, 3),
                    dtype=np.uint8
                )
                img_data = np.vstack([padding, img_data])

            # 가이드라인 영역을 빨간색으로 표시
            # img_data[:, GUIDELINE_MIN_X:GUIDELINE_MAX_X, :] = [255, 0, 0]

            # QImage로 변환
            h, w, ch = img_data.shape
            bytes_per_line = 3 * w
            q_img = QImage(
                img_data.data,
                w,
                h,
                bytes_per_line,
                QImage.Format_RGB888
            ).copy()
            pixmap = QPixmap.fromImage(q_img)

            if isinstance(self.image_label, QLabel):
                # QLabel 기반 렌더 경로
                scaled = pixmap.scaled(
                    self.image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation
                )
                self.image_label.setPixmap(scaled)
            elif getattr(self, "hyper_widget", None) and self.hyper_widget.img_item is not None:
                # QGraphicsScene 기반 렌더 경로
                self.hyper_widget.img_item.setPixmap(pixmap)

        except Exception as e:
            log(f"이미지 업데이트 오류: {str(e)}")
            log(traceback.format_exc())

    def update_hyperspectral_overlay(self):
        """물체 감지 오버레이"""
        # 현재 화면 범위를 벗어난 오래된 오버레이 정보 정리
        while self.img_data.overlay_info:
            oldest = self.img_data.overlay_info[0]
            end_frame = oldest.get("end_frame", 0)
            if self.img_data.current_line - end_frame > self.img_data.max_lines:
                self.img_data.overlay_info.popleft()
            else:
                break

        # 1. 기존 오버레이 삭제 (간단한 구현을 위해 일단 모두 제거)
        for item in self.img_data.overlay_items:
            self.hyper_widget.scene.removeItem(item)
        self.img_data.overlay_items.clear()

        # 점선 펜 설정
        pen = QPen(QColor("white"), 2)
        pen.setStyle(Qt.DashLine)

        for info in self.img_data.overlay_info:
            start_frame = info.get("start_frame")
            end_frame = info.get("end_frame")
            x0 = info.get("x0")
            x1 = info.get("x1")
            if start_frame is None or end_frame is None or x0 is None or x1 is None:
                continue

            if self.img_data.current_line < start_frame:
                continue

            y0 = self.img_data.max_lines - (self.img_data.current_line - start_frame)
            height = end_frame - start_frame + 1
            if height <= 0:
                continue
            if y0 > self.img_data.max_lines or y0 + height < 0:
                continue

            # 2. RectItem 생성 및 추가
            rect_item = QGraphicsRectItem(x0, y0, x1 - x0, height)
            rect_item.setPen(pen)

            self.hyper_widget.scene.addItem(rect_item)
            self.img_data.overlay_items.append(rect_item)


class MonitoringPage(QWidget):
    """모니터링 페이지 - 카메라 스트림"""
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rgb_cameras = []
        self.hyper_camera = None
        self.ai_manager = BatchAIManager(
            num_cameras=2,
            confidence_threshold=0.6,
            img_size=640,
            max_det=50
        )
        # model_path = sys.path[0] + "\\src\\AI\\model\\weights\\best.pt"
        model_path = sys.path[0] + "\\src\\AI\\model\\best.engine"
        if not self.ai_manager.initialize(model_path):
            log("AI 매니저 초기화 실패")
            # 초기화 실패해도 UI는 표시
        else:
            log("BatchAIManager 초기화 완료!")

        self._init_ui()

    def _init_ui(self):
        """UI 초기화"""
        # 사이드바
        self.side_widget = QFrame(self)
        side_layout = QVBoxLayout(self.side_widget)
        side_layout.setSpacing(0)
        side_layout.setContentsMargins(0, 0, 0, 0)

        self._create_side_bar(side_layout)

        side_layout.addStretch()

        # 컨텐츠 영역
        self.main_widget = QFrame(self)
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 스크롤
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        scroll_content.setMaximumWidth(1610)

        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setAlignment(Qt.AlignTop)
        scroll_layout.setSpacing(0)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        scroll_layout.addSpacing(25)

        # 상단: 제어 패널
        self._create_control_panel(scroll_layout)

        scroll_layout.addSpacing(30)

        # 중단: RGB 카메라 (2x2)
        self._create_rgb_cameras(scroll_layout)

        scroll_layout.addSpacing(30)

        # 하단: 초분광 카메라
        self._create_hyperspectral_camera(scroll_layout)

        scroll_layout.addSpacing(30)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # 스타일 적용
        self.apply_styles()

    def _create_side_bar(self, parent_layout):
        title_layout = QHBoxLayout()
        title_layout.setSpacing(0)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_layout.addSpacing(30)

        img_label = QLabel()
        img_label.setObjectName("side_title_logo")
        logo_img = QPixmap(str(UI_PATH / "logo/monitoring_page.png"))
        img_label.setPixmap(logo_img)
        img_label.setScaledContents(True)
        img_label.setFixedSize(16, 16)
        title_layout.addWidget(img_label)

        title_layout.addSpacing(10)

        title_label = QLabel("실시간 모니터링")
        title_label.setObjectName("side_title_label")
        title_layout.addWidget(title_label)

        parent_layout.addLayout(title_layout)

    def _create_control_panel(self, parent_layout):
        """제어 패널"""
        control_box = QFrame()
        control_box.setObjectName("control_box")
        layout = QHBoxLayout(control_box)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # 전체 시작/정지
        start_all_btn = QPushButton("▶️전체 시작")
        start_all_btn.setObjectName("control_btn_start")
        start_all_btn.setFixedSize(199, 60)
        start_all_btn.clicked.connect(self.on_start_all)
        layout.addWidget(start_all_btn)

        stop_all_btn = QPushButton("⏹️전체 정지")
        stop_all_btn.setObjectName("control_btn_stop")
        stop_all_btn.setFixedSize(199, 60)
        stop_all_btn.clicked.connect(self.on_stop_all)
        layout.addWidget(stop_all_btn)

        # 녹화
        self.record_btn = QPushButton("▶️녹화 시작")
        self.record_btn.setObjectName("control_btn_record")
        self.record_btn.setCheckable(True)
        self.record_btn.setFixedSize(199, 60)
        self.record_btn.clicked.connect(self.on_record)
        layout.addWidget(self.record_btn)

        # 스냅샷
        snapshot_btn = QPushButton("📸스냅샷")
        snapshot_btn.setObjectName("control_btn_snapshot")
        snapshot_btn.setFixedSize(199, 60)
        snapshot_btn.clicked.connect(self.on_snapshot)
        layout.addWidget(snapshot_btn)

        layout.addSpacing(15)

        # 해상도 선택
        res_title = QLabel("해상도:")
        res_title.setStyleSheet(
            """
            color: #000000;
            font-size: 16px;
            font-weight: normal;
            """
        )
        layout.addWidget(res_title)

        self.resolution_combo = QComboBox()
        self.resolution_combo.setObjectName("combo_box")
        self.resolution_combo.setFixedSize(220, 40)
        self.resolution_combo.addItems(["1920x1080", "1280x720", "640x480"])
        layout.addWidget(self.resolution_combo)

        # 배출 순서 제어
        layout.addWidget(QLabel("배출 순서 제어:"))

        _saved_seq = self.app.config.get("air_sequence", [])
        _prev = "".join([str(n) for n in _saved_seq])
        self.sequence_edit = QLineEdit(f"{_prev}")
        _rx = QRegularExpression("^[1-3]*$")
        self.sequence_edit.setValidator(QRegularExpressionValidator(_rx, layout))
        self.sequence_edit.setPlaceholderText("1 ~ 3 의 값을 연속 입력 가능")
        self.sequence_edit.setObjectName("input_field")
        self.sequence_edit.setMaximumWidth(300)
        self.sequence_edit.setAlignment(Qt.AlignLeft)
        self.sequence_edit.returnPressed.connect(self._on_set_sequence)
        layout.addWidget(self.sequence_edit)

        sequence_set_btn = QPushButton("설정")
        sequence_set_btn.setObjectName("setting_btn")
        sequence_set_btn.setMinimumHeight(60)
        sequence_set_btn.setMinimumWidth(60)
        sequence_set_btn.clicked.connect(self._on_set_sequence)
        layout.addWidget(sequence_set_btn)

        self.toggle_btn = QPushButton("미사용")
        self.toggle_btn.setObjectName("toggle_btn")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(False)
        self.toggle_btn.setMinimumHeight(60)
        self.toggle_btn.setMinimumWidth(60)
        self.toggle_btn.clicked.connect(lambda checked: self._on_use_sequence(checked))
        layout.addWidget(self.toggle_btn)

        layout.addStretch()

        parent_layout.addWidget(control_box)

    def _create_rgb_cameras(self, parent_layout):
        """RGB 카메라 그리드"""
        rgb_layout = QGridLayout()
        rgb_layout.setContentsMargins(0, 0, 0, 0)
        rgb_layout.setSpacing(20)

        rgb_layout.setRowMinimumHeight(0, 800)
        rgb_layout.setRowMinimumHeight(0, 800)

        rgb_layout.setRowStretch(0, 1)
        rgb_layout.setRowStretch(1, 1)
        rgb_layout.setColumnStretch(0, 1)
        rgb_layout.setColumnStretch(1, 1)

        # 4개의 RGB 카메라
        self.rgb_cameras = []

        # 카메라 추가할 떄에는 이걸 주석 풀어서 하나씩 추가
        cameras = [
            ("RGB 카메라 1", 0, 0, 0),
            ("RGB 카메라 2", 0, 1, 1),
            # ("RGB 카메라 3", 1, 0),
            # ("RGB 카메라 4", 1, 1),
        ]

        for name, row, col, camera_index in cameras:
            cam = CameraView(
                camera_id=f"rgb_{row}{col}",
                camera_name=name,
                camera_index=camera_index,
                app=self.app,
                ai_manager=self.ai_manager
            )
            cam.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            rgb_layout.addWidget(cam, row, col)
            self.rgb_cameras.append(cam)

        parent_layout.addLayout(rgb_layout)

    def _create_hyperspectral_camera(self, parent_layout):
        """초분광 카메라"""
        hyper_layout = QVBoxLayout()

        # 카메라 뷰
        camera_layout = QHBoxLayout()

        self.hyper_camera = CameraView(
            "hyperspectral",
            "Specim FX17",
            camera_index=0,
            app=self.app,
            ai_manager=None,
            is_hyperspectral=True
        )
        self.hyper_camera.setMinimumSize(600, 400)
        camera_layout.addWidget(self.hyper_camera)

        camera_layout.addSpacing(20)

        # 우측: 분류 통계
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(0)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_title = QLabel("실시간 분류 통계")
        stats_title.setStyleSheet(
            """
            color: #000000;
            font-size: 16px;
            font-weight: medium;
            """
        )
        stats_layout.addWidget(stats_title)

        stats_layout.addSpacing(15)

        stats_frame = QFrame()
        stats_frame.setObjectName("stats_frame")
        stats_frame.setFixedSize(415, 422)

        stats_frame_layout = QVBoxLayout(stats_frame)

        # 플라스틱 종류별 카운트
        self.plastic_counts = {}
        plastics = ["PET", "PE", "PP", "PS", "PVC", "기타"]
        colors = ["#258FD0", "#1CB786", "#E43C3C", "#F5A50F", "#BE5EC3", "#878787"]

        for plastic, color in zip(plastics, colors):
            count_layout = QHBoxLayout()

            label = QLabel(plastic)
            label.setStyleSheet(
                f"""
                color: {color};
                font-size: 16px;
                font-weight: medium;
                """
            )
            count_layout.addWidget(label)

            count_layout.addStretch()

            count = QLabel("0")
            count.setStyleSheet(
                f"""
                color: {color};
                font-size: 16px;
                font-weight: medium;
                """
            )
            self.plastic_counts[plastic] = count
            count_layout.addWidget(count)

            stats_frame_layout.addLayout(count_layout)

        stats_frame_layout.addSpacing(10)

        # 총 처리량
        total_layout = QHBoxLayout()
        total_label = QLabel("총 처리량:")
        total_label.setStyleSheet(
            """
            color: #000000;
            font-size: 16px;
            font-weight: medium;
            """
        )
        total_layout.addWidget(total_label)

        total_layout.addStretch()

        self.total_count = QLabel("0")
        self.total_count.setStyleSheet(
            """
            color: #000000;
            font-size: 20px;
            font-weight: medium;
            """
        )
        total_layout.addWidget(self.total_count)

        stats_frame_layout.addLayout(total_layout)

        stats_frame_layout.addSpacing(15)

        # 리셋 버튼
        reset_btn = QPushButton("카운터 리셋")
        reset_btn.setObjectName("reset_btn")
        reset_btn.setFixedHeight(60)
        reset_btn.clicked.connect(self.on_reset_counter)
        stats_frame_layout.addWidget(reset_btn)

        stats_layout.addWidget(stats_frame)

        stats_layout.addStretch()

        camera_layout.addLayout(stats_layout)
        hyper_layout.addLayout(camera_layout)

        parent_layout.addLayout(hyper_layout)

    def on_start_all(self):
        """전체 시작"""
        log("모든 카메라 시작")
        self.app.monitoring_enabled = True

        if self.ai_manager:
            self.ai_manager.start()

        for camera in self.rgb_cameras:
            camera.start_camera()

        if self.hyper_camera:
            self.hyper_camera.start_camera()

    def on_stop_all(self):
        """전체 정지"""
        log("모든 카메라 정지")
        self.app.monitoring_enabled = False
        if self.ai_manager:
            self.ai_manager.stop()

        for camera in self.rgb_cameras:
            camera.stop_camera()

        if self.hyper_camera:
            self.hyper_camera.stop_camera()

    def on_hypercam_updated(self, info):
        """초분광 카메라 스트리밍 출력"""
        if self.hyper_camera and self.hyper_camera.is_running:
            self.hyper_camera.process_hyperspectral_line(info)

    def on_object_detected(self, info, classification):
        """물체 감지됨"""
        if self.hyper_camera and self.hyper_camera.is_running and self.hyper_camera.img_data:
            payload = dict(info)
            payload["classification"] = classification
            self.hyper_camera.img_data.overlay_info.append(payload)

    # def update_cameras(self):
    #     """카메라 프레임 업데이트"""
    #     # RGB 카메라들 업데이트
    #     for camera in self.rgb_cameras:
    #         camera.update_frame()

    def on_snapshot(self):
        """스냅샷"""
        log("스냅샷 저장")
        # TODO: 현재 프레임 저장

    def on_record(self, checked):
        """녹화"""
        if checked:
            self.record_btn.setText("⏹ 녹화 중지")
            log("녹화 시작")
            # TODO: 녹화 시작
        else:
            self.record_btn.setText("⏺ 녹화 시작")
            log("녹화 중지")
            # TODO: 녹화 중지

    def on_reset_counter(self):
        """카운터 리셋"""
        log("분류 카운터 리셋")
        for count_label in self.plastic_counts.values():
            count_label.setText("0")
        self.total_count.setText("0")
        # TODO: 실제 카운터 리셋

    def _on_set_sequence(self):
        if self.app.use_air_sequence:
            log("배출 제어 순서 사용 도중에는 순서를 변경할 수 없습니다.")
            return

        air_pattern = self.sequence_edit.text()
        self.app.config["air_sequence"] = [int(c) for c in air_pattern] if air_pattern else []
        self.app.set_air_sequence_index()
        log(f"배출 제어 순서 저장됨. {self.app.config['air_sequence']}")

    def _on_use_sequence(self, onoff):
        _pattern = self.app.config.get("air_sequence", [])
        if onoff and not _pattern:
            log("지정된 배출 제어 순서가 없습니다.")
            self.toggle_btn.setChecked(False)
            return

        state = "사용" if onoff else "미사용"
        self.toggle_btn.setText(state)
        self.app.use_air_sequence = onoff
        log(f"배출 제어 순서 {state}")

    def on_legend_info(self, legend_info_list):
        self.legend_info_list = legend_info_list

    def update_values(self, values):
        """모니터링 값 업데이트"""
        # if len(values) >= 8:
        #     # 인버터 상태 업데이트
        #     self.freq_value.setText(f"{values[3]:.2f}")
        #     self.current_value.setText(f"{values[2]:.1f}")
        #     self.voltage_value.setText(f"{values[4]}")
        #     self.power_value.setText(f"{values[6]:.1f}")

        #     # 운전상태 업데이트
        #     status = values[7]
        #     if status & (1 << 0):
        #         status_text, color = "정지", "#6e7681"
        #     elif status & (1 << 1):
        #         status_text, color = "정방향", "#3fb950"
        #     elif status & (1 << 2):
        #         status_text, color = "역방향", "#58a6ff"
        #     elif status & (1 << 3):
        #         status_text, color = "Fault", "#f85149"
        #     elif status & (1 << 4):
        #         status_text, color = "가속중", "#d29922"
        #     elif status & (1 << 5):
        #         status_text, color = "감속중", "#d29922"
        #     else:
        #         status_text, color = "알 수 없음", "#6e7681"

        #     self.status_value.setText(status_text)
        #     self.status_value.setStyleSheet(
        #         f"""
        #         color: {color};
        #         font-size: 16px;
        #         font-weight: bold;
        #         """
        #     )

    def apply_styles(self):
        """스타일시트 적용"""
        self.side_widget.setStyleSheet(
            """
            /* 사이드바 제목 */
            #side_title_label {
                color: #000000;
                font-size: 16px;
                font-weight: medium;
            }
            """
        )
        self.main_widget.setStyleSheet(
            """
            /* 스크롤바 */
            QScrollArea {
                border: none;
                background-color: transparent;
            }

            QScrollBar:vertical {
                border: none;
                background: #F3F4F6;
                width: 5px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background: #E2E2E2;
                min-height: 20px;
                border-radius: 5px;
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            #scroll_content {
                background-color: transparent;
            }

            #control_box {
                background-color: #FAFAFA;
                border: 1px solid #E2E2E2;
                border-radius: 7px;
            }

            #camera_view {
                background-color: transparent;
                border: none;
            }

            #camera_title {
                color: #000000;
                font-size: 16px;
                font-weight: medium;
            }

            #camera_status {
                color: #616161;
                font-size: 14px;
                font-weight: normal;
            }

            #stats_frame {
                background-color: #FAFAFA;
                border: 1px solid #E2E2E2;
                border-radius: 7px;
                padding: 15px;
            }

            #combo_box {
                background-color: #FFFFFF;
                border: 1px solid #D4D4D4;
                border-radius: 4px;
                padding: 5px 10px;
                color: #4B4B4B;
            }

            #combo_box:hover {
                border-color: #58a6ff;
            }

            #combo_box::drop-down {
                border: none;
            }

            #combo_box QAbstractItemView {
                background-color: #FFFFFF;
                border: 1px solid #D4D4D4;
                color: #4B4B4B;
                selection-background-color: #FFFFFF;
            }

            #control_btn_start {
                background-color: #353535;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }

            #control_btn_start:hover {
                background-color: #555555;
            }

            #control_btn_stop {
                background-color: #FF2427;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }

            #control_btn_stop:hover {
                background-color: #FF6467;
            }

            #control_btn_record {
                background-color: #2DB591;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }

            #control_btn_record:hover {
                background-color: #45CAA6;
            }

            #control_btn_record:checked {
                background-color: #FF2427;
            }

            #control_btn_snapshot {
                background-color: #54B9DE;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }

            #control_btn_snapshot:hover {
                background-color: #64C9EE;
            }

            #reset_btn {
                background-color: #E6E6E6;
                border: none;
                border-radius: 4px;
                color: #000000;
                font-size: 16px;
                font-weight: medium;
            }

            #reset_btn:hover {
                background-color: #8b949e;
            }

            #input_field {
                background-color: #FFFFFF;
                border: 1px solid #D4D4D4;
                border-radius: 4px;
                padding: 10;
                color: #000000;
                font-size: 14px;
                font-weight: normal;
            }

            #input_field:focus {
                border-color: #AAAAAA;
            }

            #setting_btn {
                background-color: #161b22;
                color: #FFFFFF;
                border: 2px solid #30363d;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }

            #setting_btn:hover {
                background-color: #21262d;
                border-color: #58a6ff;
            }

            #toggle_btn {
                background-color: #238636;
                border: none;
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 16px;
                font-weight: medium;
            }

            #toggle_btn:checked {
                background-color: #238636;
                border-color: #2ea043;
            }

            #toggle_btn:!checked {
                background-color: #6e7681;
                border-color: #8b949e;
            }

            #toggle_btn:hover {
                opacity: 0.8;
            }
            """
        )
