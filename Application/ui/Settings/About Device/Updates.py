import shutil
from importlib import import_module
from pathlib import Path

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Application.styles import load_stylesheet
from Application.ui.Settings.AsyncTask import TaskRunnerMixin, run_command
from Application.ui.Settings.Logger import log_error, log_info, log_warning

device_styles = import_module("Application.ui.Settings.About Device.DeviceStyles")


def is_arch_based():
    try:
        lines = Path("/etc/os-release").read_text(encoding="utf-8").lower().splitlines()
    except OSError:
        return False
    for line in lines:
        if line.startswith(("id=", "id_like=")):
            if "arch" in line.split("=", 1)[1].strip('"').split():
                return True
    return False


# Kept at module level so closing Settings never kills a running pacman.
_RUNNING_PROCESSES = set()


class SystemUpdateWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher=None):
        super().__init__()
        self.launcher = launcher
        self.process = None
        theme_color = launcher.get_theme_color() if launcher else "#DC143C"

        layout = QVBoxLayout(self)
        device_styles.style_device_page(self, layout)
        # Page style first, then the shared launcher button/list styles on top.
        self.setStyleSheet(self.styleSheet() + load_stylesheet(theme_color=theme_color))
        layout.addWidget(device_styles.create_device_page_title("System Update"))

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        actions = QHBoxLayout()
        self.check_button = QPushButton("Check for Updates")
        self.update_button = QPushButton("Update System")
        for button in (self.check_button, self.update_button):
            button.setObjectName("soundDisplayButton")
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.check_button.clicked.connect(self.check_updates)
        self.update_button.clicked.connect(self.start_update)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Pending updates and update progress appear here.")
        layout.addWidget(self.output, stretch=1)

        self.pacman = shutil.which("pacman")
        self.privilege_command = self._find_privilege_command()
        if not is_arch_based() or not self.pacman:
            self.status.setText("System updates are only available on Arch-based systems with pacman.")
            self.check_button.setEnabled(False)
            self.update_button.setEnabled(False)
        elif not self.privilege_command:
            self.status.setText(
                "Checking works, but updating needs pkexec (polkit) or passwordless sudo."
            )
            self.update_button.setEnabled(False)
        else:
            self.status.setText("Press Check for Updates to see what is available.")

    @staticmethod
    def _find_privilege_command():
        if shutil.which("pkexec"):
            return ["pkexec"]
        if shutil.which("sudo"):
            return ["sudo", "-n"]
        return None

    def check_updates(self):
        self.status.setText("Checking for updates...")
        self.check_button.setEnabled(False)
        self.output.clear()
        checkupdates = shutil.which("checkupdates")

        def work():
            if checkupdates:
                # checkupdates syncs a temporary database, so it never touches the live one.
                return run_command([checkupdates], timeout=120), True
            return run_command([self.pacman, "-Qu"], timeout=30), False

        def done(result):
            self.check_button.setEnabled(True)
            if isinstance(result, Exception):
                self.status.setText(f"Could not check for updates: {result}")
                return
            command_result, fresh = result
            packages = command_result.stdout.strip()
            # checkupdates exits 2 and pacman -Qu exits 1 when nothing is pending.
            none_pending_code = 2 if fresh else 1
            if command_result.returncode not in (0, none_pending_code):
                self.status.setText(f"Could not check for updates: {command_result.stderr.strip()}")
                return
            if not packages:
                self.status.setText("The system is up to date." if fresh else "No updates in the local package database.")
                return
            count = len(packages.splitlines())
            note = "" if fresh else " (install pacman-contrib for a fresh check)"
            self.status.setText(f"{count} update(s) available{note}.")
            self.output.setPlainText(packages)

        self.run_async(work, done)

    def start_update(self):
        if self.process is not None:
            return
        answer = QMessageBox.question(
            self,
            "Update system",
            "Run a full system update (pacman -Syu)?\n\nThis can take several minutes. "
            "Do not power off the device while it runs.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        command = [*self.privilege_command, self.pacman, "-Syu", "--noconfirm"]
        self.output.clear()
        self.status.setText("Updating... authenticate if prompted.")
        self.check_button.setEnabled(False)
        self.update_button.setEnabled(False)
        log_info("Starting system update: pacman -Syu --noconfirm")

        self.process = QProcess()
        _RUNNING_PROCESSES.add(self.process)
        self.process.finished.connect(
            lambda *_, proc=self.process: (_RUNNING_PROCESSES.discard(proc), proc.deleteLater())
        )
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._append_output)
        self.process.finished.connect(self._update_finished)
        self.process.errorOccurred.connect(self._update_error)
        self.process.start(command[0], command[1:])

    def _append_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.output.appendPlainText(text.rstrip("\n"))

    def _finish_process(self):
        self.check_button.setEnabled(True)
        self.update_button.setEnabled(True)
        self.process = None

    def _update_finished(self, exit_code, _status):
        if exit_code == 0:
            log_info("System update completed.")
            self.status.setText("Update complete. Restart the device to apply kernel and core updates.")
        else:
            log_warning(f"System update exited with code {exit_code}.")
            self.status.setText(f"Update failed (exit code {exit_code}). See the log below.")
        self._finish_process()

    def _update_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            log_error("System update failed to start.")
            self.status.setText("Could not start the update command.")
            self._finish_process()
