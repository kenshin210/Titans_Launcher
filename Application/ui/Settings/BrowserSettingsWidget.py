from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from Application.core.packages import install_command
from Application.styles import load_stylesheet
from Application.ui.dialogs.themed_message_box import ThemedMessageBox
from Application.ui.Settings.AsyncTask import TaskRunnerMixin, command_error, run_command
from Application.ui.Settings.Logger import log_info, log_warning


class BrowserSettingsWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("soundDisplaySettings")
        self.setStyleSheet(load_stylesheet(theme_color=launcher.get_theme_color()))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(18)
        title = QLabel("Firefox Browser")
        title.setObjectName("soundDisplayTitle")
        layout.addWidget(title)

        description = QLabel(
            "Install uBlock Origin for Arch Linux's Firefox package. It applies to Firefox "
            "outside Titans too. Restart Firefox and approve or enable the add-on if prompted."
        )
        description.setObjectName("soundDisplayDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.install_button = QPushButton("Install uBlock Origin")
        self.install_button.setObjectName("soundDisplayButton")
        self.install_button.clicked.connect(self.install)
        layout.addWidget(self.install_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()

    def showEvent(self, event):
        self.setStyleSheet(load_stylesheet(theme_color=self.launcher.get_theme_color()))
        super().showEvent(event)

    def install(self):
        dialog = ThemedMessageBox(
            self.window(), title="Install uBlock Origin",
            message=(
                "Install the Arch Firefox uBlock Origin package for all users? "
                "This requires administrator access and also affects Firefox outside Titans."
            ),
            theme_color=self.launcher.get_theme_color(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.install_button.setEnabled(False)
        self.status.setText("Installing uBlock Origin... this can take a few minutes.")

        def work():
            command = install_command("firefox-ublock-origin")
            if command is None:
                raise RuntimeError("Installing needs pkexec or authorized sudo.")
            return run_command(command, timeout=1800)

        def done(result):
            self.install_button.setEnabled(True)
            if isinstance(result, Exception) or result.returncode != 0:
                message = str(result) if isinstance(result, Exception) else command_error(result)
                log_warning("Browser settings: uBlock Origin installation failed.", details=message)
                self.status.setText(f"Could not install uBlock Origin: {message}")
                return
            log_info("Browser settings: installed Firefox uBlock Origin package.")
            self.status.setText(
                "Package installed. Restart Firefox and approve or enable uBlock Origin if prompted."
            )

        self.run_async(work, done)
