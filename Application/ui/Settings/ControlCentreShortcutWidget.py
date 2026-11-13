from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QFormLayout, QLabel, QKeySequenceEdit, QVBoxLayout, QWidget

from Application.ui.Settings.Logger import log_info


class ControlCentreShortcutWidget(QWidget):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Control Centre")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel(
            "Choose one key combination to open the Control Centre from any "
            "application. Global activation requires read access to keyboard "
            "devices under /dev/input."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        self.shortcut_edit = QKeySequenceEdit(
            QKeySequence(launcher.config.get("_control_centre_shortcut", "Ctrl+Shift+Space"))
        )
        self.shortcut_edit.setMaximumSequenceLength(1)
        form.addRow("Keyboard shortcut:", self.shortcut_edit)
        layout.addLayout(form)

        self.shortcut_edit.keySequenceChanged.connect(self.save_shortcut)

    def save_shortcut(self, sequence):
        shortcut = sequence.toString(QKeySequence.SequenceFormat.PortableText)
        self.launcher.config["_control_centre_shortcut"] = shortcut
        self.launcher.save_config_file()
        self.launcher.update_control_centre_shortcut(shortcut)
        log_info(f"Updated Control Centre shortcut: {shortcut or 'disabled'}")
