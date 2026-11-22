from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from Application.core import button_style, corner_style
from Application.ui.Settings.Logger import log_info

FIELD_STYLE = (
    "background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; "
    "border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;"
)

PREVIEW_BUTTON = """
QPushButton {
    background-color: rgba(35, 35, 35, 140);
    color: #FFFFFF;
    font-size: 16px;
    font-weight: bold;
    padding: 14px 28px;
    border-radius: 14px;
    border: 2px solid rgba(255, 255, 255, 25);
}
QPushButton:hover, QPushButton:focus {
    background-color: rgba(60, 60, 60, 200);
    border: 3px solid ACCENT;
}
"""

PREVIEW_TILE = """
QToolButton {
    background-color: rgba(35, 35, 35, 140);
    color: #FFFFFF;
    font-size: 16px;
    font-weight: bold;
    border-radius: 28px;
    border: 2px solid rgba(255, 255, 255, 25);
}
QToolButton:hover, QToolButton:focus {
    background-color: rgba(60, 60, 60, 200);
    border: 3px solid ACCENT;
}
"""


class ButtonStyleWidget(QScrollArea):
    """Edit the shared button look with a live example."""

    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent; border: none;")
        accent = launcher.get_theme_color()

        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet(
            "QWidget#settingsCard { background-color: rgba(22, 22, 22, 200); "
            "border: 1px solid rgba(255, 255, 255, 30); border-radius: 14px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(18)

        title = QLabel("Buttons")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        description = QLabel(
            "Customize every button in the launcher and settings. Hover over the examples to preview the hover effect."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(title)
        layout.addWidget(description)

        shape, style = button_style.current()
        self.shape_combo = self._combo(button_style.SHAPES, shape)
        self.width_combo = self._combo([str(w) for w in button_style.BORDER_WIDTHS], str(style["border_width"]))
        self.border_combo = self._combo(button_style.BORDER_COLORS, style["border_color"])
        self.fill_combo = self._combo(button_style.FILLS, style["fill"])
        self.hover_combo = self._combo(button_style.HOVERS, style["hover"])

        form = QFormLayout()
        form.setVerticalSpacing(12)
        for label, combo in (
            ("Shape:", self.shape_combo),
            ("Border Width:", self.width_combo),
            ("Border Color:", self.border_combo),
            ("Fill:", self.fill_combo),
            ("Hover Effect:", self.hover_combo),
        ):
            form.addRow(QLabel(label), combo)
        layout.addLayout(form)

        preview_box = QFrame()
        preview_box.setStyleSheet("background-color: rgba(10, 10, 10, 200); border-radius: 10px; border: none;")
        preview_layout = QHBoxLayout(preview_box)
        preview_layout.setContentsMargins(24, 24, 24, 24)
        preview_layout.setSpacing(24)
        self.preview_button = QPushButton("⚙ Settings")
        self.preview_tile = QToolButton()
        self.preview_tile.setText("App Tile")
        self.preview_tile.setFixedSize(130, 130)
        self.preview_tile.setIconSize(QSize(48, 48))
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        preview_layout.addWidget(self.preview_tile)
        preview_layout.addStretch()
        layout.addWidget(preview_box)

        self.save_button = QPushButton("Save Button Style")
        self.reset_button = QPushButton("Reset to Default")
        self.save_button.setStyleSheet(
            f"background-color: {accent}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;"
        )
        self.reset_button.setStyleSheet(
            "background-color: rgba(40, 40, 40, 200); color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;"
        )
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.reset_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()
        self.setWidget(card)

        for combo in (self.shape_combo, self.width_combo, self.border_combo, self.fill_combo, self.hover_combo):
            combo.currentTextChanged.connect(self.update_preview)
        self.save_button.clicked.connect(self.save)
        self.reset_button.clicked.connect(self.reset)
        self.update_preview()

    @staticmethod
    def _combo(values, current):
        combo = QComboBox()
        combo.setStyleSheet(FIELD_STYLE)
        combo.addItems(list(values))
        combo.setCurrentText(current)
        return combo

    def pending(self):
        return self.shape_combo.currentText(), {
            "border_width": int(self.width_combo.currentText()),
            "border_color": self.border_combo.currentText(),
            "fill": self.fill_combo.currentText(),
            "hover": self.hover_combo.currentText(),
        }

    def update_preview(self, *_args):
        accent = self.launcher.get_theme_color()
        shape, style = self.pending()
        for widget, css in ((self.preview_button, PREVIEW_BUTTON), (self.preview_tile, PREVIEW_TILE)):
            corner_style.apply_preview(widget, css.replace("ACCENT", accent), accent, shape, style)

    def reset(self):
        self.shape_combo.setCurrentText("Rounded Square")
        self.width_combo.setCurrentText(str(button_style.DEFAULT_BUTTON_STYLE["border_width"]))
        self.border_combo.setCurrentText(button_style.DEFAULT_BUTTON_STYLE["border_color"])
        self.fill_combo.setCurrentText(button_style.DEFAULT_BUTTON_STYLE["fill"])
        self.hover_combo.setCurrentText(button_style.DEFAULT_BUTTON_STYLE["hover"])

    def save(self):
        shape, style = self.pending()
        self.launcher.config["_button_shape"] = shape
        self.launcher.config["_button_style"] = style
        self.launcher.save_config_file()
        self.launcher.apply_accessibility_settings()
        corner_style.restyle_all()
        self.launcher.refresh_applications_view()
        log_info(f"Button style saved: shape '{shape}', {style}")
        QMessageBox.information(self, "Success", "Button style updated!")
