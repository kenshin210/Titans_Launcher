"""Controller-friendly phone-assisted Wi-Fi setup dialog."""

import asyncio
import threading

import qrcode
from PyQt6 import sip
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QComboBox, QDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout

from Application.core.phone_wifi import PhoneWifiSetup


class _SetupSignals(QObject):
    ready = pyqtSignal(str, str, str)


def _qr_pixmap(value):
    qr = qrcode.QRCode(border=4, box_size=1)
    qr.add_data(value)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    scale = 5
    image = QImage(len(matrix) * scale, len(matrix) * scale, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("black"))
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                painter.drawRect(x * scale, y * scale, scale, scale)
    painter.end()
    return QPixmap.fromImage(image)


class PhoneWifiDialog(QDialog):
    def __init__(self, launcher, devices, nmcli, on_finished, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.nmcli = nmcli
        self.on_finished = on_finished
        self.cancel = threading.Event()
        self.signals = _SetupSignals(launcher)
        self.signals.ready.connect(self._ready)
        self.setWindowTitle("Phone Wi-Fi Setup")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        layout = QVBoxLayout(self)
        description = QLabel(
            "Choose a Wi-Fi adapter. Starting setup temporarily disconnects its current Wi-Fi. "
            "The phone joins a private hotspot, then opens a separate setup page. "
            "Only share the hotspot and page codes with someone you trust."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.devices = QComboBox()
        self.devices.addItems(devices)
        layout.addWidget(self.devices)
        self.status = QLabel("Setup expires after five minutes.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.join_code = QLabel()
        self.join_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.join_code)
        self.page_code = QLabel()
        self.page_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.page_code)
        self.start_button = QPushButton("Start Temporary Hotspot")
        self.start_button.clicked.connect(self.start_setup)
        layout.addWidget(self.start_button)
        close = QPushButton("Cancel / Close")
        close.clicked.connect(self.close)
        layout.addWidget(close)
        self.destroyed.connect(lambda: self.cancel.set())

    def start_setup(self):
        interface = self.devices.currentText()
        if not interface:
            self.status.setText("No Wi-Fi adapter is available.")
            return
        answer = QMessageBox.question(
            self, "Start Phone Wi-Fi Setup",
            f"Start a temporary hotspot on {interface}? Its existing Wi-Fi connection will be interrupted. "
            "The local setup page uses HTTP over that hotspot; anyone who has access to the hotspot "
            "and setup code may be able to see the credentials. Other internet connections may be shared "
            "with hotspot clients.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if getattr(self.launcher, "_phone_wifi_in_progress", False):
            self.status.setText("Another phone setup is still running or stopping.")
            return
        self.launcher._phone_wifi_in_progress = True
        self.start_button.setEnabled(False)
        self.devices.setEnabled(False)
        self.status.setText("Starting hotspot; administrator authorization may be required...")
        setup = PhoneWifiSetup(interface, self.nmcli, self.cancel, self.signals.ready.emit)
        dialog = self
        launcher = self.launcher
        on_finished = self.on_finished

        def finished(result):
            launcher._phone_wifi_in_progress = False
            if not sip.isdeleted(dialog):
                dialog.close()
            if isinstance(result, Exception):
                QMessageBox.warning(launcher, "Phone Wi-Fi Setup Failed", str(result))
            elif result:
                QMessageBox.information(launcher, "Phone Wi-Fi Setup", "Connected to the supplied Wi-Fi.")
            if not sip.isdeleted(on_finished.__self__):
                on_finished()

        self.launcher.run_async(lambda: asyncio.run(setup.run()), finished)

    def _ready(self, ssid, password, url):
        self.status.setText(
            f"1. Scan the first code to join {ssid} (password: {password}).\n"
            f"2. Scan the second code or open {url}\n"
            "Enter the target Wi-Fi details. Setup expires after five minutes."
        )
        self.join_code.setPixmap(_qr_pixmap(f"WIFI:T:WPA;S:{ssid};P:{password};;"))
        self.page_code.setPixmap(_qr_pixmap(url))

    def closeEvent(self, event):
        self.cancel.set()
        super().closeEvent(event)

    def hideEvent(self, event):
        self.cancel.set()
        super().hideEvent(event)
