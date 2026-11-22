import csv
import shutil
import subprocess
import time
from importlib import import_module
from pathlib import Path

from PyQt6.QtCore import QPointF, QTimer
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QScrollArea,
    QVBoxLayout, QWidget
)
from PyQt6.QtGui import QColor, QPainter, QPen

from Application.core.battery import read_xbox_battery
from Application.ui.Settings.AsyncTask import TaskRunnerMixin
from Application.ui.Settings.Logger import log_warning
from Application.ui.widgets.battery_indicator import BatteryIcon

device_styles = import_module("Application.ui.Settings.About Device.DeviceStyles")

create_device_page_title = device_styles.create_device_page_title
style_device_page = device_styles.style_device_page


def _read_cpu_counters():
    counters = {}
    try:
        lines = Path("/proc/stat").read_text(encoding="utf-8").splitlines()
    except OSError as error:
        log_warning(f"Could not read CPU usage: {error}")
        return counters

    for line in lines:
        fields = line.split()
        if not fields or not (fields[0] == "cpu" or fields[0].startswith("cpu") and fields[0][3:].isdigit()):
            continue
        try:
            values = [int(value) for value in fields[1:]]
        except ValueError:
            continue
        if len(values) < 4:
            continue
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values[:8]) if len(values) > 8 else sum(values)
        counters[fields[0]] = (total, idle)
    return counters


def _cpu_percentages(previous, current):
    percentages = {}
    for name, (total, idle) in current.items():
        old_total, old_idle = previous.get(name, (total, idle))
        total_delta = total - old_total
        idle_delta = idle - old_idle
        percentages[name] = (
            round(max(0.0, min(100.0, (total_delta - idle_delta) / total_delta * 100)), 1)
            if total_delta > 0 else 0.0
        )
    return percentages


def _memory_info():
    try:
        memory = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator:
                memory[key] = int(value.strip().split()[0]) * 1024
        total = memory["MemTotal"]
        available = memory.get("MemAvailable", 0)
    except (OSError, ValueError, IndexError, KeyError) as error:
        log_warning(f"Could not read memory usage: {error}")
        return None

    used = max(0, total - available)
    return total, used, available, round(used / total * 100, 1) if total else 0.0


def _network_totals():
    received = 0
    sent = 0
    try:
        lines = Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]
        for line in lines:
            _, separator, counters = line.partition(":")
            if not separator:
                continue
            values = counters.split()
            if len(values) >= 9:
                received += int(values[0])
                sent += int(values[8])
    except (OSError, ValueError, IndexError) as error:
        log_warning(f"Could not read network usage: {error}")
        return None
    return sent, received


