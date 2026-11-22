"""WiFi Network Status Indicator Widget for Home Screen Status Bar"""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget, QHBoxLayout

from Application.core.network_info import get_wifi_status
from Application.ui.Settings.Logger import log_warning

REFRESH_INTERVAL_MS = 5000  # Update every 5 seconds


class WiFiIcon(QWidget):
    """Renders WiFi signal strength bars icon."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 20)
        self.signal_strength = 0  # 0-100
        self.connected = False

    def set_state(self, connected, signal_strength):
        """Update WiFi connection state and signal strength."""
        self.connected = connected
        self.signal_strength = max(0, min(100, signal_strength))
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.connected:
            # Disconnected - draw X
            painter.setPen(QPen(QColor(200, 200, 200), 2))
            painter.drawLine(4, 4, 28, 16)
            painter.drawLine(28, 4, 4, 16)
            return

        # Connected - draw signal bars (0-4 bars based on strength)
        bar_colors = {
            0: QColor(255, 100, 100),  # Red: weak
            1: QColor(255, 150, 0),     # Orange: fair
            2: QColor(255, 200, 0),     # Yellow: good
            3: QColor(100, 200, 100),   # Green: excellent
        }

        num_bars = max(1, (self.signal_strength + 24) // 25)  # 1-4 bars
        bar_height = [4, 8, 12, 16]  # Heights for bars 1-4

        for i in range(4):
            color = bar_colors.get(min(3, i), QColor(100, 200, 100))
            alpha = 255 if i < num_bars else 80
            color.setAlpha(alpha)

            x = 6 + i * 5
            y = 16 - bar_height[i]
            painter.fillRect(x, y, 3, bar_height[i], color)
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.drawRect(x, y, 3, bar_height[i])


class WiFiIndicator(QWidget):
    """Home-screen WiFi network status shown in status bar."""

    connection_changed = pyqtSignal(str, int)  # SSID, signal_strength

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.current_ssid = "Not Connected"
        self.current_signal = 0
        self.setFixedHeight(65)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        # WiFi icon
        self.icon = WiFiIcon(self)
        icon_layout = QHBoxLayout()
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(icon_layout)

        # SSID label
        self.ssid_label = QLabel("Loading...")
        self.ssid_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ssid_label.setStyleSheet(
            "color: #CCCCCC; font-size: 11px; font-weight: bold; "
            "background: transparent; max-width: 120px;"
        )
        self.ssid_label.setWordWrap(True)
        layout.addWidget(self.ssid_label)

        # Signal % label
        self.signal_label = QLabel("--")
        self.signal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.signal_label.setStyleSheet(
            "color: #AAAAAA; font-size: 10px; background: transparent;"
        )
        layout.addWidget(self.signal_label)

        # Refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_wifi_status)
        self.refresh_timer.start(REFRESH_INTERVAL_MS)

        # Initial update
        self._update_wifi_status()

    def _update_wifi_status(self):
        """Fetch and update WiFi status from system."""
        try:
            status = get_wifi_status()
            ssid = status.get("ssid", "Not Connected")
            signal = status.get("signal_strength", 0)

            if ssid != self.current_ssid or signal != self.current_signal:
                self.current_ssid = ssid
                self.current_signal = signal
                self._sync_display()
                self.connection_changed.emit(ssid, signal)
        except Exception as e:
            log_warning(f"WiFi status update failed: {e}")

    def _sync_display(self):
        """Update UI to reflect current WiFi state."""
        connected = self.current_ssid != "Not Connected"

        # Truncate long SSIDs
        display_ssid = self.current_ssid
        if len(display_ssid) > 18:
            display_ssid = display_ssid[:15] + "..."

        self.ssid_label.setText(display_ssid)
        self.icon.set_state(connected, self.current_signal)

        if connected:
            self.signal_label.setText(f"{self.current_signal}%")
            self.setToolTip(
                f"Network: {self.current_ssid}\n"
                f"Signal: {self.current_signal}%"
            )
        else:
            self.signal_label.setText("--")
            self.setToolTip("WiFi: Not Connected")

    def hideEvent(self, event):
        """Stop updating when hidden."""
        self.refresh_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        """Resume updating when shown."""
        self.refresh_timer.start()
        super().showEvent(event)
