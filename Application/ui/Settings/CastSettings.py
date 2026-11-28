"""Choose an external Google Cast receiver."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget

from Application.core.cast_devices import scan_cast_devices
from Application.ui.Settings.AsyncTask import TaskRunnerMixin
from Application.ui.Settings.Logger import log_warning


class CastSettingsWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        layout = QVBoxLayout(self)
        title = QLabel("Cast Receiver")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        description = QLabel(
            "Select an external Cast-enabled receiver on the same network. "
            "Titans shows its status; the receiver handles playback."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.devices = QComboBox()
        self.devices.addItem("No receiver selected", "")
        saved = launcher.config.get("_cast_device_id", "")
        name = launcher.config.get("_cast_device_name", "")
        if isinstance(saved, str) and saved:
            self.devices.addItem(name if isinstance(name, str) and name else "Saved receiver", saved)
            self.devices.setCurrentIndex(1)
        layout.addWidget(self.devices)
        self.status = QLabel("Scan to find receivers.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.scan_button = QPushButton("Scan for Cast Receivers")
        self.scan_button.clicked.connect(self.scan)
        layout.addWidget(self.scan_button)
        self.devices.currentIndexChanged.connect(self.select_device)
        layout.addStretch()

    def scan(self):
        self.scan_button.setEnabled(False)
        self.status.setText("Scanning the local network...")
        self.run_async(scan_cast_devices, self._scan_finished)

    def _scan_finished(self, result):
        self.scan_button.setEnabled(True)
        if isinstance(result, Exception):
            log_warning(f"Cast discovery failed: {result}")
            self.status.setText(f"Cast discovery failed: {result}")
            return
        devices, _status = result
        current = self.devices.currentData()
        self.devices.blockSignals(True)
        self.devices.clear()
        self.devices.addItem("No receiver selected", "")
        for device in devices:
            self.devices.addItem(device.name, device.identifier)
        index = self.devices.findData(current)
        if index < 0 and current:
            name = self.launcher.config.get("_cast_device_name", "Saved receiver")
            self.devices.addItem(f"{name} (not found)", current)
            index = self.devices.count() - 1
        self.devices.setCurrentIndex(max(index, 0))
        self.devices.blockSignals(False)
        self.status.setText(f"Found {len(devices)} Cast receiver(s).")

    def select_device(self):
        identifier = self.devices.currentData()
        self.launcher.config["_cast_device_id"] = identifier
        self.launcher.config["_cast_device_name"] = self.devices.currentText() if identifier else ""
        self.launcher.save_config_file()
        self.launcher.refresh_cast_status()
