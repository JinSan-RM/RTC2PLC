"""
모니터링 페이지 - 카메라 스트림
"""
import traceback
import sys

# import numpy as np
import cv2
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QComboBox,
    QLineEdit, QSizePolicy, QCheckBox
)
from PySide6.QtCore import Qt, QTimer, QRegularExpression
from PySide6.QtGui import QPixmap, QImage, QRegularExpressionValidator

# from src.AI.predict_AI import AIPlasticDetectionSystem
# from src.AI.cam.camera_thread_old import CameraThread
from src.AI.cam.camera_thread import CameraThread
from src.AI.AI_manager import BatchAIManager
from src.utils.logger import log
from src.utils.config_util import CAMERA_CONFIGS, CAMERA_DISPLAY_CONFIG, UI_PATH


class CameraView(QFrame):
    """카메라 뷰 위젯"""
    def __init__(self, camera_id, camera_name, camera_index, app, ai_manager=None, is_hyperspectral=False):
        super().__init__()
        self.app = app
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.camera_index = camera_index
        self.ai_manager = ai_manager
        self.is_hyperspectral = is_hyperspectral
        self.detector = None
        self.detector_frame_generator = None
        #self.timer = QTimer()
        #self.timer.timeout.connect(self.update_frame)

        self.camera_thread = None
        self.is_running = False # 카메라 동작 상태

        self._init_ui()


    def _init_ui(self):
        """UI 초기화"""
        self.setObjectName("camera_view")
        # self.setMinimumSize(350, 1000) 
        self.setMinimumSize(350, 300) 
        
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
            # scroll_area = QScrollArea() 
            # scroll_area.setWidgetResizable(False) #고정되어있음, 스크롤 영역이 내용물의 크기 변화에 따라 동적으로 조정되지 않음
            # scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            # scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            # scroll_area.setStyleSheet("""
            #     QScrollArea {
            #         border: 1px solid #E2E2E2;
            #         border-radius: 7px;
            #         background-color: #FAFAFA;
            #     }
            #     QScrollBar:vertical {
            #         border: none;
            #         background: #F3F4F6;
            #         width: 8px;
            #         margin: 2px;
            #     }
            #     QScrollBar::handle:vertical {
            #         background: #C0C0C0;
            #         min-height: 30px;
            #         border-radius: 4px;
            #     }
            #     QScrollBar::handle:vertical:hover {
            #         background: #A0A0A0;
            #     }
            # """)

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

            # scroll_area.setWidget(self.image_label)
            # layout.addWidget(scroll_area)
            layout.addWidget(self.image_label)
            

        else:
            # Hyperspectral 카메라는 기존 방식 유지
            self.image_label = QLabel()
            self.image_label.setObjectName("camera_frame")
            self.image_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            # self.image_label.setMinimumHeight(500)
            self.image_label.setMinimumHeight(300)
            self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.image_label.setText("📷 카메라 대기 중...")
            self.image_label.setStyleSheet(
                """
                background-color: #FAFAFA;
                color: #B9B9B9;
                font-size: 14px;
                font-weight: medium;
                border: 1px solid #E2E2E2;
                border-radius: 7px;
                """
            )
            layout.addWidget(self.image_label)
            # 추가
            layout.setStretchFactor(self.image_label, 1)  # 이미지 라벨이 남는 공간을 모두 차지하도록 설정

        # # 하단 정보
        # info_layout = QHBoxLayout()

        # self.fps_label = QLabel("FPS: 0")
        # self.fps_label.setStyleSheet(
        #     """
        #     color: #989898;
        #     font-size: 12px;
        #     font-weight: normal;
        #     margin-left: 10px;
        #     margin-bottom: 10px;
        #     """
        # )
        # info_layout.addWidget(self.fps_label)

        # info_layout.addStretch()

        # self.resolution = QLabel("해상도: 1920x1080")
        # self.resolution.setStyleSheet(
        #     """
        #     color: #989898;
        #     font-size: 12px;
        #     font-weight: normal;
        #     margin-right: 10px;
        #     margin-bottom: 10px;
        #     """
        # )
        # info_layout.addWidget(self.resolution)

        # layout.addLayout(info_layout)
        

        # 정보 컨테이너 생성 (배경 투명, 테두리 없음)
        self.info_container = QFrame()
        self.info_container.setObjectName("info_container")
        self.info_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.info_container.setStyleSheet("background: transparent; border: none;")

        # 내부 레이아웃 (여백 0으로 설정하여 이미지와 가로폭 완전 일치)
        info_layout = QHBoxLayout(self.info_container)
        info_layout.setContentsMargins(0, 0, 0, 0) 
        info_layout.setSpacing(0)

        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setStyleSheet("color: #989898; font-size: 12px; margin-bottom: 5px;")
        
        self.resolution = QLabel("해상도: 0x0")
        self.resolution.setStyleSheet("color: #989898; font-size: 12px; margin-bottom: 5px;")

        # 요소 배치: FPS(왼쪽) --- Stretch(공간 채움) --- 해상도(오른쪽)
        info_layout.addWidget(self.fps_label)
        info_layout.addStretch() 
        info_layout.addWidget(self.resolution)

        # 전체 레이아웃에 추가 
        layout.addWidget(self.info_container, alignment=Qt.AlignLeft)

        # ROI 설정 
        roi_row = QHBoxLayout()
        roi_row.setContentsMargins(0, 0, 0, 0) # 여백 조정
        roi_row.setSpacing(8)

        current_roi = CAMERA_CONFIGS.get(self.camera_index, {}).get('roi', {})

        roi_lbl = QLabel("ROI")
        roi_lbl.setObjectName("setting_label")
        roi_row.addWidget(roi_lbl)

        self.roi_inputs = {}
        
        # roi 값이 없다면
        for label_text, default_val in [
            ("X",      current_roi.get('x', 0)),
            ("Y",      current_roi.get('y', 0)),
            ("Width",  current_roi.get('width', 1280)),
            ("Height", current_roi.get('height', 1080)),
        ]:
            lbl = QLabel(label_text)
            lbl.setObjectName("setting_label")
            roi_row.addWidget(lbl)

            inp = QLineEdit(str(default_val))
            inp.setObjectName("setting_input_field")
            inp.setFixedWidth(65)
            inp.setFixedHeight(26)
            inp.setValidator(QRegularExpressionValidator(
                QRegularExpression("^[0-9]+$"), inp
            ))
            self.roi_inputs[label_text.lower()] = inp
            roi_row.addWidget(inp)

        self.roi_apply_btn = QPushButton("적용")
        self.roi_apply_btn.setObjectName("action_apply_btn")
        self.roi_apply_btn.setFixedSize(50, 26)
        self.roi_apply_btn.clicked.connect(self._on_roi_apply)
        roi_row.addWidget(self.roi_apply_btn)

        roi_row.addStretch()
        layout.addLayout(roi_row)

        # 수정
        if not self.is_hyperspectral:
            layout.addStretch()

    def _on_roi_apply(self):
        """ROI 적용 버튼 클릭"""
        try:
            x      = int(self.roi_inputs['x'].text())
            y      = int(self.roi_inputs['y'].text())
            width  = int(self.roi_inputs['width'].text())
            height = int(self.roi_inputs['height'].text())

            log(f"{self.camera_name} ROI 변경 요청: x={x}, y={y}, w={width}, h={height}")

            if self.camera_index in CAMERA_CONFIGS:
                CAMERA_CONFIGS[self.camera_index]['roi'] = {
                    'x': x, 'y': y, 'width': width, 'height': height
                }

            if self.camera_thread and self.is_running:
                success = self.camera_thread.update_roi(x, y, width, height)
                if success:
                    log(f"{self.camera_name} ROI 변경 적용 완료")
                else:
                    log(f"{self.camera_name} ROI 변경 적용 실패")
            else:
                log(f"{self.camera_name} ROI 변경: 카메라가 실행 중이 아닙니다. 다음 실행부터 적용됩니다.")

        except ValueError:
            log(f"{self.camera_name} ROI 입력값 오류: 숫자를 입력하세요")

    def start_camera(self):
        """카메라 시작"""
        if self.is_running:
            log(f"{self.camera_name} 이미 실행 중")
            return

        try:
            log(f"{self.camera_name} 시작 (인덱스: {self.camera_index})")

            # CameraThread 생성
            self.camera_thread = CameraThread(
                camera_index=self.camera_index,
                airknife_callback=self.app.airknife_on,
                app=self.app,
                ai_manager = self.ai_manager
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

            self.is_running = False
            self.update_status(False)
            self.image_label.setText("📷 카메라 대기 중...")
            self.image_label.setPixmap(QPixmap())
            log(f"{self.camera_name} 정지 완료")

        except Exception as e:
            log(f"카메라 정지 오류: {e}")
            
    def update_frame(self, frame):
        """프레임 업데이트 (시그널로 호출됨)"""
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # pylint: disable=no-member
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)

            # 수정 여기부터
            if not self.is_hyperspectral:
                cam_view_w = self.width()   # 좌우 패딩 제외한 너비
                cam_view_h = self.height()
                
                # 이미지의 가로세로 비율 계산
                max_w = int(cam_view_w * CAMERA_DISPLAY_CONFIG["max_width_ratio"])
                max_h = int(cam_view_h * CAMERA_DISPLAY_CONFIG["max_height_ratio"])
                
                ratio_w = max_w / w
                ratio_h = max_h / h
                resize_ratio = min(ratio_w, ratio_h)  # 가로/세로 둘 다 비율 유지
    
                resize_w = int(w * resize_ratio)
                resize_h = int(h * resize_ratio)
    
                scaled_pixmap = pixmap.scaled(
                    resize_w, resize_h,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.image_label.setFixedSize(resize_w, resize_h)
                self.image_label.setPixmap(scaled_pixmap)
                    
            # 여기까지
            else:
                scaled_pixmap = pixmap.scaled(
                    self.image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)

            # if self.camera_thread:
            #     fps = self.camera_thread.current_fps
            #     self.fps_label.setText(f"FPS: {fps}")

            self.info_container.setFixedWidth(resize_w) # 정보 컨테이너 너비를 이미지와 동일하게 설정
                
            self.resolution.setText(f"해상도: {w}x{h}")
            if self.camera_thread:
                self.fps_label.setText(f"FPS: {self.camera_thread.current_fps}")

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
        self.image_label.setText(f"오류:\n{error_msg}")
        self.is_running = False
        self.update_status(False)


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

        self.plastic_counts = {}             # 플라스틱 종류별 카운트 라벨
        self.total_count = QLabel()          # 총 처리량 라벨
    
        # 체크박스 해제된 재질
        self.excluded_classes: set = set() # 초분광일 때만 적용

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
        scroll_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll_layout = QVBoxLayout(scroll_content)
        # scroll_layout.setAlignment(Qt.AlignTop)
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
        scroll_layout.addStretch()

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
        rgb_container = QWidget()
        rgb_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        rgb_layout = QGridLayout(rgb_container)
        rgb_layout.setContentsMargins(0, 0, 0, 0)
        rgb_layout.setSpacing(20)
        
        # rgb_layout.setRowMinimumHeight(0, 800)
        rgb_layout.setRowMinimumHeight(0, 800)
        
        rgb_layout.setRowStretch(0, 1)
        # rgb_layout.setRowStretch(1, 1)
        # rgb_layout.setColumnStretch(0, 1)
        # rgb_layout.setColumnStretch(1, 1)

    
        # 4개의 RGB 카메라
        self.rgb_cameras = []

        # 카메라 추가할 떄에는 이걸 주석 풀어서 하나씩 추가
        cameras = [
            ("RGB 카메라 1", 0, 0, 0),
            # ("RGB 카메라 2", 0, 1, 1),
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

        parent_layout.addWidget(rgb_container)

    def _create_hyperspectral_camera(self, parent_layout):
        """초분광 카메라 및 분리된 통계/설정창 생성"""
        hyper_layout = QVBoxLayout()
        camera_layout = QHBoxLayout()

        # 1. 카메라 뷰 설정
        self.hyper_camera = CameraView(
            "hyperspectral", "Specim FX17", camera_index=0,
            app=self.app, ai_manager=None, is_hyperspectral=True
        )
        self.hyper_camera.setMinimumSize(600, 400)
        camera_layout.addWidget(self.hyper_camera)
        camera_layout.addSpacing(20)

        # 2. 우측 사이드 바 (설정 + 통계)
        side_panel_layout = QVBoxLayout()
        side_panel_layout.setSpacing(15)
        side_panel_layout.setContentsMargins(0, 0, 0, 0)

        # --- [A] AI Configuration Group (설정 영역) ---
        config_group = QFrame()
        config_group.setObjectName("stats_frame") 
        config_group.setFixedWidth(320)
        config_layout = QVBoxLayout(config_group)
        
        cfg_title = QLabel("AI 설정")
        cfg_title.setStyleSheet("font-weight: medium; color: #333; margin-bottom: 5px;")
        config_layout.addWidget(cfg_title)

        # 설정 필드 생성 함수 
        def add_cfg_row(label_text, default_val, apply_func, validator_type="int"):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(100)
            inp = QLineEdit(str(default_val))
            inp.setObjectName("setting_input_field")
            inp.setFixedSize(65, 28)
            if validator_type == "float":
                inp.setValidator(QRegularExpressionValidator(QRegularExpression(r"^(0(\.[0-9]{0,2})?|1(\.0{0,2})?)$")))
            else:
                inp.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9]+$")))
            
            btn = QPushButton("적용")
            btn.setObjectName("action_apply_btn")
            btn.setFixedSize(50, 28)
            btn.clicked.connect(apply_func)
            
            row.addWidget(lbl)
            row.addWidget(inp)
            row.addWidget(btn)
            return row, inp

        row1, self.conf_input = add_cfg_row("Confidence:", self.ai_manager.confidence_threshold, self._on_conf_apply, "float")
        row2, self.img_size_input = add_cfg_row("Image Size:", self.ai_manager.img_size, self._on_img_size_apply)
        row3, self.max_det_input = add_cfg_row("Max Detection:", self.ai_manager.max_det, self._on_max_det_apply)

        config_layout.addLayout(row1)
        config_layout.addLayout(row2)
        config_layout.addLayout(row3)
        side_panel_layout.addWidget(config_group)

        # --- [B] Real-time Detection Stats Group (통계 영역) ---
        stats_group = QFrame()
        stats_group.setObjectName("stats_frame")
        stats_group.setFixedWidth(320)
        stats_group_layout = QVBoxLayout(stats_group)

        stats_title = QLabel("실시간 분류 통계")
        stats_title.setStyleSheet("font-weight: medium; color: #333; margin-bottom: 5px;")
        stats_group_layout.addWidget(stats_title)

        self.plastic_counts = {}
        self.plastic_checkboxes = {}
        all_plastics = ["PET", "PE", "PP", "PS", "PVC", "기타"]
        colors = ["#258FD0", "#1CB786", "#E43C3C", "#F5A50F", "#BE5EC3", "#878787"]

        for plastic, color in zip(all_plastics, colors):
            count_layout = QHBoxLayout()
            cb = QCheckBox(plastic)
            cb.setChecked(True)
            cb.stateChanged.connect(lambda state, p=plastic: self._on_plastic_checkbox_changed(p, state))
            cb.setObjectName("plastic_checkbox")
            cb.setStyleSheet(
                f"""
                QCheckBox {{ color: {color}; font-size: 14px; font-weight: medium; }}
                QCheckBox::indicator {{ width: 16px; height: 16px; }}
                QCheckBox::indicator:checked {{ background-color: {color}; border: 1px solid {color}; border-radius: 3px; }}
                QCheckBox::indicator:unchecked {{ background-color: #FFFFFF; border: 1px solid #D4D4D4; border-radius: 3px; }}
                """
            )
            
            self.plastic_checkboxes[plastic] = cb
            count_layout.addWidget(cb)
            count_layout.addStretch()

            count = QLabel("0")
            count.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: medium;")
            self.plastic_counts[plastic] = count
            count_layout.addWidget(count)
            stats_group_layout.addLayout(count_layout)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        stats_group_layout.addWidget(line)

        # 총 처리량
        total_layout = QHBoxLayout()
        total_layout.addWidget(QLabel("<b>총 처리량:</b>"))
        total_layout.addStretch()
        self.total_count = QLabel("0")
        self.total_count.setStyleSheet("font-size: 20px; font-weight: medium; color: #000;")
        total_layout.addWidget(self.total_count)
        stats_group_layout.addLayout(total_layout)

        # 리셋 버튼
        reset_btn = QPushButton("카운터 리셋")
        reset_btn.setObjectName("reset_btn")
        reset_btn.setFixedHeight(40)
        reset_btn.clicked.connect(self.on_reset_counter)
        stats_group_layout.addWidget(reset_btn)

        side_panel_layout.addWidget(stats_group)
        side_panel_layout.addStretch()

        camera_layout.addLayout(side_panel_layout)
        hyper_layout.addLayout(camera_layout)
        parent_layout.addLayout(hyper_layout)
        
    def on_start_all(self):
        """전체 시작"""
        log("모든 카메라 시작")
        if self.ai_manager:
            self.ai_manager.start()

        for camera in self.rgb_cameras:
            camera.start_camera()

    def on_stop_all(self):
        """전체 정지"""
        log("모든 카메라 정지")
        if self.ai_manager:
            self.ai_manager.stop()

        for camera in self.rgb_cameras:
            camera.stop_camera()
        # if self.hyper_camera:
        #     self.hyper_camera.stop_camera

    # PLC_Branch에서 가져옴. 
    def on_object_detected(self, info, classification):
        """물체 감지됨"""
        
        # 추가
        if classification in self.excluded_classes:
            return
        
        # 수정
        if classification not in self.plastic_counts:
            return
        
        cur_count = int(self.plastic_counts[classification].text())
        self.plastic_counts[classification].setText(str(cur_count + 1))

        total = int(self.total_count.text())
        self.total_count.setText(str(total + 1))

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

    def _on_conf_apply(self):
        """confidence threshold 적용"""
        try:
            val = float(self.conf_input.text())
            if 0.0 <= val <= 1.0:
                self.ai_manager.confidence_threshold = val
                log(f"Confidence threshold 변경: {val}")
            else:
                log("Confidence threshold는 0~1 사이 값이어야 합니다.")
        except ValueError:
            log("Confidence threshold 입력값 오류")

    def get_selected_plastics(self):
        """선택된 플라스틱 재질 목록 반환"""
        return [name for name, cb in self.plastic_checkboxes.items() if cb.isChecked()]

    def _on_img_size_apply(self):
        """img_size 적용"""
        try:
            val = int(self.img_size_input.text())
            if val > 0:
                self.ai_manager.img_size = val
                log(f"Image Size 변경: {val}")
            else:
                log("Image Size는 0보다 큰 값이어야 합니다.")
        except ValueError:
            log("Image Size 입력값 오류")

    def _on_max_det_apply(self):
        """max_det 적용"""
        try:
            val = int(self.max_det_input.text())
            if val > 0:
                self.ai_manager.max_det = val
                log(f"Max Det 변경: {val}")
            else:
                log("Max Det는 0보다 큰 값이어야 합니다.")
        except ValueError:
            log("Max Det 입력값 오류")
        
        
    def _on_plastic_checkbox_changed(self, plastic: str, state: int):
        """체크박스 상태 변경 시 excluded_classes 업데이트"""
        if state == 2: # 체크됨
            self.excluded_classes.discard(plastic)
            log(f"{plastic} 집계 포함")
        else:   # 체크 해제됨
            self.excluded_classes.add(plastic)
            log(f"{plastic} 집계 제외")
            
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

            #setting_label {
                color: #616161;
                font-size: 15px;
                font-weight: normal;
            }

            #setting_input_field {
                background-color: #FFFFFF;
                border: 1px solid #D4D4D4;
                border-radius: 4px;
                padding: 2px 4px;
                color: #000000;
                font-size: 15px;
            }

            #setting_input_field:focus {
                border-color: #AAAAAA;
            }

            #action_apply_btn {
                background-color: #353535;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 15px;
            }

            #action_apply_btn:hover {
                background-color: #555555;
            }
            """
        )
