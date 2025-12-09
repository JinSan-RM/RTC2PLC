"""
모니터링 페이지 - 카메라 스트림
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QFrame, QComboBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from src.AI.predict_AI import AIPlasticDetectionSystem
import sys
import cv2
import numpy as np
class CameraView(QFrame):
    """카메라 뷰 위젯"""
    
    def __init__(self, camera_id, camera_name):
        super().__init__()
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.detector = AIPlasticDetectionSystem(
            confidence_threshold=0.7,
            img_size=640,
        )
        self.detector_frame_generator = self.detector.run()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        
        self.init_ui()
        
    
    def init_ui(self):
        """UI 초기화"""
        self.setObjectName("camera_view")
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # 헤더
        header_layout = QHBoxLayout()
        
        # 카메라 이름
        title = QLabel(self.camera_name)
        title.setObjectName("camera_title")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # 상태 표시
        self.status = QLabel("🟢 연결됨")
        self.status.setObjectName("camera_status")
        header_layout.addWidget(self.status)
        
        layout.addLayout(header_layout)
        
        # 카메라 화면
        self.image_label = QLabel()
        self.image_label.setObjectName("camera_frame")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(380, 260)
        self.image_label.setText("📷 카메라 대기 중...")
        self.image_label.setStyleSheet("""
            background-color: #000000;
            color: #8b949e;
            font-size: 14px;
            border: 2px solid #30363d;
            border-radius: 5px;
        """)
        layout.addWidget(self.image_label)
        
        # 하단 정보
        info_layout = QHBoxLayout()
        
        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setStyleSheet("color: #8b949e; font-size: 11px;")
        info_layout.addWidget(self.fps_label)
        
        info_layout.addStretch()
        
        self.resolution = QLabel("해상도: 1920x1080")
        self.resolution.setStyleSheet("color: #8b949e; font-size: 11px;")
        info_layout.addWidget(self.resolution)
        
        layout.addLayout(info_layout)

    def update_frame(self):
        """카메라 프레임 업데이트"""
        try:
            # predict_AI.py의 run()해서 프레임 가져오기
            frame = next(self.detector_frame_generator)
            
            if frame is not None:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_frame.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qt_image)
                
                # QLabel의 크기에 맞춰서 스케일링
                scaled_pixmap = pixmap.scaled(
                    self.image_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                
                self.image_label.setPixmap(scaled_pixmap)
        except StopIteration:
            # 제너레이터 종료
            self.timer.stop()
            print("카메라 프레임 업데이트 종료")
        except Exception as e:
            print(f"카메라 프레임 업데이트 오류: {e}")
    
    def update_status(self, connected):
        """상태 업데이트"""
        if connected:
            self.status.setText("🟢 연결됨")
            self.status.setStyleSheet("color: #3fb950; font-size: 12px; font-weight: bold;")
        else:
            self.status.setText("🔴 연결 끊김")
            self.status.setStyleSheet("color: #f85149; font-size: 12px; font-weight: bold;")


class MonitoringPage(QWidget):
    """모니터링 페이지 - 카메라 스트림"""
    
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rgb_cameras = []
        self.hyper_camera = None
        self.init_ui()
        
        # 업데이트 타이머
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_cameras)
        self.timer.start(33)  # 30 FPS
        
        self.plastic_counts = {}             # 플라스틱 종류별 카운트 라벨
        self.total_count = QLabel()          # 총 처리량 라벨
    
    def init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 상단: 제어 패널
        self.create_control_panel(main_layout)
        
        # 중단: RGB 카메라 (2x2)
        self.create_rgb_cameras(main_layout)
        
        # 하단: 초분광 카메라
        self.create_hyperspectral_camera(main_layout)
        
        # 스타일 적용
        self.apply_styles()
    
    def create_control_panel(self, parent_layout):
        """제어 패널"""
        control_group = QGroupBox("제어")
        control_group.setObjectName("group_box")
        control_layout = QHBoxLayout(control_group)
        control_layout.setSpacing(15)
        
        # 전체 시작/정지
        start_all_btn = QPushButton("전체 시작")
        start_all_btn.setObjectName("control_btn_start")
        start_all_btn.setMinimumHeight(45)
        start_all_btn.clicked.connect(self.on_start_all)
        control_layout.addWidget(start_all_btn)
        
        stop_all_btn = QPushButton("전체 정지")
        stop_all_btn.setObjectName("control_btn_stop")
        stop_all_btn.setMinimumHeight(45)
        stop_all_btn.clicked.connect(self.on_stop_all)
        control_layout.addWidget(stop_all_btn)
        
        # 스냅샷
        snapshot_btn = QPushButton("스냅샷")
        snapshot_btn.setObjectName("control_btn_snapshot")
        snapshot_btn.setMinimumHeight(45)
        snapshot_btn.clicked.connect(self.on_snapshot)
        control_layout.addWidget(snapshot_btn)
        
        # 녹화
        self.record_btn = QPushButton("녹화 시작")
        self.record_btn.setObjectName("control_btn_record")
        self.record_btn.setCheckable(True)
        self.record_btn.setMinimumHeight(45)
        self.record_btn.clicked.connect(self.on_record)
        control_layout.addWidget(self.record_btn)
        
        # 해상도 선택
        control_layout.addWidget(QLabel("해상도:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.setObjectName("combo_box")
        self.resolution_combo.addItems(["1920x1080", "1280x720", "640x480"])
        control_layout.addWidget(self.resolution_combo)
        
        control_layout.addStretch()
        
        parent_layout.addWidget(control_group)
    
    def create_rgb_cameras(self, parent_layout):
        """RGB 카메라 그리드"""
        rgb_group = QGroupBox("RGB 카메라")
        rgb_group.setObjectName("group_box")
        rgb_layout = QGridLayout(rgb_group)
        rgb_layout.setSpacing(15)
        
        # 4개의 RGB 카메라
        self.rgb_cameras = []
        
        # 카메라 추가할 떄에는 이걸 주석 풀어서 하나씩 추가
        cameras = [
            ("RGB 카메라 1", 0, 0),
            # ("RGB 카메라 2", 0, 1),
            # ("RGB 카메라 3", 1, 0),
            # ("RGB 카메라 4", 1, 1),
        ]
        
        for name, row, col in cameras:
            cam = CameraView(f"rgb_{row}{col}", name)
            rgb_layout.addWidget(cam, row, col)
            self.rgb_cameras.append(cam)
        
        parent_layout.addWidget(rgb_group)
    
    def create_hyperspectral_camera(self, parent_layout):
        """초분광 카메라"""
        hyper_group = QGroupBox("초분광 카메라 (플라스틱 분류)")
        hyper_group.setObjectName("group_box")
        hyper_layout = QVBoxLayout(hyper_group)
        
        # 카메라 뷰
        camera_layout = QHBoxLayout()
        
        self.hyper_camera = CameraView("hyperspectral", "Specim FX17")
        self.hyper_camera.setMinimumSize(600, 400)
        camera_layout.addWidget(self.hyper_camera)
        
        # 우측: 분류 통계
        stats_frame = QFrame()
        stats_frame.setObjectName("stats_frame")
        stats_frame.setMaximumWidth(300)
        stats_layout = QVBoxLayout(stats_frame)
        
        stats_title = QLabel("실시간 분류 통계")
        stats_title.setStyleSheet("color: #58a6ff; font-size: 14px; font-weight: bold;")
        stats_layout.addWidget(stats_title)
        
        stats_layout.addSpacing(10)
        
        # 플라스틱 종류별 카운트
        self.plastic_counts = {}
        plastics = ["PET", "PE", "PP", "PS", "PVC", "기타"]
        colors = ["#58a6ff", "#3fb950", "#f85149", "#d29922", "#bc4c00", "#8b949e"]
        
        for plastic, color in zip(plastics, colors):
            count_layout = QHBoxLayout()
            
            label = QLabel(plastic)
            label.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
            count_layout.addWidget(label)
            
            count_layout.addStretch()
            
            count = QLabel("0")
            count.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
            self.plastic_counts[plastic] = count
            count_layout.addWidget(count)
            
            stats_layout.addLayout(count_layout)
        
        stats_layout.addSpacing(10)
        
        # 총 처리량
        total_layout = QHBoxLayout()
        total_label = QLabel("총 처리량:")
        total_label.setStyleSheet("color: #c9d1d9; font-size: 14px; font-weight: bold;")
        total_layout.addWidget(total_label)
        
        total_layout.addStretch()
        
        self.total_count = QLabel("0")
        self.total_count.setStyleSheet("color: #58a6ff; font-size: 20px; font-weight: bold;")
        total_layout.addWidget(self.total_count)
        
        stats_layout.addLayout(total_layout)
        
        # 리셋 버튼
        reset_btn = QPushButton("카운터 리셋")
        reset_btn.setObjectName("reset_btn")
        reset_btn.setMinimumHeight(40)
        reset_btn.clicked.connect(self.on_reset_counter)
        stats_layout.addWidget(reset_btn)
        
        stats_layout.addStretch()
        
        camera_layout.addWidget(stats_frame)
        hyper_layout.addLayout(camera_layout)
        
        parent_layout.addWidget(hyper_group)
    
    def update_cameras(self):
        """⭐ 카메라 프레임 업데이트 - 간단하게!"""
        # RGB 카메라들 업데이트
        for camera in self.rgb_cameras:
            camera.update_frame()
    
    def on_start_all(self):
        """전체 시작"""
        self.app.on_log("모든 카메라 시작")
        # TODO: 모든 카메라 시작
    
    def on_stop_all(self):
        """전체 정지"""
        self.app.on_log("모든 카메라 정지")
        # TODO: 모든 카메라 정지
    
    def on_snapshot(self):
        """스냅샷"""
        self.app.on_log("스냅샷 저장")
        # TODO: 현재 프레임 저장
    
    def on_record(self, checked):
        """녹화"""
        if checked:
            self.record_btn.setText("⏹ 녹화 중지")
            self.app.on_log("녹화 시작")
            # TODO: 녹화 시작
        else:
            self.record_btn.setText("⏺ 녹화 시작")
            self.app.on_log("녹화 중지")
            # TODO: 녹화 중지
    
    def on_reset_counter(self):
        """카운터 리셋"""
        self.app.on_log("분류 카운터 리셋")
        for count_label in self.plastic_counts.values():
            count_label.setText("0")
        self.total_count.setText("0")
        # TODO: 실제 카운터 리셋
    
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
        #     self.status_value.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
    
    def apply_styles(self):
        """스타일시트 적용"""
        self.setStyleSheet("""
            QGroupBox {
                background-color: #0d1117;
                border: 2px solid #30363d;
                border-radius: 8px;
                padding-top: 15px;
                margin-top: 10px;
                font-size: 14px;
                font-weight: bold;
                color: #c9d1d9;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 3px 10px;
                color: #58a6ff;
            }
            
            #camera_view {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 8px;
            }
            
            #camera_title {
                color: #58a6ff;
                font-size: 13px;
                font-weight: bold;
            }
            
            #stats_frame {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 8px;
                padding: 15px;
            }
            
            QLabel {
                color: #c9d1d9;
            }
            
            #combo_box {
                background-color: #161b22;
                border: 2px solid #30363d;
                border-radius: 5px;
                padding: 5px 10px;
                color: #c9d1d9;
                min-width: 120px;
            }
            
            #combo_box:hover {
                border-color: #58a6ff;
            }
            
            #combo_box::drop-down {
                border: none;
            }
            
            #combo_box QAbstractItemView {
                background-color: #161b22;
                border: 2px solid #30363d;
                color: #c9d1d9;
                selection-background-color: #58a6ff;
            }
            
            #control_btn_start {
                background-color: #238636;
                color: white;
                border: 2px solid #2ea043;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #control_btn_start:hover {
                background-color: #2ea043;
            }
            
            #control_btn_stop {
                background-color: #da3633;
                color: white;
                border: 2px solid #f85149;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #control_btn_stop:hover {
                background-color: #f85149;
            }
            
            #control_btn_snapshot, #control_btn_record {
                background-color: #1f6feb;
                color: white;
                border: 2px solid #58a6ff;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            
            #control_btn_snapshot:hover, #control_btn_record:hover {
                background-color: #58a6ff;
            }
            
            #control_btn_record:checked {
                background-color: #da3633;
                border-color: #f85149;
            }
            
            #reset_btn {
                background-color: #6e7681;
                color: white;
                border: 2px solid #8b949e;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            
            #reset_btn:hover {
                background-color: #8b949e;
            }
        """)