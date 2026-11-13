import shutil
import subprocess
from importlib import import_module

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from Application.core.file_check import check_launcher, check_packages
from Application.core.packages import run_pacman
from Application.styles import load_stylesheet
from Application.ui.Settings.AsyncTask import TaskRunnerMixin
from Application.ui.Settings.Logger import log_info, log_warning
from Application.core.privilege_manager import get_privilege_manager

device_styles = import_module("Application.ui.Settings.About Device.DeviceStyles")
updates = import_module("Application.ui.Settings.About Device.Updates")


class FileCheck(QObject, TaskRunnerMixin):
    changed = pyqtSignal()

    def __init__(self, owner, update_task):
        super().__init__(owner)
        self.update_task = update_task
        self.privilege_manager = get_privilege_manager()
        self.busy = False
        self.status = "Run a file check to verify this launcher and installed packages."
        self.report = ""
        self.packages = []

    def start(self, pacman, privilege, audit_operation_id=None):
        if self.busy or self.update_task.process is not None:
            return
        self.busy = True
        self.packages = []
        self.status = "Checking launcher files and all installed packages; authenticate if prompted."
        self.report = ""
        self.changed.emit()

        def work():
            errors, count = check_launcher()
            launcher_report = f"Launcher: {count} build files checked.\n"
            launcher_report += "\n".join(errors) if errors else "Launcher checks passed."
            try:
                packages, exit_code, output = check_packages(pacman, privilege)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                return launcher_report, [], f"Package check failed: {error}", None
            return launcher_report, packages, output, exit_code

        def done(result):
            self.busy = False
            if isinstance(result, Exception):
                log_warning(f"File check failed: {result}")
                self.status = f"File check failed: {result}"
                audit_status = "failed"
                return_code = None
            else:
                launcher_report, self.packages, package_report, exit_code = result
                self.report = f"{launcher_report}\n\nPackage verification:\n{package_report}"
                if exit_code is None:
                    self.status = "File check incomplete. See the report."
                elif exit_code:
                    self.status = "File check complete; package differences found. Review the report."
                else:
                    self.status = "File check complete. Review the report for differences and skipped checks."
                log_info(self.status)
                audit_status = "failed" if exit_code is None else "succeeded"
                return_code = exit_code
            if audit_operation_id and not self.privilege_manager.complete_operation(
                audit_operation_id,
                "package_check",
                audit_status,
                return_code=return_code,
            ):
                self.status += " Privilege audit log could not be updated."
            self.changed.emit()

        self.run_async(work, done)

    def repair(self, pacman, privilege, audit_operation_id=None):
        if self.busy or self.update_task.process is not None or not self.packages:
            return
        self.busy = True
        self.status = "Checking the package list before repair..."
        self.changed.emit()

        def done(result):
            if isinstance(result, Exception) or result.returncode != 0:
                self.status = f"Could not confirm installed packages: {result if isinstance(result, Exception) else result.stderr}"
                if audit_operation_id and not self.privilege_manager.complete_operation(
                    audit_operation_id,
                    "package_repair",
                    "failed",
                    return_code=getattr(result, "returncode", None),
                ):
                    self.status += " Privilege audit log could not be updated."
            elif set(result.stdout.splitlines()) != set(self.packages):
                self.status = "Installed packages changed since the check. Run File Check again."
                self.packages = []
                if audit_operation_id and not self.privilege_manager.complete_operation(
                    audit_operation_id,
                    "package_repair",
                    "cancelled",
                    return_code=result.returncode,
                ):
                    self.status += " Privilege audit log could not be updated."
            else:
                command = [*privilege, pacman, "-Syu", "--noconfirm", "--noprogressbar", "--", "-"]
                log_info(f"Starting repair of {len(self.packages)} installed packages.")
                self.update_task.start(
                    command,
                    operation="repair",
                    input_text="\n".join(self.packages) + "\n",
                    audit_operation="package_repair",
                    audit_operation_id=audit_operation_id,
                )
                self.packages = []
                self.status = "Package repair started. See System Update for progress and output."
            self.busy = False
            self.changed.emit()

        self.run_async(lambda: run_pacman(["-Qq"], timeout=30), done)


