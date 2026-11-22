"""Sudo credential caching to reduce repeated password prompts.

Features:
- In-memory password storage with TTL
- User opt-in with "Remember password" checkbox
- Automatic timeout and clearing
- Secure handling with no disk persistence
"""

import time
from typing import Optional, Tuple

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QMessageBox
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from Application.core.privilege_manager import get_privilege_manager
from Application.ui.Settings.Logger import log_info, log_warning


class CredentialCacheDialog(QDialog):
    """Dialog for requesting sudo password with optional caching."""

    def __init__(self, parent=None, ttl_minutes: int = 15):
        super().__init__(parent)
        self.setWindowTitle("Authenticate")
        self.setModal(True)
        self.setFixedWidth(400)
        self.password = None
        self.cache_enabled = False
        self.ttl_minutes = ttl_minutes

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("This operation requires administrator privileges")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(title)

        # Description
        desc = QLabel("Enter your password to continue:")
        layout.addWidget(desc)

        # Password input
        layout.addWidget(QLabel("Password:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter password")
        layout.addWidget(self.password_input)

        # Remember checkbox
        self.remember_checkbox = QCheckBox(
            f"Remember for {ttl_minutes} minutes"
        )
        self.remember_checkbox.setStyleSheet("margin-top: 10px;")
        layout.addWidget(self.remember_checkbox)

        # Buttons
        button_layout = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button = QPushButton("Authenticate")
        self.ok_button.clicked.connect(self._on_ok)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        layout.addLayout(button_layout)

        # Focus password field
        self.password_input.setFocus()

    def _on_ok(self):
        """Handle OK button click."""
        self.password = self.password_input.text()
        self.cache_enabled = self.remember_checkbox.isChecked()
        self.accept()

    def get_result(self) -> Tuple[Optional[str], bool]:
        """Get password and cache preference."""
        return self.password, self.cache_enabled


class SudoCredentialCache:
    """Manages cached sudo credentials with TTL."""

    def __init__(self, ttl_minutes: int = 15, default_enabled: bool = False):
        self.ttl_seconds = ttl_minutes * 60
        self.default_enabled = default_enabled

        self._cached_password: Optional[str] = None
        self._cache_time: Optional[float] = None
        self._cache_enabled = False

        # Cleanup timer (check every minute)
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._cleanup_expired)
        self.cleanup_timer.start(60000)

        log_info(f"SudoCredentialCache initialized (TTL: {ttl_minutes}m, enabled: {default_enabled})")

    def is_cached(self) -> bool:
        """Check if password is cached and still valid."""
        if not self._cached_password or not self._cache_time:
            return False

        elapsed = time.time() - self._cache_time
        if elapsed > self.ttl_seconds:
            self._clear_cache()
            return False

        return True

    def get_cached_password(self) -> Optional[str]:
        """Get cached password if available and valid."""
        if self.is_cached():
            return self._cached_password
        return None

    def request_password(self, parent=None) -> Tuple[Optional[str], bool]:
        """Show dialog to request password from user.

        Returns:
            Tuple of (password, should_cache)
        """
        dialog = CredentialCacheDialog(parent, ttl_minutes=self.ttl_seconds // 60)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            password, cache = dialog.get_result()
            if cache:
                self._cache_password(password)
            return password, cache
        return None, False

    def execute_with_cache(
        self,
        command: list,
        parent=None,
        timeout: Optional[int] = None,
    ) -> Tuple[int, str, str]:
        """Execute command with cached password or request new one.

        Args:
            command: Command to execute (without sudo prefix)
            parent: Parent widget for dialog
            timeout: Command timeout in seconds

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        manager = get_privilege_manager()

        # Try cached password first
        password = self.get_cached_password()
        if password:
            log_info("Using cached sudo password")
            return_code, stdout, stderr = manager.execute(
                command, input_text=password + "\n", timeout=timeout
            )
            # If auth succeeded, cache is valid
            if return_code == 0:
                return return_code, stdout, stderr
            else:
                # Auth failed, clear cache
                self._clear_cache()
                log_warning("Cached password failed, requesting new password")

        # Request password from user
        password, should_cache = self.request_password(parent)
        if not password:
            return 1, "", "Authentication cancelled"

        # Execute with password
        return_code, stdout, stderr = manager.execute(
            command, input_text=password + "\n", timeout=timeout
        )

        # On success, update cache if requested
        if return_code == 0 and should_cache:
            self._cache_password(password)

        return return_code, stdout, stderr

    def _cache_password(self, password: str):
        """Cache password for TTL period."""
        self._cached_password = password
        self._cache_time = time.time()
        self._cache_enabled = True
        log_info(f"Password cached for {self.ttl_seconds}s")

    def _clear_cache(self):
        """Clear cached password immediately."""
        self._cached_password = None
        self._cache_time = None
        self._cache_enabled = False
        log_info("Credential cache cleared")

    def _cleanup_expired(self):
        """Timer callback to clean up expired cache."""
        if self.is_cached():
            # Cache still valid
            elapsed = time.time() - self._cache_time
            remaining = self.ttl_seconds - elapsed
            # Cleanup check runs every minute, so this is periodic
        else:
            # Cache expired, clear it
            if self._cached_password:
                self._clear_cache()

    def clear_all(self):
        """Explicitly clear all cached credentials."""
        self._clear_cache()
        log_info("All credentials cleared by user request")

    def destroy(self):
        """Clean up resources on app exit."""
        self.cleanup_timer.stop()
        self._clear_cache()
        log_info("SudoCredentialCache destroyed, credentials cleared")


# Global singleton instance
_credential_cache = None


def get_credential_cache(ttl_minutes: int = 15) -> SudoCredentialCache:
    """Get or create the global SudoCredentialCache instance."""
    global _credential_cache
    if _credential_cache is None:
        _credential_cache = SudoCredentialCache(ttl_minutes=ttl_minutes)
    return _credential_cache
