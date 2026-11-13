import shlex
from pathlib import Path
from urllib.parse import urlsplit

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...styles import load_stylesheet

from Application.ui.dialogs.file_picker import ControllerFileDialog
from Application.ui.Settings.Logger import log_warning


class ApplicationEditorDialog(QDialog):
    def __init__(
        self,
        parent=None,
        title="",
        command="",
        arguments="",
        manage_am=False,
        profile_path="",
        controller_close_enabled=False,
        app_type="application",
        website_url="",
    ):
        super().__init__(parent)
        theme_color = getattr(parent, "get_theme_color", lambda: "#DC143C")()
        self.setObjectName("applicationEditorDialog")
        self.setStyleSheet(load_stylesheet(theme_color=theme_color))
        self.setWindowTitle("Add or Edit Application")
        self.resize(520, 400)

        layout = QVBoxLayout(self)
        type_form = QFormLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItem("Application", "application")
        self.type_combo.addItem("Website", "website")
        self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(app_type)))
        type_form.addRow("Type:", self.type_combo)
        layout.addLayout(type_form)

        self.mode_stack = QStackedWidget()
        self.name_input = QLineEdit(title)
        self.cmd_input = QLineEdit(command)
        self.cmd_browse_btn = QPushButton("Browse...")
        self.cmd_browse_btn.clicked.connect(self.browse_command)

        command_layout = QHBoxLayout()
        command_layout.addWidget(self.cmd_input)
        command_layout.addWidget(self.cmd_browse_btn)

        self.args_input = QLineEdit(arguments)
        application_fields = QWidget()
        application_form = QFormLayout(application_fields)
        application_form.addRow("App Executable:", command_layout)
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

        self.controller_close_cb = QCheckBox("Xbox Guide button closes this app")
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
        save_btn.setObjectName("applicationSaveButton")
        save_btn.clicked.connect(self.accept)
        layout.addWidget(save_btn)
        self.toggle_am_path(manage_am)

    def toggle_am_path(self, enabled):
        self.profile_input.setEnabled(enabled)
        self.browse_btn.setEnabled(enabled)

    def browse_command(self):
        possible_paths = [
            "/usr/bin",
            "/bin",
            "/usr/local/bin",
            str(Path.home() / ".local" / "bin"),
        ]
        start_dir = next((path for path in possible_paths if Path(path).exists()), str(Path.home()))
        file_path, _ = ControllerFileDialog.get_open_file_name(
            self, "Select Application Executable", start_dir, "All Files (*)"
        )
        if file_path:
            self.cmd_input.setText(file_path)

    def browse_profile(self):
        file_path, _ = ControllerFileDialog.get_open_file_name(
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
                    "Enter a valid website address, such as https://example.com.",
                )
                return
            if not self.website_browser_input.text().strip():
                QMessageBox.warning(self, "Missing Browser", "Enter a browser executable.")
                return
            super().accept()
            return

        command = self.cmd_input.text().strip()
        if command and (Path(command).is_absolute() or "/" in command or "\\" in command):
            if not Path(command).exists():
                log_warning(f"ApplicationEditor: Executable does not exist on disk: '{command}'")
                reply = QMessageBox.warning(
                    self,
                    "File Warning",
                    f"The specified path does not exist on disk:\n{command}\n\nDo you still want to save?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
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
                "icon_path": "",
            },
        )
