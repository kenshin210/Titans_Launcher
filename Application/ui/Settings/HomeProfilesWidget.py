"""Settings page for arranging application tiles and managing home profiles."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Application.core.home_profiles import normalize_home_profiles
from Application.ui.Settings.Logger import log_info


class HomeProfilesWidget(QWidget):
    """Configure named home layouts with reorderable, hideable app tiles."""

    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.profiles = normalize_home_profiles(launcher.config)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Home Screen Profiles")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        description = QLabel(
            "Choose a profile, drag applications to reorder them, and uncheck "
            "applications to hide them from the Home screen."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Active profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self.profiles)
        self.profile_combo.setCurrentText(
            launcher.config.get("_active_home_profile", "Default")
        )
        profile_row.addWidget(self.profile_combo, stretch=1)
        layout.addLayout(profile_row)

        self.application_list = QListWidget()
        self.application_list.setDragDropMode(
            QListWidget.DragDropMode.InternalMove
        )
        self.application_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.application_list.setStyleSheet(
            "QListWidget { background: rgba(25,25,25,220); color: white; "
            "border: 1px solid rgba(255,255,255,50); padding: 6px; }"
        )
        layout.addWidget(self.application_list, stretch=1)

        buttons = QHBoxLayout()
        self.new_button = QPushButton("New Profile")
        self.save_button = QPushButton("Save Layout")
        self.delete_button = QPushButton("Delete Profile")
        buttons.addWidget(self.new_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.new_button.clicked.connect(self.create_profile)
        self.save_button.clicked.connect(self.save_layout)
        self.delete_button.clicked.connect(self.delete_profile)
        self._load_profile(self.profile_combo.currentText())
        self.profile_combo.currentTextChanged.connect(self._select_profile)

    def _select_profile(self, name):
        if name in self.profiles:
            self.launcher.apply_home_profile(name)
            self._load_profile(name)

    def _load_profile(self, name):
        if not name or name not in self.profiles:
            return
        self.application_list.clear()
        profile = self.profiles[name]
        hidden = set(profile["hidden"])
        for app_name in profile["order"]:
            item = QListWidgetItem(app_name)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Unchecked if app_name in hidden else Qt.CheckState.Checked
            )
            self.application_list.addItem(item)
        self.delete_button.setEnabled(len(self.profiles) > 1)

    def _read_layout(self):
        order = []
        hidden = []
        for index in range(self.application_list.count()):
            item = self.application_list.item(index)
            order.append(item.text())
            if item.checkState() == Qt.CheckState.Unchecked:
                hidden.append(item.text())
        return order, hidden

    def save_layout(self):
        name = self.profile_combo.currentText()
        if not name:
            return
        order, hidden = self._read_layout()
        self.profiles[name] = {"order": order, "hidden": hidden}
        self.launcher.config["_home_profiles"] = self.profiles
        self.launcher.config["_active_home_profile"] = name
        self.launcher.save_config_file()
        self.launcher.refresh_applications_view()
        log_info(f"Saved home-screen layout profile: {name}")

    def create_profile(self):
        name, accepted = QInputDialog.getText(self, "New Home Profile", "Profile name:")
        name = name.strip()
        if not accepted:
            return
        if not name:
            QMessageBox.warning(self, "Invalid Profile", "Profile name cannot be empty.")
            return
        if name in self.profiles:
            QMessageBox.warning(self, "Profile Exists", "Choose a different profile name.")
            return
        order, hidden = self._read_layout()
        self.profiles[name] = {"order": order, "hidden": hidden}
        self.profile_combo.addItem(name)
        self.profile_combo.setCurrentText(name)
        self.save_layout()

    def delete_profile(self):
        name = self.profile_combo.currentText()
        if len(self.profiles) <= 1 or name not in self.profiles:
            return
        answer = QMessageBox.question(
            self,
            "Delete Home Profile",
            f"Delete the '{name}' home-screen profile?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        del self.profiles[name]
        self.launcher.config["_home_profiles"] = self.profiles
        self.profile_combo.blockSignals(True)
        self.profile_combo.removeItem(self.profile_combo.findText(name))
        fallback = self.profile_combo.itemText(0)
        self.profile_combo.setCurrentText(fallback)
        self.profile_combo.blockSignals(False)
        self.launcher.config["_active_home_profile"] = fallback
        self.launcher.save_config_file()
        self._load_profile(fallback)
        self.launcher.refresh_applications_view()
        log_info(f"Deleted home-screen layout profile: {name}")

