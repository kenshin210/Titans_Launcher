"""Focusable quick-settings overlay for the launcher."""

import platform

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from Application.core.control_centre import ControlCentreManager
from Application.ui.Settings.AsyncTask import TaskRunnerMixin
from Application.ui.controller_navigation import handle_focused_widget_input


class ControlCentreOverlay(QDialog, TaskRunnerMixin):
    """Quick controls and system status presented over the launcher."""

    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher
        self.manager = ControlCentreManager()
        self._refresh_running = False
        self._pending_sliders = set()
        self._slider_timers = {}
        self._slider_values = {}
        self.setObjectName("controlCentreOverlay")
        self.setWindowTitle("Control Centre")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.apply_theme()

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.addStretch()
        card = QWidget()
        card.setObjectName("controlCentreCard")
        card.setMaximumWidth(760)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("Control Centre")
        title.setObjectName("controlCentreTitle")
        header.addWidget(title)
        header.addStretch()
        self.close_button = QPushButton("Close  (Esc)")
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button)
        card_layout.addLayout(header)

        self.system_status = QLabel()
        self.system_status.setObjectName("controlCentreStatus")
        self.system_status.setWordWrap(True)
        card_layout.addWidget(self.system_status)

        toggles = QHBoxLayout()
        self.wifi_button = QPushButton("Wi-Fi")
        self.wifi_button.setCheckable(True)
        self.wifi_button.toggled.connect(self._set_wifi)
        toggles.addWidget(self.wifi_button)
        self.bluetooth_button = QPushButton("Bluetooth")
        self.bluetooth_button.setCheckable(True)
        self.bluetooth_button.toggled.connect(self._set_bluetooth)
        toggles.addWidget(self.bluetooth_button)
        card_layout.addLayout(toggles)

        controls = QFormLayout()
        self.volume_slider = self._slider()
        self.volume_value = QLabel("Unavailable")
        controls.addRow("Volume:", self._slider_row(self.volume_slider, self.volume_value))
        self.brightness_slider = self._slider()
        self.brightness_value = QLabel("Unavailable")
        controls.addRow(
            "Brightness:",
            self._slider_row(self.brightness_slider, self.brightness_value),
        )
        card_layout.addLayout(controls)

        self.status_label = QLabel("Checking available controls…")
        self.status_label.setObjectName("controlCentreStatus")
        self.status_label.setWordWrap(True)
        card_layout.addWidget(self.status_label)
        self.volume_slider.valueChanged.connect(
            lambda value: self._schedule_slider("volume", value)
        )
        self.brightness_slider.valueChanged.connect(
            lambda value: self._schedule_slider("brightness", value)
        )

        wrapper = QHBoxLayout()
        wrapper.addStretch()
        wrapper.addWidget(card)
        wrapper.addStretch()
        root.addLayout(wrapper)
        root.addStretch()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_status)
        self.refresh_timer.start(10_000)
        self.finished.connect(lambda _result: self.refresh_timer.stop())
        self.refresh_status()

    def apply_theme(self):
        config = getattr(self.launcher, "config", {})
        accent = getattr(self.launcher, "get_theme_color", lambda: "#DC143C")()
        high_contrast = config.get("_high_contrast", False)
        surface = "#000000" if high_contrast else "rgba(22, 22, 22, 240)"
        control_surface = "#101010" if high_contrast else "rgba(35, 35, 35, 180)"
        text_color = "#FFFFFF"
        muted_color = "#FFFFFF" if high_contrast else "#DDDDDD"
        focus_color = "#FFFF00" if high_contrast else accent
        border_color = "#FFFFFF" if high_contrast else "rgba(255, 255, 255, 30)"
        self.setStyleSheet(
            f"""
            QDialog#controlCentreOverlay {{ background: rgba(0, 0, 0, 205); }}
            QWidget#controlCentreCard {{
                background-color: {surface}; color: {text_color};
                border: 2px solid {accent}; border-radius: 14px;
            }}
            QLabel {{ color: {text_color}; }}
            QLabel#controlCentreTitle {{ font-size: 26px; font-weight: bold; }}
            QLabel#controlCentreStatus {{ color: {muted_color}; font-size: 15px; }}
            QPushButton, QCheckBox {{
                background-color: {control_surface}; color: {text_color};
                padding: 10px 16px; border: 2px solid {border_color};
                border-radius: 8px; font-size: 16px;
            }}
            QPushButton:hover, QPushButton:focus, QCheckBox:focus, QSlider:focus {{
                border: 3px solid {focus_color};
            }}
            QPushButton:checked {{
                background-color: {accent}; border-color: {accent}; color: #FFFFFF;
            }}
            QPushButton:disabled, QCheckBox:disabled, QSlider:disabled {{
                color: {muted_color};
            }}
            QCheckBox::indicator {{
                width: 20px; height: 20px; border: 2px solid {border_color};
                border-radius: 4px; background: {control_surface};
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent}; border-color: {accent};
            }}
            QSlider::groove:horizontal {{
                height: 8px; background: {control_surface}; border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                width: 20px; margin: -7px 0; border-radius: 10px;
                background-color: {accent};
            }}
            """
        )

    @staticmethod
    def _slider():
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setMinimumWidth(280)
        return slider

    @staticmethod
    def _slider_row(slider, label):
        row = QHBoxLayout()
        row.addWidget(slider, stretch=1)
        row.addWidget(label)
        container = QWidget()
        container.setLayout(row)
        return container

    def showEvent(self, event):
        super().showEvent(event)
        self.setGeometry(self.launcher.rect())
        self.raise_()
        self.close_button.setFocus()

    def refresh_status(self):
        if self._refresh_running:
            return
        self._refresh_running = True
        self.run_async(self.manager.get_status, self._apply_status)

    def _apply_status(self, result):
        self._refresh_running = False
        if isinstance(result, Exception):
            self.status_label.setText(f"Could not read system status: {result}")
            return

        wifi = result["wifi"]
        bluetooth = result["bluetooth"]
        self._set_toggle(self.wifi_button, wifi)
        self._set_toggle(self.bluetooth_button, bluetooth)
        self._set_slider(self.volume_slider, self.volume_value, result["volume"], "volume")
        self._set_slider(
            self.brightness_slider,
            self.brightness_value,
            result["brightness"],
            "brightness",
        )

        battery = "--"
        indicator = getattr(self.launcher, "battery_indicator", None)
        if indicator is not None and hasattr(indicator, "percent_label"):
            battery = indicator.percent_label.text()
        self.system_status.setText(
            f"{platform.node()}  •  {result['network_status']}  •  Battery: {battery}"
        )
        unavailable = [
            f"{name}: {result[name]['detail']}"
            for name in ("wifi", "bluetooth", "volume", "brightness")
            if not result[name]["available"]
        ]
        self.status_label.setText(
            "Unavailable controls — " + "; ".join(unavailable)
            if unavailable
            else "All quick-setting controls are available."
        )

    @staticmethod
    def _set_toggle(button, state):
        button.blockSignals(True)
        button.setChecked(state["enabled"])
        button.setEnabled(state["available"])
        detail = state["detail"]
        button.setText(f"{button.text().split(' · ')[0]} · {detail}")
        button.blockSignals(False)

    def _set_slider(self, slider, label, state, name):
        available = state["available"]
        slider.blockSignals(True)
        slider.setValue(state["value"])
        slider.setEnabled(available)
        slider.blockSignals(False)
        label.setText(f"{state['value']}%" if available else "Unavailable")
        if not available:
            self.status_label.setText(f"{name.title()} unavailable: {state['detail']}")

    def _run_setting(self, operation):
        self.status_label.setText("Applying setting…")
        self.run_async(operation, self._setting_finished)

    def _setting_finished(self, result):
        if isinstance(result, Exception):
            self.status_label.setText(f"Setting failed: {result}")
        elif result[0]:
            self.status_label.setText("Setting applied.")
            QTimer.singleShot(300, self.refresh_status)
        else:
            self.status_label.setText(f"Setting failed: {result[1]}")
            QTimer.singleShot(300, self.refresh_status)

    def _set_wifi(self, enabled):
        self._run_setting(lambda: self.manager.set_wifi_enabled(enabled))

    def _set_bluetooth(self, enabled):
        self._run_setting(lambda: self.manager.set_bluetooth_enabled(enabled))

    def _schedule_slider(self, name, value):
        self._slider_values[name] = value
        if name not in self._slider_timers:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda n=name: self._apply_slider(n))
            self._slider_timers[name] = timer
        self._pending_sliders.add(name)
        self._slider_timers[name].start(180)

    def _apply_slider(self, name):
        self._pending_sliders.discard(name)
        operation = (
            self.manager.set_volume if name == "volume"
            else self.manager.set_brightness
        )
        value = self._slider_values[name]
        self._run_setting(lambda: operation(value))

    def handle_controller_action(self, action):
        if action == "back":
            self.reject()
            return True
        if action == "select":
            focused = self.focusWidget()
            if isinstance(focused, (QPushButton, QCheckBox)):
                focused.click()
                return True
        if action in ("left", "right") and handle_focused_widget_input(action):
            return True
        if action == "up":
            self.focusPreviousChild()
            return True
        if action == "down":
            self.focusNextChild()
            return True
        return True