class FileCheckWidget(QWidget):
    def __init__(self, launcher, update_widget):
        super().__init__()
        owner = launcher if launcher is not None else QApplication.instance()
        if owner is None:
            raise RuntimeError("File Check requires a QApplication.")
        check = getattr(owner, "_file_check", None)
        if check is None:
            check = FileCheck(owner, update_widget.update_task)
            setattr(owner, "_file_check", check)
        self.check = check
        self.update_task = update_widget.update_task
        self.pacman = shutil.which("pacman") if updates.is_arch_based() else None
        self.privilege_manager = get_privilege_manager()

        theme_color = launcher.get_theme_color() if launcher else "#DC143C"
        layout = QVBoxLayout(self)
        device_styles.style_device_page(self, layout)
        self.setStyleSheet(self.styleSheet() + load_stylesheet(theme_color=theme_color))
        layout.addWidget(device_styles.create_device_page_title("File Check"))
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.check_button = QPushButton("Run File Check")
        self.repair_button = QPushButton("Repair All Packages")
        for button in (self.check_button, self.repair_button):
            button.setObjectName("soundDisplayButton")
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.check_button.clicked.connect(self.start_check)
        self.repair_button.clicked.connect(self.confirm_repair)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, stretch=1)
        self.check.changed.connect(self.sync)
        self.check.changed.connect(update_widget._sync_controls)
        self.update_task.changed.connect(self.sync)
        self.sync()

    def start_check(self):
        if not self.pacman:
            return
        if self.check.busy or self.update_task.process is not None:
            return
        allowed, reason, audit_operation_id = self.privilege_manager.authorize_operation(
            "package_check"
        )
        if not allowed:
            self.status.setText(f"File check denied: {reason}")
            self.check_button.setEnabled(False)
            return
        self.check.start(
            self.pacman,
            self.privilege_manager.build_command([]),
            audit_operation_id=audit_operation_id,
        )

    def confirm_repair(self):
        if (
            not self.pacman
            or not self.check.packages
            or self.check.busy
            or self.update_task.process is not None
        ):
            return
        answer = QMessageBox.question(
            self, "Repair all packages",
            f"Reinstall all {len(self.check.packages)} installed packages and perform a full system upgrade?\n\n"
            "This can download a large amount of data, change system files and run package scripts. "
            "Modified configuration files may need manual merging. Packages not in configured "
            "repositories can prevent the repair. Back up important data first.\n\n"
            "The launcher itself is not repaired. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            allowed, reason, audit_operation_id = self.privilege_manager.authorize_operation(
                "package_repair"
            )
            if not allowed:
                self.status.setText(f"Package repair denied: {reason}")
                self.repair_button.setEnabled(False)
                return
            self.check.repair(
                self.pacman,
                self.privilege_manager.build_command([]),
                audit_operation_id=audit_operation_id,
            )

    def sync(self):
        active = self.check.busy or self.update_task.process is not None
        can_check = (
            self.privilege_manager
            and self.privilege_manager.check_operation_access("package_check")[0]
        )
        can_repair = (
            self.privilege_manager
            and self.privilege_manager.check_operation_access("package_repair")[0]
        )
        self.check_button.setEnabled(not active and bool(self.pacman) and can_check)
        self.repair_button.setEnabled(
            not active and bool(self.check.packages) and bool(self.pacman) and can_repair
        )
        if not self.pacman or not can_check:
            self.status.setText("File Check needs an Arch-based system, pacman, and pkexec or passwordless sudo.")
        elif not can_repair:
            self.status.setText("Package repair requires the administrator role.")
        elif (
            getattr(self.update_task, "operation", "") == "repair"
            and self.check.status.startswith("Package repair started.")
        ):
            self.status.setText(self.update_task.status + " See System Update for progress.")
        else:
            self.status.setText(self.check.status)
        self.output.setPlainText(self.check.report)
        if self.check.busy or (
            self.update_task.process is not None and getattr(self.update_task, "operation", "") == "repair"
        ):
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100 if self.check.report else 0)
