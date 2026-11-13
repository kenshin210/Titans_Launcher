import re
import shutil

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Application.core.battery import suggest_short_name
from Application.styles import load_stylesheet
from Application.ui.Settings.AsyncTask import TaskRunnerMixin, command_error, run_command
from Application.ui.Settings.Logger import log_info, log_warning

DEVICE_PATTERN = re.compile(r"^Device\s+([0-9A-Fa-f:]{17})\s+(.*)$")
SCAN_SECONDS = 8


class BluetoothSettingsWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("soundDisplaySettings")
        self.setStyleSheet(load_stylesheet(theme_color=launcher.get_theme_color()))
        self.bluetoothctl = shutil.which("bluetoothctl")
        self.powered = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(12)

        title = QLabel("Bluetooth")
        title.setObjectName("soundDisplayTitle")
        layout.addWidget(title)

        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        card = QFrame()
        card.setObjectName("soundDisplayCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)

        heading = QLabel("Devices")
        heading.setObjectName("soundDisplaySectionTitle")
        card_layout.addWidget(heading)

        self.device_list = QListWidget()
        self.device_list.setObjectName("connectivityList")
        card_layout.addWidget(self.device_list, stretch=1)

        actions = QHBoxLayout()
        self.power_button = self._make_button("Turn Bluetooth Off", self.toggle_power)
        self.scan_button = self._make_button("Scan for Devices", self.scan_devices)
        self.add_button = self._make_button("Add Device", self.add_selected)
        self.connect_button = self._make_button("Connect / Disconnect", self.toggle_connection)
        self.remove_button = self._make_button("Remove Device", self.remove_selected)
        for button in (
            self.power_button, self.scan_button, self.add_button,
            self.connect_button, self.remove_button,
        ):
            actions.addWidget(button)
        actions.addStretch()
        card_layout.addLayout(actions)
        layout.addWidget(card, stretch=1)
        layout.addWidget(self._build_battery_card())

        self.device_list.currentItemChanged.connect(self._suggest_short_name)
        self._show_battery_selection()
        self.refresh_all()

    def _make_button(self, text, handler):
        button = QPushButton(text)
        button.setObjectName("soundDisplayButton")
        button.clicked.connect(handler)
        return button

    def _build_battery_card(self):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(8)

        heading = QLabel("Home Screen Battery Indicator")
        heading.setObjectName("soundDisplaySectionTitle")
        card_layout.addWidget(heading)

        self.battery_current = QLabel()
        self.battery_current.setObjectName("soundDisplayStatus")
        self.battery_current.setWordWrap(True)
        card_layout.addWidget(self.battery_current)

        row = QHBoxLayout()
        label = QLabel("Short name:")
        label.setObjectName("soundDisplayValue")
        self.short_name_input = QLineEdit()
        self.short_name_input.setMaxLength(12)
        self.short_name_input.setPlaceholderText("e.g. xbone")
        row.addWidget(label)
        row.addWidget(self.short_name_input, stretch=1)
        use_button = self._make_button("Use Selected Device", self.use_for_battery)
        clear_button = self._make_button("Use Automatic Xbox", self.clear_battery)
        row.addWidget(use_button)
        row.addWidget(clear_button)
        card_layout.addLayout(row)
        return card

    def _show_battery_selection(self):
        config = self.launcher.config
        address = config.get("_battery_device_address", "")
        if address:
            self.battery_current.setText(
                f"Showing battery for {config.get('_battery_device_name') or address} "
                f"as \"{config.get('_battery_short_name', '')}\"."
            )
            self.short_name_input.setText(config.get("_battery_short_name", ""))
        else:
            self.battery_current.setText(
                "The Home screen automatically shows an Xbox controller battery. "
                "Select a device above to show a different Bluetooth battery instead."
            )

    def _suggest_short_name(self, current, _previous):
        entry = current.data(Qt.ItemDataRole.UserRole) if current else None
        if entry and entry["address"] != self.launcher.config.get("_battery_device_address"):
            self.short_name_input.setText(suggest_short_name(entry["name"]))

    def use_for_battery(self):
        entry = self._selected()
        if not entry:
            self.battery_current.setText("Select a device in the list first.")
            return
        config = self.launcher.config
        config["_battery_device_address"] = entry["address"]
        config["_battery_device_name"] = entry["name"]
        config["_battery_short_name"] = (
            self.short_name_input.text().strip() or suggest_short_name(entry["name"])
        )
        self._apply_battery_change()

    def clear_battery(self):
        config = self.launcher.config
        config["_battery_device_address"] = ""
        config["_battery_device_name"] = ""
        config["_battery_short_name"] = ""
        self.short_name_input.clear()
        self._apply_battery_change()

    def _apply_battery_change(self):
        self.launcher.save_config_file()
        if hasattr(self.launcher, "refresh_battery_indicator"):
            self.launcher.refresh_battery_indicator()
        self._show_battery_selection()

    def _set_controls_enabled(self, enabled):
        for widget in (
            self.device_list, self.scan_button, self.add_button,
            self.connect_button, self.remove_button,
        ):
            widget.setEnabled(enabled)

    def _selected(self):
        item = self.device_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh_all(self):
        if not self.bluetoothctl:
            self.status.setText("Bluetooth controls unavailable: bluetoothctl (bluez-utils) was not found.")
            self.power_button.setEnabled(False)
            self._set_controls_enabled(False)
            return
        self.refresh_devices()

    def refresh_devices(self):
        def work():
            show = run_command([self.bluetoothctl, "show"])
            devices = run_command([self.bluetoothctl, "devices"])
            entries = []
            for line in devices.stdout.splitlines():
                match = DEVICE_PATTERN.match(line.strip())
                if not match:
                    continue
                address, name = match.groups()
                info = run_command([self.bluetoothctl, "info", address]).stdout
                entries.append({
                    "address": address,
                    "name": name,
                    "paired": "Paired: yes" in info,
                    "connected": "Connected: yes" in info,
                })
            return show, entries

        def done(result):
            if isinstance(result, Exception):
                self.status.setText(f"Could not query Bluetooth: {result}")
                return
            show, entries = result
            if show.returncode != 0 or "Controller" not in show.stdout:
                self.status.setText("No Bluetooth adapter was detected or the bluetooth service is not running.")
                self.power_button.setEnabled(False)
                self._set_controls_enabled(False)
                return
            self.powered = "Powered: yes" in show.stdout
            self.power_button.setEnabled(True)
            self.power_button.setText("Turn Bluetooth Off" if self.powered else "Turn Bluetooth On")
            self._set_controls_enabled(self.powered)

            self.device_list.clear()
            for entry in sorted(entries, key=lambda e: (not e["paired"], e["name"].lower())):
                flags = []
                if entry["paired"]:
                    flags.append("paired")
                if entry["connected"]:
                    flags.append("connected")
                suffix = f"  [{', '.join(flags)}]" if flags else "  [not paired]"
                item = QListWidgetItem(f"{entry['name']}  ({entry['address']}){suffix}")
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self.device_list.addItem(item)
            self.status.setText(
                f"{self.device_list.count()} device(s) known."
                if self.powered else "Bluetooth is turned off."
            )

        self.run_async(work, done)

    def scan_devices(self):
        self.status.setText(f"Scanning for {SCAN_SECONDS} seconds... put your device in pairing mode.")
        self.scan_button.setEnabled(False)

        def work():
            return run_command(
                [self.bluetoothctl, "--timeout", str(SCAN_SECONDS), "scan", "on"],
                timeout=SCAN_SECONDS + 10,
            )

        def done(_result):
            self.scan_button.setEnabled(self.powered)
            self.refresh_devices()

        self.run_async(work, done)

    def _run_steps(self, steps, success_message, failure_prefix, timeout=30):
        def work():
            for step in steps:
                result = run_command([self.bluetoothctl, *step], timeout=timeout)
                if result.returncode != 0 or "Failed" in result.stdout:
                    return result
            return None

        def done(result):
            if isinstance(result, Exception):
                self.status.setText(f"{failure_prefix}: {result}")
            elif result is not None:
                details = command_error(result)
                log_warning(f"{failure_prefix}: {details}")
                self.status.setText(f"{failure_prefix}: {details}")
            else:
                log_info(success_message)
                self.status.setText(success_message)
            self.refresh_devices()

        self.status.setText("Working...")
        self.run_async(work, done)

    def add_selected(self):
        entry = self._selected()
        if not entry:
            self.status.setText("Scan, then select a device to add.")
            return
        address = entry["address"]
        self._run_steps(
            [("pair", address), ("trust", address), ("connect", address)],
            f"Added {entry['name']}.",
            f"Could not add {entry['name']}",
            timeout=45,
        )

    def toggle_connection(self):
        entry = self._selected()
        if not entry:
            self.status.setText("Select a device first.")
            return
        action, past_tense = (
            ("disconnect", "Disconnected") if entry["connected"] else ("connect", "Connected")
        )
        self._run_steps(
            [(action, entry["address"])],
            f"{past_tense} {entry['name']}.",
            f"Could not {action} {entry['name']}",
        )

    def remove_selected(self):
        entry = self._selected()
        if not entry:
            self.status.setText("Select a device to remove.")
            return
        answer = QMessageBox.question(
            self, "Remove device", f"Remove '{entry['name']}' and forget its pairing?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_steps(
            [("remove", entry["address"])],
            f"Removed {entry['name']}.",
            f"Could not remove {entry['name']}",
        )

    def toggle_power(self):
        self._run_steps(
            [("power", "off" if self.powered else "on")],
            "Bluetooth power changed.",
            "Could not change Bluetooth power",
        )
