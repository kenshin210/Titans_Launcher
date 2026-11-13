from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from Application.core.battery import read_battery, read_xbox_battery
from Application.ui.Settings.AsyncTask import TaskRunnerMixin
from Application.ui.Settings.Logger import log_warning

REFRESH_INTERVAL_MS = 60_000


class BatteryIcon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 20)
        self.percent = None
        self.charging = False
        self.available = False

    def set_state(self, percent, charging, available):
        self.percent = percent
        self.charging = charging
        self.available = available
        self.update()

    def _fill_color(self):
        if not self.available or self.percent is None:
            return QColor(130, 130, 130)
        if self.percent <= 15:
            return QColor("#E53935")
        if self.percent <= 35:
            return QColor("#FFB300")
        return QColor("#43A047")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline = QColor(230, 230, 230) if self.available else QColor(120, 120, 120)
        body = QRectF(1, 2, 33, 16)
        painter.setPen(QPen(outline, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body, 3, 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(outline)
        painter.drawRoundedRect(QRectF(35, 6, 4, 8), 1, 1)

        if self.available and self.percent is not None:
            width = max(2.0, 27 * self.percent / 100)
            painter.setBrush(self._fill_color())
            painter.drawRoundedRect(QRectF(4, 5, width, 10), 1.5, 1.5)

        if self.charging:
            bolt = QPolygonF([
                QPointF(20, 3), QPointF(13, 11), QPointF(18, 11),
                QPointF(15, 18), QPointF(24, 8), QPointF(19, 8),
            ])
            painter.setPen(QPen(QColor(0, 0, 0, 200), 1))
            painter.setBrush(QColor("#FFEB3B"))
            painter.drawPolygon(bolt)


class BatteryIndicator(QWidget, TaskRunnerMixin):
    """Home-screen controller battery readout shown beside the power button."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._busy = False
        self._address = None
        self.setFixedHeight(65)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet(
            "color: #CCCCCC; font-size: 13px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(self.name_label)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon = BatteryIcon()
        self.percent_label = QLabel("--")
        self.percent_label.setStyleSheet(
            "color: #FFFFFF; font-size: 15px; font-weight: bold; background: transparent;"
        )
        row.addWidget(self.icon)
        row.addWidget(self.percent_label)
        layout.addLayout(row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.reload()

    def reload(self):
        address = self.config.get("_battery_device_address", "")
        if address != self._address:
            self._address = address
            self._show_state(None, False, False)
        short_name = (
            self.config.get("_battery_short_name") or self.config.get("_battery_device_name") or "Controller"
            if address else "Xbox"
        )
        self.name_label.setText(short_name)
        self.setToolTip(self.config.get("_battery_device_name", "") if address else "Xbox controller (automatic)")
        self.show()
        self.timer.start(REFRESH_INTERVAL_MS)
        self.refresh()

    def refresh(self):
        address = self.config.get("_battery_device_address", "")
        if self._busy:
            return
        self._busy = True

        def done(result):
            self._busy = False
            if address != self.config.get("_battery_device_address", ""):
                self.refresh()
                return
            if isinstance(result, Exception):
                log_warning(f"Could not read controller battery: {result}")
                self._show_state(None, False, False)
                return
            if result is None:
                self._show_state(None, False, False)
                return
            percent = result["percent"]
            available = (
                result.get("connected") is not False
                and percent is not None and 0 <= percent <= 100
            )
            self._show_state(percent, result["charging"] if available else False, available)

        self.run_async(lambda: read_battery(address) if address else read_xbox_battery(), done)

    def _show_state(self, percent, charging, available):
        self.icon.set_state(percent, charging, available)
        self.percent_label.setText(f"{percent}%" if available else "--")
        self.percent_label.setToolTip("" if available else "Controller battery level unavailable")
