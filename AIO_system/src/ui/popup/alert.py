from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer


class CustomPopup(QDialog):
    """메인 UI 스타일과 통일된 커스텀 팝업"""

    def __init__(self, parent, title, message, type_="info"):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)
        self.setObjectName("popup")

        # 크기 
        self.setMinimumSize(360, 200)
        self.setMaximumWidth(420)

        # 타입별 색상&아이콘
        if type_ == "info":
            border_color = "#2DB591"
            btn_color = "#2DB591"
            icon = "🔔"

        elif type_ == "warning":
                    border_color = "#FFA500"   # 🟠 경고 = 주황
                    btn_color = "#FFA500"
                    icon = "⚠️"

        elif type_ == "error":
            border_color = "#FF2427"   # 🔴 정지 = 빨강
            btn_color = "#FF2427"
            icon = "🔴"
        else: 
             border_color, btn_color, icon = "#4A90E2", "#4A90E2", "❓"

        # 스타일
        self.setStyleSheet(f"""
            QDialog#popup {{
                background-color: #FFFFFF;
                border: 2px solid {border_color};
                border-radius: 10px;
            }}

            QLabel#title {{
                font-size: 16px;
                font-weight: bold;
                color: #2D3039;
            }}

            QLabel#message {{
                color: #000000;
                font-family: 'Pretendard';
                font-size: 14px;
                padding-top: 6px;
                padding-bottom: 6px;
            }}

            QPushButton {{
                background-color: {btn_color};
                color: #FFFFFF;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }}

            QPushButton:hover {{
                opacity: 0.8;
            }}
        """)

        # 그림자
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

        # 타이틀
        title_label = QLabel(f"{icon} {title}")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)

        # 메시지 
        message_label = QLabel(message)
        message_label.setObjectName("message")
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setMinimumHeight(60)
        message_label.setContentsMargins(0, 6, 0, 6)

        # 레이아웃
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        layout.addWidget(title_label)
        layout.addWidget(message_label)
        layout.addStretch()

        # 버튼 영역
        btn_layout = QHBoxLayout()

        if type_ == "confirm":
            ok_btn = QPushButton("확인")
            cancel_btn = QPushButton("취소")

            ok_btn.clicked.connect(self.accept)
            cancel_btn.clicked.connect(self.reject)

            btn_layout.addStretch()
            btn_layout.addWidget(ok_btn)
            btn_layout.addWidget(cancel_btn)
            btn_layout.addStretch()

        else:
            btn = QPushButton("확인")
            btn.clicked.connect(self.accept)

            btn_layout.addStretch()
            btn_layout.addWidget(btn)
            btn_layout.addStretch()

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.move_to_center()

    def move_to_center(self):
        """부모 창 기준 중앙 정렬"""
        if self.parent():
            parent_geom = self.parent().geometry()
            self.move(
                parent_geom.center().x() - self.width() // 2,
                parent_geom.center().y() - self.height() // 2
            )


class PopUp:
    """팝업 호출용 클래스"""

    def __init__(self, main_window):
        self.main_window = main_window
        self._last_popup = None

    def info(self, message):
        popup = CustomPopup(self.main_window, "알림", message, "info")
        self._last_popup = popup
        popup.show()

    def warning(self, message):
        CustomPopup(self.main_window, "경고", message, "warning").exec()

    def error(self, message):
        CustomPopup(self.main_window, "에러", message, "error").exec()

    # except 부분의 메시지 내용