def _read_gpu_sysfs():
    devices = []
    for device_path in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        device = device_path / "device"
        if not device.exists():
            continue

        values = {}
        for key, filename in (
            ("usage", "gpu_busy_percent"),
            ("memory_used", "mem_info_vram_used"),
            ("memory_total", "mem_info_vram_total"),
        ):
            try:
                values[key] = int((device / filename).read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pass

        temperatures = []
        for input_path in sorted(device.glob("hwmon/hwmon*/temp*_input")):
            try:
                temperature = int(input_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            if temperature > 0:
                temperatures.append(temperature / 1000)
        if temperatures:
            values["temperature"] = max(temperatures)

        if values:
            devices.append(values)
    if not devices:
        return None

    usages = [device["usage"] for device in devices if "usage" in device]
    temperatures = [device["temperature"] for device in devices if "temperature" in device]
    memory_used = [device["memory_used"] for device in devices if "memory_used" in device]
    memory_total = [device["memory_total"] for device in devices if "memory_total" in device]
    return {
        "usage": sum(usages) / len(usages) if usages else None,
        "temperature": max(temperatures) if temperatures else None,
        "memory_used": sum(memory_used) if memory_used else None,
        "memory_total": sum(memory_total) if memory_total else None,
    }


def _gpu_info():
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            result = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            if result.returncode == 0:
                devices = []
                for row in csv.reader(result.stdout.splitlines()):
                    if len(row) != 4:
                        continue
                    values = []
                    for field in row:
                        try:
                            values.append(float(field.strip()))
                        except ValueError:
                            values.append(None)
                    if any(value is not None for value in values):
                        devices.append(values)
                if devices:
                    usages = [device[0] for device in devices if device[0] is not None]
                    temperatures = [device[1] for device in devices if device[1] is not None]
                    memory_used = [device[2] for device in devices if device[2] is not None]
                    memory_total = [device[3] for device in devices if device[3] is not None]
                    return {
                        "usage": sum(usages) / len(usages) if usages else None,
                        "temperature": max(temperatures) if temperatures else None,
                        "memory_used": sum(memory_used) * 1024**2 if memory_used else None,
                        "memory_total": sum(memory_total) * 1024**2 if memory_total else None,
                    }
        except (OSError, subprocess.SubprocessError) as error:
            log_warning(f"Could not read NVIDIA GPU metrics: {error}")

    return _read_gpu_sysfs()


def _cpu_temperature():
    sensor_values = []
    thermal_zones = sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
    for temperature_path in thermal_zones:
        try:
            zone_type = (temperature_path.parent / "type").read_text(encoding="utf-8").strip().lower()
            temperature = int(temperature_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if temperature <= 0:
            continue
        sensor_values.append((zone_type, temperature))

    for input_path in sorted(Path("/sys/class/hwmon").glob("hwmon*/temp*_input")):
        sensor_index = input_path.stem[:-6]
        try:
            sensor_name_path = input_path.parent / f"{sensor_index}_label"
            sensor_name = (
                sensor_name_path.read_text(encoding="utf-8").strip().lower()
                if sensor_name_path.exists()
                else (input_path.parent / "name").read_text(encoding="utf-8").strip().lower()
            )
            temperature = int(input_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if temperature > 0:
            sensor_values.append((sensor_name, temperature))

    if not sensor_values:
        return "Unavailable"

    preferred_sensors = [
        temperature for name, temperature in sensor_values
        if any(cpu_name in name for cpu_name in ("cpu", "core", "package", "tctl", "tdie", "k10temp", "x86"))
    ]
    value = (preferred_sensors or [sensor_values[0][1]])[0] / 1000
    return f"{value:.1f} °C"


def _format_bytes(value):
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{amount:.0f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"


def _create_metric_card(title, value, detail):
    card = QFrame()
    card.setObjectName("overviewMetricCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(7)

    title_label = QLabel(title)
    title_label.setStyleSheet("color: rgba(255, 255, 255, 190); font-size: 14px; font-weight: 500;")
    value_label = QLabel(value)
    value_label.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: 600;")
    detail_label = QLabel(detail)
    detail_label.setWordWrap(True)
    detail_label.setStyleSheet("color: rgba(255, 255, 255, 185); font-size: 12px;")

    layout.addWidget(title_label)
    layout.addWidget(value_label)
    layout.addWidget(detail_label)
    return card, value_label, detail_label, layout


class _HistoryChart(QWidget):
    def __init__(self, names, fixed_range=None, parent=None):
        super().__init__(parent)
        self.names = list(names)
        self.fixed_range = fixed_range
        self.samples = [[] for _ in self.names]
        self.setMinimumHeight(150)

    def append(self, values):
        if len(values) != len(self.samples):
            self.samples = [[] for _ in values]
        for history, value in zip(self.samples, values):
            history.append(value)
            if len(history) > 30:
                del history[0]
        self.update()

    def set_names(self, names):
        names = list(names)
        if names != self.names:
            self.names = names
            self.samples = [[] for _ in names]
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self.rect().adjusted(8, 8, -8, -25)
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        for row in range(4):
            y = plot.top() + plot.height() * row / 3
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        values = [value for history in self.samples for value in history]
        maximum = self.fixed_range or max(values, default=1.0)
        if self.fixed_range is None:
            maximum = max(maximum * 1.15, 1.0)
        palette = [
            QColor.fromHsv(round(index * 360 / max(len(self.samples), 1)), 210, 255)
            for index in range(len(self.samples))
        ]
        for history, color in zip(self.samples, palette):
            if len(history) < 2:
                continue
            painter.setPen(QPen(color, 2))
            points = [
                QPointF(
                    plot.left() + index * plot.width() / (len(history) - 1),
                    plot.bottom() - value / maximum * plot.height(),
                )
                for index, value in enumerate(history)
            ]
            for first, second in zip(points, points[1:]):
                painter.drawLine(first, second)

        for index, name in enumerate(self.names):
            painter.setPen(palette[index])
            step = max(36, (self.width() - 16) // max(len(self.names), 1))
            painter.drawText(8 + index * step, self.height() - 5, name)
        painter.end()


class OverviewWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher=None, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.setStyleSheet("color: #FFFFFF;")
        layout = QVBoxLayout(self)
        style_device_page(self, layout)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("background: transparent;")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        topbar = QFrame()
        topbar.setObjectName("overviewTopbar")
        self.topbar = topbar
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(16, 10, 16, 10)
        title = create_device_page_title("System Overview")
        self.status_label = QLabel("LIVE SYSTEM METRICS")
        self.status_label.setStyleSheet(
            "color: #FFFFFF; background-color: rgba(220, 2, 60, 115);"
            "padding: 5px 10px; border-radius: 9px; font-size: 11px; font-weight: 600;"
        )
        topbar_layout.addWidget(title)
        topbar_layout.addStretch()
        topbar_layout.addWidget(self.status_label)
        self.controller_battery_icon = BatteryIcon()
        self.controller_battery_label = QLabel("Xbox battery: --")
        self.controller_battery_label.setToolTip("Xbox controller battery level, when reported by the system.")
        topbar_layout.addWidget(self.controller_battery_icon)
        topbar_layout.addWidget(self.controller_battery_label)
        content_layout.addWidget(topbar)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        self.cpu_card, self.cpu_value, self.cpu_detail, self.cpu_layout = _create_metric_card(
            "CPU USAGE", "Collecting...", "Per-core usage: collecting..."
        )
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setRange(0, 100)
        self.cpu_progress.setTextVisible(False)
        self.cpu_progress.setFixedHeight(7)
        self.cpu_layout.insertWidget(2, self.cpu_progress)

        self.temperature_card, self.temperature_value, self.temperature_detail, _ = _create_metric_card(
            "CPU TEMP", "Reading sensor...", "Processor temperature"
        )
        self.memory_card, self.memory_value, self.memory_detail, _ = _create_metric_card(
            "RAM USAGE", "Reading memory...", "Used / total memory"
        )
        self.memory_percent_card, self.memory_percent_value, self.memory_percent_detail, self.memory_layout = _create_metric_card(
            "RAM USED", "Reading memory...", "Memory utilization"
        )
        self.memory_progress = QProgressBar()
        self.memory_progress.setRange(0, 100)
        self.memory_progress.setTextVisible(False)
        self.memory_progress.setFixedHeight(7)
        self.memory_layout.insertWidget(2, self.memory_progress)

        self.network_card, self.network_value, self.network_detail, _ = _create_metric_card(
            "NETWORK", "Collecting...", "Upload / download rate"
        )
        self.gpu_card, self.gpu_value, self.gpu_detail, _ = _create_metric_card(
            "GPU USAGE", "Reading sensor...", "Graphics processor utilization"
        )
        self.gpu_temperature_card, self.gpu_temperature_value, self.gpu_temperature_detail, _ = _create_metric_card(
            "GPU TEMP", "Reading sensor...", "Graphics processor temperature"
        )
        self.vram_card, self.vram_value, self.vram_detail, _ = _create_metric_card(
            "VRAM USAGE", "Reading sensor...", "Used / total graphics memory"
        )

        self.metric_cards = [
            self.cpu_card, self.temperature_card, self.memory_card,
            self.memory_percent_card, self.network_card, self.gpu_card,
            self.gpu_temperature_card, self.vram_card,
        ]
        for index, card in enumerate(self.metric_cards):
            card.setMinimumHeight(112)
            grid.addWidget(card, index // 3, index % 3)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        content_layout.addLayout(grid)

        chart_grid = QGridLayout()
        chart_grid.setContentsMargins(0, 0, 0, 0)
        chart_grid.setHorizontalSpacing(8)
        chart_grid.setVerticalSpacing(8)
        self.cpu_chart = _HistoryChart([], fixed_range=100)
        self.network_chart = _HistoryChart(["Upload Mbps", "Download Mbps"])
        self.memory_chart = _HistoryChart(["RAM %"], fixed_range=100)
        self.gpu_chart = _HistoryChart(["GPU %"], fixed_range=100)
        self.chart_cards = [
            self._create_chart_card("CPU LOAD (PER CORE)", self.cpu_chart),
            self._create_chart_card("NETWORK USAGE", self.network_chart),
            self._create_chart_card("RAM USAGE", self.memory_chart),
            self._create_chart_card("GPU LOAD", self.gpu_chart),
        ]
        for index, card in enumerate(self.chart_cards):
            chart_grid.addWidget(card, index // 2, index % 2)
            chart_grid.setColumnStretch(index % 2, 1)
        content_layout.addLayout(chart_grid)

        self.alert_card = QFrame()
        self.alert_card.setObjectName("overviewMetricCard")
        alert_layout = QVBoxLayout(self.alert_card)
        alert_layout.setContentsMargins(14, 12, 14, 12)
        alert_title = QLabel("ALERTS")
        alert_title.setStyleSheet("color: rgba(255, 255, 255, 190); font-size: 14px; font-weight: 500;")
        self.alert_message = QLabel("No alerts configured.")
        self.alert_message.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        alert_layout.addWidget(alert_title)
        alert_layout.addWidget(self.alert_message)
        content_layout.addWidget(self.alert_card)
        content_layout.addStretch()

        self.apply_theme()

        self._previous_cpu = {}
        self._previous_network = None
        self._previous_update = None
        self._battery_busy = False
        self._battery_timer = QTimer(self)
        self._battery_timer.setInterval(30000)
        self._battery_timer.timeout.connect(self.refresh_controller_battery)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh_metrics)
        self.refresh_metrics()

    @staticmethod
    def _create_chart_card(title, chart):
        card = QFrame()
        card.setObjectName("overviewMetricCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 8)
        card_layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setStyleSheet("color: rgba(255, 255, 255, 190); font-size: 14px; font-weight: 500;")
        card_layout.addWidget(title_label)
        card_layout.addWidget(chart)
        return card

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_theme()
        self.refresh_metrics()
        self._timer.start()
        self.refresh_controller_battery()
        self._battery_timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        self._battery_timer.stop()
        super().hideEvent(event)

    def refresh_controller_battery(self):
        if self._battery_busy:
            return
        self._battery_busy = True

        def done(result):
            self._battery_busy = False
            if isinstance(result, Exception):
                log_warning(f"Could not read Xbox controller battery: {result}")
                result = None
            available = result is not None
            percent = result["percent"] if available else None
            charging = result["charging"] if available else False
            self.controller_battery_icon.set_state(percent, charging, available)
            self.controller_battery_label.setText(
                f"Xbox battery: {percent}%" + (" (charging)" if charging else "")
                if available else "Xbox battery: unavailable"
            )

        self.run_async(read_xbox_battery, done)

    def apply_theme(self):
        theme_color = QColor(
            self.launcher.get_theme_color()
            if self.launcher and hasattr(self.launcher, "get_theme_color")
            else "#DC143C"
        )
        if not theme_color.isValid():
            theme_color = QColor("#DC143C")

        accent = theme_color.name()
        accent_rgba = (
            f"rgba({theme_color.red()}, {theme_color.green()}, "
            f"{theme_color.blue()}, 110)"
        )
        accent_soft_rgba = (
            f"rgba({theme_color.red()}, {theme_color.green()}, "
            f"{theme_color.blue()}, 65)"
        )
        self.topbar.setStyleSheet(f"""
            QFrame#overviewTopbar {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {accent_rgba},
                    stop: 0.55 rgba(22, 18, 19, 235),
                    stop: 1 {accent_soft_rgba}
                );
                border: 1px solid rgba(0, 0, 0, 190);
                border-radius: 12px;
            }}
        """)
        self.status_label.setStyleSheet(
            f"color: #FFFFFF; background-color: {accent_rgba};"
            "padding: 5px 10px; border-radius: 9px; font-size: 11px; font-weight: 600;"
        )
        for card in self.metric_cards + self.chart_cards + [self.alert_card]:
            card.setStyleSheet(f"""
                QFrame#overviewMetricCard {{
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 1, y2: 1,
                        stop: 0 {accent_rgba},
                        stop: 0.55 rgba(34, 20, 23, 235),
                        stop: 1 {accent_soft_rgba}
                    );
                    border: 1px solid rgba(0, 0, 0, 190);
                    border-radius: 12px;
                    padding: 8px;
                }}
            """)
        for progress_bar in (self.cpu_progress, self.memory_progress):
            progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: rgba(0, 0, 0, 100);
                    border: none;
                    border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background-color: {accent};
                    border-radius: 3px;
                }}
            """)

    def refresh_metrics(self):
        now = time.monotonic()
        current_cpu = _read_cpu_counters()
        if self._previous_cpu and current_cpu:
            percentages = _cpu_percentages(self._previous_cpu, current_cpu)
            overall = percentages.get("cpu")
            core_values = [
                (name, usage)
                for name, usage in percentages.items()
                if name.startswith("cpu") and name != "cpu"
            ]
            if overall is not None:
                self.cpu_value.setText(f"{overall:.1f}%")
                self.cpu_progress.setValue(round(overall))
            self.cpu_detail.setText(
                "Per-core usage: " + (
                    ", ".join(f"{name[3:]}: {usage:.1f}%" for name, usage in core_values)
                    if core_values else "Unavailable"
                )
            )
            self.cpu_chart.set_names([f"CPU{name[3:]}" for name, _ in core_values])
            self.cpu_chart.append([usage for _, usage in core_values])
        self._previous_cpu = current_cpu

        self.temperature_value.setText(_cpu_temperature())

        memory = _memory_info()
        if memory:
            total, used, available, percent = memory
            self.memory_value.setText(f"{_format_bytes(used)} / {_format_bytes(total)}")
            self.memory_detail.setText(f"{_format_bytes(available)} available")
            self.memory_percent_value.setText(f"{percent:.1f}%")
            self.memory_percent_detail.setText("Memory utilization")
            self.memory_progress.setValue(round(percent))
            self.memory_chart.append([percent])
        else:
            self.memory_value.setText("Unavailable")
            self.memory_detail.setText("Memory usage could not be read")
            self.memory_percent_value.setText("Unavailable")
            self.memory_percent_detail.setText("Memory usage could not be read")

        network = _network_totals()
        if network:
            sent, received = network
            self.network_detail.setText(
                f"{_format_bytes(sent)} sent · {_format_bytes(received)} received"
            )
            if self._previous_network is not None and self._previous_update is not None:
                elapsed = max(now - self._previous_update, 0.001)
                previous_sent, previous_received = self._previous_network
                upload_rate = max(0, sent - previous_sent) / elapsed
                download_rate = max(0, received - previous_received) / elapsed
                upload_mbps = upload_rate * 8 / 1024**2
                download_mbps = download_rate * 8 / 1024**2
                self.network_value.setText(
                    f"{upload_mbps:.2f} Mbps ↑ / {download_mbps:.2f} Mbps ↓"
                )
                self.network_chart.append([upload_mbps, download_mbps])
            self._previous_network = sent, received
            self._previous_update = now
        else:
            self.network_value.setText("Unavailable")
            self.network_detail.setText("Network counters could not be read")

        gpu = _gpu_info()
        if gpu:
            usage = gpu.get("usage")
            temperature = gpu.get("temperature")
            memory_used = gpu.get("memory_used")
            memory_total = gpu.get("memory_total")
            if usage is None:
                self.gpu_value.setText("Unavailable")
                self.gpu_detail.setText("GPU utilization sensor unavailable")
            else:
                usage = max(0.0, min(100.0, usage))
                self.gpu_value.setText(f"{usage:.1f}%")
                self.gpu_detail.setText("Graphics processor utilization")
                self.gpu_chart.append([usage])
            self.gpu_temperature_value.setText(
                f"{temperature:.1f} °C" if temperature is not None else "Unavailable"
            )
            self.gpu_temperature_detail.setText("Graphics processor temperature")
            if memory_used is not None and memory_total is not None:
                self.vram_value.setText(
                    f"{_format_bytes(memory_used)} / {_format_bytes(memory_total)}"
                )
                self.vram_detail.setText("Used / total graphics memory")
            else:
                self.vram_value.setText("Unavailable")
                self.vram_detail.setText("VRAM usage sensor unavailable")
        else:
            self.gpu_value.setText("Unavailable")
            self.gpu_detail.setText("GPU telemetry unavailable")
            self.gpu_temperature_value.setText("Unavailable")
            self.gpu_temperature_detail.setText("GPU telemetry unavailable")
            self.vram_value.setText("Unavailable")
            self.vram_detail.setText("GPU telemetry unavailable")
