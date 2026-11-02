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
import cv2
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QLabel,
    QDialog, QFormLayout, QLineEdit, QCheckBox, QFileDialog, QListWidget,
    QMessageBox, QTabWidget, QComboBox, QToolButton, QCompleter, QMenu
)
from PyQt6.QtCore import Qt, QUrl, QTimer, QSize, QPropertyAnimation, QEasingCurve, QRect, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QIcon, QAction

CONFIG_PATH = Path.home() / ".config" / "Titans-launcher" / "profiles.json"
DEFAULT_VIDEO_PATH = Path.home() / ".config" / "Titans-launcher" / "background.mp4"

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
        "command": "youtube",
        "arguments": "",
        "manage_antimicrox": True,
        "profile": "",
        "icon_path": ""
    }
}

def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG)
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
            return data
    except Exception:
        return DEFAULT_CONFIG

def save_config(data):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

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
            return dt_utc.astimezone(timezone(timedelta(hours=offset_hours)))
    except Exception:
        pass

    return datetime.now(timezone(timedelta(hours=offset_hours)))

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
    def __init__(self, parent=None, title="", command="", arguments="", manage_am=False, profile_path=""):
        super().__init__(parent)
        self.setWindowTitle("Edit Application")
        self.resize(480, 340)
        self.setStyleSheet("background-color: #222; color: white;")

        layout = QFormLayout(self)

        self.name_input = QLineEdit(title)

        self.cmd_input = QLineEdit(command)
        self.cmd_browse_btn = QPushButton("Browse...")
        self.cmd_browse_btn.clicked.connect(self.browse_command)

        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(self.cmd_input)
        cmd_layout.addWidget(self.cmd_browse_btn)

        self.args_input = QLineEdit(arguments)

        self.manage_am_cb = QCheckBox("Manage AntiMicroX (Kill & Load Profile)")
        self.manage_am_cb.setChecked(manage_am)
        self.manage_am_cb.toggled.connect(self.toggle_am_path)

        self.profile_input = QLineEdit(profile_path)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_profile)

        profile_layout = QHBoxLayout()
        profile_layout.addWidget(self.profile_input)
        profile_layout.addWidget(self.browse_btn)

        layout.addRow("Application Name:", self.name_input)
        layout.addRow("App Executable:", cmd_layout)
        layout.addRow("Arguments (optional):", self.args_input)
        layout.addRow(self.manage_am_cb)
        layout.addRow("AntiMicroX .amxp Path:", profile_layout)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet("background-color: #DC143C; padding: 8px; font-weight: bold;")
        save_btn.clicked.connect(self.accept)
        layout.addRow(save_btn)

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
        cmd = self.cmd_input.text().strip()
        if cmd and (Path(cmd).is_absolute() or "/" in cmd or "\\" in cmd):
            if not Path(cmd).exists():
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
        return (
            self.name_input.text().strip(),
            {
                "command": self.cmd_input.text().strip(),
                "arguments": self.args_input.text().strip(),
                "manage_antimicrox": self.manage_am_cb.isChecked(),
                "profile": self.profile_input.text().strip(),
                "icon_path": ""
            }
        )

