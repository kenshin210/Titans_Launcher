import codecs
import re
import shutil
from importlib import import_module
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Application.styles import load_stylesheet
from Application.ui.Settings.AsyncTask import TaskRunnerMixin, run_command
from Application.ui.Settings.Logger import log_error, log_info, log_warning
from Application.core.github_update import GitHubUpdateService, UPDATE_CHANNELS
from Application.core.privilege_manager import get_privilege_manager
from Application.core.sudo_cache import get_credential_cache

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


class SystemUpdate(QObject):
    changed = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.process = None
        self.status = ""
        self.output = ""
        self.total = 0
        self.started = 0
        self.progress = None
        self.progress_text = "Waiting to update"
        self._pending = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.audit_operation = None
        self.audit_operation_id = None

    def start(
        self,
        command,
        operation="update",
        input_text=None,
        audit_operation=None,
        audit_operation_id=None,
    ):
        if self.process is not None:
            return
        self.operation = operation
        self.audit_operation = audit_operation
        self.audit_operation_id = audit_operation_id
        self.status = f"{'Repairing packages' if operation == 'repair' else 'Updating'}... authenticate if prompted."
        self.output = ""
        self.total = self.started = 0
        self.progress = None
        self.progress_text = "Preparing repair..." if operation == "repair" else "Preparing update..."
        self._pending = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        process = QProcess(self)
        self.process = process
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("LC_ALL", "C")
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        if input_text is not None:
            def send_input():
                process.write(input_text.encode("utf-8"))
                process.closeWriteChannel()
            process.started.connect(send_input)
        self.changed.emit()
        process.start(command[0], command[1:])

    def _read_output(self):
        text = self._decoder.decode(bytes(self.process.readAllStandardOutput()))
        if not text:
            return
        self.output = (self.output + text)[-200000:]
        self._pending += text
        lines = re.split(r"[\r\n]", self._pending)
        self._pending = lines.pop()
        for line in lines:
            self._parse_line(line)
        self.changed.emit()

    def _parse_line(self, line):
        match = re.search(r"\bPackages \((\d+)\)", line)
        if match:
            self.total = int(match.group(1))
        if re.search(r"^\s*(?:\(\s*\d+/\s*\d+\)\s*)?"
                     r"(?:installing|upgrading|reinstalling|downgrading|removing)\s+\S+", line):
            self.started += 1
            if self.total:
                self.progress = min(99, (self.started - 1) * 100 // self.total)
                self.progress_text = f"Package {min(self.started, self.total)} of {self.total}"
        elif line.startswith(":: Running post-transaction hooks"):
            self.progress = None
            self.progress_text = "Finishing repair..." if self.operation == "repair" else "Finishing update..."

    def _finished(self, exit_code, exit_status):
        self._read_output()
        tail = self._decoder.decode(b"", final=True)
        if tail:
            self.output = (self.output + tail)[-200000:]
            self._pending += tail
        if self._pending:
            self._parse_line(self._pending)
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            log_info(f"System {self.operation} completed.")
            self.status = (
                "Package repair complete. Run File Check again to verify; restart if core packages changed."
                if self.operation == "repair"
                else "Update complete. Restart the device to apply kernel and core updates."
            )
            self.progress = 100
            self.progress_text = "Repair complete" if self.operation == "repair" else "Update complete"
        else:
            log_warning(f"System {self.operation} exited with code {exit_code} ({exit_status.name}).")
            self.status = f"{self.operation.title()} failed (exit code {exit_code}). See the log below."
            self.progress = 0
            self.progress_text = f"{self.operation.title()} failed"
        if not self._finish_audit(
            "succeeded" if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0 else "failed",
            exit_code,
        ):
            self.status += " Privilege audit log could not be updated."
        self._release_process()

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            log_error(f"System {self.operation} failed to start: {self.process.errorString()}")
            self.status = f"Could not start the {self.operation} command: {self.process.errorString()}"
            self.progress = 0
            self.progress_text = f"{self.operation.title()} failed"
            if not self._finish_audit("failed", None):
                self.status += " Privilege audit log could not be updated."
            self._release_process()
        else:
            log_warning(f"System update process error: {self.process.errorString()}")
            self.status = f"Update process error: {self.process.errorString()}"
            self.changed.emit()

    def _finish_audit(self, status, return_code):
        if self.audit_operation_id is None:
            return True
        from Application.core.privilege_manager import get_privilege_manager

        operation_id = self.audit_operation_id
        operation = self.audit_operation
        self.audit_operation_id = None
        return get_privilege_manager().complete_operation(
            operation_id,
            operation,
            status,
            return_code=return_code,
        )

    def _release_process(self):
        process = self.process
        self.process = None
        process.deleteLater()
        self.changed.emit()


class SystemUpdateWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher=None):
        super().__init__()
        self.launcher = launcher
        owner = launcher if launcher is not None else QApplication.instance()
        self.owner = owner
        if not hasattr(owner, "_system_update"):
            owner._system_update = SystemUpdate(owner)
        self.update_task = owner._system_update
        if not hasattr(owner, "_launcher_update_service"):
            owner._launcher_update_service = GitHubUpdateService(owner, auto_start=False)
        self.launcher_update_service = owner._launcher_update_service
        theme_color = launcher.get_theme_color() if launcher else "#DC143C"

        layout = QVBoxLayout(self)
        device_styles.style_device_page(self, layout)
        # Page style first, then the shared launcher button/list styles on top.
        self.setStyleSheet(self.styleSheet() + load_stylesheet(theme_color=theme_color))
        layout.addWidget(device_styles.create_device_page_title("System Update"))

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        launcher_update_title = QLabel("Launcher updates")
        layout.addWidget(launcher_update_title)
        channel_row = QHBoxLayout()
        channel_row.addWidget(QLabel("Update channel:"))
        self.update_channel_combo = QComboBox()
        self.update_channel_combo.addItems(UPDATE_CHANNELS)
        self.update_channel_combo.setCurrentText(self.launcher_update_service.branch)
        self.update_channel_combo.currentTextChanged.connect(self._set_update_channel)
        channel_row.addWidget(self.update_channel_combo)
        channel_row.addStretch()
        layout.addLayout(channel_row)
        self.launcher_update_status = QLabel()
        self.launcher_update_status.setWordWrap(True)
        layout.addWidget(self.launcher_update_status)
        launcher_actions = QHBoxLayout()
        self.check_launcher_button = QPushButton("Check GitHub")
        self.install_launcher_button = QPushButton("Install Launcher Update")
        for button in (self.check_launcher_button, self.install_launcher_button):
            button.setObjectName("soundDisplayButton")
            launcher_actions.addWidget(button)
        launcher_actions.addStretch()
        layout.addLayout(launcher_actions)
        self.check_launcher_button.clicked.connect(self.launcher_update_service.check)
        self.install_launcher_button.clicked.connect(self.start_launcher_update)

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

        self.progress_label = QLabel("Waiting to update")
        layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Pending updates and update progress appear here.")
        layout.addWidget(self.output, stretch=1)

        self.pacman = shutil.which("pacman")
        self.privilege_manager = get_privilege_manager()
        self.credential_cache = get_credential_cache()
        
        if not is_arch_based() or not self.pacman:
            self.status.setText("System updates are only available on Arch-based systems with pacman.")
            self.check_button.setEnabled(False)
            self.update_button.setEnabled(False)
        elif not self.privilege_manager.check_operation_access("system_update")[0]:
            self.status.setText(
                "System updates need the administrator role and privilege escalation "
                "(polkit/pkexec or sudo)."
            )
            self.update_button.setEnabled(False)
        else:
            self.status.setText("Press Check for Updates to see what is available.")
        self.update_task.changed.connect(self._sync_update)
        self.launcher_update_service.changed.connect(self._sync_launcher_update)
        if self.update_task.status:
            self._sync_update()
        self._sync_launcher_update()

    def _set_update_channel(self, branch):
        try:
            self.launcher_update_service.set_branch(branch)
        except (RuntimeError, ValueError) as error:
            QMessageBox.warning(self, "Launcher Update Channel", str(error))
            self._sync_launcher_update()

    def start_launcher_update(self):
        file_check = getattr(self.owner, "_file_check", None)
        if (
            self.launcher_update_service.busy
            or not self.launcher_update_service.available
            or self.update_task.process is not None
            or (file_check and file_check.busy)
        ):
            return
        answer = QMessageBox.question(
            self,
            "Install launcher update",
            f"Download and install the launcher files from GitHub "
            f"{self.launcher_update_service.branch}? "
            "Your launcher will need to restart to apply the update.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.launcher_update_service.install()

    def check_updates(self):
        file_check = getattr(self.owner, "_file_check", None)
        if self.update_task.process is not None or (file_check and file_check.busy):
            return
        self.status.setText("Checking for updates...")
        self.check_button.setEnabled(False)
        self.update_button.setEnabled(False)
        self.output.clear()
        checkupdates = shutil.which("checkupdates")

        def work():
            if checkupdates:
                # checkupdates syncs a temporary database, so it never touches the live one.
                return run_command([checkupdates], timeout=120), True
            return run_command([self.pacman, "-Qu"], timeout=30), False

        def done(result):
            self.check_button.setEnabled(True)
            self.update_button.setEnabled(
                self.privilege_manager.check_operation_access("system_update")[0]
            )
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
        file_check = getattr(self.owner, "_file_check", None)
        if self.update_task.process is not None or (file_check and file_check.busy):
            return
        answer = QMessageBox.question(
            self,
            "Update system",
            "Run a full system update (pacman -Syu)?\n\nThis can take several minutes. "
            "Do not power off the device while it runs.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        allowed, reason, audit_operation_id = self.privilege_manager.authorize_operation(
            "system_update"
        )
        if not allowed:
            self.status.setText(f"System update denied: {reason}")
            self.update_button.setEnabled(False)
            return

        command = [self.pacman, "-Syu", "--noconfirm", "--noprogressbar"]
        log_info("Starting system update: pacman -Syu --noconfirm")
        self.update_task.start(
            self.privilege_manager.build_command(command),
            audit_operation="system_update",
            audit_operation_id=audit_operation_id,
        )


    def _sync_update(self):
        self.status.setText(self.update_task.status)
        self.output.setPlainText(self.update_task.output)
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())
        self._sync_controls()
        self.progress_label.setText(self.update_task.progress_text)
        if self.update_task.progress is None:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(self.update_task.progress)
        self._sync_launcher_update()

    def _sync_launcher_update(self):
        self.launcher_update_status.setText(self.launcher_update_service.status)
        self.update_channel_combo.blockSignals(True)
        self.update_channel_combo.setCurrentText(self.launcher_update_service.branch)
        self.update_channel_combo.blockSignals(False)
        self.update_channel_combo.setEnabled(not self.launcher_update_service.busy)
        self.check_launcher_button.setEnabled(not self.launcher_update_service.busy)
        self.install_launcher_button.setEnabled(
            not self.launcher_update_service.busy
            and self.launcher_update_service.available
            and self.update_task.process is None
        )

    def _sync_controls(self):
        file_check = getattr(self.owner, "_file_check", None)
        available = self.update_task.process is None and not (file_check and file_check.busy)
        can_update = (
            self.privilege_manager
            and self.privilege_manager.check_operation_access("system_update")[0]
        )
        self.check_button.setEnabled(available and bool(self.pacman) and is_arch_based())
        self.update_button.setEnabled(
            available and bool(self.pacman) and is_arch_based() and can_update
        )
