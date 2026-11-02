# -*- coding: utf-8 -*-
from pathlib import Path
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QTabWidget,
    QListWidget, QComboBox, QCompleter
)
from PyQt6.QtCore import Qt

DEFAULT_VIDEO_PATH = Path.home() / ".config" / "Titans-launcher" / "background.mp4"

class BasicSettingsWidget(QWidget):
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
        self.init_theme_tab()

        self.main_layout.addWidget(self.tabs)

    # --- TAB 1: General (First Tab) ---
    def init_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()

        self.advanced_cb = QCheckBox("Enable Advanced Settings")
        self.advanced_cb.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        self.advanced_cb.setChecked(self.launcher.config.get("_advanced_mode", False))
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
        row = QHBoxLayout()
        row.addWidget(bg_input)
        row.addWidget(bg_browse_btn)
        form.addRow("Background Video:", row)

        save_btn = QPushButton("Save Background")
        save_btn.setStyleSheet("background-color: #DC143C; padding: 8px; font-weight: bold;")

        def save_bg():
            self.launcher.config["_background_path"] = bg_input.text().strip()
            self.launcher.save_config_file()
            self.launcher.init_video_background()
            QMessageBox.information(self, "Success", "Background video updated!")

        save_btn.clicked.connect(save_bg)
        layout.addLayout(form)
        layout.addWidget(save_btn)
        layout.addStretch()
        self.tabs.addTab(tab, "Background")

    # --- TAB 3: Applications ---
    def init_apps_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        list_widget = QListWidget()
        list_widget.setStyleSheet("background-color: #2a2a2a; color: white; font-size: 16px;")
        for name in self.launcher.config.keys():
            if not name.startswith("_"):
                list_widget.addItem(name)
        layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Application")
        del_btn = QPushButton("Remove Selected")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        layout.addLayout(btn_layout)

        def add_app():
            from launcher import ApplicationEditorDialog
            editor = ApplicationEditorDialog(self.dialog)
            if editor.exec() == 1:
                name, data = editor.get_data()
                if name:
                    self.launcher.config[name] = data
                    self.launcher.save_config_file()
                    list_widget.addItem(name)
                    self.launcher.refresh_applications_view()

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

        add_btn.clicked.connect(add_app)
        del_btn.clicked.connect(del_app)
        self.tabs.addTab(tab, "Applications")

    # --- TAB 4: Basic Theme ---
    def init_theme_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()

        theme_combo = QComboBox()
        theme_combo.setStyleSheet("background-color: #2a2a2a; color: white; padding: 6px;")
        theme_combo.addItems(["Crimson Red", "Cyberpunk Blue", "Emerald Green", "Purple Neon"])
        theme_combo.setCurrentText(self.launcher.config.get("_theme", "Crimson Red"))

        form.addRow("Theme Color:", theme_combo)
        save_btn = QPushButton("Save Theme")
        save_btn.setStyleSheet("background-color: #DC143C; padding: 8px; font-weight: bold;")

        def save_theme():
            self.launcher.config["_theme"] = theme_combo.currentText()
            self.launcher.save_config_file()
            self.launcher.refresh_applications_view()
            QMessageBox.information(self, "Success", "Theme updated!")

        save_btn.clicked.connect(save_theme)
        layout.addLayout(form)
        layout.addWidget(save_btn)
        layout.addStretch()
        self.tabs.addTab(tab, "Theme")