class MainApp(QWidget):
    # Custom signal to safely pop the launcher back up from a background thread
    app_finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.cap = None
        self.current_ntp_time = datetime.now()

        # Connect the process finish signal to the handler method
        self.app_finished_signal.connect(self.on_app_finished)

        self.initUI()
        self.start_ntp_sync_thread()

    def save_config_file(self):
        save_config(self.config)

    def initUI(self):
        self.setWindowTitle("Application Launcher")
        self.showFullScreen()

        self.bg_label = QLabel(self)
        self.bg_label.setGeometry(self.rect())
        self.bg_label.setScaledContents(True)
        self.bg_label.setStyleSheet("background-color: #141414;")
        self.bg_label.show()

        self.init_video_background()

        self.content_widget = QWidget(self)
        self.content_widget.setGeometry(self.rect())
        self.content_widget.setStyleSheet("background-color: rgba(20, 20, 20, 160);")
        self.content_widget.show()

        self.main_layout = QVBoxLayout(self.content_widget)
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
        self.config_btn.clicked.connect(self.open_configurator)
        bottom_layout.addWidget(self.config_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self.apps_layout = QHBoxLayout()
        self.apps_layout.setSpacing(35)
        self.apps_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addLayout(self.apps_layout)

        self.refresh_applications_view()

        self.main_layout.addStretch()
        self.main_layout.addLayout(bottom_layout)
        self.content_widget.raise_()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock_display)
        self.clock_timer.start(1000)

    def exit_launcher(self):
        confirm = QMessageBox.question(
            self, "Exit Launcher", "Are you sure you want to exit the launcher?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if hasattr(self, 'video_timer'):
                self.video_timer.stop()
            if self.cap:
                self.cap.release()
            QApplication.quit()

    def trigger_sleep(self):
        confirm = QMessageBox.question(
            self, "Sleep System", "Are you sure you want to put the system to sleep?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            sleep_cmd = self.config.get("_sleep_command", "systemctl suspend")
            try:
                subprocess.Popen(sleep_cmd.split())
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to execute sleep command: {e}")

    def trigger_restart(self):
        confirm = QMessageBox.question(
            self, "Restart System", "Are you sure you want to restart the system?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            restart_cmd = self.config.get("_restart_command", "systemctl reboot")
            try:
                subprocess.Popen(restart_cmd.split())
                self.close()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to execute restart command: {e}")

    def trigger_shutdown(self):
        confirm = QMessageBox.question(
            self, "Shutdown System", "Are you sure you want to shut down the system?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            power_cmd = self.config.get("_power_command", "systemctl poweroff")
            try:
                subprocess.Popen(power_cmd.split())
                self.close()
            except Exception as e:
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
        def sync_worker():
            while True:
                server = self.config.get("_ntp_server", "nz.pool.ntp.org")
                offset = float(self.config.get("_ntp_offset", 12))
                ntp_time = fetch_ntp_time(server, offset)
                if ntp_time:
                    self.current_ntp_time = ntp_time
                time.sleep(1800)

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

    def update_settings_button_style(self):
        theme_color = self.get_theme_color()
        border_radius = self.get_border_radius()

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
                self.video_timer = QTimer(self)
                self.video_timer.timeout.connect(self.update_video_frame)
                self.video_timer.start(33)

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
            QMessageBox.warning(self, "Missing Executable", "No executable or command specified for this application.")
            self.init_video_background()
            return

        if Path(executable).is_absolute() or "/" in executable or "\\" in executable:
            if not Path(executable).exists():
                QMessageBox.critical(
                    self,
                    "Application Not Found",
                    f"The executable file could not be found:\n\n{executable}\n\nPlease check your application settings."
                )
                self.init_video_background()
                return
        else:
            if shutil.which(executable) is None:
                QMessageBox.critical(
                    self,
                    "Command Not Found",
                    f"The command '{executable}' could not be found in your system PATH or as a valid file."
                )
                self.init_video_background()
                return

        if data.get("manage_antimicrox", False):
            subprocess.run(["pkill", "-f", "antimicrox"])

            profile_path = data.get("profile", "")
            if profile_path and Path(profile_path).exists():
                subprocess.Popen([
                    "antimicrox",
                    "--profile", profile_path,
                    "--hidden",
                    "--eventgen", "uinput"
                ])

        cmd_list = [executable]
        if arguments_str:
            cmd_list.extend(shlex.split(arguments_str))

        try:
            proc = subprocess.Popen(cmd_list)
        except Exception as e:
            QMessageBox.critical(self, "Launch Error", f"Failed to launch application:\n{e}")
            self.init_video_background()
            return

        # Hide the launcher instead of closing it
        self.hide()

        # Monitor process completion in a background thread
        def wait_and_restore():
            proc.wait()
            self.app_finished_signal.emit()

        threading.Thread(target=wait_and_restore, daemon=True).start()

    def on_app_finished(self):
        # Called safely on the GUI thread when the launched app exits
        self.showFullScreen()
        self.init_video_background()

    def open_configurator(self):
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle("Settings")
            dialog.resize(600, 640)
            dialog.setStyleSheet("background-color: #1c1c1c; color: white;")

            main_layout = QVBoxLayout(dialog)

            def build_settings_view(is_advanced):
                while main_layout.count():
                    item = main_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

                def on_toggle_advanced(checked):
                    self.config["_advanced_mode"] = checked
                    self.save_config_file()
                    build_settings_view(checked)

                if is_advanced:
                    from Settings.Settings_Advanced import AdvancedSettingsWidget
                    widget = AdvancedSettingsWidget(self, dialog, on_toggle_advanced)
                else:
                    from Settings.Settings_Basic import BasicSettingsWidget
                    widget = BasicSettingsWidget(self, dialog, on_toggle_advanced)

                main_layout.addWidget(widget)

            build_settings_view(self.config.get("_advanced_mode", False))
            dialog.exec()
        except Exception as e:
            print(f"CRASH in open_configurator: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec())
