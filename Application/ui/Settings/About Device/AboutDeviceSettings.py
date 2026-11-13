import csv
import platform
import re
import shlex
import shutil
import socket
import subprocess
from importlib import import_module
from pathlib import Path

from PyQt6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTabWidget, QVBoxLayout, QWidget
)

from Application.ui.Settings.Logger import log_error, log_info, log_warning
from Application.ui.Settings.tab_style import tab_widget_stylesheet

SystemUpdateWidget = import_module(
    "Application.ui.Settings.About Device.Updates"
).SystemUpdateWidget
FileCheckWidget = import_module(
    "Application.ui.Settings.About Device.FileCheck"
).FileCheckWidget
device_styles = import_module("Application.ui.Settings.About Device.DeviceStyles")
StorageOverviewWidget = import_module(
    "Application.ui.Settings.Phase3Settings"
).StorageOverviewWidget

create_device_page_title = device_styles.create_device_page_title
style_device_page = device_styles.style_device_page
style_device_form = device_styles.style_device_form


def get_distribution_version():
    release_file = Path("/etc/os-release")
    try:
        release_data = {}
        for line in release_file.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            parsed_value = shlex.split(value, comments=False, posix=True)
            release_data[key] = parsed_value[0] if parsed_value else ""
        return release_data.get("PRETTY_NAME") or release_data.get("VERSION_ID") or "Unknown"
    except (OSError, ValueError) as error:
        log_warning(f"Could not read Linux distribution version from {release_file}: {error}")
        return "Unknown"


def _format_bytes(value):
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{amount:.0f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"


def get_cpu_name():
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            normalized_key = key.strip().lower()
            model_name = value.strip()
            if (
                separator
                and normalized_key in ("model name", "hardware", "model")
                and not (normalized_key == "model" and model_name.isdigit())
            ):
                return model_name
    except OSError as error:
        log_warning(f"Could not read CPU information: {error}")
    return platform.processor() or platform.machine() or "Unknown"


def get_memory_size():
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                total_kib = int(line.split()[1])
                return _format_bytes(total_kib * 1024)
    except (OSError, ValueError, IndexError) as error:
        log_warning(f"Could not read memory information: {error}")
    return "Unknown"


def get_graphics_from_sysfs():
    vendor_names = {
        "1002": "AMD",
        "10de": "NVIDIA",
        "8086": "Intel",
        "1af4": "Virtual GPU",
    }
    devices = []
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        uevent_path = card / "device" / "uevent"
        try:
            device_data = dict(
                line.split("=", 1)
                for line in uevent_path.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )
        except OSError:
            continue
        pci_id = device_data.get("PCI_ID", "")
        vendor_id = pci_id.split(":", 1)[0].lower()
        vendor = vendor_names.get(vendor_id)
        driver = device_data.get("DRIVER")
        description = " ".join(part for part in (vendor, driver) if part)
        if pci_id:
            description = f"{description} (PCI ID {pci_id})" if description else f"PCI ID {pci_id}"
        elif driver:
            description = f"{driver} graphics driver"
        if description and description not in devices:
            devices.append(description)
    return ", ".join(devices)


def get_gpu_name():
    lspci = shutil.which("lspci")
    if not lspci:
        return get_graphics_from_sysfs() or "Unknown"
    try:
        result = subprocess.run(
            [lspci, "-mm"], capture_output=True, text=True, check=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError) as error:
        log_warning(f"Could not detect graphics hardware with lspci: {error}")
        return "Unknown"

    graphics_devices = []
    for row in csv.reader(result.stdout.splitlines(), delimiter=" ", quotechar='"', skipinitialspace=True):
        if len(row) >= 4 and any(
            device_type in row[1].lower()
            for device_type in ("vga", "3d controller", "display controller")
        ):
            graphics_devices.append(" ".join(row[2:4]))
    return ", ".join(graphics_devices) if graphics_devices else "Not detected"


def get_root_storage():
    try:
        usage = shutil.disk_usage("/")
        used_percent = usage.used / usage.total * 100 if usage.total else 0
        return (
            f"{_format_bytes(usage.used)} used of {_format_bytes(usage.total)} "
            f"({used_percent:.0f}%)"
        )
    except OSError as error:
        log_warning(f"Could not read root filesystem storage information: {error}")
        return "Unknown"


def get_device_serial_number():
    serial_paths = (
        Path("/sys/class/dmi/id/product_serial"),
        Path("/sys/class/dmi/id/board_serial"),
    )
    unavailable_values = {"", "none", "unknown", "not specified", "to be filled by o.e.m."}
    for serial_path in serial_paths:
        try:
            serial = serial_path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if serial.lower() not in unavailable_values:
            return serial

    device_tree_serial = Path("/sys/firmware/devicetree/base/serial-number")
    try:
        serial = device_tree_serial.read_bytes().rstrip(b"\0").decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return "Unavailable"
    return serial if serial.lower() not in unavailable_values else "Unavailable"


def get_mac_addresses():
    addresses = []
    for address_path in sorted(Path("/sys/class/net").glob("*/address")):
        interface = address_path.parent.name
        if interface == "lo":
            continue
        try:
            address = address_path.read_text(encoding="utf-8").strip().lower()
        except OSError as error:
            log_warning(f"Could not read MAC address for interface {interface}: {error}")
            continue
        if address and address != "00:00:00:00:00:00":
            addresses.append(f"{interface}: {address}")
    return ", ".join(addresses) if addresses else "Unavailable"


def get_bluetooth_address():
    addresses = []
    for address_path in sorted(Path("/sys/class/bluetooth").glob("hci*/address")):
        try:
            address = address_path.read_text(encoding="utf-8").strip().upper()
        except OSError as error:
            log_warning(f"Could not read Bluetooth address from {address_path}: {error}")
            continue
        if address:
            addresses.append(address)
    return ", ".join(addresses) if addresses else "Unavailable"


def get_system_uptime():
    try:
        uptime_seconds = int(float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0]))
    except (OSError, ValueError, IndexError) as error:
        log_warning(f"Could not read system uptime: {error}")
        return "Unavailable"

    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    parts = []
    if days:
        parts.append(f"{days} day" + ("s" if days != 1 else ""))
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes or not parts:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    return ", ".join(parts)


