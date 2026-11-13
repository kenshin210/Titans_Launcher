"""Accessibility and quick-settings shortcut preferences."""

from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QKeySequenceEdit,
    QVBoxLayout,
    QWidget,
)

from Application.ui.Settings.Logger import log_info


class AccessibilitySettingsWidget(QWidget):
    """Configure visual accessibility and the Control Centre shortcut."""

    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Accessibility")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        description = QLabel(
            "Adjust visibility and motion preferences. The Control Centre shortcut "
            "works while Titans is the active application."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.focus_checkbox = QCheckBox("Show a clear focus indicator")
        self.focus_checkbox.setChecked(launcher.config.get("_show_focus_indicators", True))
        layout.addWidget(self.focus_checkbox)

        self.contrast_checkbox = QCheckBox("High-contrast interface")
        self.contrast_checkbox.setChecked(launcher.config.get("_high_contrast", False))
        layout.addWidget(self.contrast_checkbox)

        self.large_text_checkbox = QCheckBox("Larger interface text")
        self.large_text_checkbox.setChecked(launcher.config.get("_large_text", False))
        layout.addWidget(self.large_text_checkbox)

        self.reduce_motion_checkbox = QCheckBox("Reduce motion and disable transitions")
        self.reduce_motion_checkbox.setChecked(launcher.config.get("_reduce_motion", False))
        layout.addWidget(self.reduce_motion_checkbox)

        form = QFormLayout()
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

        self.shortcut_edit = QKeySequenceEdit(
            QKeySequence(launcher.config.get("_control_centre_shortcut", "Ctrl+Shift+Space"))
        )
        form.addRow("Control Centre shortcut:", self.shortcut_edit)
        layout.addLayout(form)
        layout.addStretch()

        for checkbox in (
            self.focus_checkbox,
            self.contrast_checkbox,
            self.large_text_checkbox,
            self.reduce_motion_checkbox,
        ):
            checkbox.toggled.connect(self.save_preferences)
        self.palette_combo.currentTextChanged.connect(self.save_preferences)
        self.shortcut_edit.keySequenceChanged.connect(self.save_shortcut)

    def save_preferences(self, *_args):
        self.launcher.config["_show_focus_indicators"] = self.focus_checkbox.isChecked()
        self.launcher.config["_high_contrast"] = self.contrast_checkbox.isChecked()
        self.launcher.config["_large_text"] = self.large_text_checkbox.isChecked()
        self.launcher.config["_reduce_motion"] = self.reduce_motion_checkbox.isChecked()
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

    def save_shortcut(self, sequence):
        shortcut = sequence.toString(QKeySequence.SequenceFormat.PortableText)
        self.launcher.config["_control_centre_shortcut"] = shortcut
        self.launcher.save_config_file()
        self.launcher.update_control_centre_shortcut(shortcut)
        log_info(f"Updated Control Centre shortcut: {shortcut or 'disabled'}")
