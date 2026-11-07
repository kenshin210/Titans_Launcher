# -*- coding: utf-8 -*-
from pathlib import Path
from importlib import import_module
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QStackedWidget,
    QListWidget, QComboBox, QCompleter, QLabel, QScrollArea
)
from PyQt6.QtCore import Qt

from Application.core.config import DEFAULT_VIDEO_PATH
from Application.ui.Settings.Logger import log_error, log_info, log_warning
from Application.ui.Settings.ControllerSettings import ControllerSettingsWidget
from Application.ui.Settings.SoundDisplaySettings import SoundDisplaySettingsWidget

AboutDeviceWidget = import_module(
    "Application.ui.Settings.About Device.AboutDeviceSettings"
).AboutDeviceWidget

class MenuNavButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

class BasicSettingsWidget(QWidget):
    def __init__(
        self, parent_launcher, dialog_instance=None, on_toggle_advanced=None,
        initial_section="general"
    ):
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

        menu_header = QLabel("SETTINGS")
        menu_header.setStyleSheet("""
            color: rgba(255, 255, 255, 140);
            font-size: 15px;
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
            ("🎨  Theme", 3),
            ("🎛  Sound & Display", 4),
            ("🎮  Controller", 5),
            ("ℹ  About Device", 6)
        ]
        self.section_keys = [
            "general", "background", "applications", "theme", "sound_display",
            "controller", "about_device"
        ]

        for label, idx in categories:
            btn = MenuNavButton(label)
            btn.clicked.connect(lambda checked, i=idx: self.switch_tab(i))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Sidebar Toggle Button (replaces checkbox)
        self.mode_toggle_btn = QPushButton("Advanced Menu")
        self.mode_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_toggle_btn.setStyleSheet(f"""
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
        self.mode_toggle_btn.clicked.connect(self.handle_mode_toggle)
        sidebar_layout.addWidget(self.mode_toggle_btn)

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
        self.pages.addWidget(self.create_theme_page())
        self.pages.addWidget(SoundDisplaySettingsWidget(self.launcher))
        self.pages.addWidget(ControllerSettingsWidget(self.launcher))
        self.pages.addWidget(AboutDeviceWidget(self.launcher))

        root_layout.addWidget(self.pages, stretch=1)

        initial_index = (
            self.section_keys.index(initial_section)
            if initial_section in self.section_keys else 0
        )
        self.switch_tab(initial_index)

    def handle_mode_toggle(self):
        if self.on_toggle_advanced:
            # Currently in Basic, switch to Advanced (True)
            self.on_toggle_advanced(True)

    def switch_tab(self, index):
        self.pages.setCurrentIndex(index)
        self.current_section = self.section_keys[index]
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

    def navigate_tabs(self, direction):
        next_index = (self.pages.currentIndex() + direction) % len(self.nav_buttons)
        self.nav_buttons[next_index].setFocus()
        self.switch_tab(next_index)

    def focus_current_menu_item(self):
        if self.nav_buttons:
            self.nav_buttons[self.pages.currentIndex()].setFocus()

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

        title = QLabel("General Settings")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Configure basic launcher behavior or switch to the Advanced Menu using the sidebar control.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)
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

        desc = QLabel("Select a video file (.mp4, .avi, .mkv) to loop in the background of your launcher.")
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
        row = QHBoxLayout()
        row.addWidget(bg_input)
        row.addWidget(bg_browse_btn)
        form.addRow(QLabel("Video Path:"), row)

        save_btn = QPushButton("Save Background")
        save_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        def save_bg():
            new_path = bg_input.text().strip()
            self.launcher.config["_background_path"] = new_path
            self.launcher.save_config_file()
            self.launcher.init_video_background()
            log_info(f"Basic Settings: Updated background video path to '{new_path}'")
            QMessageBox.information(self, "Success", "Background video updated!")

        save_btn.clicked.connect(save_bg)
        layout.addLayout(form)
        layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return card

    # --- TAB 3: Applications ---
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

        title = QLabel("Applications")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Manage your games and media apps shown on the main launcher carousel.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        list_widget = QListWidget()
        list_widget.setStyleSheet("background-color: rgba(30, 30, 30, 200); color: white; font-size: 16px; border: 1px solid rgba(255, 255, 255, 30); border-radius: 8px; padding: 6px;")
        for name in self.launcher.config.keys():
            if not name.startswith("_"):
                list_widget.addItem(name)
        layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("+ Add Application")
        add_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 10px 20px; font-weight: bold; border-radius: 8px;")
        del_btn = QPushButton("Remove Selected")
        del_btn.setStyleSheet("background-color: rgba(65, 65, 65, 200); color: white; padding: 10px 20px; font-weight: bold; border-radius: 8px;")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        def add_app():
            from Application.ui.dialogs.app_editor import ApplicationEditorDialog
            editor = ApplicationEditorDialog(self.dialog or self.launcher)
            if editor.exec() == 1:
                name, data = editor.get_data()
                if name:
                    self.launcher.config[name] = data
                    self.launcher.save_config_file()
                    list_widget.addItem(name)
                    self.launcher.refresh_applications_view()
                    log_info(f"Basic Settings: Added application '{name}'")

        def del_app():
            current_item = list_widget.currentItem()
            if not current_item:
                return
            name = current_item.text()
            if QMessageBox.question(self, "Delete", f"Remove '{name}'?") == QMessageBox.StandardButton.Yes:
                del self.launcher.config[name]
                self.launcher.save_config_file()
                list_widget.takeItem(list_widget.row(current_item))
                self.launcher.refresh_applications_view()
                log_info(f"Basic Settings: Removed application '{name}'")

        add_btn.clicked.connect(add_app)
        del_btn.clicked.connect(del_app)
        return card

    # --- TAB 4: Basic Theme ---
    def create_theme_page(self):
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

        title = QLabel("Theme & Colors")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Select an accent color theme for button highlights, borders, and active tabs.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        form = QFormLayout()
        form.setVerticalSpacing(15)

        theme_combo = QComboBox()
        theme_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")
        theme_combo.addItems(["Crimson Red", "Cyberpunk Blue", "Emerald Green", "Purple Neon"])
        theme_combo.setCurrentText(self.launcher.config.get("_theme", "Crimson Red"))

        form.addRow(QLabel("Theme Color:"), theme_combo)

        save_btn = QPushButton("Save Theme")
        save_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        def save_theme():
            selected_theme = theme_combo.currentText()
            self.launcher.config["_theme"] = selected_theme
            self.launcher.save_config_file()
            self.launcher.refresh_applications_view()
            log_info(f"Basic Settings: Saved theme color '{selected_theme}'")
            QMessageBox.information(self, "Success", "Theme updated!")

        save_btn.clicked.connect(save_theme)
        layout.addLayout(form)
        layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return card
