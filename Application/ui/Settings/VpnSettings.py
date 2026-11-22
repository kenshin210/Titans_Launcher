import re
import shutil
from pathlib import Path

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

from Application.ui.dialogs.file_picker import ControllerFileDialog
from Application.styles import load_stylesheet
from Application.ui.Settings.AsyncTask import TaskRunnerMixin, command_error, run_command
from Application.ui.Settings.Logger import log_info, log_warning
from Application.ui.Settings.WifiSettings import split_terse

VPN_TYPES = {"vpn", "wireguard"}
IMPORT_TYPES = [
    ("OpenVPN (.ovpn)", "openvpn"),
    ("WireGuard (.conf)", "wireguard"),
    ("OpenConnect / Cisco (.conf)", "openconnect"),
    ("PPTP", "pptp"),
    ("L2TP", "l2tp"),
]
UUID_PATTERN = re.compile(r"\(([0-9a-fA-F-]{36})\)")


def guess_import_type(path):
    """Pick the nmcli import type from a config file's extension and contents."""
    suffix = Path(path).suffix.lower()
    if suffix == ".ovpn":
        return "openvpn"
    if suffix == ".conf":
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return "wireguard"
        return "wireguard" if "[Interface]" in text else "openvpn"
    return "openvpn"


def parse_vpn_connections(output):
    """List of {name, uuid, type, active} for VPN and WireGuard profiles."""
    connections = []
    for line in output.splitlines():
        fields = split_terse(line)
        if len(fields) >= 4 and fields[2] in VPN_TYPES:
            connections.append({
                "name": fields[0], "uuid": fields[1], "type": fields[2],
                "active": fields[3].lower() == "yes",
            })
    return connections


class VpnSettingsWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("soundDisplaySettings")
        self.setStyleSheet(load_stylesheet(theme_color=launcher.get_theme_color()))
        self.nmcli = shutil.which("nmcli")
        self.connections = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(12)

        title = QLabel("VPN")
        title.setObjectName("soundDisplayTitle")
        layout.addWidget(title)

        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        layout.addWidget(self._build_list_card(), stretch=1)
        layout.addWidget(self._build_add_card())

        self.refresh()

    def _make_button(self, text, handler):
        button = QPushButton(text)
        button.setObjectName("soundDisplayButton")
        button.clicked.connect(handler)
        return button

    def _build_list_card(self):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)

        heading = QLabel("VPN Connections")
        heading.setObjectName("soundDisplaySectionTitle")
        card_layout.addWidget(heading)

        self.vpn_list = QListWidget()
        self.vpn_list.setObjectName("connectivityList")
        self.vpn_list.itemDoubleClicked.connect(lambda _item: self.toggle_selected())
        card_layout.addWidget(self.vpn_list, stretch=1)

        actions = QHBoxLayout()
        self.toggle_button = self._make_button("Enable / Disable", self.toggle_selected)
        self.remove_button = self._make_button("Remove", self.remove_selected)
        self.refresh_button = self._make_button("Refresh", self.refresh)
        for button in (self.toggle_button, self.remove_button, self.refresh_button):
            actions.addWidget(button)
        actions.addStretch()
        card_layout.addLayout(actions)
        return card

    def _build_add_card(self):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)

        heading = QLabel("Add VPN")
        heading.setObjectName("soundDisplaySectionTitle")
        card_layout.addWidget(heading)

        file_row = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Path to a .ovpn or WireGuard .conf file")
        self.file_input.textChanged.connect(self._guess_type)
        self.browse_button = self._make_button("Browse...", self.browse_file)
        file_row.addWidget(self.file_input, stretch=1)
        file_row.addWidget(self.browse_button)
        card_layout.addLayout(file_row)

        options_row = QHBoxLayout()
        self.type_combo = QComboBox()
        self.type_combo.setObjectName("soundDisplayControl")
        for label, value in IMPORT_TYPES:
            self.type_combo.addItem(label, value)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username (optional)")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password (optional)")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        options_row.addWidget(self.type_combo)
        options_row.addWidget(self.username_input, stretch=1)
        options_row.addWidget(self.password_input, stretch=1)
        card_layout.addLayout(options_row)

        actions = QHBoxLayout()
        self.add_button = self._make_button("Add VPN", self.add_vpn)
        actions.addWidget(self.add_button)
        actions.addStretch()
        card_layout.addLayout(actions)
        return card

    def _set_controls_enabled(self, enabled):
        for widget in (
            self.vpn_list, self.toggle_button, self.remove_button, self.refresh_button,
            self.file_input, self.browse_button, self.type_combo, self.username_input,
            self.password_input, self.add_button,
        ):
            widget.setEnabled(enabled)

    def _selected(self):
        item = self.vpn_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _guess_type(self, path):
        if Path(path).is_file():
            index = self.type_combo.findData(guess_import_type(path))
            if index >= 0:
                self.type_combo.setCurrentIndex(index)

    def browse_file(self):
        path, _ = ControllerFileDialog.get_open_file_name(
            self, "Select VPN configuration", str(Path.home()),
            "VPN configuration (*.ovpn *.conf);;All files (*)",
        )
        if path:
            self.file_input.setText(path)

    def refresh(self, notice=None):
        if not self.nmcli:
            self.status.setText("VPN controls unavailable: NetworkManager (nmcli) was not found.")
            self._set_controls_enabled(False)
            return
        self.status.setText(notice or "Loading VPN connections...")
        current = self._selected()
        selected_uuid = current["uuid"] if current else None

        def work():
            return run_command([self.nmcli, "-t", "-f", "NAME,UUID,TYPE,ACTIVE", "connection", "show"])

        def done(result):
            if isinstance(result, Exception) or result.returncode != 0:
                error = result if isinstance(result, Exception) else command_error(result)
                self.status.setText(f"Could not list VPN connections: {error}")
                return
            self.connections = parse_vpn_connections(result.stdout)
            self.vpn_list.clear()
            for connection in self.connections:
                kind = "WireGuard" if connection["type"] == "wireguard" else "VPN"
                state = "Connected" if connection["active"] else "Disconnected"
                item = QListWidgetItem(f"{connection['name']}   [{kind}]   {state}")
                item.setData(Qt.ItemDataRole.UserRole, connection)
                self.vpn_list.addItem(item)
                if connection["uuid"] == selected_uuid:
                    self.vpn_list.setCurrentItem(item)
            active = sum(1 for connection in self.connections if connection["active"])
            if notice:
                self.status.setText(notice)
            elif not self.connections:
                self.status.setText("No VPNs configured. Add one below.")
            else:
                self.status.setText(f"{len(self.connections)} VPN(s) configured, {active} connected.")

        self.run_async(work, done)

    def toggle_selected(self):
        connection = self._selected()
        if not connection:
            self.status.setText("Select a VPN first.")
            return
        action = "down" if connection["active"] else "up"
        self.status.setText(f"{'Disconnecting' if connection['active'] else 'Connecting'} {connection['name']}...")
        self._set_controls_enabled(False)

        def work():
            return run_command([self.nmcli, "connection", action, "uuid", connection["uuid"]], timeout=60)

        def done(result):
            self._set_controls_enabled(True)
            if isinstance(result, Exception) or result.returncode != 0:
                error = result if isinstance(result, Exception) else command_error(result)
                log_warning(f"VPN {action} failed for {connection['name']}: {error}")
                self.refresh(f"Could not turn {connection['name']} {'off' if action == 'down' else 'on'}: {error}")
            else:
                log_info(f"VPN {action}: {connection['name']}")
                self.refresh()

        self.run_async(work, done)

    def remove_selected(self):
        connection = self._selected()
        if not connection:
            self.status.setText("Select a VPN first.")
            return
        answer = QMessageBox.question(
            self, "Remove VPN", f"Remove '{connection['name']}'? This deletes the saved configuration.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._set_controls_enabled(False)

        def work():
            return run_command([self.nmcli, "connection", "delete", "uuid", connection["uuid"]])

        def done(result):
            self._set_controls_enabled(True)
            if isinstance(result, Exception) or result.returncode != 0:
                error = result if isinstance(result, Exception) else command_error(result)
                log_warning(f"VPN removal failed for {connection['name']}: {error}")
                self.refresh(f"Could not remove {connection['name']}: {error}")
            else:
                log_info(f"VPN removed: {connection['name']}")
                self.refresh()

        self.run_async(work, done)

    def add_vpn(self):
        path = self.file_input.text().strip()
        if not path or not Path(path).is_file():
            self.status.setText("Choose an existing VPN configuration file first.")
            return
        vpn_type = self.type_combo.currentData()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        self._set_controls_enabled(False)
        self.status.setText("Importing VPN...")

        def work():
            result = run_command([self.nmcli, "connection", "import", "type", vpn_type, "file", path], timeout=30)
            if result.returncode != 0:
                return result, None
            match = UUID_PATTERN.search(result.stdout)
            extra = None
            if match and (username or password) and vpn_type != "wireguard":
                settings = []
                if username:
                    settings += ["+vpn.data", f"username={username}"]
                if password:
                    settings += ["+vpn.data", "password-flags=0", "vpn.secrets", f"password={password}"]
                extra = run_command([self.nmcli, "connection", "modify", match.group(1), *settings])
            return result, extra

        def done(result):
            self._set_controls_enabled(True)
            if isinstance(result, Exception):
                self.status.setText(f"Could not add VPN: {result}")
                return
            imported, extra = result
            if imported.returncode != 0:
                error = command_error(imported)
                log_warning(f"VPN import failed: {error}")
                self.refresh(f"Could not add VPN: {error}")
                return
            log_info(f"VPN imported from {path}")
            self.file_input.clear()
            self.username_input.clear()
            self.password_input.clear()
            if extra is not None and extra.returncode != 0:
                self.refresh(f"VPN added, but credentials were not saved: {command_error(extra)}")
            else:
                self.refresh()

        self.run_async(work, done)