class AboutDeviceWidget(QWidget):
    def __init__(self, launcher=None, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.setStyleSheet("color: white;")

        root_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        theme_color = launcher.get_theme_color() if launcher and hasattr(launcher, "get_theme_color") else "#DC143C"
        self.tabs.setStyleSheet(tab_widget_stylesheet(theme_color))
        root_layout.addWidget(self.tabs)

        self.about_page = QWidget()
        about_layout = QVBoxLayout(self.about_page)
        style_device_page(self.about_page, about_layout)
        about_layout.addWidget(create_device_page_title("About Device"))

        details = QFormLayout()
        style_device_form(details)
        hostname_row = QHBoxLayout()
        self.hostname_input = QLineEdit(socket.gethostname())
        save_hostname_button = QPushButton("Save Device Name")
        save_hostname_button.clicked.connect(self.save_device_name)
        hostname_row.addWidget(self.hostname_input, stretch=1)
        hostname_row.addWidget(save_hostname_button)
        details.addRow("Device Name:", hostname_row)

        self.linux_version_label = QLabel(f"Linux {platform.release()}")
        self.distribution_label = QLabel(get_distribution_version())
        self.linux_version_label.setWordWrap(True)
        self.distribution_label.setWordWrap(True)
        details.addRow("Linux OS Version:", self.linux_version_label)
        details.addRow("Distribution Version:", self.distribution_label)
        about_layout.addLayout(details)
        about_layout.addStretch()
        self.tabs.addTab(self.about_page, "About Device")

        self.specifications_page = QWidget()
        specifications_layout = QVBoxLayout(self.specifications_page)
        style_device_page(self.specifications_page, specifications_layout)
        specifications_layout.addWidget(create_device_page_title("Device Specifications"))

        self.specification_values = {
            "CPU:": QLabel(),
            "Memory:": QLabel(),
            "Graphics:": QLabel(),
            "Storage (root):": QLabel(),
            "Serial Number:": QLabel(),
            "MAC Address(es):": QLabel(),
            "Bluetooth Address:": QLabel(),
            "Uptime:": QLabel(),
        }
        specifications_form = QFormLayout()
        style_device_form(specifications_form)
        for label, value_label in self.specification_values.items():
            value_label.setWordWrap(True)
            specifications_form.addRow(label, value_label)
        specifications_layout.addLayout(specifications_form)
        specifications_layout.addStretch()
        self.tabs.addTab(self.specifications_page, "Device Specifications")
        update_page = SystemUpdateWidget(launcher)
        self.tabs.addTab(update_page, "System Update")
        self.tabs.addTab(FileCheckWidget(launcher, update_page), "File Check")
        self.tabs.addTab(StorageOverviewWidget(launcher), "Storage")
        self.tabs.currentChanged.connect(self.update_specifications)

    def update_specifications(self, index):
        if self.tabs.widget(index) is not self.specifications_page:
            return
        self.specification_values["CPU:"].setText(get_cpu_name())
        self.specification_values["Memory:"].setText(get_memory_size())
        self.specification_values["Graphics:"].setText(get_gpu_name())
        self.specification_values["Storage (root):"].setText(get_root_storage())
        self.specification_values["Serial Number:"].setText(get_device_serial_number())
        self.specification_values["MAC Address(es):"].setText(get_mac_addresses())
        self.specification_values["Bluetooth Address:"].setText(get_bluetooth_address())
        self.specification_values["Uptime:"].setText(get_system_uptime())

    def save_device_name(self):
        hostname = self.hostname_input.text().strip().lower()
        labels = hostname.split(".")
        if (
            not hostname
            or len(hostname) > 253
            or any(
                not label
                or len(label) > 63
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
                for label in labels
            )
        ):
            QMessageBox.warning(
                self,
                "Invalid Device Name",
                "Use letters, numbers, and hyphens; each part must start and end with a letter or number."
            )
            return

        hostnamectl = shutil.which("hostnamectl")
        if not hostnamectl:
            QMessageBox.critical(
                self,
                "Hostname Change Unavailable",
                "The hostnamectl command is not installed on this system."
            )
            return

        pkexec = shutil.which("pkexec")
        command = [hostnamectl, "set-hostname", hostname]
        if pkexec:
            command = [pkexec, *command]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        except subprocess.CalledProcessError as error:
            details = (error.stderr or error.stdout or str(error)).strip()
            log_error(f"Could not change the device hostname to '{hostname}'.", details=details)
            QMessageBox.critical(
                self,
                "Hostname Change Failed",
                f"Could not change the device name. Administrator authorization may be required.\n\n{details}"
            )
            return
        except (OSError, subprocess.TimeoutExpired) as error:
            log_error(f"Could not change the device hostname to '{hostname}': {error}")
            QMessageBox.critical(
                self,
                "Hostname Change Failed",
                f"Could not change the device name:\n{error}"
            )
            return

        self.hostname_input.setText(hostname)
        log_info(f"Changed system hostname to '{hostname}'.")
        QMessageBox.information(self, "Device Name Updated", f"Device name changed to {hostname}.")
