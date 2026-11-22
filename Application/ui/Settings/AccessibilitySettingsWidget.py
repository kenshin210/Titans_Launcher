"""Accessibility preferences."""

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from Application.core.accessibility import (
    FOCUS_MODES,
    TEXT_SCALES,
    focus_indicator_mode,
    text_scale_percent,
)
from Application.ui.Settings.Logger import log_info


class AccessibilitySettingsWidget(QWidget):
    """Configure visual accessibility preferences."""

    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Accessibility")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        description = QLabel("Adjust visibility and motion preferences.")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.contrast_checkbox = QCheckBox("High-contrast interface")
        self.contrast_checkbox.setChecked(launcher.config.get("_high_contrast", False))
        layout.addWidget(self.contrast_checkbox)

        self.reduce_motion_checkbox = QCheckBox("Reduce motion and disable transitions")
        self.reduce_motion_checkbox.setChecked(launcher.config.get("_reduce_motion", False))
        layout.addWidget(self.reduce_motion_checkbox)

        self.control_centre_checkbox = QCheckBox(
            "Show the Control Centre button on the main screen"
        )
        self.control_centre_checkbox.setChecked(
            launcher.config.get("_show_control_centre_button", False)
        )
        layout.addWidget(self.control_centre_checkbox)

        form = QFormLayout()
        self.focus_combo = QComboBox()
        self.focus_combo.addItems(FOCUS_MODES)
        self.focus_combo.setCurrentText(focus_indicator_mode(launcher.config))
        form.addRow("Focus indicator:", self.focus_combo)

        self.text_scale_combo = QComboBox()
        for percent in TEXT_SCALES:
            self.text_scale_combo.addItem(f"{percent}%", percent)
        index = self.text_scale_combo.findData(text_scale_percent(launcher.config))
        self.text_scale_combo.setCurrentIndex(max(index, 0))
        form.addRow("Interface text size:", self.text_scale_combo)

        self.palette_combo = QComboBox()
        self.palette_combo.addItems(
            ["Standard", "Colorblind Blue", "Colorblind Orange", "Colorblind Purple"]
        )
        current_theme = launcher.config.get("_theme", "Crimson Red")
        self.palette_combo.setCurrentText(
            current_theme if current_theme in (
                "Colorblind Blue", "Colorblind Orange", "Colorblind Purple"
            ) else "Standard"
        )
        form.addRow("Color-vision-friendly accent:", self.palette_combo)

        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        for combo in (self.focus_combo, self.text_scale_combo, self.palette_combo):
            combo.setMinimumWidth(240)
        layout.addLayout(form)
        layout.addStretch()

        accent = getattr(launcher, "get_theme_color", lambda: "#DC143C")()
        self.setStyleSheet(
            f"""
            QCheckBox {{ spacing: 12px; padding: 6px 0; }}
            QCheckBox::indicator {{
                width: 20px; height: 20px;
                border: 2px solid rgba(255, 255, 255, 0.55);
                border-radius: 5px;
                background: rgba(0, 0, 0, 0.35);
            }}
            QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
            QCheckBox::indicator:focus {{ border-color: {accent}; }}
            """
        )

        for checkbox in (
            self.contrast_checkbox,
            self.reduce_motion_checkbox,
            self.control_centre_checkbox,
        ):
            checkbox.toggled.connect(self.save_preferences)
        self.palette_combo.currentTextChanged.connect(self.save_preferences)
        self.focus_combo.currentIndexChanged.connect(self.save_preferences)
        self.text_scale_combo.currentIndexChanged.connect(self.save_preferences)

    def save_preferences(self, *_args):
        mode = self.focus_combo.currentText()
        self.launcher.config["_focus_indicator"] = mode
        self.launcher.config["_show_focus_indicators"] = mode != "Off"
        self.launcher.config["_high_contrast"] = self.contrast_checkbox.isChecked()
        percent = self.text_scale_combo.currentData()
        self.launcher.config["_text_scale"] = percent
        self.launcher.config["_large_text"] = percent > 100
        self.launcher.config["_reduce_motion"] = self.reduce_motion_checkbox.isChecked()
        self.launcher.config["_show_control_centre_button"] = (
            self.control_centre_checkbox.isChecked()
        )
        palette = self.palette_combo.currentText()
        if palette == "Standard":
            current = self.launcher.config.get("_theme", "Crimson Red")
            if current.startswith("Colorblind "):
                self.launcher.config["_theme"] = "Crimson Red"
        else:
            self.launcher.config["_theme"] = palette
        self.launcher.save_config_file()
        self.launcher.apply_accessibility_settings()
        self.launcher.refresh_applications_view()
        log_info("Saved accessibility preferences")
