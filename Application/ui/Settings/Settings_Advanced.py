# -*- coding: utf-8 -*-
from pathlib import Path
from datetime import datetime, timezone
from importlib import import_module
import json
import threading
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QCheckBox, QMessageBox, QStackedWidget,
    QListWidget, QComboBox, QCompleter, QLabel, QScrollArea,
    QTextEdit, QTabWidget
)
from PyQt6.QtCore import Qt, QProcess, QTimer
from PyQt6.QtGui import QColor, QIcon

from Application.ui.dialogs.file_picker import ControllerFileDialog
from Application.core.config import DEFAULT_VIDEO_PATH
from Application.core.time_sync import (
    COUNTRY_TIMEZONES, available_timezones, configured_timezone, effective_offset, fetch_ntp_time,
    timezone_offset_hours,
)
from Application.ui.Settings.Logger import (
    LOG_FILE,
    logger,
    log_critical,
    log_error,
    log_info,
    log_warning,
)
from Application.ui.Settings.ControllerSettings import ControllerSettingsWidget
from Application.ui.Settings.ControlCentreShortcutWidget import ControlCentreShortcutWidget
from Application.ui.Settings.SoundDisplaySettings import SoundDisplaySettingsWidget
from Application.ui.Settings.NetworkSettings import NetworkSettingsWidget
from Application.ui.Settings.NavigationSoundSettings import NavigationSoundCard
from Application.ui.Settings.BluetoothSettings import BluetoothSettingsWidget
from Application.ui.Settings.WeatherSettings import WeatherSettingsWidget
from Application.ui.Settings.tab_style import tab_widget_stylesheet, update_tab_styles
from Application.ui.Settings.controller_focus import SettingsFocusOverlay
from Application.ui.Settings.TaskManager.TaskManagerWidget import TaskManagerWidget
from Application.ui.Settings.UninstallApps import UninstallAppsWidget
from Application.ui.Settings.UserNotificationStorageSettings import UserSessionsTabs, NotificationSettingsWidget
from Application.ui.Settings.NotificationInboxWidget import NotificationInboxWidget
from Application.ui.Settings.AccessibilitySettingsWidget import AccessibilitySettingsWidget
from Application.ui.Settings.HomeProfilesWidget import HomeProfilesWidget
from Application.ui.Settings.ButtonStyleWidget import ButtonStyleWidget
from Application.core import corner_style

AboutDeviceWidget = import_module(
    "Application.ui.Settings.About Device.AboutDeviceSettings"
).AboutDeviceWidget

class MenuNavButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

