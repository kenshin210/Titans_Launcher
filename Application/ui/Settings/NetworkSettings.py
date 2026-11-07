# -*- coding: utf-8 -*-
import shutil
from PyQt6.QtCore import Qt

from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from Application.core.network_info import (
    band_from_frequency, build_modify_command, parse_device_show, parse_iw_link,
    split_cidr, split_terse, validate_network_settings, wired_speed,
)
from Application.core.proxy import PROXY_KINDS, apply_system_proxy, validate_endpoint
from Application.styles import load_stylesheet
from Application.ui.Settings.AsyncTask import TaskRunnerMixin, command_error, run_command
from Application.ui.Settings.Logger import log_info, log_warning
from Application.ui.Settings.VpnSettings import VpnSettingsWidget
from Application.ui.Settings.WifiSettings import WifiSettingsWidget
from Application.ui.Settings.tab_style import tab_widget_stylesheet

INPUT_STYLE = (
    "background-color: rgba(40, 40, 40, 200); color: white; padding: 8px; "
    "border-radius: 6px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25);"
)
READONLY_STYLE = INPUT_STYLE.replace("rgba(40, 40, 40, 200)", "rgba(28, 28, 28, 200)") + "color: #BBBBBB;"


class _SettingsTab(QWidget):
    """Shared look for the Network tabs: title, status line and a card."""

    def __init__(self, launcher, title_text):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("soundDisplaySettings")
        self.setStyleSheet(load_stylesheet(theme_color=launcher.get_theme_color()))

        self.page_layout = QVBoxLayout(self)
        self.page_layout.setContentsMargins(10, 10, 10, 0)
        self.page_layout.setSpacing(12)

        title = QLabel(title_text)
        title.setObjectName("soundDisplayTitle")
        self.page_layout.addWidget(title)

        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        self.page_layout.addWidget(self.status)

        self.card = QFrame()
        self.card.setObjectName("soundDisplayCard")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(18, 16, 18, 16)
        self.card_layout.setSpacing(12)
        self.page_layout.addWidget(self.card)
        self.page_layout.addStretch()

    def make_button(self, text, handler):
        button = QPushButton(text)
        button.setObjectName("soundDisplayButton")
        button.clicked.connect(handler)
        return button


class ProxySettingsTab(_SettingsTab):
    def __init__(self, launcher):
        super().__init__(launcher, "Proxy")
        config = launcher.config

        self.enable_box = QCheckBox("Use a manual proxy")
        self.enable_box.setChecked(config.get("_proxy_mode", "Off") == "Manual")
        self.enable_box.toggled.connect(self._update_enabled)
        self.card_layout.addWidget(self.enable_box)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.inputs = {}
        for kind, label in (("http", "HTTP proxy:"), ("https", "HTTPS proxy:"), ("socks", "SOCKS proxy:")):
            field = QLineEdit(config.get(f"_proxy_{kind}", ""))
            field.setPlaceholderText("host:port")
            self.inputs[kind] = field
            form.addRow(QLabel(label), field)
        self.no_proxy_input = QLineEdit(config.get("_proxy_no_proxy", ""))
        self.no_proxy_input.setPlaceholderText("localhost,127.0.0.1,192.168.0.0/16")
        form.addRow(QLabel("No proxy for:"), self.no_proxy_input)
        self.card_layout.addLayout(form)

        row = QHBoxLayout()
        row.addWidget(self.make_button("Save Proxy", self.save))
        row.addStretch()
        self.card_layout.addLayout(row)

        hint = QLabel(
            "Applied to applications started from the launcher, and to the system proxy "
            "settings when gsettings is available."
        )
        hint.setObjectName("soundDisplayStatus")
        hint.setWordWrap(True)
        self.card_layout.addWidget(hint)
        self._update_enabled()

    def _update_enabled(self):
        enabled = self.enable_box.isChecked()
        for field in [*self.inputs.values(), self.no_proxy_input]:
            field.setEnabled(enabled)
            field.setStyleSheet(INPUT_STYLE if enabled else READONLY_STYLE)

    def save(self):
        try:
            endpoints = {kind: validate_endpoint(self.inputs[kind].text()) for kind in PROXY_KINDS}
        except ValueError as error:
            QMessageBox.warning(self, "Proxy", str(error))
            return
        manual = self.enable_box.isChecked()
        if manual and not any(endpoints.values()):
            QMessageBox.warning(self, "Proxy", "Enter at least one proxy address, or untick the proxy option.")
            return

        config = self.launcher.config
        config["_proxy_mode"] = "Manual" if manual else "Off"
        for kind, endpoint in endpoints.items():
            config[f"_proxy_{kind}"] = endpoint
        config["_proxy_no_proxy"] = self.no_proxy_input.text().strip()
        self.launcher.save_config_file()

        applied = apply_system_proxy(config)
        log_info(f"Network Settings: Proxy mode set to {config['_proxy_mode']}")
        self.status.setText(
            "Proxy saved and applied to system settings." if applied
            else "Proxy saved. It will be used by applications launched from here."
        )


