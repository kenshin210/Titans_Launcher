"""Controller-friendly account and notification preference settings."""

from PyQt6.QtWidgets import (
    QComboBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QHBoxLayout,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from Application.core.notification_system import NotificationCategory, NotificationManager
from Application.core.storage_manager import StorageManager
from Application.core.user_manager import UserManager, UserManagerError
from Application.ui.Settings.tab_style import tab_widget_stylesheet


class UserSessionsSettingsWidget(QWidget):
    """Display local accounts and allow safe switching through system services."""

    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.user_manager = UserManager()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Accounts are managed by Linux. Titans does not create accounts or "
            "switch identities directly; the display manager handles sign-in."
        ))
        layout.addWidget(QLabel("Local accounts"))
        self.accounts_list = QListWidget()
        self.accounts_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.accounts_list)

        layout.addWidget(QLabel("Available login sessions"))
        self.sessions_list = QListWidget()
        self.sessions_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.sessions_list)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)

        self.activate_button = QPushButton("Switch to Selected Session")
        self.activate_button.clicked.connect(self.activate_selected_session)
        layout.addWidget(self.activate_button)

        self.greeter_button = QPushButton("Switch User / Sign In")
        self.greeter_button.clicked.connect(self.switch_to_login_screen)
        layout.addWidget(self.greeter_button)

        self.refresh()

    def refresh(self):
        self.accounts_list.clear()
        self.sessions_list.clear()
        try:
            for account in self.user_manager.list_accounts():
                suffix = " (current user)" if account.is_current else ""
                item = QListWidgetItem(f"{account.display_name}  —  {account.username}{suffix}")
                item.setData(Qt.ItemDataRole.UserRole, account.username)
                self.accounts_list.addItem(item)
        except UserManagerError as error:
            self.status_label.setText(str(error))
            self.activate_button.setEnabled(False)
            return

        try:
            sessions = self.user_manager.list_sessions()
        except UserManagerError as error:
            self.status_label.setText(str(error))
            self.activate_button.setEnabled(False)
            return

        for session in sessions:
            location = session.seat if not session.terminal else f"{session.seat}, {session.terminal}"
            item = QListWidgetItem(f"{session.username}  —  session {session.session_id} ({location})")
            item.setData(Qt.ItemDataRole.UserRole, session.session_id)
            self.sessions_list.addItem(item)
        self.status_label.setText(
            f"{self.accounts_list.count()} local account(s), {len(sessions)} login session(s)."
        )
        self.activate_button.setEnabled(bool(sessions))

    def activate_selected_session(self):
        item = self.sessions_list.currentItem()
        if item is None:
            self.status_label.setText("Select an available session first.")
            return
        try:
            self.user_manager.activate_session(item.data(Qt.ItemDataRole.UserRole))
        except UserManagerError as error:
            QMessageBox.warning(self, "Session Switch Failed", str(error))
            self.refresh()
            return
        self.status_label.setText("Session switch requested.")

    def switch_to_login_screen(self):
        answer = QMessageBox.question(
            self,
            "Switch User",
            "The display manager will show its sign-in screen. Save work in open applications first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.user_manager.switch_to_login_screen()
        except UserManagerError as error:
            QMessageBox.warning(self, "User Switching Unavailable", str(error))


class NotificationSettingsWidget(QWidget):
    """Configure per-category notification delivery."""

    _CATEGORY_LABELS = {
        NotificationCategory.DEVICE.value: "Device events",
        NotificationCategory.DEVICE_ADDED.value: "Devices connected",
        NotificationCategory.DEVICE_ERROR.value: "Device and system errors",
        NotificationCategory.NETWORK.value: "Network events",
        NotificationCategory.NETWORK_CONNECTED.value: "Network connected",
        NotificationCategory.NETWORK_DISCONNECTED.value: "Network disconnected",
        NotificationCategory.BATTERY.value: "Power and battery",
        NotificationCategory.BATTERY_LOW.value: "Low battery",
        NotificationCategory.BATTERY_CRITICAL.value: "Critical battery",
        NotificationCategory.TRANSFER_COMPLETE.value: "Transfer complete",
        NotificationCategory.PRESENTATION.value: "Presentation",
        NotificationCategory.SCREENSAVER.value: "Screen saver",
        NotificationCategory.APP_NOTIFICATION.value: "Application notifications",
    }

    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.notification_manager = NotificationManager()
        self.buttons = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose which notification categories Titans may deliver."))
        for category, label in self._CATEGORY_LABELS.items():
            button = QPushButton()
            button.setCheckable(True)
            button.setChecked(self.notification_manager.is_category_enabled(category))
            button.setText(self._button_text(label, button.isChecked()))
            button.clicked.connect(
                lambda checked, value=category, title=label: self.set_category(value, title, checked)
            )
            self.buttons[category] = button
            layout.addWidget(button)
        layout.addStretch()

    @staticmethod
    def _button_text(label, enabled):
        return f"{label}: {'On' if enabled else 'Off'}"

    def set_category(self, category, label, enabled):
        button = self.buttons[category]
        try:
            self.notification_manager.set_category_enabled(category, enabled)
        except (OSError, ValueError) as error:
            button.setChecked(not enabled)
            button.setText(self._button_text(label, not enabled))
            QMessageBox.warning(self, "Notification Preference Not Saved", str(error))
            return
        button.setText(self._button_text(label, enabled))


class StorageOverviewWidget(QWidget):
    """Display disks and offer UDisks-authorized mount/eject operations."""

    def __init__(self, launcher):
        super().__init__()
        self.storage_manager = StorageManager()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Storage devices and mounted filesystems"))
        self.items = QListWidget()
        self.items.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.items)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        controls = QHBoxLayout()
        self.mount_button = QPushButton("Mount Selected Volume")
        self.mount_button.clicked.connect(self.mount_or_unmount_selected)
        controls.addWidget(self.mount_button)
        self.eject_button = QPushButton("Eject Selected Device")
        self.eject_button.clicked.connect(self.eject_selected)
        controls.addWidget(self.eject_button)
        layout.addLayout(controls)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        self.refresh()
        self._selection_changed()

    @staticmethod
    def _format_size(value):
        size = float(value)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if size < 1024 or unit == "TiB":
                return f"{size:.1f} {unit}"
            size /= 1024

    def refresh(self):
        self.items.clear()
        disk_ok, disks = self.storage_manager.list_disks()
        volume_ok, volumes = self.storage_manager.list_volumes()
        if disk_ok:
            for disk in disks:
                details = f"{disk.path} — {self._format_size(disk.size)}"
                if disk.is_removable:
                    details += " (removable)"
                item = QListWidgetItem(details)
                item.setData(Qt.ItemDataRole.UserRole, {
                    "kind": "disk",
                    "device": disk.path,
                    "removable": disk.is_removable,
                })
                self.items.addItem(item)
        if volume_ok:
            for volume in volumes:
                mount_state = ", ".join(volume.mount_points) if volume.mount_points else "not mounted"
                details = (
                    f"{volume.path} — {self._format_size(volume.size)} "
                    f"({volume.filesystem or 'no filesystem'}, {mount_state})"
                )
                item = QListWidgetItem(details)
                item.setData(Qt.ItemDataRole.UserRole, {
                    "kind": "volume",
                    "device": volume.path,
                    "parent_device": volume.parent_device,
                    "mounted": bool(volume.mount_points),
                    "mountable": bool(volume.filesystem),
                    "removable": volume.is_removable,
                })
                self.items.addItem(item)
        failures = []
        if not disk_ok:
            failures.append("Disk enumeration failed")
        if not volume_ok:
            failures.append("Volume enumeration failed")
        self.status_label.setText("; ".join(failures) if failures else "Storage information is current.")
        self._selection_changed()

    def _selected_data(self):
        item = self.items.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selection_changed(self):
        data = self._selected_data()
        is_volume = bool(data and data.get("kind") == "volume")
        mounted = bool(is_volume and data.get("mounted"))
        self.mount_button.setText("Unmount Selected Volume" if mounted else "Mount Selected Volume")
        self.mount_button.setEnabled(
            bool(is_volume and (mounted or data.get("mountable")))
        )
        self.eject_button.setEnabled(bool(data and data.get("removable")))

    def mount_or_unmount_selected(self):
        data = self._selected_data()
        if not data or data.get("kind") != "volume":
            return
        if data.get("mounted"):
            answer = QMessageBox.question(
                self,
                "Unmount Volume",
                "Close files on this volume before unmounting it.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            success, message = self.storage_manager.unmount_device(data["device"])
        else:
            success, message = self.storage_manager.mount_device(data["device"])
        self.status_label.setText(message)
        if not success:
            QMessageBox.warning(self, "Storage Operation Failed", message)
            return
        self.refresh()

    def eject_selected(self):
        data = self._selected_data()
        if not data or not data.get("removable"):
            return
        device = data.get("parent_device") or data["device"]
        answer = QMessageBox.question(
            self,
            "Eject Device",
            f"Safely power off {device}? Its volumes must be unmounted first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        success, message = self.storage_manager.eject_device(device)
        self.status_label.setText(message)
        if not success:
            QMessageBox.warning(self, "Eject Failed", message)
            return
        self.refresh()


class Phase3SettingsWidget(QTabWidget):
    """Keep refinement settings grouped and reachable through controller tabs."""

    def __init__(self, launcher):
        super().__init__()
        theme_color = launcher.get_theme_color() if hasattr(launcher, "get_theme_color") else "#DC143C"
        self.setStyleSheet(tab_widget_stylesheet(theme_color))
        self.addTab(UserSessionsSettingsWidget(launcher), "Users & Sessions")