class AdvancedSettingsWidget(QWidget):
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
        self.general_subsections = [
            ("General", "general", self.create_general_page),
            ("Background", "background", self.create_background_page),
            ("Theme", "theme", self.create_theme_page),
            ("Buttons", "buttons", lambda: ButtonStyleWidget(self.launcher)),
            ("Power", "power", self.create_power_page),
            ("Date & Time", "ntp", self.create_ntp_page),
            ("Weather", "weather", lambda: WeatherSettingsWidget(self.launcher)),
            ("Notifications", "notifications", lambda: NotificationSettingsWidget(self.launcher)),
            ("Accessibility", "accessibility", lambda: AccessibilitySettingsWidget(self.launcher)),
        ]
        # Ordered from most to least important; pages are built from this same list.
        self.sections = [
            ("⚙  General", "general", self.create_general_container),
            ("🎛  Display & Sound", "sound_display", lambda: SoundDisplaySettingsWidget(self.launcher)),
            ("🌐  Network", "network", lambda: NetworkSettingsWidget(self.launcher, advanced=True)),
            ("🔵  Bluetooth", "bluetooth", lambda: BluetoothSettingsWidget(self.launcher)),
            ("🎮  Controller", "controller", lambda: ControllerSettingsWidget(self.launcher)),
            ("🚀  Applications", "applications", self.create_applications_container),
            ("🏠  Home Screen", "home_profiles", lambda: HomeProfilesWidget(self.launcher)),
            ("📊  Task Manager", "task_manager", lambda: TaskManagerWidget(self.launcher)),
            ("👤  Users", "users", lambda: UserSessionsTabs(self.launcher)),
            ("📬  Notification Inbox", "notification_inbox", lambda: NotificationInboxWidget(self.launcher)),
            ("📋  Logging", "logging", self.create_logging_page),
            ("ℹ  About Device", "about_device", lambda: AboutDeviceWidget(self.launcher)),
        ]
        categories = [(label, index) for index, (label, _key, _build) in enumerate(self.sections)]
        self.section_keys = [key for _label, key, _build in self.sections]

        for label, idx in categories:
            btn = MenuNavButton(label)
            btn.clicked.connect(lambda checked, i=idx: self.switch_tab(i))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Sidebar Toggle Button (switches back to Basic Menu)
        self.mode_toggle_btn = QPushButton("Basic Menu")
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

        for _label, _key, build_page in self.sections:
            self.pages.addWidget(build_page())

        root_layout.addWidget(self.pages, stretch=1)
        self.controller_focus_overlay = SettingsFocusOverlay(self)

        # Theme, Background and NTP now live inside the General page as tabs.
        general_index = self.section_keys.index("general")
        if initial_section in self.general_tab_keys:
            self.general_tabs.setCurrentIndex(self.general_tab_keys.index(initial_section))
        initial_index = (
            self.section_keys.index(initial_section)
            if initial_section in self.section_keys else general_index
        )
        self.switch_tab(initial_index)
        if initial_section in self.general_tab_keys:
            self.current_section = initial_section

    def handle_mode_toggle(self):
        if self.on_toggle_advanced:
            self.on_toggle_advanced(False)

    def switch_tab(self, index):
        self.pages.setCurrentIndex(index)
        self.current_section = self.section_keys[index]
        if self.current_section == "general" and self.general_tab_keys:
            self.current_section = self.general_tab_keys[self.general_tabs.currentIndex()]
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
                    QPushButton:hover, QPushButton:focus {
                        background-color: rgba(45, 45, 45, 180);
                        color: #FFFFFF;
                        border-left: 6px solid rgba(255, 255, 255, 80);
                    }
                """)

    def navigate_tabs(self, direction):
        next_index = (self.pages.currentIndex() + direction) % len(self.nav_buttons)
        self.nav_buttons[next_index].setFocus()
        self.switch_tab(next_index)

    def navigate_embedded_tabs(self, direction):
        current_page = self.pages.currentWidget()
        candidates = current_page.findChildren(QTabWidget)
        if isinstance(current_page, QTabWidget):
            candidates.insert(0, current_page)
        tab_widgets = [
            tab_widget for tab_widget in candidates
            if tab_widget.isVisible() and tab_widget.count() > 1
        ]
        if not tab_widgets:
            return False

        focused_widget = QApplication.focusWidget()
        target_tab = None
        while focused_widget is not None and focused_widget is not current_page:
            if isinstance(focused_widget, QTabWidget) and focused_widget in tab_widgets:
                target_tab = focused_widget
                break
            focused_widget = focused_widget.parentWidget()

        if target_tab is None:
            target_tab = tab_widgets[0]
        target_index = (target_tab.currentIndex() + direction) % target_tab.count()
        target_tab.setCurrentIndex(target_index)
        return True

    def create_general_container(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        self.general_tabs = QTabWidget()
        self.general_tabs.setStyleSheet(tab_widget_stylesheet(theme_color))
        self.general_tab_keys = []
        for label, key, build_page in self.general_subsections:
            self.general_tabs.addTab(build_page(), label)
            self.general_tab_keys.append(key)
        self.general_tabs.currentChanged.connect(self.on_general_tab_changed)
        return self.general_tabs

    def create_applications_container(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        tabs = QTabWidget()
        tabs.setStyleSheet(tab_widget_stylesheet(theme_color))
        tabs.addTab(self.create_apps_page(), "Applications")
        tabs.addTab(self.create_icons_page(), "App Icons")
        tabs.addTab(UninstallAppsWidget(self.launcher), "Uninstall Apps")
        tabs.addTab(self.create_applications_module_page(), "Applications Module")
        return tabs

    def create_applications_module_page(self):
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

        title = QLabel("Applications Module")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel(
            "Adds the Home and Applications tabs to the top of the home screen, where apps can be "
            "browsed, installed and uninstalled. When disabled, both tabs are hidden and only the "
            "launcher view is shown."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        checkbox = QCheckBox("Enable the Applications module")
        checkbox.setStyleSheet("color: white; font-size: 16px; border: none;")
        checkbox.setChecked(self.launcher.applications_module_enabled())

        def toggle(checked):
            self.launcher.config["_module_applications"] = checked
            self.launcher.save_config_file()
            self.launcher.apply_applications_module()
            log_info(f"Applications module {'enabled' if checked else 'disabled'}")

        checkbox.toggled.connect(toggle)
        layout.addWidget(checkbox)
        layout.addStretch()
        return card

    def on_general_tab_changed(self, index):
        if self.section_keys[self.pages.currentIndex()] == "general" and 0 <= index < len(self.general_tab_keys):
            self.current_section = self.general_tab_keys[index]

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

        title = QLabel("General Settings (Advanced)")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)

        desc = QLabel("Advanced mode is enabled. Use the sidebar button to switch back to the Basic Menu.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        layout.addWidget(ControlCentreShortcutWidget(self.launcher))
        layout.addWidget(NavigationSoundCard(self.launcher))
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
            file_path, _ = ControllerFileDialog.get_open_file_name(
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
            from Application.ui.dialogs.app_editor import ApplicationEditorDialog
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

            from Application.ui.dialogs.app_editor import ApplicationEditorDialog
            editor = ApplicationEditorDialog(
                self.dialog or self.launcher,
                title=old_name,
                command=data.get("command", ""),
                arguments=data.get("arguments", ""),
                manage_am=data.get("manage_antimicrox", False),
                profile_path=data.get("profile", ""),
                controller_close_enabled=data.get("controller_close_enabled", False),
                app_type=data.get("type", "application"),
                website_url=data.get("website_url", "")
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

    # --- TAB 4: App Icons & Power Icon ---
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
            file_path, _ = ControllerFileDialog.get_open_file_name(
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
            file_path, _ = ControllerFileDialog.get_open_file_name(
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

    # --- TAB 5: Theme colour, corners and animation ---
    def create_theme_page(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        field_style = "background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;"

        scroll, card, layout = self._settings_card(
            "Theme & Style",
            "Customize the accent color, corner style, and animations. Button looks live in the Buttons tab.",
        )

        theme_form = QFormLayout()
        theme_form.setVerticalSpacing(12)

        theme_combo = QComboBox()
        theme_combo.setStyleSheet(field_style)
        theme_combo.addItems([
            "Crimson Red", "Cyberpunk Blue", "Emerald Green", "Purple Neon",
            "Colorblind Blue", "Colorblind Orange", "Colorblind Purple",
        ])
        theme_combo.setCurrentText(self.launcher.config.get("_theme", "Crimson Red"))

        hex_input = QLineEdit()
        hex_input.setStyleSheet(field_style)

        corner_combo = QComboBox()
        corner_combo.setStyleSheet(field_style)
        corner_combo.addItems(list(corner_style.CORNER_STYLES))
        corner_combo.setCurrentText(self.launcher.config.get("_corner_style", corner_style.ROUNDED))

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
        theme_form.addRow(QLabel("Corner Style:"), corner_combo)
        theme_form.addRow(anim_checkbox)
        theme_form.addRow(glitch_checkbox)

        save_theme_btn = QPushButton("Save Theme")

        def update_save_button_color(color):
            save_theme_btn.setStyleSheet(f"background-color: {color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        update_save_button_color(theme_color)

        def save_launcher_theme():
            selected_theme = theme_combo.currentText()
            custom_hex = hex_input.text().strip()
            color = QColor(custom_hex)
            if not color.isValid() or color.alpha() != 255:
                QMessageBox.warning(self, "Invalid Theme Color", "Enter a valid opaque theme color, such as #DC143C.")
                return
            enable_anim = anim_checkbox.isChecked()
            enable_glitch = glitch_checkbox.isChecked()

            self.launcher.config["_theme"] = selected_theme
            self.launcher.config["_corner_style"] = corner_combo.currentText()
            self.launcher.config["_enable_animations"] = enable_anim
            self.launcher.config["_enable_glitch"] = enable_glitch
            if "_custom_colors" not in self.launcher.config:
                self.launcher.config["_custom_colors"] = {}
            self.launcher.config["_custom_colors"][selected_theme] = custom_hex

            self.launcher.save_config_file()
            self.launcher.apply_accessibility_settings()
            corner_style.set_corner_style(corner_combo.currentText())
            self.launcher.refresh_applications_view()
            update_tab_styles(self, self.launcher.get_theme_color())
            update_save_button_color(color.name())
            log_info(f"Advanced Settings: Saved theme '{selected_theme}', hex '{custom_hex}', corners '{corner_combo.currentText()}', anim={enable_anim}, glitch={enable_glitch}")
            QMessageBox.information(self, "Success", "Theme settings saved successfully!")

        save_theme_btn.clicked.connect(save_launcher_theme)
        layout.addLayout(theme_form)
        layout.addWidget(save_theme_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

        scroll.setWidget(card)
        return scroll

    # --- TAB 5b: Power commands ---
    def create_power_page(self):
        theme_color = self.launcher.get_theme_color() if hasattr(self.launcher, 'get_theme_color') else "#DC143C"
        field_style = "background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;"

        scroll, card, layout = self._settings_card(
            "Power",
            "Set the commands used by the launcher's shutdown, sleep, and restart actions.",
        )

        power_cmd_input = QLineEdit(self.launcher.config.get("_power_command", "systemctl poweroff"))
        sleep_cmd_input = QLineEdit(self.launcher.config.get("_sleep_command", "systemctl suspend"))
        restart_cmd_input = QLineEdit(self.launcher.config.get("_restart_command", "systemctl reboot"))
        for field in (power_cmd_input, sleep_cmd_input, restart_cmd_input):
            field.setStyleSheet(field_style)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow(QLabel("Shutdown Command:"), power_cmd_input)
        form.addRow(QLabel("Sleep Command:"), sleep_cmd_input)
        form.addRow(QLabel("Restart Command:"), restart_cmd_input)

        save_btn = QPushButton("Save Power Settings")
        save_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        def save_power():
            self.launcher.config["_power_command"] = power_cmd_input.text().strip()
            self.launcher.config["_sleep_command"] = sleep_cmd_input.text().strip()
            self.launcher.config["_restart_command"] = restart_cmd_input.text().strip()
            self.launcher.save_config_file()
            log_info("Advanced Settings: Saved power commands")
            QMessageBox.information(self, "Success", "Power settings saved successfully!")

        save_btn.clicked.connect(save_power)
        layout.addLayout(form)
        layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

        scroll.setWidget(card)
        return scroll

    @staticmethod
    def _settings_card(title_text, description_text):
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
        title = QLabel(title_text)
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)
        desc = QLabel(description_text)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)
        return scroll, card, layout

    # --- TAB 6: Date & Time ---
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

        title = QLabel("Date & Time")
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

        timezone_combo = QComboBox()
        timezone_combo.setEditable(True)
        timezone_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")
        zone_names = sorted(available_timezones())
        timezone_combo.addItems(zone_names)
        timezone_combo.setCurrentText(configured_timezone(self.launcher.config))
        zone_completer = QCompleter(zone_names, timezone_combo)
        zone_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        zone_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        timezone_combo.setCompleter(zone_completer)

        auto_dst_checkbox = QCheckBox("Adjust for daylight saving automatically (uses the time zone above)")
        auto_dst_checkbox.setChecked(bool(self.launcher.config.get("_ntp_auto_dst", True)))
        auto_dst_checkbox.setStyleSheet("color: white; font-size: 14px;")

        dst_checkbox = QCheckBox("Daylight saving time is active (adds 1 hour to the UTC offset)")
        dst_checkbox.setChecked(bool(self.launcher.config.get("_ntp_dst", False)))
        dst_checkbox.setStyleSheet("color: white; font-size: 14px;")

        time_format_combo = QComboBox()
        time_format_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25); border-radius: 6px;")
        time_format_combo.addItems(["12-Hour (AM/PM)", "24-Hour"])
        time_format_combo.setCurrentText(self.launcher.config.get("_time_format", "12-Hour (AM/PM)"))

        ntp_form.addRow(QLabel("Country Name:"), country_combo)
        ntp_form.addRow(QLabel("NTP Server Address:"), server_input)
        ntp_form.addRow(QLabel("UTC Offset (Hours):"), offset_input)
        ntp_form.addRow(QLabel("Time Zone:"), timezone_combo)
        ntp_form.addRow(QLabel("Automatic Daylight Saving:"), auto_dst_checkbox)
        ntp_form.addRow(QLabel("Manual Daylight Saving:"), dst_checkbox)
        zone_status = QLabel()
        zone_status.setStyleSheet("color: #888888; font-size: 13px;")
        ntp_form.addRow(QLabel(""), zone_status)

        def update_manual_state():
            automatic = auto_dst_checkbox.isChecked()
            offset_input.setEnabled(not automatic)
            dst_checkbox.setEnabled(not automatic)
            timezone_combo.setEnabled(automatic)
            current = timezone_offset_hours(timezone_combo.currentText().strip())
            if not automatic:
                zone_status.setText("Using the manual UTC offset above.")
            elif current is None:
                zone_status.setText("Unknown time zone - the manual offset will be used instead.")
            else:
                zone_status.setText(f"Current offset for this zone: UTC{current:+g} (daylight saving included).")

        def country_changed(name):
            zone = COUNTRY_TIMEZONES.get(name.strip())
            if zone and zone in zone_names:
                timezone_combo.setCurrentText(zone)

        country_combo.currentTextChanged.connect(country_changed)
        auto_dst_checkbox.toggled.connect(update_manual_state)
        timezone_combo.currentTextChanged.connect(lambda _text: update_manual_state())
        update_manual_state()
        ntp_form.addRow(QLabel("Time Format:"), time_format_combo)

        save_ntp_btn = QPushButton("Save NTP Settings")
        save_ntp_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 12px 24px; font-weight: bold; border-radius: 8px; font-size: 15px;")

        def save_ntp_config():
            self.launcher.config["_ntp_country"] = country_combo.currentText().strip()
            self.launcher.config["_ntp_server"] = server_input.text().strip()
            self.launcher.config["_time_format"] = time_format_combo.currentText()
            self.launcher.config["_ntp_dst"] = dst_checkbox.isChecked()
            self.launcher.config["_ntp_auto_dst"] = auto_dst_checkbox.isChecked()
            self.launcher.config["_ntp_timezone"] = timezone_combo.currentText().strip()
            try:
                self.launcher.config["_ntp_offset"] = float(offset_input.text().strip())
            except ValueError:
                self.launcher.config["_ntp_offset"] = 12.0

            self.launcher.save_config_file()
            log_info(f"Advanced Settings: Updated NTP server='{self.launcher.config['_ntp_server']}', country='{self.launcher.config['_ntp_country']}', offset={self.launcher.config['_ntp_offset']}, dst={self.launcher.config['_ntp_dst']}, auto_dst={self.launcher.config['_ntp_auto_dst']}, timezone='{self.launcher.config['_ntp_timezone']}'")

            def immediate_fetch():
                t = fetch_ntp_time(self.launcher.config["_ntp_server"], effective_offset(self.launcher.config))
                if t:
                    self.launcher.current_ntp_time = t
            threading.Thread(target=immediate_fetch, daemon=True).start()

            QMessageBox.information(self, "Success", "NTP and region settings updated successfully!")

        save_ntp_btn.clicked.connect(save_ntp_config)
        layout.addLayout(ntp_form)
        layout.addWidget(save_ntp_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return card

    # --- TAB 7: Logging (with Terminal first, then Application Logs) ---
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

        desc = QLabel("Test commands in the terminal or review real-time application diagnostics and launch operations.")
        desc.setStyleSheet("color: #888888; font-size: 14px; border: none;")
        layout.addWidget(desc)

        # Primary Sub-Tabs inside the Logging page: "Terminal" first, then "Application Logs"
        self.log_main_tabs = QTabWidget()
        self.log_main_tabs.setStyleSheet(tab_widget_stylesheet(theme_color))

        # --- SUB-PAGE 1: Embedded Terminal (Added First) ---
        terminal_container = QWidget()
        terminal_layout = QVBoxLayout(terminal_container)
        terminal_layout.setContentsMargins(15, 15, 15, 15)
        terminal_layout.setSpacing(10)

        terminal_view = QTextEdit()
        terminal_view.setReadOnly(True)
        terminal_view.setStyleSheet("""
            QTextEdit {
                background-color: rgba(10, 10, 10, 245);
                color: #00FF66;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
                border: none;
                padding: 10px;
            }
        """)
        terminal_view.setPlainText("Titans Launcher Embedded Terminal initialized.\nType shell commands below and press Enter or click Run.\n\n")
        terminal_layout.addWidget(terminal_view)

        input_row = QHBoxLayout()
        prompt_label = QLabel("❯")
        prompt_label.setStyleSheet("color: #00FF66; font-weight: bold; font-size: 14px; background: transparent;")

        cmd_input = QLineEdit()
        cmd_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(30, 30, 30, 220);
                color: white;
                font-family: 'Consolas', 'Courier New', monospace;
                padding: 8px;
                font-size: 13px;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 6px;
            }
        """)
        cmd_input.setPlaceholderText("Enter shell command (e.g., uname -a, ps aux)...")

        run_btn = QPushButton("Run")
        run_btn.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 8px 18px; font-weight: bold; border-radius: 6px;")

        input_row.addWidget(prompt_label)
        input_row.addWidget(cmd_input)
        input_row.addWidget(run_btn)
        terminal_layout.addLayout(input_row)

        def execute_command():
            cmd = cmd_input.text().strip()
            if not cmd:
                return
            terminal_view.append(f"❯ {cmd}")
            cmd_input.clear()
            process = QProcess(self)
            process.setProgram("/bin/sh")
            process.setArguments(["-c", cmd])
            process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            run_btn.setEnabled(False)

            captured_output = []
            timed_out = {"value": False}
            handled = {"value": False}
            timeout_timer = QTimer(process)
            timeout_timer.setSingleShot(True)

            def read_output():
                text = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
                if text:
                    captured_output.append(text)
                    terminal_view.append(text.rstrip())

            def finish_command(exit_code=None, error_message=None):
                if handled["value"]:
                    return
                handled["value"] = True
                timeout_timer.stop()
                read_output()
                run_btn.setEnabled(True)

                if error_message:
                    err_msg = f"Execution error: {error_message}"
                    terminal_view.append(err_msg)
                    logger.error(err_msg)
                elif timed_out["value"]:
                    err_msg = "Execution error: command timed out after 15 seconds"
                    terminal_view.append(err_msg)
                    logger.error(err_msg)
                else:
                    output = "".join(captured_output).strip()
                    if not output:
                        terminal_view.append("[Command executed successfully with no output]")
                    logger.info(f"Terminal Command (exit {exit_code}): {cmd}", details=output[:300])
                process.deleteLater()

            process.readyReadStandardOutput.connect(read_output)
            process.finished.connect(lambda exit_code, _status: finish_command(exit_code))
            process.errorOccurred.connect(
                lambda error: finish_command(error_message=process.errorString())
                if error == QProcess.ProcessError.FailedToStart else None
            )
            timeout_timer.timeout.connect(lambda: (timed_out.__setitem__("value", True), process.kill()))
            timeout_timer.start(15000)
            process.start()

        run_btn.clicked.connect(execute_command)
        cmd_input.returnPressed.connect(execute_command)

        self.log_main_tabs.addTab(terminal_container, "Terminal")

        # --- SUB-PAGE 2: Application Logging (Added Second) ---
        app_log_container = QWidget()
        app_log_layout = QVBoxLayout(app_log_container)
        app_log_layout.setContentsMargins(15, 15, 15, 15)
        app_log_layout.setSpacing(12)

        self.level_tabs = QTabWidget()
        self.level_tabs.setStyleSheet(tab_widget_stylesheet(theme_color))

        self.log_views = {}
        levels = [
            ("Critical", "🔴 Critical", "#FF4466"),
            ("Error", "❌ Error", "#FF6666"),
            ("Warning", "⚠️ Warning", "#FFCC00"),
            ("Information", "ℹ️ Information", "#00E5FF"),
            ("Debug", "🐞 Debug", "#BB86FC")
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

        self.log_main_tabs.addTab(app_log_container, "Application Logs")

        # --- SUB-PAGE 3: Operating System Logs ---
        system_log_container = QWidget()
        system_log_layout = QVBoxLayout(system_log_container)
        system_log_layout.setContentsMargins(15, 15, 15, 15)
        system_log_layout.setSpacing(12)

        system_log_tabs = QTabWidget()
        system_log_tabs.setStyleSheet(self.level_tabs.styleSheet())
        system_log_views = {}
        system_log_levels = [
            ("Critical", "#FF4466"),
            ("Error", "#FF6666"),
            ("Warning", "#FFCC00"),
            ("Information", "#00E5FF")
        ]
        for level_name, color_code in system_log_levels:
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
            system_log_views[level_name] = view
            system_log_tabs.addTab(view, level_name)

        system_log_layout.addWidget(system_log_tabs)
        system_log_status = QLabel("Showing the latest 1000 system journal entries.")
        system_log_status.setStyleSheet("color: #888888; font-size: 13px;")
        system_log_layout.addWidget(system_log_status)

        refresh_system_logs_button = QPushButton("Refresh System Logs")
        refresh_system_logs_button.setStyleSheet(f"background-color: {theme_color}; color: white; padding: 8px 16px; font-weight: bold; border-radius: 6px;")
        system_log_layout.addWidget(refresh_system_logs_button, alignment=Qt.AlignmentFlag.AlignLeft)

        system_log_process = QProcess(self)
        system_log_process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        system_log_output = bytearray()
        system_log_error = bytearray()
        system_log_request_finished = {"value": False}

        def read_system_log_output():
            system_log_output.extend(bytes(system_log_process.readAllStandardOutput()))

        def read_system_log_error():
            system_log_error.extend(bytes(system_log_process.readAllStandardError()))

        def display_system_log_error(message):
            for view in system_log_views.values():
                view.setPlainText(message)

        def finish_system_log_refresh(exit_code=None, error_message=None):
            if system_log_request_finished["value"]:
                return
            system_log_request_finished["value"] = True
            read_system_log_output()
            read_system_log_error()
            refresh_system_logs_button.setEnabled(True)

            if error_message or exit_code != 0:
                details = bytes(system_log_error).decode("utf-8", errors="replace").strip()
                message = error_message or details or f"journalctl exited with status {exit_code}."
                if "permission denied" in message.lower() or "not seeing messages" in message.lower():
                    message += "\nAccess to system-wide logs may require systemd-journal group permissions."
                display_system_log_error(message)
                system_log_status.setText("Unable to read system logs.")
                return

            filtered_entries = {level_name: [] for level_name, _ in system_log_levels}
            for line in bytes(system_log_output).splitlines():
                try:
                    entry = json.loads(line)
                    priority = int(entry.get("PRIORITY", -1))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

                if priority <= 2:
                    level_name = "Critical"
                elif priority == 3:
                    level_name = "Error"
                elif priority == 4:
                    level_name = "Warning"
                elif priority in (5, 6):
                    level_name = "Information"
                else:
                    continue

                try:
                    timestamp = datetime.fromtimestamp(
                        int(entry.get("__REALTIME_TIMESTAMP", "0")) / 1_000_000,
                        tz=timezone.utc
                    ).astimezone().strftime("%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError, OSError):
                    timestamp = "Unknown time"
                source = entry.get("_SYSTEMD_UNIT") or entry.get("SYSLOG_IDENTIFIER") or entry.get("_COMM", "system")
                message = str(entry.get("MESSAGE", ""))
                filtered_entries[level_name].append(f"[{timestamp}] [{source}] {message}")

            for level_name, view in system_log_views.items():
                lines = filtered_entries[level_name]
                view.setPlainText("\n".join(lines) if lines else f"No {level_name.lower()} system logs found.")
                view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
            system_log_status.setText("Showing the latest 1000 system journal entries.")

        def refresh_system_logs():
            if system_log_process.state() != QProcess.ProcessState.NotRunning:
                return
            system_log_output.clear()
            system_log_error.clear()
            system_log_request_finished["value"] = False
            refresh_system_logs_button.setEnabled(False)
            system_log_status.setText("Loading system logs...")
            for view in system_log_views.values():
                view.setPlainText("Loading system logs...")
            system_log_process.setProgram("journalctl")
            system_log_process.setArguments(["--no-pager", "--output=json", "-n", "1000"])
            system_log_process.start()

        system_log_process.readyReadStandardOutput.connect(read_system_log_output)
        system_log_process.readyReadStandardError.connect(read_system_log_error)
        system_log_process.finished.connect(
            lambda exit_code, _status: finish_system_log_refresh(exit_code)
        )
        system_log_process.errorOccurred.connect(
            lambda error: finish_system_log_refresh(error_message=system_log_process.errorString())
            if error == QProcess.ProcessError.FailedToStart else None
        )
        refresh_system_logs_button.clicked.connect(refresh_system_logs)
        system_log_timer = QTimer(self)
        system_log_timer.timeout.connect(refresh_system_logs)
        system_log_timer.start(15000)
        refresh_system_logs()

        self.log_main_tabs.addTab(system_log_container, "System Logs")

        layout.addWidget(self.log_main_tabs)
        return card
