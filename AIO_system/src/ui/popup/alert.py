from PySide6.QtWidgets import (
    QDialog, QLabel, QPushButton, 
    QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt

class CustomPopup(QDialog):
    def __init__(self, parent, title, message, type_="info"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setObjectName("popup")
        self.setMinimumSize(360, 200)

        # 타입별 색상 및 아이콘 설정
        if type_ == "info":
            color, icon = "#2DB591", "🔔"
        elif type_ == "warning":
            color, icon = "#FFA500", "⚠️"
        elif type_ == "error":
            color, icon = "#FF2427", "🔴"
        else: # confirm 포함
            color, icon = "#4A90E2", "❓"

        # 스타일시트
        self.setStyleSheet(f"""
            QDialog#popup {{
                background-color: #FFFFFF;
                border: 2px solid {color};
                border-radius: 10px;
            }}
            QLabel#title {{
                font-size: 16px; font-weight: bold; color: {color};
            }}
            QLabel#message {{
                color: #000000; font-size: 14px;
            }}
            QPushButton {{
                background-color: {color};
                color: #FFFFFF; border-radius: 6px; padding: 6px 12px; font-weight: bold;
            }}
        """)

        # 레이아웃 구성
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # 타이틀
        title_label = QLabel(f"{icon} {title}")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)

        # 메시지
        message_label = QLabel(message)
        message_label.setObjectName("message")
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(message_label)
        layout.addStretch()

        # 4. 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        if type_ == "confirm":
            cancel_btn = QPushButton("취소")
            cancel_btn.clicked.connect(self.reject)
            btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("확인")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 5. 효과 및 중앙 정렬
        self._apply_effects()
        self.move_to_center()

    def _apply_effects(self):
        shadow = QGraphicsDropShadowEffect(self, blurRadius=20, xOffset=0, yOffset=0)
        self.setGraphicsEffect(shadow)

    def move_to_center(self):
        if self.parent():
            p = self.parent().geometry()
            self.move(p.center().x() - self.width()//2, p.center().y() - self.height()//2)
    

class PopUp:
    def __init__(self, main_window):
        self.main_window = main_window

    def show_message(self, popup_type: str, title: str, message: str):
        popup = CustomPopup(self.main_window, title, message, popup_type)
        
        if popup_type == "info":
            popup.show()
        else: 
            popup.exec()
    
    # def info(self, message, title="알림"):
    #     self.show_message("info", title, message)

    # def warning(self, message, title="경고"):
    #     self.show_message("warning", title, message)

    # def error(self, message, title="에러"):
    #     self.show_message("error", title, message)