class NetworkDetailsTab(_SettingsTab, TaskRunnerMixin):
    def __init__(self, launcher):
        super().__init__(launcher, "Details")
        self.nmcli = shutil.which("nmcli")
        self.device = None
        self.uuid = None
        self.connection_type = "802-3-ethernet"

        self.dhcp_box = QCheckBox("DHCP (automatic)")
        self.static_box = QCheckBox("Static (manual)")
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.dhcp_box)
        self.mode_group.addButton(self.static_box)
        self.dhcp_box.setChecked(True)
        self.dhcp_box.toggled.connect(self._update_editable)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.dhcp_box)
        mode_row.addWidget(self.static_box)
        mode_row.addStretch()
        self.card_layout.addLayout(mode_row)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.read_only = {}
        for key, label in (
            ("status", "Status:"), ("connection", "Connection:"),
            ("technology", "Wi-Fi technology:"), ("speed", "Connection speed:"),
            ("signal", "Signal strength:"),
        ):
            value = QLabel("—")
            value.setObjectName("soundDisplayValue")
            self.read_only[key] = value
            form.addRow(QLabel(label), value)

        self.ip_input = QLineEdit()
        self.subnet_input = QLineEdit()
        self.gateway_input = QLineEdit()
        self.mac_input = QLineEdit()
        self.mac_input.setReadOnly(True)
        self.mac_input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mac_input.setCursor(Qt.CursorShape.ArrowCursor)
        self.mac_input.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        form.addRow(QLabel("IP address:"), self.ip_input)
        form.addRow(QLabel("Subnet mask:"), self.subnet_input)
        form.addRow(QLabel("Default route:"), self.gateway_input)
        form.addRow(QLabel("MAC address:"), self.mac_input)
        self.card_layout.addLayout(form)

        row = QHBoxLayout()
        self.apply_button = self.make_button("Apply", self.apply_changes)
        self.refresh_button = self.make_button("Refresh", self.refresh)
        row.addWidget(self.apply_button)
        row.addWidget(self.refresh_button)
        row.addStretch()
        self.card_layout.addLayout(row)

        self._update_editable()
        self.refresh()

    def _update_editable(self):
        static = self.static_box.isChecked()
        for field in (self.ip_input, self.subnet_input, self.gateway_input):
            field.setReadOnly(not static)
            field.setStyleSheet(INPUT_STYLE if static else READONLY_STYLE)
        self.mac_input.setStyleSheet(READONLY_STYLE)

    def refresh(self):
        if not self.nmcli:
            self.status.setText("Network details unavailable: NetworkManager (nmcli) was not found.")
            self.apply_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
            return
        self.status.setText("Reading network details...")
        self.run_async(self._read_details, self._show_details)

    def _read_details(self):
        listing = run_command([self.nmcli, "-t", "-f", "DEVICE,TYPE,STATE", "device"])
        candidates = []
        for line in listing.stdout.splitlines():
            device, kind, state = (split_terse(line) + ["", "", ""])[:3]
            if kind in ("wifi", "ethernet"):
                candidates.append((state != "connected", kind != "wifi", device, kind))
        if not candidates:
            return {"error": "No Wi-Fi or Ethernet adapter was found."}
        _, _, device, kind = sorted(candidates)[0]

        info = parse_device_show(run_command([self.nmcli, "-t", "device", "show", device]).stdout)
        details = {"device": device, "kind": kind, "info": info, "method": "auto"}
        uuid = info.get("GENERAL.CON-UUID", "")
        if uuid:
            method = run_command([self.nmcli, "-g", "ipv4.method", "connection", "show", "uuid", uuid])
            details["method"] = method.stdout.strip() or "auto"

        if kind == "wifi":
            wifi = run_command([self.nmcli, "-t", "-f", "IN-USE,SIGNAL,RATE,FREQ",
                                "device", "wifi", "list", "ifname", device, "--rescan", "no"])
            for line in wifi.stdout.splitlines():
                fields = split_terse(line)
                if len(fields) >= 4 and fields[0].strip() == "*":
                    details.update(signal=fields[1], rate=fields[2], freq=fields[3])
                    break
            iw = shutil.which("iw")
            if iw:
                details["iw"] = parse_iw_link(run_command([iw, "dev", device, "link"]).stdout)
        else:
            details["rate"] = wired_speed(device)
        return details

    def _show_details(self, result):
        if isinstance(result, Exception) or "error" in result:
            self.status.setText(str(result) if isinstance(result, Exception) else result["error"])
            return
        info = result["info"]
        self.device = result["device"]
        self.uuid = info.get("GENERAL.CON-UUID") or None
        self.connection_type = "802-11-wireless" if result["kind"] == "wifi" else "802-3-ethernet"

        state = info.get("GENERAL.STATE", "unknown")
        self.read_only["status"].setText(state.split(" ", 1)[-1].strip("()") or state)
        self.read_only["connection"].setText(
            f"{info.get('GENERAL.CONNECTION', 'Not connected')} ({self.device})"
        )

        ip_text, subnet = split_cidr(info.get("IP4.ADDRESS", ""))
        self.ip_input.setText(ip_text)
        self.subnet_input.setText(subnet)
        self.gateway_input.setText(info.get("IP4.GATEWAY", ""))
        self.mac_input.setText(info.get("GENERAL.HWADDR", ""))

        standard, dbm, bitrate = result.get("iw", ("", "", ""))
        if result["kind"] == "wifi":
            band = band_from_frequency(result.get("freq", ""))
            technology = standard or "Wi-Fi"
            self.read_only["technology"].setText(f"{technology} · {band}" if band else technology)
            self.read_only["speed"].setText(bitrate or result.get("rate", "") or "—")
            percent = result.get("signal", "")
            signal = f"{percent}%" if percent else "—"
            self.read_only["signal"].setText(f"{signal} ({dbm})" if dbm else signal)
        else:
            self.read_only["technology"].setText("Wired (Ethernet)")
            self.read_only["speed"].setText(result.get("rate") or "—")
            self.read_only["signal"].setText("N/A (wired)")

        (self.static_box if result["method"] == "manual" else self.dhcp_box).setChecked(True)
        self._update_editable()
        self.apply_button.setEnabled(self.uuid is not None)
        self.status.setText(
            "" if self.uuid else "Not connected: connect to a network to change its settings."
        )

    def apply_changes(self):
        if not self.uuid:
            return
        method = "manual" if self.static_box.isChecked() else "auto"
        settings, error = validate_network_settings(
            method, self.ip_input.text(), self.subnet_input.text(),
            self.gateway_input.text(),
        )
        if error:
            QMessageBox.warning(self, "Network Details", error)
            return
        answer = QMessageBox.question(
            self, "Apply Network Settings",
            "The connection will restart and may drop for a moment. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        modify = build_modify_command(self.nmcli, self.uuid, self.connection_type, settings)
        self.status.setText("Applying network settings...")
        self.apply_button.setEnabled(False)

        def work():
            result = run_command(modify)
            if result.returncode != 0:
                return result
            return run_command([self.nmcli, "connection", "up", "uuid", self.uuid], timeout=45)

        def done(result):
            self.apply_button.setEnabled(True)
            if isinstance(result, Exception) or result.returncode != 0:
                message = str(result) if isinstance(result, Exception) else command_error(result)
                log_warning("Network Settings: Failed to apply settings.", details=message)
                self.status.setText(f"Could not apply settings: {message}")
                return
            log_info(f"Network Settings: Applied {method} settings on {self.device}")
            self.refresh()

        self.run_async(work, done)


class NetworkSettingsWidget(QTabWidget):
    """Network section: Wi-Fi, VPN and Proxy tabs; the Details tab is Advanced-only."""

    def __init__(self, launcher, advanced=False):
        super().__init__()
        self.setStyleSheet(tab_widget_stylesheet(launcher.get_theme_color()))
        self.addTab(WifiSettingsWidget(launcher), "Wi-Fi")
        self.addTab(VpnSettingsWidget(launcher), "VPN")
        self.addTab(ProxySettingsTab(launcher), "Proxy")
        if advanced:
            self.addTab(NetworkDetailsTab(launcher), "Details")
