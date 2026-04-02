"""
PiP (Picture-in-Picture) 창 및 매니저

- PiPWindow  : 항상 최상단에 떠 있는 플로팅 영상 창
- PiPManager : 카메라 연결/해제 및 페이지 전환에 따른 표시/숨김 제어
"""
import cv2

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
from PySide6.QtCore import Qt, QTimer, QPoint, Signal
from PySide6.QtGui import QPixmap, QImage

from src.utils.logger import log


MONITORING_PAGE_INDEX = 1   #  모니터링 페이지를 1이라고 정의해둔 거

# 원본 기준 해상도(고정값)와 비율. 창 크기는 이 기준으로 1회 계산 후 고정 유지.
_SRC_REF_W = 1920
_SRC_REF_H = 1080
_PIP_SCALE = 0.40
_PIP_W = max(1, int(_SRC_REF_W * _PIP_SCALE))
_PIP_H = max(1, int(_SRC_REF_H * _PIP_SCALE))
_TITLE_H = 25


class PiPWindow(QWidget):
    """
    PiP 플로팅 창

    - 항상 최상단(WindowStaysOnTopHint), 테두리 없음(FramelessWindowHint)
    - 제목바 드래그로 이동 가능
    - 렌더링은 QTimer 기반 ~15 FPS (리소스 절약)
    - 프레임은 latest만 보관, 타이머 tick마다 한 번만 그림
    """
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self._video_w = _PIP_W
        self._video_h = _PIP_H
        self._size_locked = False  # 아직 첫 프레임 들어오기 전, 화면 크기 미정 상태
        self.setFixedSize(self._video_w, self._video_h + _TITLE_H)

        self._latest_frame = None
        self._drag_active = False
        self._drag_offset = QPoint()
        self._positioned = False  # 첫 표시 시 기본 위치 설정 여부

        # 타이머: 66ms ≈ 15 FPS
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(66)
        self._render_timer.timeout.connect(self._render_frame)

        self._init_ui()
        self._apply_style()

    # ── UI 구성 ───────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 제목바 (드래그 영역)
        self._title_bar = QWidget()
        self._title_bar.setObjectName("pip_title_bar")
        self._title_bar.setFixedHeight(_TITLE_H)
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(8, 0, 4, 0)

        self._title_label = QLabel("PiP")
        self._title_label.setObjectName("pip_title_label")
        title_layout.addWidget(self._title_label)
        title_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("pip_close_btn")
        close_btn.setFixedSize(22, 22)
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)

        layout.addWidget(self._title_bar)

        # 영상 영역
        self._video_label = QLabel()
        self._video_label.setObjectName("pip_video")
        self._video_label.setAlignment(Qt.AlignCenter)
        self._video_label.setFixedSize(self._video_w, self._video_h)
        self._video_label.setText("📷 카메라 대기 중...")
        layout.addWidget(self._video_label)

    def _apply_style(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a2e;
                border: 1px solid #555;
                border-radius: 6px;
            }
            #pip_title_bar {
                background-color: #16213e;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border-bottom: 1px solid #555;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
            #pip_title_label {
                color: #dddddd;
                font-size: 18px;
                background: transparent;
                border: none;
            }
            #pip_close_btn {
                background-color: transparent;
                color: #aaaaaa;
                border: none;
                font-size: 11px;
                border-radius: 3px;
            }
            #pip_close_btn:hover {
                background-color: #c0392b;
                color: #ffffff;
            }
            #pip_video {
                background-color: #0d0d1a;
                color: #555555;
                font-size: 12px;
                border: none;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
            }
        """)

    # ── 제목 ─────────────────────────────────────────────────

    def set_title(self, title: str):
        self._title_label.setText(f"PiP  {title}")

    # ── 프레임 수신 / 렌더링 ─────────────────────────────────

    def on_new_frame(self, frame):
        """
        CameraView.pip_frame_ready 시그널로 호출됨.
        매 프레임마다 호출되지만 버퍼만 갱신 — 렌더링은 타이머가 담당.
        """
        # _size_locked = False일 때만 _lock_size_from_first_frame 호출 -> 프레임 처음 들어올 때 딱 1번만 크기 계산하도록
        if not self._size_locked:
            self._lock_size_from_first_frame(frame)
        self._latest_frame = frame

    def reset_size_lock(self):
        """카메라 변경 시 PiP 크기 잠금을 해제하고 fallback 크기로 복귀."""
        self._size_locked = False
        self._set_video_size(_PIP_W, _PIP_H)

    def _lock_size_from_first_frame(self, frame):
        """첫 프레임 해상도를 기준으로 PiP 고정 크기를 1회 확정."""
        try:
            src_h, src_w = frame.shape[:2]
            if src_w <= 0 or src_h <= 0:
                return

            # 실제 소스 해상도에 비례한 크기로 1회 확정
            target_w = max(1, int(src_w * _PIP_SCALE))
            target_h = max(1, int(src_h * _PIP_SCALE))
            self._set_video_size(target_w, target_h)
            self._size_locked = True
            log(f"PiP 크기 1회 확정: {target_w}x{target_h} (source: {src_w}x{src_h})")
        except Exception as e:
            log(f"PiP 첫 프레임 크기 확정 실패: {e}")

    def _set_video_size(self, w: int, h: int):
        """PiP 영상/창 고정 크기 적용"""
        self._video_w = max(1, int(w))
        self._video_h = max(1, int(h))
        self._video_label.setFixedSize(self._video_w, self._video_h)
        self.setFixedSize(self._video_w, self._video_h + _TITLE_H)

    def clear_frame(self):
        """소스 전환 시 이전 카메라 잔상 프레임 제거"""
        self._latest_frame = None
        self._video_label.setPixmap(QPixmap())
        self._video_label.setText("📷 카메라 대기 중...")

    def _render_frame(self):
        """타이머 tick마다 최신 프레임을 PiP 라벨에 렌더링."""
        # 크기 재계산 없이 현재 고정 크기에 맞춰 스케일링만 수행
        if self._latest_frame is None:
            return
        try:
            rgb = cv2.cvtColor(self._latest_frame, cv2.COLOR_BGR2RGB)  # pylint: disable=no-member
            h, w, ch = rgb.shape
            qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_img)
            scaled = pixmap.scaled(
                self._video_w, self._video_h,
                Qt.KeepAspectRatio,
                Qt.FastTransformation    # SmoothTransformation 보다 연산 비용 낮음
            )
            self._video_label.setPixmap(scaled)
        except Exception as e:
            log(f"PiP 렌더링 오류: {e}")

    # ── 표시 / 숨김 ──────────────────────────────────────────

    def show_pip(self):
        """PiP 창을 표시하고 필요 시 렌더 타이머를 시작."""
        already_visible = self.isVisible()
        if already_visible and self._render_timer.isActive():
            return

        if not already_visible:
            self._latest_frame = None
            if not self._positioned:  # 최초 표시 시 우측 하단에 위치
                screen = QApplication.primaryScreen().availableGeometry()
                self.move(screen.right() - self.width() - 20,
                          screen.bottom() - self.height() - 60)
                self._positioned = True
            self.show()
            self.raise_()

        if not self._render_timer.isActive():
            self._render_timer.start()

    def hide_pip(self):
        # todo monitoring page에서 hide가 아닌 stop and start action trigger로 change
        self._render_timer.stop()
        # 숨김 상태에서는 마지막 프레임 버퍼도 비워 메모리 사용을 줄임
        self._latest_frame = None
        self.hide()

    # ── 종료 ─────────────────────────────────────────────────

    def closeEvent(self, event):
        self._render_timer.stop()
        self.closed.emit()
        event.accept()

    # ── 드래그 이동 ──────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_active and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_active = False
        super().mouseReleaseEvent(event)


# ─────────────────────────────────────────────────────────────


class PiPManager:
    """
    PiP 전체 흐름 관리

    - select_camera  : 대상 카메라 설정 (frame_ready 신호 연결/해제)
    - set_enabled    : PiP 활성화 여부
    - on_page_changed: 페이지 이동 시 창 표시/숨김 결정
    - cleanup        : 앱 종료 시 정리
    """

    def __init__(self, main_window):
        """PiP 창/상태를 초기화하고 닫힘 이벤트 핸들러를 연결."""
        self._main_window = main_window
        self._window = PiPWindow()

        self._active_camera_view = None # 생성자에서 cam 할당하지 않고 설정 가능한 위치, cam 선택 가능한 위치에서 인자로 설정.
        self._enabled = False         # 사용자가 PiP 켰는지
        self._signal_connected = False
        self._current_page_index = MONITORING_PAGE_INDEX
        self._window.closed.connect(self._on_window_closed)

    def _sync_toggle_ui(self):
        """MonitoringPage의 PiP 토글 UI 상태를 내부 정책과 일치시킴"""
        try:
            monitoring_page = self._main_window.pages.monitoring_page
            toggle_btn = getattr(monitoring_page, 'pip_toggle_btn', None)
            if toggle_btn is None:
                return
            toggle_btn.blockSignals(True)
            try:
                toggle_btn.setChecked(self._enabled)
                toggle_btn.setText("on" if self._enabled else "off")
            finally:
                toggle_btn.blockSignals(False)
        except Exception:
            # UI 동기화 실패가 PiP 동작 자체를 막지 않도록 방어
            pass

    def _on_window_closed(self):
        """사용자가 PiP 창의 X 버튼으로 닫았을 때 상태를 완전히 정리"""
        self._disconnect_signal()
        self._enabled = False
        self._sync_toggle_ui()

    def _should_show_pip(self) -> bool:
        return (
            self._current_page_index != MONITORING_PAGE_INDEX
            and self._enabled
            and self._active_camera_view is not None
        )

    def _connect_signal(self):
        if not self._active_camera_view or self._signal_connected:
            return
        self._active_camera_view.pip_frame_ready.connect(self._window.on_new_frame)
        self._signal_connected = True

    def _disconnect_signal(self):
        if not self._active_camera_view or not self._signal_connected:
            return
        try:
            self._active_camera_view.pip_frame_ready.disconnect(self._window.on_new_frame)
        except RuntimeError:
            pass
        self._signal_connected = False

    def _sync_pip_state(self):
        if self._should_show_pip():
            self._connect_signal()
            self._window.show_pip()
            return

        self._disconnect_signal()
        self._window.hide_pip()

    # ── 설정 ────────────────────────────────────────────────

    def set_enabled(self, enabled: bool):
        # "사용" 플래그는 페이지 전환 훅(on_page_changed)에서 최종 판단에 사용
        # 즉 여기서는 상태만 바꾸고, 실제 show/hide는 호출 지점에서 결정
        #todo 개념 이해 status control 이 개념을 보는 곳은. typescript, react
        self._enabled = enabled
        self._sync_toggle_ui()
        self._sync_pip_state()

    def select_camera(self, camera_view):
        """PiP 대상 카메라 변경 — 기존 연결 해제 후 새 카메라에 연결"""
        if self._active_camera_view is camera_view:
            return

        # 기존 연결 해제
        self._disconnect_signal()

        self._active_camera_view = camera_view
        # 카메라가 바뀌는 이벤트에서만 크기 확정을 초기화
        self._window.reset_size_lock()
        # 새 카메라 프레임이 들어오기 전까지 이전 소스 잔상이 남지 않게 초기화
        self._window.clear_frame()

        if camera_view:
            self._window.set_title(camera_view.camera_name)
            log(f"PiP 카메라 선택: {camera_view.camera_name}")

        self._sync_pip_state()

    # ── 페이지 전환 훅 ───────────────────────────────────────

    def on_page_changed(self, page_index: int):
        """
        MainWindow.change_page 에서 호출됨.
        - 모니터링 페이지(1): PiP 숨김
        - 다른 페이지 + enabled + 카메라 선택됨: PiP 표시
        """
        #:todo 훅 개념에 대한 이해하면 좋을 것 같습니다.
        #:todo hide가 아니라 같은 페이지에서는 훅 안걸고 있도록 리소스 낭비 최적화 작업.
        self._current_page_index = page_index
        self._sync_pip_state()

    # ── 정리 ────────────────────────────────────────────────

    def cleanup(self):
        # 종료 시 signal 연결을 먼저 끊어야 
        self._disconnect_signal()
        self._window.close()