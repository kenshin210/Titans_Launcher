"""Advanced settings page for uninstalling apps; system-critical packages are never listed."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from Application.core.packages import plan_removal, remove_command, removable_packages
from Application.styles import load_stylesheet
from Application.ui.dialogs.themed_message_box import ThemedMessageBox
from Application.ui.Settings.AsyncTask import TaskRunnerMixin, command_error, run_command
from Application.ui.Settings.Logger import log_info, log_warning


class UninstallAppsWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("soundDisplaySettings")
        self.setStyleSheet(load_stylesheet(theme_color=launcher.get_theme_color()))
        self._apps = []
        self._busy = False
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 0)
        layout.setSpacing(12)

        title = QLabel("Uninstall Apps")
        title.setObjectName("soundDisplayTitle")
        layout.addWidget(title)

        description = QLabel(
            "Remove apps you installed on this device. The operating system, kernel, boot loader, "
            "drivers, desktop, networking and the launcher's own requirements are hidden and cannot be removed."
        )
        description.setObjectName("soundDisplayDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        card = QFrame()
        card.setObjectName("soundDisplayCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter installed apps")
        self.filter_input.setStyleSheet(
            "background-color: rgba(40, 40, 40, 200); color: white; padding: 8px; "
            "border-radius: 6px; font-size: 14px; border: 1px solid rgba(255, 255, 255, 25);"
        )
        self.filter_input.textChanged.connect(self.apply_filter)
        card_layout.addWidget(self.filter_input)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "background-color: rgba(30, 30, 30, 200); color: white; font-size: 15px; "
            "border: 1px solid rgba(255, 255, 255, 30); border-radius: 8px; padding: 6px;"
        )
        card_layout.addWidget(self.list_widget, stretch=1)

        row = QHBoxLayout()
        self.remove_button = QPushButton("Uninstall Selected")
        self.remove_button.setObjectName("soundDisplayButton")
        self.remove_button.clicked.connect(self.uninstall_selected)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("soundDisplayButton")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.remove_button)
        row.addWidget(self.refresh_button)
        row.addStretch()
        card_layout.addLayout(row)
        layout.addWidget(card, stretch=1)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self, note=""):
        self.status.setText(f"{note}Reading installed apps...")
        self.refresh_button.setEnabled(False)

        def done(result):
            self.refresh_button.setEnabled(True)
            if isinstance(result, Exception):
                log_warning("Uninstall Apps: could not read installed packages.", details=str(result))
                self.status.setText(f"Could not read installed apps: {result}")
                self._apps = []
                self.apply_filter()
                return
            self._apps, hidden = result
            self.status.setText(f"{note}{len(self._apps)} apps can be removed. {hidden} system packages are protected.")
            self.apply_filter()

        self.run_async(removable_packages, done)

    def apply_filter(self):
        needle = self.filter_input.text().strip().lower()
        self.list_widget.clear()
        for app in self._apps:
            if needle and needle not in app["name"].lower() and needle not in app["description"].lower():
                continue
            label = f"{app['name']}  {app['version']}"
            if app["size"]:
                label += f"  ·  {app['size']}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, app["name"])
            item.setToolTip(app["description"])
            self.list_widget.addItem(item)

    def uninstall_selected(self):
        item = self.list_widget.currentItem()
        if item is None or self._busy:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        self._busy = True
        self.remove_button.setEnabled(False)
        self.status.setText(f"Checking what removing {name} would affect...")

        def check_done(result):
            if isinstance(result, Exception):
                self._finish(f"Could not check {name}: {result}")
                return
            planned, error = result
            if error:
                self._finish(error)
                return
            command = remove_command(planned)
            if command is None:
                self._finish("Removing apps needs pkexec or sudo, and neither was found.")
                return
            dialog = ThemedMessageBox(
                self.window(), title="Uninstall App",
                message="Remove: " + ", ".join(planned) + "?",
                theme_color=self.launcher.get_theme_color(),
            )
            if dialog.exec() != dialog.DialogCode.Accepted:
                self._finish("")
                return
            self.status.setText(f"Removing {name}...")

            def remove_done(outcome):
                if isinstance(outcome, Exception) or outcome.returncode != 0:
                    message = str(outcome) if isinstance(outcome, Exception) else command_error(outcome)
                    log_warning(f"Uninstall Apps: failed to remove {name}.", details=message)
                    self._finish(f"Could not remove {name}: {message}")
                    return
                log_info(f"Uninstall Apps: removed {', '.join(planned)}")
                self._finish("")
                self.refresh(note=f"Removed {', '.join(planned)}. ")

            self.run_async(lambda: run_command(command, timeout=900), remove_done)

        self.run_async(lambda: plan_removal(name), check_done)

    def _finish(self, message):
        self._busy = False
        self.remove_button.setEnabled(True)
        if message:
            self.status.setText(message)
