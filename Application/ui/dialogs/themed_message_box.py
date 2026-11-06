from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...styles import load_stylesheet


class ThemedMessageBox(QDialog):
    def __init__(self, parent=None, title="", message="", theme_color="#DC143C"):
        super().__init__(parent)
        self.setObjectName("themedMessageBox")
        self.setStyleSheet(load_stylesheet(theme_color=theme_color))
        self.setWindowTitle(title)
        self.setFixedSize(420, 180)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        card = QWidget(self)
        card.setObjectName("msgCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(25, 25, 25, 25)
        card_layout.setSpacing(15)

        message_label = QLabel(message, card)
        message_label.setObjectName("messageLabel")
        message_label.setWordWrap(True)
        card_layout.addWidget(message_label)
        card_layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        self.yes_btn = QPushButton("Yes", card)
        self.yes_btn.setObjectName("dialogPrimaryButton")
        self.yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.yes_btn.clicked.connect(self.accept)

        self.no_btn = QPushButton("No", card)
        self.no_btn.setObjectName("dialogSecondaryButton")
        self.no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.no_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.no_btn)
        button_layout.addWidget(self.yes_btn)
        card_layout.addLayout(button_layout)
        layout.addWidget(card)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
