import re
import shutil

from PyQt6.QtWidgets import (
    QComboBox,
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
from PyQt6.QtCore import Qt

from Application.styles import load_stylesheet
from Application.ui.Settings.AsyncTask import TaskRunnerMixin, command_error, run_command
from Application.ui.Settings.Logger import log_info, log_warning


def split_terse(line):
    """Split an nmcli terse (-t) line on unescaped colons."""
    fields = re.split(r"(?<!\\):", line)
    return [field.replace("\\:", ":").replace("\\\\", "\\") for field in fields]


class WifiSettingsWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("soundDisplaySettings")
        self.setStyleSheet(load_stylesheet(theme_color=launcher.get_theme_color()))
        self.nmcli = shutil.which("nmcli")
        self.wifi_device = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(12)

        title = QLabel("Wi-Fi")
        title.setObjectName("soundDisplayTitle")
        layout.addWidget(title)

        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        layout.addWidget(self._build_quick_card())
        layout.addWidget(self._build_available_card(), stretch=1)
        layout.addWidget(self._build_saved_card(), stretch=1)

        self.refresh_all()

    def _make_button(self, text, handler):
        button = QPushButton(text)
        button.setObjectName("soundDisplayButton")
        button.clicked.connect(handler)
        return button

    def _build_quick_card(self):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)

        heading = QLabel("Quick Connect")
        heading.setObjectName("soundDisplaySectionTitle")
        card_layout.addWidget(heading)

        row = QHBoxLayout()
        self.quick_combo = QComboBox()
        self.quick_combo.setObjectName("soundDisplayControl")
        self.quick_combo.setPlaceholderText("No saved networks")
        self.quick_button = self._make_button("Quick Connect", self.quick_connect_selected)
        row.addWidget(self.quick_combo, stretch=1)
        row.addWidget(self.quick_button)
        card_layout.addLayout(row)

        hint = QLabel("Reconnect to a saved network in one step. Double-click any network below to connect as well.")
        hint.setObjectName("soundDisplayStatus")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)
        return card

    def _build_available_card(self):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)

        heading = QLabel("Available Networks")
        heading.setObjectName("soundDisplaySectionTitle")
        card_layout.addWidget(heading)

        self.network_list = QListWidget()
        self.network_list.setObjectName("connectivityList")
        self.network_list.itemDoubleClicked.connect(self._connect_item)
        card_layout.addWidget(self.network_list, stretch=1)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password (leave empty for open or saved networks)")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        card_layout.addWidget(self.password_input)

        actions = QHBoxLayout()
        self.scan_button = self._make_button("Scan", self.scan_networks)
        self.connect_button = self._make_button("Connect", self.connect_selected)
        self.disconnect_button = self._make_button("Disconnect", self.disconnect_current)
        self.radio_button = self._make_button("Turn Wi-Fi Off", self.toggle_radio)
        for button in (self.scan_button, self.connect_button, self.disconnect_button, self.radio_button):
            actions.addWidget(button)
        actions.addStretch()
        card_layout.addLayout(actions)
        return card

    def _build_saved_card(self):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)

        heading = QLabel("Saved Networks")
        heading.setObjectName("soundDisplaySectionTitle")
        card_layout.addWidget(heading)

        self.saved_list = QListWidget()
        self.saved_list.setObjectName("connectivityList")
        self.saved_list.itemDoubleClicked.connect(self._quick_connect_item)
        card_layout.addWidget(self.saved_list, stretch=1)

        actions = QHBoxLayout()
        actions.addWidget(self._make_button("Forget Network", self.forget_selected))
        actions.addWidget(self._make_button("Refresh", self.refresh_saved))
        actions.addStretch()
        card_layout.addLayout(actions)
        return card

    def _set_controls_enabled(self, enabled):
        for widget in (
            self.network_list, self.saved_list, self.password_input, self.scan_button,
            self.quick_combo, self.quick_button,
            self.connect_button, self.disconnect_button, self.radio_button,
        ):
            widget.setEnabled(enabled)

    def refresh_all(self):
        if not self.nmcli:
            self.status.setText("Wi-Fi controls unavailable: NetworkManager (nmcli) was not found.")
            self._set_controls_enabled(False)
            return
        self.refresh_radio()
        self.refresh_saved()
        self.scan_networks()

    def refresh_radio(self):
        def work():
            radio = run_command([self.nmcli, "radio", "wifi"])
            devices = run_command([self.nmcli, "-t", "-f", "DEVICE,TYPE,STATE", "device"])
            return radio, devices

        def done(result):
            if isinstance(result, Exception):
                self.status.setText(f"Could not query Wi-Fi state: {result}")
                return
            radio, devices = result
            enabled = radio.stdout.strip().lower() == "enabled"
            self.radio_button.setText("Turn Wi-Fi Off" if enabled else "Turn Wi-Fi On")
            self.wifi_device = None
            for line in devices.stdout.splitlines():
                fields = split_terse(line)
                if len(fields) >= 3 and fields[1] == "wifi":
                    self.wifi_device = fields[0]
                    break
            if self.wifi_device is None:
                self.status.setText("No Wi-Fi adapter was detected.")
                self._set_controls_enabled(False)
            else:
                self._set_controls_enabled(True)
                self.status.setText("Wi-Fi is on." if enabled else "Wi-Fi is turned off.")

        self.run_async(work, done)

    def scan_networks(self):
        if not self.nmcli:
            return
        self.status.setText("Scanning for networks...")
        self.scan_button.setEnabled(False)

        def work():
            return run_command(
                [self.nmcli, "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
                 "device", "wifi", "list", "--rescan", "yes"],
                timeout=20,
            )

        def done(result):
            self.scan_button.setEnabled(self.wifi_device is not None)
            self.network_list.clear()
            if isinstance(result, Exception) or result.returncode != 0:
                self.status.setText(
                    f"Scan failed: {result if isinstance(result, Exception) else command_error(result)}"
                )
                return
            seen = set()
            for line in result.stdout.splitlines():
                fields = split_terse(line)
                if len(fields) < 4 or not fields[1] or fields[1] in seen:
                    continue
                in_use, ssid, signal, security = fields[0], fields[1], fields[2], fields[3]
                seen.add(ssid)
                connected = " ✔ connected" if in_use.strip() == "*" else ""
                lock = security if security and security != "--" else "open"
                item = QListWidgetItem(f"{ssid}  —  {signal}%  ({lock}){connected}")
                item.setData(Qt.ItemDataRole.UserRole, (ssid, lock != "open"))
                self.network_list.addItem(item)
            self.status.setText(f"Found {self.network_list.count()} network(s).")

        self.run_async(work, done)

    def refresh_saved(self):
        if not self.nmcli:
            return

        def work():
            return run_command([self.nmcli, "-t", "-f", "NAME,UUID,TYPE", "connection", "show"])

        def done(result):
            self.saved_list.clear()
            self.quick_combo.clear()
            if isinstance(result, Exception) or result.returncode != 0:
                return
            for line in result.stdout.splitlines():
                fields = split_terse(line)
                if len(fields) >= 3 and fields[2] == "802-11-wireless":
                    item = QListWidgetItem(fields[0])
                    item.setData(Qt.ItemDataRole.UserRole, (fields[0], fields[1]))
                    self.saved_list.addItem(item)
                    self.quick_combo.addItem(fields[0], (fields[0], fields[1]))

        self.run_async(work, done)

    def quick_connect_selected(self):
        network = self.quick_combo.currentData()
        if network is None:
            self.status.setText("There are no saved networks to quick connect to.")
            return
        self.quick_connect(*network)

    def _quick_connect_item(self, item):
        self.quick_connect(*item.data(Qt.ItemDataRole.UserRole))

    def _connect_item(self, item):
        self.network_list.setCurrentItem(item)
        self.connect_selected()

    def quick_connect(self, name, uuid):
        self.status.setText(f"Connecting to {name}...")
        self.quick_button.setEnabled(False)

        def work():
            return run_command([self.nmcli, "connection", "up", "uuid", uuid], timeout=45)

        def done(result):
            self.quick_button.setEnabled(True)
            if isinstance(result, Exception) or result.returncode != 0:
                details = result if isinstance(result, Exception) else command_error(result)
                log_warning(f"Quick connect to {name} failed: {details}")
                self.status.setText(f"Could not connect to {name}: {details}")
                return
            log_info(f"Quick connected to Wi-Fi network {name}.")
            self.status.setText(f"Connected to {name}.")
            self.scan_networks()

        self.run_async(work, done)

    def connect_selected(self):
        item = self.network_list.currentItem()
        if item is None:
            self.status.setText("Select a network to connect to.")
            return
        ssid, _secured = item.data(Qt.ItemDataRole.UserRole)
        password = self.password_input.text()
        self.status.setText(f"Connecting to {ssid}...")
        self.connect_button.setEnabled(False)

        def work():
            # --ask reads the password from stdin so it never appears in the process list.
            return run_command(
                [self.nmcli, "--ask", "device", "wifi", "connect", ssid],
                timeout=45,
                input_text=f"{password}\n" if password else "\n",
            )

        def done(result):
            self.connect_button.setEnabled(True)
            if isinstance(result, Exception) or result.returncode != 0:
                details = result if isinstance(result, Exception) else command_error(result)
                log_warning(f"Wi-Fi connection to {ssid} failed: {details}")
                self.status.setText(f"Could not connect to {ssid}: {details}")
                return
            log_info(f"Connected to Wi-Fi network {ssid}.")
            self.password_input.clear()
            self.status.setText(f"Connected to {ssid}.")
            self.refresh_saved()
            self.scan_networks()

        self.run_async(work, done)

    def disconnect_current(self):
        if not self.wifi_device:
            return

        def work():
            return run_command([self.nmcli, "device", "disconnect", self.wifi_device], timeout=20)

        def done(result):
            if isinstance(result, Exception) or result.returncode != 0:
                details = result if isinstance(result, Exception) else command_error(result)
                self.status.setText(f"Could not disconnect: {details}")
                return
            self.status.setText("Disconnected.")
            self.scan_networks()

        self.run_async(work, done)

    def toggle_radio(self):
        turn_on = self.radio_button.text().endswith("On")

        def work():
            return run_command([self.nmcli, "radio", "wifi", "on" if turn_on else "off"])

        def done(result):
            if isinstance(result, Exception) or result.returncode != 0:
                details = result if isinstance(result, Exception) else command_error(result)
                self.status.setText(f"Could not change Wi-Fi power: {details}")
                return
            self.refresh_all()

        self.run_async(work, done)

    def forget_selected(self):
        item = self.saved_list.currentItem()
        if item is None:
            self.status.setText("Select a saved network to forget.")
            return
        name, uuid = item.data(Qt.ItemDataRole.UserRole)
        answer = QMessageBox.question(
            self, "Forget network", f"Forget the saved network '{name}'?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def work():
            return run_command([self.nmcli, "connection", "delete", "uuid", uuid])

        def done(result):
            if isinstance(result, Exception) or result.returncode != 0:
                details = result if isinstance(result, Exception) else command_error(result)
                self.status.setText(f"Could not forget {name}: {details}")
                return
            self.status.setText(f"Forgot {name}.")
            self.refresh_saved()

        self.run_async(work, done)
