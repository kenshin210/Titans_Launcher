# -*- coding: utf-8 -*-
import sys
import json
import subprocess
import threading
import time
import shutil
import shlex
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit
import cv2
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QLabel,
    QDialog, QFormLayout, QLineEdit, QCheckBox, QFileDialog, QListWidget,
    QMessageBox, QTabWidget, QComboBox, QToolButton, QCompleter, QMenu,
    QStackedWidget, QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, QUrl, QTimer, QSize, QPropertyAnimation, QEasingCurve, QRect,
    pyqtSignal, QPoint, QParallelAnimationGroup, QThread
)
from PyQt6.QtGui import QImage, QPixmap, QIcon, QAction

# Optional pygame-ce import for robust gamepad support
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    from Settings.Logger import log_critical, log_error, log_warning, log_info, install_excepthook
except ImportError:
    from Logger import log_critical, log_error, log_warning, log_info, install_excepthook

install_excepthook()

CONFIG_PATH = Path.home() / ".config" / "Titans-launcher" / "profiles.json"
DEFAULT_VIDEO_PATH = Path.home() / ".config" / "Titans-launcher" / "background.mp4"
CONTROLLER_INPUTS_DIR = Path(__file__).resolve().parent / "Settings" / "Inputs"
DEFAULT_CONTROLLER_BINDINGS = {
    "up": ["hat:up", "axis:1:negative"],
    "down": ["hat:down", "axis:1:positive"],
    "left": ["hat:left", "axis:0:negative"],
    "right": ["hat:right", "axis:0:positive"],
    "select": ["button:0"],
    "back": ["button:1"],
    "previous_tab": ["button:4"],
    "next_tab": ["button:5"],
    "close_app": ["button:8"]
}

# Default configuration generated on first run
DEFAULT_CONFIG = {
    "_advanced_mode": False,
    "_background_path": str(DEFAULT_VIDEO_PATH),
    "_theme": "Crimson Red",
    "_button_shape": "Rounded Square",
    "_enable_animations": True,
    "_enable_glitch": False,
    "_ntp_server": "nz.pool.ntp.org",
    "_ntp_country": "New Zealand",
    "_ntp_offset": 12,
    "_time_format": "12-Hour (AM/PM)",
    "_power_command": "systemctl poweroff",
    "_sleep_command": "systemctl suspend",
    "_restart_command": "systemctl reboot",
    "_power_icon_path": "",
    "_custom_colors": {
        "Crimson Red": "#DC143C",
        "Cyberpunk Blue": "#00F0FF",
        "Emerald Green": "#00C853",
        "Purple Neon": "#AA00FF"
    },
    "Jellyfin": {
        "command": "Jellyfin",
        "arguments": "",
        "manage_antimicrox": True,
        "profile": str(Path.home() / ".config/antimicrox/retro.amxp"),
        "icon_path": ""
    },
    "Moonlight": {
        "command": "moonlight",
        "arguments": "",
        "manage_antimicrox": False,
        "profile": "",
        "icon_path": ""
    },
    "Youtube": {
        "command": "firefox",
        "arguments": "--kiosk https://www.youtube.com",
        "type": "website",
        "website_url": "https://www.youtube.com",
        "manage_antimicrox": True,
        "profile": "",
        "controller_close_enabled": False,
        "icon_path": ""
    },
    "Google TV": {
        "command": "firefox",
        "arguments": "--kiosk https://tv.google/",
        "type": "website",
        "website_url": "https://tv.google/",
        "manage_antimicrox": True,
        "profile": "",
        "controller_close_enabled": False,
        "icon_path": ""
    }
}

def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG)
        log_info(f"Initialized default configuration at {CONFIG_PATH}")
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
            if "_advanced_mode" not in data:
                data["_advanced_mode"] = False
            if "_background_path" not in data:
                data["_background_path"] = str(DEFAULT_VIDEO_PATH)
            if "_theme" not in data or data["_theme"] == "Netflix Red":
                data["_theme"] = "Crimson Red"
            if "_button_shape" not in data:
                data["_button_shape"] = "Rounded Square"
            if "_enable_animations" not in data:
                data["_enable_animations"] = True
            if "_enable_glitch" not in data:
                data["_enable_glitch"] = False
            if "_ntp_server" not in data:
                data["_ntp_server"] = "nz.pool.ntp.org"
            if "_ntp_country" not in data:
                data["_ntp_country"] = "New Zealand"
            if "_ntp_offset" not in data:
                data["_ntp_offset"] = 12
            if "_time_format" not in data:
                data["_time_format"] = "12-Hour (AM/PM)"
            if "_power_command" not in data:
                data["_power_command"] = "systemctl poweroff"
            if "_sleep_command" not in data:
                data["_sleep_command"] = "systemctl suspend"
            if "_restart_command" not in data:
                data["_restart_command"] = "systemctl reboot"
            if "_power_icon_path" not in data:
                data["_power_icon_path"] = ""
            if "_custom_colors" not in data:
                data["_custom_colors"] = DEFAULT_CONFIG["_custom_colors"]

            for k, v in data.items():
                if not k.startswith("_") and isinstance(v, dict):
                    if "arguments" not in v:
                        v["arguments"] = ""
            log_info(f"Loaded configuration successfully from {CONFIG_PATH}")
            return data
    except Exception as e:
        log_error(f"Error parsing configuration file {CONFIG_PATH}: {e}", details=str(e))
        return DEFAULT_CONFIG

def save_config(data):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
        log_info(f"Configuration saved to {CONFIG_PATH}")
    except Exception as e:
        log_error(f"Failed to save configuration: {e}", details=str(e))

def fetch_ntp_time(server_address, offset_hours):
    import socket
    import struct
    port = 123
    data = b'\x1b' + 47 * b'\0'
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2.0)
            s.sendto(data, (server_address, port))
            response, _ = s.recvfrom(1024)
        if response:
            unpacked = struct.unpack('!12I', response)[10]
            UNIX_EPOCH_DIFF = 2208988800
            unix_time = unpacked - UNIX_EPOCH_DIFF

            dt_utc = datetime.fromtimestamp(unix_time, tz=timezone.utc)
            res = dt_utc.astimezone(timezone(timedelta(hours=offset_hours)))
            log_info(f"NTP sync successful with {server_address}: {res.strftime('%Y-%m-%d %H:%M:%S')}")
            return res
    except Exception as e:
        log_warning(f"NTP sync timed out/failed for {server_address}. Using system clock.", details=str(e))

    return datetime.now(timezone(timedelta(hours=offset_hours)))

