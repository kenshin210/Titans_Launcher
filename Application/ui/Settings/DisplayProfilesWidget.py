"""
Display Profiles Widget for Titans Launcher Settings UI.

Manages named display profiles with resolution, refresh rate, scaling, and DPI settings.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QDialog, QFormLayout, QLineEdit, QSpinBox,
    QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt
from typing import Optional

from Application.core.display_profiles import DisplayProfilesManager, DisplayProfile
from Application.ui.Settings.Logger import log_info, log_error


class CreateEditProfileDialog(QDialog):
    """Dialog for creating or editing a display profile."""

    def __init__(self, parent=None, profile: Optional[DisplayProfile] = None):
        super().__init__(parent)
        self.profile = profile
        self.setWindowTitle("Display Profile")
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit, QSpinBox {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #333333;
                border: none;
            }
        """)

        layout = QFormLayout(self)

        # Profile name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., 4K Gaming")
        if profile:
            self.name_input.setText(profile.name)
        layout.addRow("Profile Name:", self.name_input)

        # Resolution
        self.resolution_input = QLineEdit()
        self.resolution_input.setPlaceholderText("e.g., 3840x2160")
        if profile:
            self.resolution_input.setText(profile.resolution)
        layout.addRow("Resolution (WxH):", self.resolution_input)

        # Refresh Rate
        self.refresh_rate_input = QSpinBox()
        self.refresh_rate_input.setRange(24, 240)
        self.refresh_rate_input.setValue(60)
        if profile:
            self.refresh_rate_input.setValue(profile.refresh_rate)
        layout.addRow("Refresh Rate (Hz):", self.refresh_rate_input)

        # Scaling
        self.scaling_input = QSpinBox()
        self.scaling_input.setRange(50, 200)
        self.scaling_input.setValue(100)
        self.scaling_input.setSuffix("%")
        if profile:
            self.scaling_input.setValue(profile.scaling)
        layout.addRow("Scaling:", self.scaling_input)

        # DPI
        self.dpi_input = QSpinBox()
        self.dpi_input.setRange(72, 300)
        self.dpi_input.setValue(96)
        if profile:
            self.dpi_input.setValue(profile.dpi)
        layout.addRow("DPI:", self.dpi_input)

        # Buttons
        button_layout = QHBoxLayout()

        save_button = QPushButton("Save")
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #DC143C;
                color: #ffffff;
                border: 1px solid #DC143C;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #FF1744;
            }
        """)
        save_button.clicked.connect(self.accept)
        button_layout.addWidget(save_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #444444;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addRow(button_layout)

        self.setMinimumWidth(400)

    def get_profile(self) -> DisplayProfile:
        """Get the profile from the dialog inputs."""
        return DisplayProfile(
            name=self.name_input.text(),
            resolution=self.resolution_input.text(),
            refresh_rate=self.refresh_rate_input.value(),
            scaling=self.scaling_input.value(),
            dpi=self.dpi_input.value()
        )

    def validate(self) -> bool:
        """Validate the profile inputs."""
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Profile name cannot be empty")
            return False

        if not self.resolution_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Resolution cannot be empty")
            return False

        # Validate resolution format
        res_parts = self.resolution_input.text().split('x')
        if len(res_parts) != 2:
            QMessageBox.warning(self, "Validation Error", "Resolution must be in WxH format (e.g., 1920x1080)")
            return False

        try:
            int(res_parts[0])
            int(res_parts[1])
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "Resolution must contain valid numbers")
            return False

        return True

    def accept(self):
        """Accept the dialog only if validation passes."""
        if self.validate():
            super().accept()


class DisplayProfilesWidget(QWidget):
    """Display profiles management widget for Settings."""

    def __init__(self, launcher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.profile_manager = DisplayProfilesManager()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QLabel("Display Profiles")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        # Info label
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        layout.addWidget(self.info_label)

        # Current profile display
        current_layout = QHBoxLayout()
        current_layout.setSpacing(10)

        current_label = QLabel("Current Profile:")
        current_label.setStyleSheet("color: #ffffff;")
        current_layout.addWidget(current_label)

        self.current_profile_display = QLabel("None")
        self.current_profile_display.setStyleSheet("color: #FFD700; font-weight: bold;")
        current_layout.addWidget(self.current_profile_display)

        current_layout.addStretch()
        layout.addLayout(current_layout)

        # Profiles list
        self.profiles_list = QListWidget()
        self.profiles_list.setStyleSheet("""
            QListWidget {
                background-color: #1a1a1a;
                border: 1px solid #444444;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #2a2a2a;
            }
            QListWidget::item:selected {
                background-color: #333333;
            }
        """)
        self.profiles_list.setMinimumHeight(250)
        self.profiles_list.itemClicked.connect(self.on_profile_selected)
        layout.addWidget(self.profiles_list)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.apply_button = QPushButton("Apply Profile")
        self.apply_button.setEnabled(False)
        self.apply_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #444444;
            }
            QPushButton:disabled {
                color: #666666;
                background-color: #222222;
            }
        """)
        self.apply_button.clicked.connect(self.apply_selected_profile)
        button_layout.addWidget(self.apply_button)

        self.create_button = QPushButton("New Profile")
        self.create_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #444444;
            }
        """)
        self.create_button.clicked.connect(self.create_new_profile)
        button_layout.addWidget(self.create_button)

        self.save_current_button = QPushButton("Save Current as Profile")
        self.save_current_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #444444;
            }
        """)
        self.save_current_button.clicked.connect(self.save_current_display)
        button_layout.addWidget(self.save_current_button)

        button_layout.addStretch()

        self.rename_button = QPushButton("Rename")
        self.rename_button.setEnabled(False)
        self.rename_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #444444;
            }
            QPushButton:disabled {
                color: #666666;
                background-color: #222222;
            }
        """)
        self.rename_button.clicked.connect(self.rename_selected)
        button_layout.addWidget(self.rename_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setEnabled(False)
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: #8B0000;
                color: #ffffff;
                border: 1px solid #A00000;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #A00000;
            }
            QPushButton:disabled {
                color: #666666;
                background-color: #222222;
            }
        """)
        self.delete_button.clicked.connect(self.delete_selected)
        button_layout.addWidget(self.delete_button)

        layout.addLayout(button_layout)

        self.selected_profile_name = None
        self.refresh_profiles()

    def refresh_profiles(self):
        """Refresh the profiles list."""
        self.profiles_list.clear()

        profiles = self.profile_manager.get_all_profiles()
        current = self.profile_manager.get_current_profile()

        # Update info label
        count = self.profile_manager.get_profile_count()
        self.info_label.setText(f"Profiles: {count}/{self.profile_manager.MAX_PROFILES}")

        # Update current profile display
        if current:
            self.current_profile_display.setText(f"{current.name} ({current.resolution}@{current.refresh_rate}Hz)")
        else:
            self.current_profile_display.setText("None")

        # Populate list
        for profile in profiles:
            display_text = f"{profile.name}\n{profile.resolution} @ {profile.refresh_rate}Hz | {profile.scaling}% scale | {profile.dpi} DPI"
            item = QListWidgetItem(display_text, self.profiles_list)
            item.setData(Qt.ItemDataRole.UserRole, profile.name)

            # Highlight current profile
            if current and current.name == profile.name:
                item.setBackground(QColor("#333333"))
                item.setForeground(QColor("#FFD700"))

        self.selected_profile_name = None
        self.update_button_states()

    def on_profile_selected(self, item):
        """Handle profile selection."""
        self.selected_profile_name = item.data(Qt.ItemDataRole.UserRole)
        self.update_button_states()

    def update_button_states(self):
        """Update button enabled states based on selection."""
        has_selection = self.selected_profile_name is not None
        self.apply_button.setEnabled(has_selection)
        self.rename_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def create_new_profile(self):
        """Create a new display profile."""
        if not self.profile_manager.has_capacity_for_new_profile():
            QMessageBox.warning(
                self,
                "Profile Limit",
                f"Maximum number of profiles ({self.profile_manager.MAX_PROFILES}) reached"
            )
            return

        dialog = CreateEditProfileDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            profile = dialog.get_profile()
            if self.profile_manager.add_profile(profile):
                log_info(f"Profile created: {profile.name}")
                self.refresh_profiles()
            else:
                log_error(f"Failed to create profile: {profile.name}")
                QMessageBox.critical(self, "Error", "Failed to create profile. Name may already exist.")

    def apply_selected_profile(self):
        """Apply the selected display profile."""
        if self.selected_profile_name is None:
            return

        profile = self.profile_manager.get_profile(self.selected_profile_name)
        if profile is None:
            log_error("Selected profile not found")
            return

        if self.profile_manager.apply_profile(self.selected_profile_name):
            log_info(f"Applied profile: {self.selected_profile_name}")
            QMessageBox.information(
                self,
                "Profile Applied",
                f"Profile '{self.selected_profile_name}' has been applied.\n\n"
                f"Resolution: {profile.resolution}\n"
                f"Refresh Rate: {profile.refresh_rate}Hz\n"
                f"Scaling: {profile.scaling}%\n"
                f"DPI: {profile.dpi} (saved with profile; DPI changes require desktop-session support)"
            )
            self.refresh_profiles()
        else:
            log_error("Failed to apply profile")

    def save_current_display(self):
        """Save the current display settings as a new profile."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Save Current Display")
        dialog.setModal(True)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
            }
        """)

        layout = QFormLayout(dialog)

        name_input = QLineEdit()
        name_input.setPlaceholderText("Profile Name")
        layout.addRow("Name:", name_input)

        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(dialog.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)

        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addRow(button_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            profile_name = name_input.text().strip()
            if not profile_name:
                QMessageBox.warning(self, "Invalid Input", "Profile name cannot be empty")
                return

            if self.profile_manager.save_current_display_as_profile(profile_name):
                log_info(f"Saved current display as profile: {profile_name}")
                self.refresh_profiles()
            else:
                log_error("Failed to save current display")
                QMessageBox.critical(self, "Error", "Failed to save current display settings.")

    def rename_selected(self):
        """Rename the selected profile."""
        if self.selected_profile_name is None:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Rename Profile")
        dialog.setModal(True)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
            }
        """)

        layout = QFormLayout(dialog)

        name_input = QLineEdit()
        name_input.setText(self.selected_profile_name)
        layout.addRow("New Name:", name_input)

        button_layout = QHBoxLayout()
        save_button = QPushButton("Rename")
        save_button.clicked.connect(dialog.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)

        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addRow(button_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = name_input.text().strip()
            if not new_name:
                QMessageBox.warning(self, "Invalid Input", "Profile name cannot be empty")
                return

            if self.profile_manager.rename_profile(self.selected_profile_name, new_name):
                log_info(f"Renamed profile to: {new_name}")
                self.refresh_profiles()
            else:
                log_error("Failed to rename profile")
                QMessageBox.critical(self, "Error", "Failed to rename profile.")

    def delete_selected(self):
        """Delete the selected profile."""
        if self.selected_profile_name is None:
            return

        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete profile '{self.selected_profile_name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.profile_manager.delete_profile(self.selected_profile_name):
                log_info(f"Deleted profile: {self.selected_profile_name}")
                self.refresh_profiles()
            else:
                log_error("Failed to delete profile")
