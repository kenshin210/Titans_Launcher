"""
App Switcher UI Component for Titans Launcher - Phase 1.

Provides visual interface for switching between running applications,
displaying open apps, and managing app lifecycle from the UI.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QPushButton,
    QLabel, QGridLayout, QFrame, QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont, QIcon
import logging
import uuid
from typing import Optional, List, Dict
from pathlib import Path

from Application.core.application_manager import ApplicationManager, AppInfo

logger = logging.getLogger(__name__)


class AppButton(QPushButton):
    """Button representing a single running application."""
    
    def __init__(self, app_info: AppInfo, parent=None):
        super().__init__(parent)
        self.app_info = app_info
        
        self.setStyleSheet("""
            QPushButton {
                background-color: #2b2b2b;
                color: white;
                border: 2px solid #444;
                border-radius: 8px;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 2px solid #666;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
                border: 2px solid #888;
            }
        """)
        
        self.setText(app_info.name)
        self.setMinimumHeight(80)
        self.setMinimumWidth(150)
        
        # Show app state in tooltip
        self.update_info(app_info)
    
    def update_info(self, app_info: AppInfo) -> None:
        """Update button with new app info."""
        self.app_info = app_info
        
        # Add state indicator
        state_color = self._get_state_color(app_info.state)
        state_text = f"{app_info.name}\n({app_info.state})"
        self.setText(state_text)
        
        # Update stylesheet with state color
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #2b2b2b;
                color: white;
                border: 3px solid {state_color};
                border-radius: 8px;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3a3a3a;
                border: 3px solid {state_color};
            }}
            QPushButton:pressed {{
                background-color: #1a1a1a;
                border: 3px solid {state_color};
            }}
        """)
    
    @staticmethod
    def _get_state_color(state: str) -> str:
        """Get border color based on app state."""
        colors = {
            "running": "#00dd00",      # Green
            "starting": "#ffff00",     # Yellow
            "crashed": "#ff0000",      # Red
            "hung": "#ff6600",         # Orange
            "stopped": "#666666",      # Gray
        }
        return colors.get(state, "#666666")


