"""Settings for the launcher-local screensaver."""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QFormLayout, QHBoxLayout, QLabel, QListWidget, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from Application.ui.dialogs.file_picker import ControllerFileDialog
from Application.ui.Settings.Logger import log_warning


class ScreensaverSettingsWidget(QWidget):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        layout = QVBoxLayout(self)
        title = QLabel("Screensaver")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        description = QLabel("Rotate local images and videos while Titans is visible and idle.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.enabled = QCheckBox("Enable screensaver")
        self.enabled.setChecked(launcher.config.get("_screensaver_enabled", False))
        layout.addWidget(self.enabled)
        self.idle = QSpinBox()
        self.idle.setRange(10, 86400)
        self.idle.setSuffix(" seconds")
        self.idle.setValue(self._seconds("_screensaver_idle_seconds", 300, 10, 86400))
        self.rotation = QSpinBox()
        self.rotation.setRange(5, 3600)
        self.rotation.setSuffix(" seconds")
        self.rotation.setValue(self._seconds("_screensaver_rotation_seconds", 30, 5, 3600))
        form = QFormLayout()
        form.addRow("Idle time:", self.idle)
        form.addRow("Change media every:", self.rotation)
        layout.addLayout(form)
        self.items = QListWidget()
        items = launcher.config.get("_screensaver_items", [])
        if isinstance(items, list):
            self.items.addItems([item for item in items if isinstance(item, str)])
        layout.addWidget(self.items, stretch=1)
        buttons = QHBoxLayout()
        add = QPushButton("Add Image or Video")
        add.clicked.connect(self.add_item)
        remove = QPushButton("Remove Selected")
        remove.clicked.connect(self.remove_item)
        save = QPushButton("Save Screensaver")
        save.clicked.connect(self.save)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addWidget(save)
        buttons.addStretch()
        layout.addLayout(buttons)

    def _seconds(self, key, default, minimum, maximum):
        value = self.launcher.config.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            log_warning(f"Invalid screensaver setting {key}; using {default}.")
            return default
        return value

    def add_item(self):
        path, _ = ControllerFileDialog.get_open_file_name(
            self, "Select Screensaver Media", str(Path.home()),
            "Images and videos (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.mp4 *.mkv *.webm *.avi *.mov);;All Files (*)",
        )
        if path and not self.items.findItems(path, Qt.MatchFlag.MatchExactly):
            self.items.addItem(path)

    def remove_item(self):
        row = self.items.currentRow()
        if row >= 0:
            self.items.takeItem(row)

    def save(self):
        items = [self.items.item(index).text() for index in range(self.items.count())]
        missing = [path for path in items if not Path(path).is_file()]
        if missing:
            QMessageBox.warning(self, "Screensaver", "A selected file is missing:\n" + missing[0])
            return
        if self.enabled.isChecked() and not items:
            QMessageBox.warning(self, "Screensaver", "Add at least one image or video first.")
            return
        self.launcher.config.update({
            "_screensaver_enabled": self.enabled.isChecked(),
            "_screensaver_idle_seconds": self.idle.value(),
            "_screensaver_rotation_seconds": self.rotation.value(),
            "_screensaver_items": items,
        })
        self.launcher.save_config_file()
        self.launcher.screensaver.activity()
        QMessageBox.information(self, "Screensaver", "Screensaver settings saved.")
