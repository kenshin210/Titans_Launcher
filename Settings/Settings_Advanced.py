# -*- coding: utf-8 -*-
from pathlib import Path
import json
import threading
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QStackedWidget,
    QListWidget, QComboBox, QCompleter, QLabel, QScrollArea,
    QTextEdit, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon

try:
    from Settings.Logger import logger, LOG_FILE, log_info, log_warning, log_error, log_critical
except ImportError:
    from Logger import logger, LOG_FILE, log_info, log_warning, log_error, log_critical

DEFAULT_VIDEO_PATH = Path.home() / ".config" / "Titans-launcher" / "background.mp4"

class MenuNavButton(QPushButton):
    focused = pyqtSignal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

class AdvancedSettingsWidget(QWidget):
    def __init__(self, parent_launcher, dialog_instance=None, on_toggle_advanced=None):
        super().__init__()
        self.launcher = parent_launcher
        self.dialog = dialog_instance or parent_launcher
        self.on_toggle_advanced = on_toggle_advanced

        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"

        # Main horizontal layout: Left sidebar + Right content stack
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(35)

        # ---------------- LEFT SIDEBAR (VIDEO GAME MENU) ----------------
        sidebar_widget = QWidget()
        sidebar_widget.setFixedWidth(280)
        sidebar_widget.setStyleSheet("background: transparent;")
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(10)

        menu_header = QLabel("SETTINGS (ADVANCED)")
        menu_header.setStyleSheet("""
            color: rgba(255, 255, 255, 140);
            font-size: 14px;
            font-weight: bold;
            letter-spacing: 2px;
            padding-left: 6px;
            padding-bottom: 6px;
        """)
        sidebar_layout.addWidget(menu_header)

        self.nav_buttons = []
        categories = [
            ("⚙  General", 0),
            ("🖼  Background", 1),
            ("🚀  Applications", 2),
            ("🎮  Controllers", 3),
            ("🏷  App Icons", 4),
            ("🎨  Theme & Power", 5),
            ("🌐  NTP & Region", 6),
            ("📋  Logging", 7)
        ]

        for label, idx in categories:
            btn = MenuNavButton(label)
            btn.clicked.connect(lambda checked, i=idx: self.switch_tab(i))
            btn.focused.connect(lambda i=idx: self.switch_tab(i))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Bottom Left: Back to Launcher button
        self.back_btn = QPushButton("← Back to Launcher")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(35, 35, 35, 170);
                color: #FFFFFF;
                font-size: 15px;
                font-weight: bold;
                padding: 14px 20px;
                border-radius: 10px;
                border: 2px solid rgba(255, 255, 255, 30);
                text-align: center;
            }}
            QPushButton:hover, QPushButton:focus {{
                color: #FFFFFF;
                background-color: rgba(65, 65, 65, 220);
                border: 2px solid {theme_color};
            }}
        """)
        self.back_btn.clicked.connect(self.launcher.show_home_page)
        sidebar_layout.addWidget(self.back_btn)

        root_layout.addWidget(sidebar_widget)

        # ---------------- RIGHT CONTENT AREA (STACKED PAGES) ----------------
        self.pages = QStackedWidget()
        self.pages.setStyleSheet("background: transparent;")

        self.pages.addWidget(self.create_general_page())
        self.pages.addWidget(self.create_background_page())
        self.pages.addWidget(self.create_apps_page())
        self.pages.addWidget(self.create_controllers_page())
        self.pages.addWidget(self.create_icons_page())
        self.pages.addWidget(self.create_theme_page())
        self.pages.addWidget(self.create_ntp_page())
        self.pages.addWidget(self.create_logging_page())

        root_layout.addWidget(self.pages, stretch=1)

        self.switch_tab(0)

    def switch_tab(self, index):
        self.pages.setCurrentIndex(index)
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: rgba(65, 65, 65, 220);
                        color: #FFFFFF;
                        font-size: 16px;
                        font-weight: bold;
                        text-align: left;
                        padding: 16px 20px;
                        border-radius: 10px;
                        border: 1px solid rgba(255, 255, 255, 45);
                        border-left: 6px solid {theme_color};
                    }}
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(30, 30, 30, 130);
                        color: #999999;
                        font-size: 16px;
                        font-weight: bold;
                        text-align: left;
                        padding: 16px 20px;
                        border-radius: 10px;
                        border: 1px solid transparent;
                        border-left: 6px solid transparent;
                    }
                    QPushButton:hover {
                        background-color: rgba(45, 45, 45, 180);
                        color: #FFFFFF;
                        border-left: 6px solid rgba(255, 255, 255, 80);
                    }
                """)

    def focus_first_menu_item(self):
        if self.nav_buttons:
            self.nav_buttons[0].setFocus()

    # --- TAB 1: General ---
    def create_general_page(self):
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(20)

        title = QLabel("General Settings (Advanced)")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Advanced mode is enabled. Uncheck to return to the simplified basic settings view.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        form = QFormLayout()
        form.setVerticalSpacing(15)

        self.advanced_cb = QCheckBox("Enable Advanced Settings")
        self.advanced_cb.setStyleSheet("color: white; font-size: 16px; font-weight: bold; border: none;")
        self.advanced_cb.setChecked(self.launcher.config.get("_advanced_mode", True))
        self.advanced_cb.toggled.connect(self.on_toggle_advanced)

        form.addRow(self.advanced_cb)
        layout.addLayout(form)
        layout.addStretch()
        return card

    # --- TAB 2: Background ---
    def create_background_page(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(20)

        title = QLabel("Background Video")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Specify the exact file path to a background video loop.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        form = QFormLayout()
        form.setVerticalSpacing(15)

        bg_input = QLineEdit(self.launcher.config.get("_background_path", str(DEFAULT_VIDEO_PATH)))
        bg_input.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; border-radius: 6px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25);")
        bg_browse_btn = QPushButton("Browse...")
        bg_browse_btn.setStyleSheet("background-color: rgba(60, 60, 60, 200); color: white; padding: 10px 18px; border-radius: 6px; font-weight: bold;")

        def browse_background():
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Background Video", str(Path.home()), "Video Files (*.mp4 *.avi *.mkv);;All Files (*)"
            )
            if file_path:
                bg_input.setText(file_path)

        bg_browse_btn.clicked.connect(browse_background)
        bg_row = QHBoxLayout()
        bg_row.addWidget(bg_input)
        bg_row.addWidget(bg_browse_btn)
        form.addRow(QLabel("Video Path:"), bg_row)

        save_bg_btn = QPushButton("Save Background")
        save_bg_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        def save_bg_path():
            new_path = bg_input.text().strip()
            self.launcher.config["_background_path"] = new_path
            self.launcher.save_config_file()
            self.launcher.init_video_background()
            log_info(f"Advanced Settings: Updated background video path to '{new_path}'")
            QMessageBox.information(self, "Success", "Background video updated successfully!")

        save_bg_btn.clicked.connect(save_bg_path)
        layout.addLayout(form)
        layout.addWidget(save_bg_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return card

    # --- TAB 3: Application Profiles ---
    def create_apps_page(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(18)

        title = QLabel("Application Profiles")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Configure executable commands, launch arguments, and AntiMicroX controller profiles.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        list_widget = QListWidget()
        list_widget.setStyleSheet("background-color: rgba(30, 30, 30, 200); color: white; font-size: 16px; border: 1px solid rgba(255, 255, 255, 30); border-radius: 8px; padding: 6px;")
        for name in self.launcher.config.keys():
            if not name.startswith("_"):
                list_widget.addItem(name)
        layout.addWidget(list_widget)

        app_btn_layout = QHBoxLayout()
        add_btn = QPushButton("+ Add Application")
        add_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 10px 18px; font-weight: bold; border-radius: 8px;")
        edit_btn = QPushButton("Edit Application")
        edit_btn.setStyleSheet("background-color: rgba(65, 65, 65, 200); color: white; padding: 10px 18px; font-weight: bold; border-radius: 8px;")
        del_btn = QPushButton("Remove Selected")
        del_btn.setStyleSheet("background-color: rgba(55, 55, 55, 200); color: white; padding: 10px 18px; font-weight: bold; border-radius: 8px;")
        app_btn_layout.addWidget(add_btn)
        app_btn_layout.addWidget(edit_btn)
        app_btn_layout.addWidget(del_btn)
        app_btn_layout.addStretch()
        layout.addLayout(app_btn_layout)

        def add_application():
            try:
                from Launcher import ApplicationEditorDialog
            except ImportError:
                from launcher import ApplicationEditorDialog
            editor = ApplicationEditorDialog(self.dialog or self.launcher)
            if editor.exec() == 1:
                name, data = editor.get_data()
                if name:
                    self.launcher.config[name] = data
                    self.launcher.save_config_file()
                    list_widget.addItem(name)
                    self.launcher.refresh_applications_view()
                    log_info(f"Advanced Settings: Added application '{name}' (Command: '{data.get('command')}')")

        def edit_application():
            current_item = list_widget.currentItem()
            if not current_item:
                return
            old_name = current_item.text()
            data = self.launcher.config.get(old_name, {})

            try:
                from Launcher import ApplicationEditorDialog
            except ImportError:
                from launcher import ApplicationEditorDialog
            editor = ApplicationEditorDialog(
                self.dialog or self.launcher,
                title=old_name,
                command=data.get("command", ""),
                arguments=data.get("arguments", ""),
                manage_am=data.get("manage_antimicrox", False),
                profile_path=data.get("profile", "")
            )
            if editor.exec() == 1:
                new_name, new_data = editor.get_data()
                if new_name:
                    new_data["icon_path"] = data.get("icon_path", "")
                    if old_name != new_name:
                        del self.launcher.config[old_name]
                    self.launcher.config[new_name] = new_data
                    self.launcher.save_config_file()
                    current_item.setText(new_name)
                    self.launcher.refresh_applications_view()
                    log_info(f"Advanced Settings: Modified application profile '{old_name}' -> '{new_name}'")

        def delete_application():
            current_item = list_widget.currentItem()
            if not current_item:
                return
            name = current_item.text()
            confirm = QMessageBox.question(
                self, "Delete Application", f"Remove '{name}' application?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                del self.launcher.config[name]
                self.launcher.save_config_file()
                list_widget.takeItem(list_widget.row(current_item))
                self.launcher.refresh_applications_view()
                log_info(f"Advanced Settings: Removed application '{name}'")

        add_btn.clicked.connect(add_application)
        edit_btn.clicked.connect(edit_application)
        del_btn.clicked.connect(delete_application)
        return card

    # --- TAB 4: Controllers ---
    def create_controllers_page(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(20)

        title = QLabel("Controller Configuration")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Select the active controller device detected by the operating system.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        form = QFormLayout()
        form.setVerticalSpacing(15)

        controller_combo = QComboBox()
        controller_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")

        detected_devices = ["Auto-Detect (OS Default)"]
        try:
            import pygame
            if not pygame.get_init():
                pygame.init()
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            for i in range(pygame.joystick.get_count()):
                js = pygame.joystick.Joystick(i)
                detected_devices.append(js.get_name())
        except Exception as e:
            log_warning(f"Could not query joysticks for settings menu: {e}")

        controller_combo.addItems(detected_devices)
        saved_ctrl = self.launcher.config.get("_selected_controller", "Auto-Detect (OS Default)")
        if saved_ctrl in detected_devices:
            controller_combo.setCurrentText(saved_ctrl)

        form.addRow(QLabel("Active Gamepad:"), controller_combo)

        save_btn = QPushButton("Save Controller Setup")
        save_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        def save_controller_config():
            selected = controller_combo.currentText()
            self.launcher.config["_selected_controller"] = selected
            self.launcher.save_config_file()

            input_dir = Path("Settings") / "Input"
            input_dir.mkdir(parents=True, exist_ok=True)
            
            safe_name = "".join(c if c.isalnum() else "_" for c in selected)
            file_path = input_dir / f"{safe_name}.json"
            
            payload = {
                "device_name": selected,
                "mapping_profile": "default_xbox_layout",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4)

            log_info(f"Advanced Settings: Controller config saved to {file_path}")
            QMessageBox.information(self, "Success", f"Controller profile saved successfully to:\n{file_path}")

        save_btn.clicked.connect(save_controller_config)
        layout.addLayout(form)
        layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return card

    # --- TAB 5: App Icons & Power Icon ---
    def create_icons_page(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(18)

        title = QLabel("App & Power Icons")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Assign custom icon images (.png, .jpg, .ico, .svg) to your applications and the power menu button.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        icon_form = QFormLayout()
        icon_form.setVerticalSpacing(15)

        app_combo = QComboBox()
        app_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")
        for name in self.launcher.config.keys():
            if not name.startswith("_"):
                app_combo.addItem(name)

        icon_input = QLineEdit()
        icon_input.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")
        icon_browse_btn = QPushButton("Browse...")
        icon_browse_btn.setStyleSheet("background-color: rgba(60, 60, 60, 200); color: white; padding: 10px 18px; border-radius: 6px; font-weight: bold;")

        def update_icon_path_field(text):
            if text and text in self.launcher.config:
                icon_input.setText(self.launcher.config[text].get("icon_path", ""))

        app_combo.currentTextChanged.connect(update_icon_path_field)
        if app_combo.count() > 0:
            update_icon_path_field(app_combo.currentText())

        def browse_icon():
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Application Icon", str(Path.home()), "Image Files (*.png *.jpg *.ico *.svg);;All Files (*)"
            )
            if file_path:
                icon_input.setText(file_path)

        icon_browse_btn.clicked.connect(browse_icon)

        icon_row = QHBoxLayout()
        icon_row.addWidget(icon_input)
        icon_row.addWidget(icon_browse_btn)

        power_icon_input = QLineEdit(self.launcher.config.get("_power_icon_path", ""))
        power_icon_input.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")
        power_icon_browse_btn = QPushButton("Browse...")
        power_icon_browse_btn.setStyleSheet("background-color: rgba(60, 60, 60, 200); color: white; padding: 10px 18px; border-radius: 6px; font-weight: bold;")

        def browse_power_icon():
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Power Button Icon", str(Path.home()), "Image Files (*.png *.jpg *.ico *.svg);;All Files (*)"
            )
            if file_path:
                power_icon_input.setText(file_path)

        power_icon_browse_btn.clicked.connect(browse_power_icon)

        power_icon_row = QHBoxLayout()
        power_icon_row.addWidget(power_icon_input)
        power_icon_row.addWidget(power_icon_browse_btn)

        icon_form.addRow(QLabel("Application:"), app_combo)
        icon_form.addRow(QLabel("App Icon Path:"), icon_row)
        icon_form.addRow(QLabel("Power Button Icon:"), power_icon_row)

        save_icon_btn = QPushButton("Save Icon Mappings")
        save_icon_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        def save_app_icon():
            app_name = app_combo.currentText()
            if app_name in self.launcher.config:
                self.launcher.config[app_name]["icon_path"] = icon_input.text().strip()
            self.launcher.config["_power_icon_path"] = power_icon_input.text().strip()

            self.launcher.save_config_file()
            self.launcher.refresh_applications_view()
            self.launcher.update_power_button_display()
            log_info(f"Advanced Settings: Updated icon mappings (App='{app_name}', Power Icon='{power_icon_input.text().strip()}')")
            QMessageBox.information(self, "Success", "Icon mappings updated successfully!")

        save_icon_btn.clicked.connect(save_app_icon)
        layout.addLayout(icon_form)
        layout.addWidget(save_icon_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return card

    # --- TAB 6: Themes & Animation/Glitch/Power Customization ---
    def create_theme_page(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(18)

        title = QLabel("Theme, Style & System Commands")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Customize theme hex values, tile button shape, animations, and system power commands.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        theme_form = QFormLayout()
        theme_form.setVerticalSpacing(12)

        theme_combo = QComboBox()
        theme_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")
        theme_combo.addItems(["Crimson Red", "Cyberpunk Blue", "Emerald Green", "Purple Neon"])
        theme_combo.setCurrentText(self.launcher.config.get("_theme", "Crimson Red"))

        hex_input = QLineEdit()
        hex_input.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")

        shape_combo = QComboBox()
        shape_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")
        shape_combo.addItems(["Rounded Square", "Circle"])
        shape_combo.setCurrentText(self.launcher.config.get("_button_shape", "Rounded Square"))

        power_cmd_input = QLineEdit(self.launcher.config.get("_power_command", "systemctl poweroff"))
        power_cmd_input.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")

        sleep_cmd_input = QLineEdit(self.launcher.config.get("_sleep_command", "systemctl suspend"))
        sleep_cmd_input.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")

        restart_cmd_input = QLineEdit(self.launcher.config.get("_restart_command", "systemctl reboot"))
        restart_cmd_input.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")

        anim_checkbox = QCheckBox("Enable Hover & Click Animations")
        anim_checkbox.setStyleSheet("color: white; font-size: 15px; border: none;")
        anim_checkbox.setChecked(self.launcher.config.get("_enable_animations", True))

        glitch_checkbox = QCheckBox("Enable Glitch Effect (Cyberpunk Jitter)")
        glitch_checkbox.setStyleSheet("color: white; font-size: 15px; border: none;")
        glitch_checkbox.setChecked(self.launcher.config.get("_enable_glitch", False))

        def update_hex_field(theme_name):
            custom_colors = self.launcher.config.get("_custom_colors", {})
            hex_input.setText(custom_colors.get(theme_name, "#DC143C"))

        theme_combo.currentTextChanged.connect(update_hex_field)
        update_hex_field(theme_combo.currentText())

        theme_form.addRow(QLabel("Theme Style:"), theme_combo)
        theme_form.addRow(QLabel("Theme Hex Color:"), hex_input)
        theme_form.addRow(QLabel("Button Shape:"), shape_combo)
        theme_form.addRow(QLabel("Shutdown Command:"), power_cmd_input)
        theme_form.addRow(QLabel("Sleep Command:"), sleep_cmd_input)
        theme_form.addRow(QLabel("Restart Command:"), restart_cmd_input)
        theme_form.addRow(anim_checkbox)
        theme_form.addRow(glitch_checkbox)

        save_theme_btn = QPushButton("Save Theme & Power Settings")
        save_theme_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        def save_launcher_theme():
            selected_theme = theme_combo.currentText()
            custom_hex = hex_input.text().strip()
            selected_shape = shape_combo.currentText()
            power_cmd = power_cmd_input.text().strip()
            sleep_cmd = sleep_cmd_input.text().strip()
            restart_cmd = restart_cmd_input.text().strip()
            enable_anim = anim_checkbox.isChecked()
            enable_glitch = glitch_checkbox.isChecked()

            self.launcher.config["_theme"] = selected_theme
            self.launcher.config["_button_shape"] = selected_shape
            self.launcher.config["_power_command"] = power_cmd
            self.launcher.config["_sleep_command"] = sleep_cmd
            self.launcher.config["_restart_command"] = restart_cmd
            self.launcher.config["_enable_animations"] = enable_anim
            self.launcher.config["_enable_glitch"] = enable_glitch
            if "_custom_colors" not in self.launcher.config:
                self.launcher.config["_custom_colors"] = {}
            self.launcher.config["_custom_colors"][selected_theme] = custom_hex

            self.launcher.save_config_file()
            self.launcher.refresh_applications_view()
            log_info(f"Advanced Settings: Saved theme '{selected_theme}', hex '{custom_hex}', shape '{selected_shape}', anim={enable_anim}, glitch={enable_glitch}")
            QMessageBox.information(self, "Success", "Theme and power settings saved successfully!")

        save_theme_btn.clicked.connect(save_launcher_theme)
        layout.addLayout(theme_form)
        layout.addWidget(save_theme_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

        scroll.setWidget(card)
        return scroll

    # --- TAB 7: NTP & Region ---
    def create_ntp_page(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(18)

        title = QLabel("NTP & Region Synchronization")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Configure network time synchronization, time format, and country offset.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        ntp_form = QFormLayout()
        ntp_form.setVerticalSpacing(12)

        country_combo = QComboBox()
        country_combo.setEditable(True)
        country_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")

        countries_list = [
            "New Zealand", "Australia", "United States", "United Kingdom", "Canada",
            "Germany", "France", "Japan", "Singapore", "Brazil", "India", "South Africa",
            "Argentina", "Austria", "Belgium", "China", "Denmark", "Fiji", "Finland",
            "Greece", "Hong Kong", "Ireland", "Italy", "Malaysia", "Mexico", "Netherlands",
            "Norway", "Philippines", "Poland", "Portugal", "Russia", "South Korea", "Spain",
            "Sweden", "Switzerland", "Taiwan", "Thailand", "Turkey", "Ukraine", "United Arab Emirates"
        ]
        country_combo.addItems(sorted(countries_list))
        country_combo.setCurrentText(self.launcher.config.get("_ntp_country", "New Zealand"))

        completer = QCompleter(sorted(countries_list), country_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        country_combo.setCompleter(completer)

        server_input = QLineEdit(self.launcher.config.get("_ntp_server", "nz.pool.ntp.org"))
        server_input.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")

        offset_input = QLineEdit(str(self.launcher.config.get("_ntp_offset", 12)))
        offset_input.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")

        time_format_combo = QComboBox()
        time_format_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")
        time_format_combo.addItems(["12-Hour (AM/PM)", "24-Hour"])
        time_format_combo.setCurrentText(self.launcher.config.get("_time_format", "12-Hour (AM/PM)"))

        ntp_form.addRow(QLabel("Country Name:"), country_combo)
        ntp_form.addRow(QLabel("NTP Server Address:"), server_input)
        ntp_form.addRow(QLabel("UTC Offset (Hours):"), offset_input)
        ntp_form.addRow(QLabel("Time Format:"), time_format_combo)

        save_ntp_btn = QPushButton("Save NTP Settings")
        save_ntp_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        def save_ntp_config():
            self.launcher.config["_ntp_country"] = country_combo.currentText().strip()
            self.launcher.config["_ntp_server"] = server_input.text().strip()
            self.launcher.config["_time_format"] = time_format_combo.currentText()
            try:
                self.launcher.config["_ntp_offset"] = float(offset_input.text().strip())
            except ValueError:
                self.launcher.config["_ntp_offset"] = 12.0

            self.launcher.save_config_file()
            log_info(f"Advanced Settings: Updated NTP server='{self.launcher.config['_ntp_server']}', country='{self.launcher.config['_ntp_country']}', offset={self.launcher.config['_ntp_offset']}")

            try:
                from Launcher import fetch_ntp_time
            except ImportError:
                from launcher import fetch_ntp_time
            def immediate_fetch():
                t = fetch_ntp_time(self.launcher.config["_ntp_server"], self.launcher.config["_ntp_offset"])
                if t:
                    self.launcher.current_ntp_time = t
            threading.Thread(target=immediate_fetch, daemon=True).start()

            QMessageBox.information(self, "Success", "NTP and region settings updated successfully!")

        save_ntp_btn.clicked.connect(save_ntp_config)
        layout.addLayout(ntp_form)
        layout.addWidget(save_ntp_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return card

    # --- TAB 8: Logging (Application Logging: Critical, Error, Warning, Information) ---
    def create_logging_page(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(14)

        title = QLabel("System & Application Logging")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Review real-time application diagnostics, launch operations, warnings, and error logs.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        # Primary Sub-Tab: Application Logging
        self.log_main_tabs = QTabWidget()
        self.log_main_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid rgba(255, 255, 255, 25);
                background: rgba(18, 18, 18, 220);
                border-radius: 10px;
            }}
            QTabBar::tab {{
                background: rgba(35, 35, 35, 180);
                color: #bbb;
                padding: 10px 22px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background: {theme_color};
                color: white;
            }}
        """)

        app_log_container = QWidget()
        app_log_layout = QVBoxLayout(app_log_container)
        app_log_layout.setContentsMargins(15, 15, 15, 15)
        app_log_layout.setSpacing(12)

        # Category Sub-Tabs: Critical, Error, Warning, Information
        self.level_tabs = QTabWidget()
        self.level_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid rgba(255, 255, 255, 20);
                background: rgba(12, 12, 12, 240);
                border-radius: 8px;
            }
            QTabBar::tab {
                background: rgba(30, 30, 30, 190);
                color: #aaa;
                padding: 8px 18px;
                margin-right: 3px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: rgba(60, 60, 60, 240);
                color: white;
            }
        """)

        self.log_views = {}
        levels = [
            ("Critical", "🔴 Critical", "#FF4466"),
            ("Error", "❌ Error", "#FF6666"),
            ("Warning", "⚠️ Warning", "#FFCC00"),
            ("Information", "ℹ️ Information", "#00E5FF")
        ]

        for level_key, level_label, color_code in levels:
            view = QTextEdit()
            view.setReadOnly(True)
            view.setStyleSheet(f"""
                QTextEdit {{
                    background-color: rgba(10, 10, 10, 245);
                    color: {color_code};
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 13px;
                    border: none;
                    padding: 10px;
                }}
            """)
            self.log_views[level_key] = view
            self.level_tabs.addTab(view, level_label)

        app_log_layout.addWidget(self.level_tabs)

        action_layout = QHBoxLayout()
        clear_btn = QPushButton("Clear Current Category")
        clear_btn.setStyleSheet("background-color: rgba(60, 60, 60, 200); color: white; padding: 8px 16px; border-radius: 6px; font-weight: bold;")

        clear_all_btn = QPushButton("Clear All Logs")
        clear_all_btn.setStyleSheet("background-color: rgba(70, 30, 30, 200); color: #FFAAAA; padding: 8px 16px; border-radius: 6px; font-weight: bold;")

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setStyleSheet("background-color: rgba(60, 60, 60, 200); color: white; padding: 8px 16px; border-radius: 6px; font-weight: bold;")

        open_file_btn = QPushButton("Open Log File")
        open_file_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 8px 16px; border-radius: 6px; font-weight: bold;")

        action_layout.addWidget(clear_btn)
        action_layout.addWidget(clear_all_btn)
        action_layout.addWidget(refresh_btn)
        action_layout.addStretch()
        action_layout.addWidget(open_file_btn)
        app_log_layout.addLayout(action_layout)

        def reload_logs():
            for lvl_key, view in self.log_views.items():
                entries = logger.get_logs(lvl_key)
                lines = []
                for e in entries:
                    detail_str = f"\n       ↳ {e['details']}" if e.get('details') else ""
                    lines.append(f"[{e['timestamp']}] {e['message']}{detail_str}")
                view.setPlainText("\n".join(lines) if lines else f"No {lvl_key} logs recorded.")
                view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())

        def clear_current():
            current_idx = self.level_tabs.currentIndex()
            current_level = levels[current_idx][0]
            logger.clear(current_level)
            reload_logs()

        def clear_all():
            if QMessageBox.question(self, "Clear Logs", "Are you sure you want to clear all logs?") == QMessageBox.StandardButton.Yes:
                logger.clear()
                reload_logs()

        def open_file():
            import subprocess, os, sys
            if LOG_FILE.exists():
                if sys.platform == "win32":
                    os.startfile(str(LOG_FILE))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(LOG_FILE)])
                else:
                    subprocess.Popen(["xdg-open", str(LOG_FILE)])
            else:
                QMessageBox.information(self, "Log File", "Log file does not exist yet.")

        clear_btn.clicked.connect(clear_current)
        clear_all_btn.clicked.connect(clear_all)
        refresh_btn.clicked.connect(reload_logs)
        open_file_btn.clicked.connect(open_file)

        def on_log_emitted(entry):
            lvl = entry.get("level")
            if lvl in self.log_views:
                view = self.log_views[lvl]
                detail_str = f"\n       ↳ {entry['details']}" if entry.get('details') else ""
                log_line = f"[{entry['timestamp']}] {entry['message']}{detail_str}"
                view.append(log_line)
                view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())

        logger.add_listener(on_log_emitted)
        reload_logs()

        self.log_main_tabs.addTab(app_log_container, "Application Logging")
        layout.addWidget(self.log_main_tabs)
        return card
