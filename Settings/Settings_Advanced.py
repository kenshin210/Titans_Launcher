# -*- coding: utf-8 -*-
from pathlib import Path
import json
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QTabWidget,
    QListWidget, QComboBox, QCompleter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

DEFAULT_VIDEO_PATH = Path.home() / ".config" / "Titans-launcher" / "background.mp4"

class AdvancedSettingsWidget(QWidget):
    def __init__(self, parent_launcher, dialog_instance, on_toggle_advanced):
        super().__init__()
        self.launcher = parent_launcher
        self.dialog = dialog_instance
        self.on_toggle_advanced = on_toggle_advanced

        self.main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333; background: #222; }
            QTabBar::tab { background: #333; color: #aaa; padding: 10px 15px; margin-right: 2px; }
            QTabBar::tab:selected { background: #DC143C; color: white; font-weight: bold; }
        """)

        self.init_general_tab()
        self.init_background_tab()
        self.init_apps_tab()
        self.init_icons_tab()
        self.init_theme_tab()
        self.init_ntp_tab()

        self.main_layout.addWidget(self.tabs)

    # --- TAB 1: General (First Tab) ---
    def init_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()

        self.advanced_cb = QCheckBox("Enable Advanced Settings")
        self.advanced_cb.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        self.advanced_cb.setChecked(self.launcher.config.get("_advanced_mode", True))
        self.advanced_cb.toggled.connect(self.on_toggle_advanced)

        form.addRow(self.advanced_cb)
        layout.addLayout(form)
        layout.addStretch()
        self.tabs.addTab(tab, "General")

    # --- TAB 2: Background ---
    def init_background_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()

        bg_input = QLineEdit(self.launcher.config.get("_background_path", str(DEFAULT_VIDEO_PATH)))
        bg_input.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")
        bg_browse_btn = QPushButton("Browse...")
        bg_browse_btn.setStyleSheet("background-color: #444; padding: 6px;")

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
        form.addRow("Background Video Path:", bg_row)

        save_bg_btn = QPushButton("Save Background")
        save_bg_btn.setStyleSheet("background-color: #DC143C; padding: 8px; font-weight: bold;")

        def save_bg_path():
            self.launcher.config["_background_path"] = bg_input.text().strip()
            self.launcher.save_config_file()
            self.launcher.init_video_background()
            QMessageBox.information(self, "Success", "Background video updated successfully!")

        save_bg_btn.clicked.connect(save_bg_path)
        layout.addLayout(form)
        layout.addWidget(save_bg_btn)
        layout.addStretch()
        self.tabs.addTab(tab, "Background")

    # --- TAB 3: Application Profiles ---
    def init_apps_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        list_widget = QListWidget()
        list_widget.setStyleSheet("background-color: #2a2a2a; color: white; font-size: 16px;")
        for name in self.launcher.config.keys():
            if not name.startswith("_"):
                list_widget.addItem(name)
        layout.addWidget(list_widget)

        app_btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Application")
        edit_btn = QPushButton("Edit Application")
        del_btn = QPushButton("Remove Selected")
        app_btn_layout.addWidget(add_btn)
        app_btn_layout.addWidget(edit_btn)
        app_btn_layout.addWidget(del_btn)
        layout.addLayout(app_btn_layout)

        def add_application():
            from launcher import ApplicationEditorDialog
            editor = ApplicationEditorDialog(self.dialog)
            if editor.exec() == 1:
                name, data = editor.get_data()
                if name:
                    self.launcher.config[name] = data
                    self.launcher.save_config_file()
                    list_widget.addItem(name)
                    self.launcher.refresh_applications_view()

        def edit_application():
            current_item = list_widget.currentItem()
            if not current_item:
                return
            old_name = current_item.text()
            data = self.launcher.config.get(old_name, {})

            from launcher import ApplicationEditorDialog
            editor = ApplicationEditorDialog(
                self.dialog,
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

        add_btn.clicked.connect(add_application)
        edit_btn.clicked.connect(edit_application)
        del_btn.clicked.connect(delete_application)
        self.tabs.addTab(tab, "Application Profiles")

    # --- TAB 4: App Icons & Power Icon ---
    def init_icons_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        icon_form = QFormLayout()

        app_combo = QComboBox()
        app_combo.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")
        for name in self.launcher.config.keys():
            if not name.startswith("_"):
                app_combo.addItem(name)

        icon_input = QLineEdit()
        icon_input.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")
        icon_browse_btn = QPushButton("Browse...")
        icon_browse_btn.setStyleSheet("background-color: #444; padding: 6px;")

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
        power_icon_input.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")
        power_icon_browse_btn = QPushButton("Browse...")
        power_icon_browse_btn.setStyleSheet("background-color: #444; padding: 6px;")

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

        icon_form.addRow("Select Application:", app_combo)
        icon_form.addRow("App Icon Path:", icon_row)
        icon_form.addRow("Power Button Icon Path:", power_icon_row)

        save_icon_btn = QPushButton("Save Icon Mappings")
        save_icon_btn.setStyleSheet("background-color: #DC143C; padding: 8px; font-weight: bold;")

        def save_app_icon():
            app_name = app_combo.currentText()
            if app_name in self.launcher.config:
                self.launcher.config[app_name]["icon_path"] = icon_input.text().strip()
            self.launcher.config["_power_icon_path"] = power_icon_input.text().strip()

            self.launcher.save_config_file()
            self.launcher.refresh_applications_view()
            self.launcher.update_power_button_display()
            QMessageBox.information(self, "Success", "Icon mappings updated successfully!")

        save_icon_btn.clicked.connect(save_app_icon)
        layout.addLayout(icon_form)
        layout.addWidget(save_icon_btn)
        layout.addStretch()
        self.tabs.addTab(tab, "App Icons")

    # --- TAB 5: Themes & Animation/Glitch/Power Customization ---
    def init_theme_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        theme_form = QFormLayout()
        theme_combo = QComboBox()
        theme_combo.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")
        theme_combo.addItems(["Crimson Red", "Cyberpunk Blue", "Emerald Green", "Purple Neon"])
        theme_combo.setCurrentText(self.launcher.config.get("_theme", "Crimson Red"))

        hex_input = QLineEdit()
        hex_input.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")

        shape_combo = QComboBox()
        shape_combo.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")
        shape_combo.addItems(["Rounded Square", "Circle"])
        shape_combo.setCurrentText(self.launcher.config.get("_button_shape", "Rounded Square"))

        power_cmd_input = QLineEdit(self.launcher.config.get("_power_command", "systemctl poweroff"))
        power_cmd_input.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")

        sleep_cmd_input = QLineEdit(self.launcher.config.get("_sleep_command", "systemctl suspend"))
        sleep_cmd_input.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")

        restart_cmd_input = QLineEdit(self.launcher.config.get("_restart_command", "systemctl reboot"))
        restart_cmd_input.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")

        anim_checkbox = QCheckBox("Enable Hover & Click Animations")
        anim_checkbox.setStyleSheet("color: white;")
        anim_checkbox.setChecked(self.launcher.config.get("_enable_animations", True))

        glitch_checkbox = QCheckBox("Enable Glitch Effect (Cyberpunk Jitter)")
        glitch_checkbox.setStyleSheet("color: white;")
        glitch_checkbox.setChecked(self.launcher.config.get("_enable_glitch", False))

        def update_hex_field(theme_name):
            custom_colors = self.launcher.config.get("_custom_colors", {})
            hex_input.setText(custom_colors.get(theme_name, "#DC143C"))

        theme_combo.currentTextChanged.connect(update_hex_field)
        update_hex_field(theme_combo.currentText())

        theme_form.addRow("Select Theme Style:", theme_combo)
        theme_form.addRow("Theme Hex Color:", hex_input)
        theme_form.addRow("Button Shape:", shape_combo)
        theme_form.addRow("Shutdown Command:", power_cmd_input)
        theme_form.addRow("Sleep Command:", sleep_cmd_input)
        theme_form.addRow("Restart Command:", restart_cmd_input)
        theme_form.addRow(anim_checkbox)
        theme_form.addRow(glitch_checkbox)

        save_theme_btn = QPushButton("Save Theme & Power Settings")
        save_theme_btn.setStyleSheet("background-color: #DC143C; padding: 8px; font-weight: bold;")

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
            QMessageBox.information(self, "Success", "Theme and power settings saved successfully!")

        save_theme_btn.clicked.connect(save_launcher_theme)
        layout.addLayout(theme_form)
        layout.addWidget(save_theme_btn)
        layout.addStretch()
        self.tabs.addTab(tab, "Themes")

    # --- TAB 6: NTP & Region ---
    def init_ntp_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        ntp_form = QFormLayout()

        country_combo = QComboBox()
        country_combo.setEditable(True)
        country_combo.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")

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
        server_input.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")

        offset_input = QLineEdit(str(self.launcher.config.get("_ntp_offset", 12)))
        offset_input.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")

        time_format_combo = QComboBox()
        time_format_combo.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")
        time_format_combo.addItems(["12-Hour (AM/PM)", "24-Hour"])
        time_format_combo.setCurrentText(self.launcher.config.get("_time_format", "12-Hour (AM/PM)"))

        ntp_form.addRow("Country Name:", country_combo)
        ntp_form.addRow("NTP Server Address:", server_input)
        ntp_form.addRow("UTC Offset (Hours):", offset_input)
        ntp_form.addRow("Time Format:", time_format_combo)

        save_ntp_btn = QPushButton("Save NTP Settings")
        save_ntp_btn.setStyleSheet("background-color: #DC143C; padding: 8px; font-weight: bold;")

        def save_ntp_config():
            self.launcher.config["_ntp_country"] = country_combo.currentText().strip()
            self.launcher.config["_ntp_server"] = server_input.text().strip()
            self.launcher.config["_time_format"] = time_format_combo.currentText()
            try:
                self.launcher.config["_ntp_offset"] = float(offset_input.text().strip())
            except ValueError:
                self.launcher.config["_ntp_offset"] = 12.0

            self.launcher.save_config_file()

            from launcher import fetch_ntp_time
            def immediate_fetch():
                t = fetch_ntp_time(self.launcher.config["_ntp_server"], self.launcher.config["_ntp_offset"])
                if t:
                    self.launcher.current_ntp_time = t
            threading.Thread(target=immediate_fetch, daemon=True).start()

            QMessageBox.information(self, "Success", "NTP and region settings updated successfully!")

        save_ntp_btn.clicked.connect(save_ntp_config)
        layout.addLayout(ntp_form)
        layout.addWidget(save_ntp_btn)
        layout.addStretch()
        self.tabs.addTab(tab, "NTP & Region")