class PygameControllerThread(QThread):
    raw_input = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()
        self.requestInterruption()

    def run(self):
        if not PYGAME_AVAILABLE:
            log_warning("pygame-ce module not available. Gamepad input disabled.")
            return

        try:
            pygame.init()
            pygame.joystick.init()
        except Exception as e:
            log_error(f"Failed to initialize pygame joystick subsystem: {e}")
            return

        joysticks = {}
        active_axes = {}

        while not self._stop_event.is_set() and not self.isInterruptionRequested():
            try:
                if not pygame.joystick.get_init():
                    pygame.joystick.init()
                    joysticks.clear()
                    active_axes.clear()
                    log_info("Reinitialized pygame joystick subsystem.")

                pygame.event.pump()

                for i in range(pygame.joystick.get_count()):
                    if i not in joysticks:
                        js = pygame.joystick.Joystick(i)
                        js.init()
                        joysticks[i] = js
                        log_info(f"Pygame-ce detected controller: {js.get_name()} (ID: {i})")

                for event in pygame.event.get():
                    if event.type == pygame.JOYBUTTONDOWN:
                        self.raw_input.emit(f"button:{event.button}")
                    elif event.type == pygame.JOYHATMOTION:
                        hat_x, hat_y = event.value
                        if hat_x == 1:
                            self.raw_input.emit("hat:right")
                        elif hat_x == -1:
                            self.raw_input.emit("hat:left")
                        if hat_y == 1:
                            self.raw_input.emit("hat:up")
                        elif hat_y == -1:
                            self.raw_input.emit("hat:down")
                    elif event.type == pygame.JOYAXISMOTION:
                        axis_key = (event.joy, event.axis)
                        if event.value <= -0.5:
                            axis_input = f"axis:{event.axis}:negative"
                        elif event.value >= 0.5:
                            axis_input = f"axis:{event.axis}:positive"
                        else:
                            axis_input = None

                        if axis_input and active_axes.get(axis_key) != axis_input:
                            self.raw_input.emit(axis_input)
                            active_axes[axis_key] = axis_input
                        elif axis_input is None:
                            active_axes.pop(axis_key, None)

                self._stop_event.wait(0.03)
            except Exception as e:
                if self._stop_event.is_set() or self.isInterruptionRequested():
                    break
                log_warning(f"Pygame controller polling error: {e}")
                if not pygame.joystick.get_init():
                    try:
                        pygame.joystick.init()
                        joysticks.clear()
                        log_info("Recovered pygame joystick subsystem after polling error.")
                    except Exception as init_error:
                        log_error(f"Failed to recover pygame joystick subsystem: {init_error}")
                self._stop_event.wait(2)

        pygame.quit()