class AppSwitcherWidget(QWidget):
    """Widget for switching between running applications."""
    
    app_selected = pyqtSignal(str)  # Emits app_id
    app_terminated = pyqtSignal(str)  # Emits app_id
    app_launched = pyqtSignal(str)  # Emits app_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app_manager = ApplicationManager()
        self.app_buttons: Dict[str, AppButton] = {}
        self.selected_app_id: Optional[str] = None
        
        # Start update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_app_display)
        self.update_timer.start(2000)  # Update every 2 seconds
        
        self.initUI()
        self.update_app_display()
        logger.info("AppSwitcherWidget initialized")
    
    def initUI(self) -> None:
        """Initialize the UI."""
        main_layout = QVBoxLayout()
        
        # Title
        title = QLabel("Running Applications")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        main_layout.addWidget(title)

        launch_layout = QHBoxLayout()
        self.app_name_input = QLineEdit()
        self.app_name_input.setPlaceholderText("Application name")
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Command and arguments")
        self.command_input.returnPressed.connect(self.launch_application)
        self.launch_btn = QPushButton("Launch")
        self.launch_btn.clicked.connect(self.launch_application)
        launch_layout.addWidget(self.app_name_input)
        launch_layout.addWidget(self.command_input, stretch=1)
        launch_layout.addWidget(self.launch_btn)
        main_layout.addLayout(launch_layout)
        
        # Scroll area for app buttons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        self.app_container = QWidget()
        self.app_grid = QGridLayout()
        self.app_grid.setSpacing(10)
        self.app_grid.setContentsMargins(5, 5, 5, 5)
        self.app_container.setLayout(self.app_grid)
        
        scroll.setWidget(self.app_container)
        main_layout.addWidget(scroll)
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.update_app_display)
        control_layout.addWidget(self.refresh_btn)
        
        self.close_app_btn = QPushButton("Close Selected")
        self.close_app_btn.clicked.connect(self.close_selected_app)
        self.close_app_btn.setEnabled(False)
        control_layout.addWidget(self.close_app_btn)
        
        main_layout.addLayout(control_layout)
        
        self.setLayout(main_layout)
        
        # Apply stylesheet
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                color: white;
            }
            QPushButton {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
            QLabel {
                color: white;
            }
            QScrollArea {
                background-color: #1a1a1a;
                border: 1px solid #444;
            }
        """)
    
    def update_app_display(self) -> None:
        """Update the display with current running apps."""
        try:
            for app_id, app in self.app_manager.get_all_apps().items():
                if app.state == "running":
                    self.app_manager.check_app_health(app_id)
            running_apps = self.app_manager.get_running_apps()
            all_apps = self.app_manager.get_all_apps()

            old_buttons = self.app_buttons
            while self.app_grid.count() > 0:
                item = self.app_grid.takeAt(0)
                widget = item.widget()
                if widget is not None and widget not in old_buttons.values():
                    widget.deleteLater()

            if not all_apps:
                empty_label = QLabel("No applications")
                self.app_grid.addWidget(empty_label)
                for button in old_buttons.values():
                    button.deleteLater()
                self.app_buttons = {}
                self.selected_app_id = None
                self.close_app_btn.setEnabled(False)
                return

            self.app_buttons = {}
            row = 0
            col = 0
            for app_id, app_info in all_apps.items():
                button = old_buttons.get(app_id)
                if button is None:
                    button = AppButton(app_info)
                    button.clicked.connect(lambda checked, aid=app_id: self._on_app_selected(aid))
                elif button.app_info != app_info:
                    button.update_info(app_info)
                self.app_buttons[app_id] = button
                self.app_grid.addWidget(button, row, col)

                col += 1
                if col >= 3:  # 3 columns
                    col = 0
                    row += 1
            for app_id, button in old_buttons.items():
                if app_id not in all_apps:
                    button.deleteLater()
                    if self.selected_app_id == app_id:
                        self.selected_app_id = None
            self.app_grid.setRowStretch(row, 1)
            self.app_grid.setColumnStretch(3, 1)

            selected = self.app_manager.get_app_info(self.selected_app_id) if self.selected_app_id else None
            self.close_app_btn.setEnabled(bool(selected and selected.state == "running"))
        
        except Exception as e:
            logger.error(f"Error updating app display: {e}")
    
    def _on_app_selected(self, app_id: str) -> None:
        """Handle app selection."""
        app_info = self.app_manager.get_app_info(app_id)
        if app_info:
            self.selected_app_id = app_id
            self.close_app_btn.setEnabled(app_info.state == "running")
            logger.info(f"App selected: {app_info.name}")
            self.app_selected.emit(app_id)
    
    def launch_application(self) -> None:
        """Launch a named application using an argument-parsed, non-shell command."""
        name = self.app_name_input.text().strip()
        command = self.command_input.text().strip()
        if not name or not command:
            QMessageBox.warning(self, "Launch Application", "Enter an application name and command.")
            return
        app_id = f"app-{uuid.uuid4().hex}"
        success, message, _pid = self.app_manager.launch_app(app_id, name, command)
        if not success:
            QMessageBox.warning(self, "Launch Failed", message)
            return
        self.app_name_input.clear()
        self.command_input.clear()
        self.selected_app_id = app_id
        self.app_launched.emit(app_id)
        self.update_app_display()

    def close_selected_app(self) -> None:
        """Close the currently selected app."""
        if self.selected_app_id:
            self._terminate_app(self.selected_app_id)
    
    def _terminate_app(self, app_id: str) -> None:
        """Terminate an application."""
        app_info = self.app_manager.get_app_info(app_id)
        if not app_info:
            return
        
        # Confirm termination
        reply = QMessageBox.question(
            self,
            "Close Application",
            f"Close {app_info.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success, msg = self.app_manager.terminate_app(app_id)
            if success:
                logger.info(f"Terminated: {app_info.name}")
                self.app_terminated.emit(app_id)
                self.selected_app_id = None
                self.update_app_display()
            else:
                QMessageBox.warning(self, "Error", msg)
    
    def closeEvent(self, event):
        """Clean up when widget closes."""
        self.update_timer.stop()
        super().closeEvent(event)


class AppLauncherDialog(QWidget):
    """Dialog for launching new applications."""
    
    app_launched = pyqtSignal(str)  # Emits app_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app_manager = ApplicationManager()
        self.initUI()
        logger.info("AppLauncherDialog initialized")
    
    def initUI(self) -> None:
        """Initialize the UI."""
        layout = QVBoxLayout()
        
        title = QLabel("Launch Application")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Instructions
        info = QLabel(
            "Enter application command to launch.\n"
            "Applications will be monitored and isolated from Titans."
        )
        layout.addWidget(info)
        
        self.setLayout(layout)
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                color: white;
            }
            QLabel {
                color: white;
            }
        """)
    
    def launch_app(
        self,
        app_id: str,
        name: str,
        command: str,
        working_dir: Optional[str] = None
    ) -> bool:
        """Launch an application.
        
        Args:
            app_id: Unique app identifier
            name: Display name
            command: Command to execute
            working_dir: Working directory
        
        Returns:
            bool: Success status
        """
        success, msg, pid = self.app_manager.launch_app(
            app_id, name, command, working_dir
        )
        
        if success:
            logger.info(f"Launched app: {name} (PID: {pid})")
            self.app_launched.emit(app_id)
        else:
            logger.error(f"Failed to launch app: {msg}")
        
        return success
