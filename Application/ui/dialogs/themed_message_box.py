from math import ceil

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...core.accessibility import text_scale_percent
from ...styles import load_stylesheet


class ThemedMessageBox(QDialog):
    def __init__(self, parent=None, title="", message="", theme_color="#DC143C"):
        super().__init__(parent)
        self._theme_color = theme_color
        self._text_scale = None
        self._resize_pending = False
        self._text_layout_key = None
        self.setObjectName("themedMessageBox")
        self.setWindowTitle(title)
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
        self.message_label = message_label
        self.card_layout = card_layout
        self.button_layout = button_layout
        scale = QApplication.instance().property("_text_scale")
        ancestor = parent
        while scale is None and ancestor is not None:
            config = getattr(ancestor, "config", None)
            if config is not None:
                scale = text_scale_percent(config)
                break
            ancestor = ancestor.parentWidget()
        self.apply_text_scale(scale if scale is not None else 100)

    def apply_text_scale(self, percent):
        if self._text_scale == percent:
            return
        self._text_scale = percent
        scale = percent / 100
        self.setStyleSheet(load_stylesheet(theme_color=self._theme_color) + f"""
            QLabel#messageLabel {{ font-size: {16 * scale:g}px; }}
            QPushButton#dialogPrimaryButton, QPushButton#dialogSecondaryButton {{
                font-size: {14 * scale:g}px;
                padding: {10 * scale:g}px {20 * scale:g}px;
            }}
        """)
        margin = ceil(25 * scale)
        self.card_layout.setContentsMargins(margin, margin, margin, margin)
        self.card_layout.setSpacing(ceil(15 * scale))
        self.button_layout.setSpacing(ceil(12 * scale))
        self._fit_to_text()

    def event(self, event):
        result = super().event(event)
        if (
            event.type() == QEvent.Type.LayoutRequest
            and hasattr(self, "message_label")
            and not self._resize_pending
        ):
            self._resize_pending = True
            QTimer.singleShot(0, self._fit_to_text)
        return result

    def showEvent(self, event):
        self._fit_to_text()
        super().showEvent(event)

    def _fit_to_text(self):
        self._resize_pending = False
        scale = self._text_scale / 100
        label = self.message_label
        label.ensurePolished()
        metrics = label.fontMetrics()
        text_width = max((metrics.horizontalAdvance(line) for line in label.text().splitlines()), default=0)
        margins = self.card_layout.contentsMargins()
        horizontal_padding = margins.left() + margins.right() + ceil(4 * scale)
        buttons = [button for button in (self.no_btn, self.yes_btn) if not button.isHidden()]
        for button in buttons:
            button.ensurePolished()
            text = button.text().replace("&", "")
            width = ceil(button.fontMetrics().horizontalAdvance(text) * 1.15 + 40 * scale)
            button.setMinimumWidth(max(width, button.sizeHint().width()))
        buttons_width = sum(button.minimumWidth() for button in buttons)
        buttons_width += max(0, len(buttons) - 1) * self.button_layout.spacing()
        width = max(
            ceil(460 * scale),
            ceil(text_width * 1.15) + horizontal_padding,
            buttons_width + horizontal_padding,
        )
        width = ceil(width * 1.25)
        # Long messages wrap rather than extending beyond the display.
        width = min(width, max(1, self.screen().availableGeometry().width() - ceil(40 * scale)))
        text_layout_key = (label.text(), label.font().toString(), width, horizontal_padding)
        if self._text_layout_key != text_layout_key:
            self._text_layout_key = text_layout_key
            # QLabel's heightForWidth includes its minimum height; measure without
            # the previous headroom to avoid compounding it on each layout pass.
            label.setMinimumHeight(0)
            text_height = label.heightForWidth(max(1, width - horizontal_padding))
            label.setMinimumHeight(ceil(text_height * 1.15))
        self.layout().invalidate()
        height = max(ceil(220 * scale), self.layout().totalHeightForWidth(width))
        self.setMinimumSize(width, height)
        self.resize(width, height)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