class ThemedMessageBox(QDialog):
    def __init__(self, parent=None, title="", message="", theme_color="#DC143C"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(420, 180)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        card = QWidget(self)
        card.setObjectName("msgCard")
        card.setStyleSheet(f"""
            QWidget#msgCard {{
                background-color: rgba(22, 22, 22, 240);
                border: 2px solid {theme_color};
                border-radius: 14px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(25, 25, 25, 25)
        card_layout.setSpacing(15)

        msg_label = QLabel(message, card)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold; background: transparent; border: none;")
        card_layout.addWidget(msg_label)

        card_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.yes_btn = QPushButton("Yes", card)
        self.yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.yes_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme_color};
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 8px;
                border: none;
            }}
            QPushButton:hover, QPushButton:focus {{
                background-color: rgba(255, 255, 255, 30);
                border: 1px solid {theme_color};
            }}
        """)
        self.yes_btn.clicked.connect(self.accept)

        self.no_btn = QPushButton("No", card)
        self.no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.no_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(45, 45, 45, 200);
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
            QPushButton:hover, QPushButton:focus {
                background-color: rgba(65, 65, 65, 220);
                border: 1px solid rgba(255, 255, 255, 60);
            }
        """)
        self.no_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.no_btn)
        btn_layout.addWidget(self.yes_btn)
        card_layout.addLayout(btn_layout)

        layout.addWidget(card)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

class AnimatedLauncherButton(QToolButton):
    def __init__(self, parent=None, enable_animations=True, enable_glitch=False, theme_color="#DC143C"):
        super().__init__(parent)
        self.enable_animations = enable_animations
        self.enable_glitch = enable_glitch
        self.theme_color = theme_color
        self.setFixedSize(225, 235)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.original_rect = QRect()

    def set_original_geometry(self, rect: QRect):
        self.original_rect = rect
        self.setGeometry(rect)

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.enable_animations and not self.original_rect.isEmpty():
            target_w, target_h = 235, 245
            center_x = self.original_rect.x() + self.original_rect.width() // 2
            center_y = self.original_rect.y() + self.original_rect.height() // 2

            glitch_x_offset = 3 if self.enable_glitch else 0
            glitch_y_offset = -2 if self.enable_glitch else 0

            self.animate_to(QRect(center_x - target_w // 2 + glitch_x_offset, center_y - target_h // 2 + glitch_y_offset, target_w, target_h))

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.enable_animations and not self.original_rect.isEmpty():
            self.animate_to(self.original_rect)

    def animate_to(self, target_rect: QRect):
        if hasattr(self, 'anim') and self.anim.state() == QPropertyAnimation.State.Running:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(120)
        self.anim.setEndValue(target_rect)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.anim.start()

    def play_click_animation(self, callback):
        if not self.enable_animations:
            callback()
            return

        self.click_anim = QPropertyAnimation(self, b"geometry")
        self.click_anim.setDuration(80)

        small_w, small_h = 210, 220
        center_x = self.original_rect.x() + self.original_rect.width() // 2
        center_y = self.original_rect.y() + self.original_rect.height() // 2

        glitch_x_offset = -4 if self.enable_glitch else 0
        glitch_y_offset = 4 if self.enable_glitch else 0

        self.click_anim.setEndValue(QRect(center_x - small_w // 2 + glitch_x_offset, center_y - small_h // 2 + glitch_y_offset, small_w, small_h))
        self.click_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self.click_anim.finished.connect(callback)
        self.click_anim.start()

class ApplicationEditorDialog(QDialog):
    def __init__(
        self, parent=None, title="", command="", arguments="", manage_am=False,
        profile_path="", controller_close_enabled=False, app_type="application",
        website_url=""
    ):
        super().__init__(parent)
        self.setWindowTitle("Add or Edit Application")
        self.resize(520, 400)
        self.setStyleSheet("background-color: #222; color: white;")

        layout = QVBoxLayout(self)
        type_form = QFormLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItem("Application", "application")
        self.type_combo.addItem("Website", "website")
        self.type_combo.setCurrentIndex(
            max(0, self.type_combo.findData(app_type))
        )
        type_form.addRow("Type:", self.type_combo)
        layout.addLayout(type_form)

        self.mode_stack = QStackedWidget()
        self.name_input = QLineEdit(title)

        self.cmd_input = QLineEdit(command)
        self.cmd_browse_btn = QPushButton("Browse...")
        self.cmd_browse_btn.clicked.connect(self.browse_command)

        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(self.cmd_input)
        cmd_layout.addWidget(self.cmd_browse_btn)

        self.args_input = QLineEdit(arguments)

        application_fields = QWidget()
        application_form = QFormLayout(application_fields)
        application_form.addRow("App Executable:", cmd_layout)
        application_form.addRow("Arguments (optional):", self.args_input)
        self.mode_stack.addWidget(application_fields)

        website_fields = QWidget()
        website_form = QFormLayout(website_fields)
        self.website_url_input = QLineEdit(website_url)
        self.website_url_input.setPlaceholderText("https://example.com")
        self.website_browser_input = QLineEdit(command or "firefox")
        self.website_browser_input.setPlaceholderText("firefox")
        website_form.addRow("Website URL:", self.website_url_input)
        website_form.addRow("Browser executable:", self.website_browser_input)
        self.mode_stack.addWidget(website_fields)
        self.type_combo.currentIndexChanged.connect(
            lambda: self.mode_stack.setCurrentIndex(self.type_combo.currentIndex())
        )
        self.mode_stack.setCurrentIndex(self.type_combo.currentIndex())

        self.controller_close_cb = QCheckBox(
            "Xbox Guide button closes this app"
        )
        self.controller_close_cb.setChecked(controller_close_enabled)

        self.manage_am_cb = QCheckBox("Manage AntiMicroX (Kill & Load Profile)")
        self.manage_am_cb.setChecked(manage_am)
        self.manage_am_cb.toggled.connect(self.toggle_am_path)

        self.profile_input = QLineEdit(profile_path)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_profile)

        profile_layout = QHBoxLayout()
        profile_layout.addWidget(self.profile_input)
        profile_layout.addWidget(self.browse_btn)

        details_form = QFormLayout()
        details_form.addRow("Application Name:", self.name_input)
        details_form.addRow(self.controller_close_cb)
        details_form.addRow(self.manage_am_cb)
        details_form.addRow("AntiMicroX .amxp Path:", profile_layout)
        layout.addWidget(self.mode_stack)
        layout.insertLayout(1, details_form)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet("background-color: #DC143C; padding: 8px; font-weight: bold;")
        save_btn.clicked.connect(self.accept)
        layout.addWidget(save_btn)

        self.toggle_am_path(manage_am)

    def toggle_am_path(self, enabled):
        self.profile_input.setEnabled(enabled)
        self.browse_btn.setEnabled(enabled)

    def browse_command(self):
        possible_paths = ["/usr/bin", "/bin", "/usr/local/bin", str(Path.home() / ".local" / "bin")]
        start_dir = next((p for p in possible_paths if Path(p).exists()), str(Path.home()))

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Application Executable", start_dir, "All Files (*)"
        )
        if file_path:
            self.cmd_input.setText(file_path)

    def browse_profile(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select AntiMicroX Profile", str(Path.home()), "AMXP Files (*.amxp);;All Files (*)"
        )
        if file_path:
            self.profile_input.setText(file_path)

    def accept(self):
        if self.type_combo.currentData() == "website":
            website_url = self.website_url_input.text().strip()
            if website_url and "://" not in website_url:
                website_url = f"https://{website_url}"
                self.website_url_input.setText(website_url)
            try:
                parsed_url = urlsplit(website_url)
            except ValueError:
                parsed_url = None
            if (
                parsed_url is None
                or parsed_url.scheme not in ("http", "https")
                or not parsed_url.netloc
            ):
                QMessageBox.warning(
                    self,
                    "Invalid Website URL",
                    "Enter a valid website address, such as https://example.com."
                )
                return
            if not self.website_browser_input.text().strip():
                QMessageBox.warning(self, "Missing Browser", "Enter a browser executable.")
                return
            super().accept()
            return

        cmd = self.cmd_input.text().strip()
        if cmd and (Path(cmd).is_absolute() or "/" in cmd or "\\" in cmd):
            if not Path(cmd).exists():
                log_warning(f"ApplicationEditor: Executable does not exist on disk: '{cmd}'")
                reply = QMessageBox.warning(
                    self,
                    "File Warning",
                    f"The specified path does not exist on disk:\n{cmd}\n\nDo you still want to save?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
        super().accept()

    def get_data(self):
        app_type = self.type_combo.currentData()
        if app_type == "website":
            website_url = self.website_url_input.text().strip()
            command = self.website_browser_input.text().strip()
            arguments = f"--kiosk {shlex.quote(website_url)}"
        else:
            website_url = ""
            command = self.cmd_input.text().strip()
            arguments = self.args_input.text().strip()
        return (
            self.name_input.text().strip(),
            {
                "type": app_type,
                "website_url": website_url,
                "command": command,
                "arguments": arguments,
                "controller_close_enabled": self.controller_close_cb.isChecked(),
                "manage_antimicrox": self.manage_am_cb.isChecked(),
                "profile": self.profile_input.text().strip(),
                "icon_path": ""
            }
        )

class MainApp(QWidget):
    app_finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        log_info("Starting Titans HTPC Launcher...")
        self.config = load_config()
        self.controller_capture_active = False
        self.active_app_process = None
        self.active_app_controller_close_enabled = False
        self.launcher_sleeping = False
        self.controller_back_suppressed_until = 0.0
        self.reload_controller_profile()
        self.cap = None
        self.current_ntp_time = datetime.now()

        self.app_finished_signal.connect(self.on_app_finished)

        self.initUI()
        self.start_ntp_sync_thread()

        if PYGAME_AVAILABLE:
            self.controller_thread = PygameControllerThread(self)
            self.controller_thread.raw_input.connect(self.handle_controller_input)
            self.controller_thread.start()

    def reload_controller_profile(self):
        profile_name = Path(self.config.get("_controller_profile", "Xbox Controller.json")).name
        profile_path = CONTROLLER_INPUTS_DIR / profile_name
        bindings = DEFAULT_CONTROLLER_BINDINGS
        try:
            if not profile_path.exists():
                CONTROLLER_INPUTS_DIR.mkdir(parents=True, exist_ok=True)
                with profile_path.open("w", encoding="utf-8") as profile_file:
                    json.dump({"name": profile_path.stem, "bindings": DEFAULT_CONTROLLER_BINDINGS}, profile_file, indent=4)
                    profile_file.write("\n")
                log_info(f"Created default controller profile at {profile_path}")

            with profile_path.open("r", encoding="utf-8") as profile_file:
                profile_data = json.load(profile_file)
            if isinstance(profile_data, dict) and isinstance(profile_data.get("bindings"), dict):
                bindings = {**DEFAULT_CONTROLLER_BINDINGS, **profile_data["bindings"]}
        except json.JSONDecodeError as error:
            backup_path = profile_path.with_name(
                f"{profile_path.stem}.invalid-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}{profile_path.suffix}"
            )
            try:
                profile_path.replace(backup_path)
                with profile_path.open("w", encoding="utf-8") as profile_file:
                    json.dump({"name": profile_path.stem, "bindings": DEFAULT_CONTROLLER_BINDINGS}, profile_file, indent=4)
                    profile_file.write("\n")
                log_warning(
                    f"Invalid controller profile {profile_path} was reset to defaults.",
                    details=f"{error}; original backed up to {backup_path}"
                )
            except OSError as repair_error:
                log_warning(
                    f"Could not repair controller profile {profile_path}; using default bindings.",
                    details=f"{error}; {repair_error}"
                )
        except OSError as error:
            log_warning(f"Could not load controller profile {profile_path}; using default bindings.", details=str(error))
        self.controller_bindings = {}
        for action, input_names in bindings.items():
            if not isinstance(action, str):
                continue
            if isinstance(input_names, str):
                input_names = [input_names]
                if action in ("up", "down", "left", "right"):
                    default_axis_input = DEFAULT_CONTROLLER_BINDINGS[action][1]
                    if default_axis_input not in input_names:
                        input_names.append(default_axis_input)
            if not isinstance(input_names, list):
                continue
            for input_name in input_names:
                if isinstance(input_name, str) and input_name:
                    self.controller_bindings[input_name] = action

    def handle_controller_input(self, input_name):
        if self.controller_capture_active:
            return
        action = self.controller_bindings.get(input_name)
        if self.launcher_sleeping or self.isHidden():
            if (
                action == "close_app"
                and self.active_app_controller_close_enabled
                and self.active_app_process is not None
            ):
                if self.active_app_process.poll() is None:
                    log_info("Closing the launched application from controller close-app input.")
                    try:
                        self.active_app_process.terminate()
                    except OSError as error:
                        log_error(f"Failed to close launched application: {error}", details=str(error))
            return
        if action == "back" and time.monotonic() < self.controller_back_suppressed_until:
            return
        if self.handle_power_menu_input(action):
            return
        if self.handle_confirmation_dialog_input(action):
            return
        if action in ("right", "down"):
            if action == "right" and self.stacked_widget.currentWidget() == self.settings_page:
                settings_widget = getattr(self, "current_settings_widget", None)
                if settings_widget:
                    settings_widget.navigate_tabs(1)
                else:
                    self.focusNextChild()
            else:
                self.focusNextChild()
        elif action in ("left", "up"):
            if action == "left" and self.stacked_widget.currentWidget() == self.settings_page:
                settings_widget = getattr(self, "current_settings_widget", None)
                if settings_widget:
                    settings_widget.navigate_tabs(-1)
                else:
                    self.focusPreviousChild()
            else:
                self.focusPreviousChild()
        elif action in ("previous_tab", "next_tab"):
            settings_widget = getattr(self, "current_settings_widget", None)
            if self.stacked_widget.currentWidget() == self.settings_page and settings_widget:
                direction = -1 if action == "previous_tab" else 1
                settings_widget.navigate_embedded_tabs(direction)
        elif action == "select":
            focused = QApplication.focusWidget()
            if isinstance(focused, (QPushButton, QToolButton, AnimatedLauncherButton)):
                focused.click()
        elif action == "back":
            modal_dialog = QApplication.activeModalWidget()
            if modal_dialog:
                modal_dialog.reject()
            elif hasattr(self, 'stacked_widget') and self.stacked_widget.currentWidget() == self.settings_page:
                self.show_home_page()
            else:
                self.exit_launcher()

    def handle_confirmation_dialog_input(self, action):
        if action not in ("left", "right"):
            return False

        dialog = QApplication.activeModalWidget()
        if dialog is None:
            return False

        if isinstance(dialog, ThemedMessageBox):
            (dialog.no_btn if action == "left" else dialog.yes_btn).setFocus()
            return True

        if isinstance(dialog, QMessageBox):
            no_button = dialog.button(QMessageBox.StandardButton.No)
            yes_button = dialog.button(QMessageBox.StandardButton.Yes)
            if no_button and yes_button:
                (no_button if action == "left" else yes_button).setFocus()
                return True

            buttons = dialog.buttons()
            if len(buttons) > 1:
                current_button = QApplication.focusWidget()
                current_index = buttons.index(current_button) if current_button in buttons else 0
                direction = -1 if action == "left" else 1
                buttons[(current_index + direction) % len(buttons)].setFocus()
            return True

        return True

    def handle_power_menu_input(self, action):
        if not self.power_menu.isVisible():
            return False

        available_actions = [
            menu_action for menu_action in self.power_menu.actions()
            if menu_action.isEnabled() and not menu_action.isSeparator()
        ]
        if not available_actions:
            return True

        if action in ("up", "left", "down", "right"):
            current_action = self.power_menu.activeAction()
            current_index = available_actions.index(current_action) if current_action in available_actions else 0
            direction = -1 if action in ("up", "left") else 1
            next_index = (current_index + direction) % len(available_actions)
            self.power_menu.setActiveAction(available_actions[next_index])
        elif action == "select":
            selected_action = self.power_menu.activeAction()
            if selected_action in available_actions:
                self.power_menu.close()
                selected_action.trigger()
        elif action == "back":
            self.power_menu.close()
        return True

    def save_config_file(self):
        save_config(self.config)

    def initUI(self):
        self.setWindowTitle("Application Launcher")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.showFullScreen()

        self.bg_label = QLabel(self)
        self.bg_label.setGeometry(self.rect())
        self.bg_label.setScaledContents(True)
        self.bg_label.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.bg_label.setStyleSheet("background-color: #141414;")
        self.bg_label.show()

        self.init_video_background()

        self.content_widget = QWidget(self)
        self.content_widget.setObjectName("contentWidget")
        self.content_widget.setGeometry(self.rect())
        self.content_widget.setStyleSheet("QWidget#contentWidget { background-color: rgba(20, 20, 20, 160); }")
        self.content_widget.show()

        root_layout = QVBoxLayout(self.content_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.stacked_widget = QStackedWidget(self.content_widget)
        root_layout.addWidget(self.stacked_widget)

        # ================= PAGE 0: HOME LAUNCHER PAGE =================
        self.home_page = QWidget()
        self.home_page.setStyleSheet("background: transparent;")
        self.main_layout = QVBoxLayout(self.home_page)
        self.main_layout.setContentsMargins(40, 40, 40, 40)

        top_layout = QHBoxLayout()
        top_layout.addStretch()

        self.power_btn = QToolButton(self)
        self.power_btn.setFixedSize(65, 65)
        self.power_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self.power_menu = QMenu(self)
        self.power_menu.setStyleSheet("""
            QMenu {
                background-color: #222222;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 30);
                padding: 6px;
                font-size: 14px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                background: transparent;
            }
            QMenu::item:selected {
                background-color: #DC143C;
                color: #FFFFFF;
            }
        """)

        action_exit = QAction("Exit Launcher", self)
        action_exit.triggered.connect(self.exit_launcher)

        action_sleep = QAction("Sleep", self)
        action_sleep.triggered.connect(self.trigger_sleep)

        action_restart = QAction("Restart", self)
        action_restart.triggered.connect(self.trigger_restart)

        action_shutdown = QAction("Shutdown", self)
        action_shutdown.triggered.connect(self.trigger_shutdown)

        self.power_menu.addAction(action_exit)
        self.power_menu.addAction(action_sleep)
        self.power_menu.addAction(action_restart)
        self.power_menu.addAction(action_shutdown)
        self.power_menu.aboutToShow.connect(
            lambda: self.power_menu.setActiveAction(self.power_menu.actions()[0])
        )

        self.power_btn.setMenu(self.power_menu)
        self.update_power_button_display()
        top_layout.addWidget(self.power_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self.main_layout.addLayout(top_layout)

        self.title_label = QLabel("Choose Application:")
        self.title_label.setStyleSheet("color: #FFFFFF; font-size: 38px; font-weight: bold; background: transparent;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        self.main_layout.addStretch()

        bottom_layout = QHBoxLayout()

        self.clock_label = QLabel("Loading Time...")
        self.clock_label.setStyleSheet("""
            QLabel {
                color: #AAAAAA;
                font-size: 15px;
                font-weight: bold;
                background: transparent;
            }
        """)
        bottom_layout.addWidget(self.clock_label, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        bottom_layout.addStretch()

        self.config_btn = QPushButton("⚙ Settings")
        self.update_settings_button_style()
        self.config_btn.clicked.connect(self.show_settings_page)
        bottom_layout.addWidget(self.config_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self.apps_layout = QHBoxLayout()
        self.apps_layout.setSpacing(35)
        self.apps_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addLayout(self.apps_layout)

        self.refresh_applications_view()

        self.main_layout.addStretch()
        self.main_layout.addLayout(bottom_layout)

        # ================= PAGE 1: INTEGRATED SETTINGS PAGE =================
        self.settings_page = QWidget()
        self.settings_page.setStyleSheet("background: transparent;")
        self.settings_page_layout = QVBoxLayout(self.settings_page)
        self.settings_page_layout.setContentsMargins(40, 30, 40, 30)

        self.settings_container = QVBoxLayout()
        self.settings_container.setContentsMargins(0, 0, 0, 0)
        self.settings_page_layout.addLayout(self.settings_container)

        self.stacked_widget.addWidget(self.home_page)
        self.stacked_widget.addWidget(self.settings_page)

        self.content_widget.raise_()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock_display)
        self.clock_timer.start(1000)

    def exit_launcher(self):
        theme_color = self.get_theme_color()
        dialog = ThemedMessageBox(
            self,
            title="Exit Launcher",
            message="Are you sure you want to exit the launcher?",
            theme_color=theme_color
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            log_info("User initiated exit. Stopping background video and closing launcher.")
            self.close()

    def closeEvent(self, event):
        if hasattr(self, "clock_timer"):
            self.clock_timer.stop()
        if hasattr(self, "video_timer"):
            self.video_timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None

        ntp_stop_event = getattr(self, "_ntp_stop_event", None)
        if ntp_stop_event is not None:
            ntp_stop_event.set()

        controller_thread = getattr(self, "controller_thread", None)
        if controller_thread is not None and controller_thread.isRunning():
            log_info("Stopping controller polling thread during launcher shutdown.")
            controller_thread.stop()
            controller_thread.wait()

        event.accept()

    def trigger_sleep(self):
        theme_color = self.get_theme_color()
        dialog = ThemedMessageBox(
            self,
            title="Sleep System",
            message="Are you sure you want to put the system to sleep?",
            theme_color=theme_color
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            sleep_cmd = self.config.get("_sleep_command", "systemctl suspend")
            log_info(f"Executing system sleep command: '{sleep_cmd}'")
            try:
                subprocess.Popen(sleep_cmd.split())
            except Exception as e:
                log_error(f"Failed to execute sleep command '{sleep_cmd}': {e}", details=str(e))
                QMessageBox.critical(self, "Error", f"Failed to execute sleep command: {e}")

    def trigger_restart(self):
        theme_color = self.get_theme_color()
        dialog = ThemedMessageBox(
            self,
            title="Restart System",
            message="Are you sure you want to restart the system?",
            theme_color=theme_color
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            restart_cmd = self.config.get("_restart_command", "systemctl reboot")
            log_info(f"Executing system restart command: '{restart_cmd}'")
            try:
                subprocess.Popen(restart_cmd.split())
                self.close()
            except Exception as e:
                log_error(f"Failed to execute restart command '{restart_cmd}': {e}", details=str(e))
                QMessageBox.critical(self, "Error", f"Failed to execute restart command: {e}")

    def trigger_shutdown(self):
        theme_color = self.get_theme_color()
        dialog = ThemedMessageBox(
            self,
            title="Shutdown System",
            message="Are you sure you want to shut down the system?",
            theme_color=theme_color
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            power_cmd = self.config.get("_power_command", "systemctl poweroff")
            log_info(f"Executing system shutdown command: '{power_cmd}'")
            try:
                subprocess.Popen(power_cmd.split())
                self.close()
            except Exception as e:
                log_error(f"Failed to execute power command '{power_cmd}': {e}", details=str(e))
                QMessageBox.critical(self, "Error", f"Failed to execute power command: {e}")

    def update_power_button_display(self):
        if not hasattr(self, 'power_btn'):
            return
        power_icon_path = self.config.get("_power_icon_path", "")
        if power_icon_path and Path(power_icon_path).exists():
            self.power_btn.setText("")
            self.power_btn.setIcon(QIcon(power_icon_path))
            self.power_btn.setIconSize(QSize(32, 32))
        else:
            self.power_btn.setIcon(QIcon())
            self.power_btn.setText("⏻")

    def start_ntp_sync_thread(self):
        self._ntp_stop_event = threading.Event()

        def sync_worker():
            while not self._ntp_stop_event.is_set():
                server = self.config.get("_ntp_server", "nz.pool.ntp.org")
                offset = float(self.config.get("_ntp_offset", 12))
                ntp_time = fetch_ntp_time(server, offset)
                if ntp_time:
                    self.current_ntp_time = ntp_time
                self._ntp_stop_event.wait(1800)

        t = threading.Thread(target=sync_worker, daemon=True)
        t.start()

    def update_clock_display(self):
        self.current_ntp_time = self.current_ntp_time + timedelta(seconds=1)
        country = self.config.get("_ntp_country", "New Zealand")
        time_format = self.config.get("_time_format", "12-Hour (AM/PM)")

        if time_format == "24-Hour":
            time_str = self.current_ntp_time.strftime("%H:%M:%S")
        else:
            time_str = self.current_ntp_time.strftime("%I:%M:%S %p")

        formatted_time = f"{self.current_ntp_time.strftime('%A, %d %B %Y')}  –  {time_str} ({country})"
        self.clock_label.setText(formatted_time)

    def get_theme_color(self):
        theme = self.config.get("_theme", "Crimson Red")
        custom_colors = self.config.get("_custom_colors", {})
        return custom_colors.get(theme, "#DC143C")

    def get_border_radius(self):
        shape = self.config.get("_button_shape", "Rounded Square")
        if shape == "Circle":
            return "50%"
        return "28px"

    def update_back_button_style(self):
        theme_color = self.get_theme_color()
        if hasattr(self, 'back_btn'):
            self.back_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(35, 35, 35, 160);
                    color: #FFFFFF;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 10px 24px;
                    border-radius: 12px;
                    border: 2px solid rgba(255, 255, 255, 30);
                }}
                QPushButton:hover, QPushButton:focus {{
                    color: #FFFFFF;
                    background-color: rgba(60, 60, 60, 210);
                    border: 2px solid {theme_color};
                }}
            """)

    def update_settings_button_style(self):
        theme_color = self.get_theme_color()
        border_radius = self.get_border_radius()
        self.update_back_button_style()

        if hasattr(self, 'config_btn'):
            self.config_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(35, 35, 35, 140);
                    color: #FFFFFF;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 14px 28px;
                    border-radius: {border_radius};
                    border: 2px solid rgba(255, 255, 255, 25);
                }}
                QPushButton:hover, QPushButton:focus {{
                    color: #FFFFFF;
                    background-color: rgba(60, 60, 60, 200);
                    border: 3px solid {theme_color};
                }}
            """)

        if hasattr(self, 'power_btn'):
            self.power_btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: rgba(35, 35, 35, 140);
                    color: #FFFFFF;
                    font-size: 24px;
                    font-weight: bold;
                    border-radius: {border_radius};
                    border: 2px solid rgba(255, 255, 255, 25);
                }}
                QToolButton:hover, QToolButton:focus {{
                    color: #FFFFFF;
                    background-color: rgba(60, 60, 60, 200);
                    border: 3px solid {theme_color};
                }}
                QToolButton:pressed, QToolButton:on, QToolButton:checked {{
                    background-color: rgba(35, 35, 35, 140);
                    border: 2px solid rgba(255, 255, 255, 25);
                }}
                QToolButton::menu-indicator {{
                    width: 0px;
                }}
            """)

    def init_video_background(self):
        if hasattr(self, 'video_timer') and self.video_timer.isActive():
            self.video_timer.stop()
        if self.cap:
            self.cap.release()

        video_path = Path(self.config.get("_background_path", str(DEFAULT_VIDEO_PATH)))
        if video_path.exists():
            self.cap = cv2.VideoCapture(str(video_path))
            if self.cap.isOpened():
                log_info(f"Background video opened successfully: {video_path}")
                self.video_timer = QTimer(self)
                self.video_timer.timeout.connect(self.update_video_frame)
                self.video_timer.start(33)
            else:
                log_error(f"Failed to open background video file (codec or format error): {video_path}")
        else:
            log_warning(f"Background video file not found at: {video_path}")

    def update_video_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            if ret:
                if self.width() > 0 and self.height() > 0:
                    frame = cv2.resize(frame, (self.width(), self.height()))

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                qt_image = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
                self.bg_label.setPixmap(QPixmap.fromImage(qt_image))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'bg_label'):
            self.bg_label.setGeometry(self.rect())
        if hasattr(self, 'content_widget'):
            self.content_widget.setGeometry(self.rect())
        QTimer.singleShot(50, self.refresh_button_geometries)

    def refresh_button_geometries(self):
        for i in range(self.apps_layout.count()):
            item = self.apps_layout.itemAt(i)
            if item and item.widget():
                btn = item.widget()
                if isinstance(btn, AnimatedLauncherButton):
                    btn.set_original_geometry(btn.geometry())

    def refresh_applications_view(self):
        while self.apps_layout.count():
            item = self.apps_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        theme_color = self.get_theme_color()
        border_radius = self.get_border_radius()
        enable_anim = self.config.get("_enable_animations", True)
        enable_glitch = self.config.get("_enable_glitch", False)
        self.update_settings_button_style()

        first_app_btn = None

        for name, data in self.config.items():
            if name.startswith("_"):
                continue

            btn = AnimatedLauncherButton(self, enable_animations=enable_anim, enable_glitch=enable_glitch, theme_color=theme_color)
            btn.setText(name)

            icon_path = data.get("icon_path", "")
            if icon_path and Path(icon_path).exists():
                btn.setIcon(QIcon(icon_path))
            else:
                btn.setIcon(QIcon())

            btn.setIconSize(QSize(115, 115))

            btn.setStyleSheet(f"""
                AnimatedLauncherButton {{
                    background-color: rgba(35, 35, 35, 140);
                    color: #FFFFFF;
                    font-size: 18px;
                    font-weight: bold;
                    border-radius: {border_radius};
                    border: 2px solid rgba(255, 255, 255, 25);
                    padding-top: 28px;
                    padding-bottom: 15px;
                }}
                AnimatedLauncherButton:hover, AnimatedLauncherButton:focus {{
                    background-color: rgba(60, 60, 60, 200);
                    border: 3px solid {theme_color};
                }}
            """)

            btn.clicked.connect(lambda checked, b=btn, app_data=data: b.play_click_animation(lambda: self.launch_app(app_data)))
            self.apps_layout.addWidget(btn)

            if first_app_btn is None:
                first_app_btn = btn

        if first_app_btn is not None:
            first_app_btn.setFocus()

        QTimer.singleShot(100, self.refresh_button_geometries)

    def launch_app(self, data):
        if hasattr(self, 'video_timer'):
            self.video_timer.stop()
        if self.cap:
            self.cap.release()

        executable = data.get("command", "").strip()
        arguments_str = data.get("arguments", "").strip()

        if not executable:
            log_warning("Launch cancelled: No executable or command specified for application.")
            QMessageBox.warning(self, "Missing Executable", "No executable or command specified for this application.")
            self.init_video_background()
            return

        if Path(executable).is_absolute() or "/" in executable or "\\" in executable:
            if not Path(executable).exists():
                log_error(f"Application launch failed: Executable file not found on disk at '{executable}'")
                QMessageBox.critical(
                    self,
                    "Application Not Found",
                    f"The executable file could not be found:\n\n{executable}\n\nPlease check your application settings."
                )
                self.init_video_background()
                return
        else:
            if shutil.which(executable) is None:
                log_error(f"Application launch failed: Command '{executable}' not found in system PATH or as executable file.")
                QMessageBox.critical(
                    self,
                    "Command Not Found",
                    f"The command '{executable}' could not be found in your system PATH or as a valid file."
                )
                self.init_video_background()
                return

        if data.get("manage_antimicrox", False):
            log_info("Managing AntiMicroX: Terminating existing antimicrox instances.")
            subprocess.run(["pkill", "-f", "antimicrox"])

            profile_path = data.get("profile", "")
            if profile_path and Path(profile_path).exists():
                log_info(f"Applying AntiMicroX profile: {profile_path}")
                subprocess.Popen([
                    "antimicrox",
                    "--profile", profile_path,
                    "--hidden",
                    "--eventgen", "uinput"
                ])
            elif profile_path:
                log_warning(f"AntiMicroX profile specified but not found on disk: {profile_path}")

        cmd_list = [executable]
        arguments = shlex.split(arguments_str)
        executable_name = Path(executable).name.lower()
        is_website = data.get("type") == "website"
        if executable_name in ("firefox", "firefox-esr") and not is_website:
            arguments = [argument for argument in arguments if argument != "--kiosk"]

        url_index = next(
            (index for index, argument in enumerate(arguments) if argument.startswith(("http://", "https://"))),
            None
        )
        controller_close_enabled = data.get("controller_close_enabled", False)
        if (
            (is_website or controller_close_enabled)
            and executable_name in ("firefox", "firefox-esr")
            and url_index is not None
        ):
            if not any(
                argument in ("--new-window", "-new-window", "--new-tab", "-new-tab")
                for argument in arguments
            ):
                arguments.insert(url_index, "--new-window")

            arguments.extend(["--no-remote"])
            has_explicit_profile = any(
                argument in ("--profile", "-profile", "-P") or argument.startswith("--profile=")
                for argument in arguments
            )
            if has_explicit_profile:
                log_warning(
                    "Firefox URL launch uses an explicitly configured profile; "
                    "the launcher cannot guarantee that Firefox will use an isolated profile."
                )
            else:
                firefox_profile = CONFIG_PATH.parent / "firefox-app-profile"
                try:
                    firefox_profile.mkdir(parents=True, exist_ok=True)
                except OSError as error:
                    log_error(f"Could not create the dedicated Firefox profile at {firefox_profile}: {error}")
                    QMessageBox.critical(
                        self,
                        "Firefox Profile Error",
                        f"Could not create a dedicated Firefox profile:\n{error}"
                    )
                    self.init_video_background()
                    return
                arguments[0:0] = ["--profile", str(firefox_profile)]
        cmd_list.extend(arguments)

        try:
            log_info(f"Spawning application process: {' '.join(cmd_list)}")
            proc = subprocess.Popen(cmd_list)
            self.active_app_process = proc
            self.active_app_controller_close_enabled = controller_close_enabled
            log_info(f"Application '{executable}' running (PID: {proc.pid})")
        except Exception as e:
            log_critical(f"Failed to execute process '{executable}': {e}", details=str(e))
            QMessageBox.critical(self, "Launch Error", f"Failed to launch application:\n{e}")
            self.init_video_background()
            return

        self.enter_sleep_state()

        def wait_and_restore():
            proc.wait()
            log_info(f"Application '{executable}' process exited with returncode {proc.returncode}")
            self.app_finished_signal.emit()

        threading.Thread(target=wait_and_restore, daemon=True).start()

    def enter_sleep_state(self):
        log_info("Putting launcher to sleep while the application is running.")
        self.launcher_sleeping = True
        if hasattr(self, "clock_timer"):
            self.clock_timer.stop()
        if hasattr(self, "video_timer"):
            self.video_timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        self.hide()

    def on_app_finished(self):
        log_info("Restoring launcher interface after application exit.")
        self.active_app_process = None
        self.active_app_controller_close_enabled = False
        self.launcher_sleeping = False
        self.controller_back_suppressed_until = time.monotonic() + 1.0
        self.showFullScreen()
        if hasattr(self, "clock_timer"):
            self.clock_timer.start(1000)
        self.update_clock_display()
        self.init_video_background()

    def show_settings_page(self):
        if getattr(self, 'is_animating', False):
            return

        log_info("Opening Settings view.")
        enable_anim = self.config.get("_enable_animations", True)
        if not enable_anim:
            try:
                self.build_settings_view(self.config.get("_advanced_mode", False))
                self.stacked_widget.setCurrentWidget(self.settings_page)
                if hasattr(self, 'current_settings_widget') and hasattr(self.current_settings_widget, 'focus_current_menu_item'):
                    self.current_settings_widget.focus_current_menu_item()
                elif hasattr(self, 'back_btn'):
                    self.back_btn.setFocus()
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                log_critical(f"CRASH in show_settings_page: {e}", details=tb)
                traceback.print_exc()
            return

        self.animate_transition_to_settings()

    def show_home_page(self):
        if getattr(self, 'is_animating', False):
            return

        log_info("Returning to Home Launcher view.")
        enable_anim = self.config.get("_enable_animations", True)
        if not enable_anim:
            self.stacked_widget.setCurrentWidget(self.home_page)
            self.refresh_applications_view()
            return

        self.animate_transition_to_home()

    def animate_transition_to_settings(self):
        self.is_animating = True

        home_widgets = []
        if hasattr(self, 'title_label') and self.title_label.isVisible():
            home_widgets.append(self.title_label)
        if hasattr(self, 'power_btn') and self.power_btn.isVisible():
            home_widgets.append(self.power_btn)

        if hasattr(self, 'apps_layout'):
            for i in range(self.apps_layout.count()):
                item = self.apps_layout.itemAt(i)
                if item and item.widget() and item.widget().isVisible():
                    home_widgets.append(item.widget())

        if hasattr(self, 'clock_label') and self.clock_label.isVisible():
            home_widgets.append(self.clock_label)
        if hasattr(self, 'config_btn') and self.config_btn.isVisible():
            home_widgets.append(self.config_btn)

        proxies = []
        target_corner = QRect(0, self.content_widget.height(), 0, 0)
        disintegrate_group = QParallelAnimationGroup(self)

        for w in home_widgets:
            pixmap = QPixmap(w.size())
            pixmap.fill(Qt.GlobalColor.transparent)
            w.render(pixmap)
            if pixmap.isNull():
                pixmap = w.grab()

            global_pos = w.mapToGlobal(QPoint(0, 0))
            local_pos = self.content_widget.mapFromGlobal(global_pos)
            start_rect = QRect(local_pos.x(), local_pos.y(), w.width(), w.height())

            proxy = QLabel(self.content_widget)
            proxy.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            proxy.setStyleSheet("background: transparent; border: none;")
            proxy.setPixmap(pixmap)
            proxy.setScaledContents(True)
            proxy.setGeometry(start_rect)
            proxy.show()
            proxy.raise_()

            op_effect = QGraphicsOpacityEffect(proxy)
            proxy.setGraphicsEffect(op_effect)

            proxies.append(proxy)

            anim_geom = QPropertyAnimation(proxy, b"geometry")
            anim_geom.setDuration(330)
            anim_geom.setStartValue(start_rect)
            anim_geom.setEndValue(target_corner)
            anim_geom.setEasingCurve(QEasingCurve.Type.InCubic)

            anim_op = QPropertyAnimation(op_effect, b"opacity")
            anim_op.setDuration(330)
            anim_op.setStartValue(1.0)
            anim_op.setEndValue(0.0)

            disintegrate_group.addAnimation(anim_geom)
            disintegrate_group.addAnimation(anim_op)

        self.stacked_widget.setVisible(False)
        self.build_settings_view(self.config.get("_advanced_mode", False))

        def on_disintegrate_done():
            for p in proxies:
                p.deleteLater()

            def start_expand_settings():
                corner_rect = QRect(0, self.content_widget.height(), 0, 0)
                full_rect = QRect(0, 0, self.content_widget.width(), self.content_widget.height())

                self.stacked_widget.setCurrentWidget(self.settings_page)
                self.settings_page.resize(self.content_widget.size())
                self.settings_page.ensurePolished()

                settings_pixmap = QPixmap(self.content_widget.size())
                settings_pixmap.fill(Qt.GlobalColor.transparent)
                self.settings_page.render(settings_pixmap)

                if settings_pixmap.isNull() or settings_pixmap.width() == 0:
                    settings_pixmap = self.settings_page.grab()

                settings_proxy = QLabel(self.content_widget)
                settings_proxy.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                settings_proxy.setStyleSheet("background: transparent; border: none;")
                settings_proxy.setPixmap(settings_pixmap)
                settings_proxy.setScaledContents(True)
                settings_proxy.setGeometry(corner_rect)
                settings_proxy.show()
                settings_proxy.raise_()

                settings_op = QGraphicsOpacityEffect(settings_proxy)
                settings_proxy.setGraphicsEffect(settings_op)
                settings_op.setOpacity(0.0)

                expand_group = QParallelAnimationGroup(self)

                anim_s_geom = QPropertyAnimation(settings_proxy, b"geometry")
                anim_s_geom.setDuration(360)
                anim_s_geom.setStartValue(corner_rect)
                anim_s_geom.setEndValue(full_rect)
                anim_s_geom.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_s_op = QPropertyAnimation(settings_op, b"opacity")
                anim_s_op.setDuration(360)
                anim_s_op.setStartValue(0.0)
                anim_s_op.setEndValue(1.0)

                expand_group.addAnimation(anim_s_geom)
                expand_group.addAnimation(anim_s_op)

                def on_expand_done():
                    self.stacked_widget.setVisible(True)
                    self.settings_page.show()
                    QTimer.singleShot(25, settings_proxy.deleteLater)
                    self.is_animating = False
                    if hasattr(self, 'current_settings_widget') and hasattr(self.current_settings_widget, 'focus_current_menu_item'):
                        self.current_settings_widget.focus_current_menu_item()
                    elif hasattr(self, 'back_btn'):
                        self.back_btn.setFocus()

                expand_group.finished.connect(on_expand_done)
                self._active_anim = expand_group
                expand_group.start()

            QTimer.singleShot(250, start_expand_settings)

        disintegrate_group.finished.connect(on_disintegrate_done)
        self._active_anim = disintegrate_group
        disintegrate_group.start()

    def animate_transition_to_home(self):
        self.is_animating = True

        full_rect = QRect(0, 0, self.content_widget.width(), self.content_widget.height())
        corner_rect = QRect(0, self.content_widget.height(), 0, 0)

        settings_pixmap = QPixmap(self.content_widget.size())
        settings_pixmap.fill(Qt.GlobalColor.transparent)
        self.settings_page.render(settings_pixmap)
        if settings_pixmap.isNull():
            settings_pixmap = self.settings_page.grab()

        settings_proxy = QLabel(self.content_widget)
        settings_proxy.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        settings_proxy.setStyleSheet("background: transparent; border: none;")
        settings_proxy.setPixmap(settings_pixmap)
        settings_proxy.setScaledContents(True)
        settings_proxy.setGeometry(full_rect)
        settings_proxy.show()
        settings_proxy.raise_()

        self.stacked_widget.setVisible(False)

        settings_op = QGraphicsOpacityEffect(settings_proxy)
        settings_proxy.setGraphicsEffect(settings_op)

        collapse_group = QParallelAnimationGroup(self)

        anim_s_geom = QPropertyAnimation(settings_proxy, b"geometry")
        anim_s_geom.setDuration(290)
        anim_s_geom.setStartValue(full_rect)
        anim_s_geom.setEndValue(corner_rect)
        anim_s_geom.setEasingCurve(QEasingCurve.Type.InCubic)

        anim_s_op = QPropertyAnimation(settings_op, b"opacity")
        anim_s_op.setDuration(290)
        anim_s_op.setStartValue(1.0)
        anim_s_op.setEndValue(0.0)

        collapse_group.addAnimation(anim_s_geom)
        collapse_group.addAnimation(anim_s_op)

        def on_collapse_done():
            settings_proxy.deleteLater()

            def start_restore_home():
                self.refresh_applications_view()
                self.stacked_widget.setCurrentWidget(self.home_page)
                self.home_page.resize(self.content_widget.size())
                self.home_page.ensurePolished()

                home_pixmap = QPixmap(self.content_widget.size())
                home_pixmap.fill(Qt.GlobalColor.transparent)
                self.home_page.render(home_pixmap)

                if home_pixmap.isNull() or home_pixmap.width() == 0:
                    home_pixmap = self.home_page.grab()

                home_proxy = QLabel(self.content_widget)
                home_proxy.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                home_proxy.setStyleSheet("background: transparent; border: none;")
                home_proxy.setPixmap(home_pixmap)
                home_proxy.setScaledContents(True)
                home_proxy.setGeometry(corner_rect)
                home_proxy.show()
                home_proxy.raise_()

                home_op = QGraphicsOpacityEffect(home_proxy)
                home_proxy.setGraphicsEffect(home_op)
                home_op.setOpacity(0.0)

                restore_group = QParallelAnimationGroup(self)

                anim_geom = QPropertyAnimation(home_proxy, b"geometry")
                anim_geom.setDuration(340)
                anim_geom.setStartValue(corner_rect)
                anim_geom.setEndValue(full_rect)
                anim_geom.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_op = QPropertyAnimation(home_op, b"opacity")
                anim_op.setDuration(340)
                anim_op.setStartValue(0.0)
                anim_op.setEndValue(1.0)

                restore_group.addAnimation(anim_geom)
                restore_group.addAnimation(anim_op)

                def on_restore_done():
                    self.stacked_widget.setVisible(True)
                    self.home_page.show()
                    QTimer.singleShot(25, home_proxy.deleteLater)
                    self.is_animating = False

                restore_group.finished.connect(on_restore_done)
                self._active_anim = restore_group
                restore_group.start()

            QTimer.singleShot(250, start_restore_home)

        collapse_group.finished.connect(on_collapse_done)
        self._active_anim = collapse_group
        collapse_group.start()

    def open_configurator(self):
        self.show_settings_page()

    def build_settings_view(self, is_advanced):
        selected_section = getattr(self, "current_settings_widget", None)
        selected_section = getattr(selected_section, "current_section", "general")

        while self.settings_container.count():
            item = self.settings_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        def on_toggle_advanced(checked):
            log_info(f"Toggled settings advanced mode: {checked}")
            self.config["_advanced_mode"] = checked
            self.save_config_file()
            self.build_settings_view(checked)

        try:
            if is_advanced:
                from Settings.Settings_Advanced import AdvancedSettingsWidget
                self.current_settings_widget = AdvancedSettingsWidget(
                    self, self, on_toggle_advanced, initial_section=selected_section
                )
            else:
                from Settings.Settings_Basic import BasicSettingsWidget
                self.current_settings_widget = BasicSettingsWidget(
                    self, self, on_toggle_advanced, initial_section=selected_section
                )
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log_critical(f"Failed to load {'Advanced' if is_advanced else 'Basic'} settings widget: {e}", details=tb)
            raise

        if hasattr(self.current_settings_widget, 'back_btn'):
            self.back_btn = self.current_settings_widget.back_btn

        self.settings_container.addWidget(self.current_settings_widget)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if hasattr(self, 'stacked_widget') and self.stacked_widget.currentWidget() == self.settings_page:
                self.show_home_page()
                return
        super().keyPressEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec())
