"""
Notification System for Titans Launcher - Phase 2 System Integration.

Provides desktop notifications via D-Bus Notifications specification
for system events and user notifications.
"""

import logging
import os
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Callable, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from Application.core.notification_history import NotificationHistoryManager

logger = logging.getLogger(__name__)


class NotificationUrgency(Enum):
    """Notification urgency levels."""
    LOW = 0
    NORMAL = 1
    CRITICAL = 2


class NotificationCategory(Enum):
    """Notification categories."""
    DEVICE = "device"
    DEVICE_ADDED = "device.added"
    DEVICE_ERROR = "device.error"
    NETWORK = "network"
    NETWORK_CONNECTED = "network.connected"
    NETWORK_DISCONNECTED = "network.disconnected"
    BATTERY = "power"
    BATTERY_LOW = "power.battery.low"
    BATTERY_CRITICAL = "power.battery.critical"
    POWER = "power"
    DESKTOP = "im.received"
    IM_RECEIVED = "im.received"
    TRANSFER_COMPLETE = "transfer.complete"
    PRESENTATION = "presentation"
    SCREENSAVER = "screensaver"
    APP_NOTIFICATION = "app.notification"


class NotificationPreferences:
    """Persist per-user notification category preferences with private permissions."""

    def __init__(self, path: Optional[Path] = None):
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.path = path or config_home / "Titans-launcher" / "notifications.json"
        self._enabled = self._load()

    @staticmethod
    def _supported_categories():
        return {category.value for category in NotificationCategory}

    def _load(self) -> Dict[str, bool]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read notification preferences: {error}") from error
        if not isinstance(data, dict) or any(
            category not in self._supported_categories() or not isinstance(enabled, bool)
            for category, enabled in data.items()
        ):
            raise ValueError("Notification preferences contain invalid categories or values")
        return data

    def is_enabled(self, category: str) -> bool:
        if category not in self._supported_categories():
            raise ValueError(f"Unsupported notification category: {category}")
        return self._enabled.get(category, True)

    def get_preferences(self) -> Dict[str, bool]:
        return {
            category: self._enabled.get(category, True)
            for category in sorted(self._supported_categories())
        }

    def set_enabled(self, category: str, enabled: bool) -> None:
        if category not in self._supported_categories() or not isinstance(enabled, bool):
            raise ValueError("Invalid notification category preference")
        updated = {**self._enabled, category: enabled}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(json.dumps(updated, indent=2, sort_keys=True) + "\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            temporary_path.chmod(0o600)
            os.replace(temporary_path, self.path)
        except OSError:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
        self._enabled = updated


@dataclass
class Notification:
    """Represents a notification."""
    title: str
    body: str
    app_name: str = "Titans"
    urgency: NotificationUrgency = NotificationUrgency.NORMAL
    timeout: int = 5000  # milliseconds
    actions: Optional[List[Tuple[str, str]]] = None  # (action_id, label)
    hints: Optional[Dict[str, Any]] = None
    icon: Optional[str] = None
    category: Optional[NotificationCategory] = None
    id: int = 0  # Server-assigned notification ID


class NotificationManager:
    """Manages desktop notifications via D-Bus."""
    
    def __init__(
        self,
        preferences_path: Optional[Path] = None,
        history_manager: Optional[NotificationHistoryManager] = None,
    ):
        """Initialize the NotificationManager."""
        self.user_home = Path.home()
        self.config_dir = self.user_home / ".local" / "share" / "titans"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.notifications: Dict[int, Notification] = {}
        self.notification_callbacks: Dict[int, Callable] = {}
        self.next_notification_id = 1
        self.preferences = NotificationPreferences(preferences_path)
        self.history_manager = history_manager or NotificationHistoryManager()
        
        logger.info("NotificationManager initialized")
    
    def send_notification(
        self,
        title: str,
        body: str,
        app_name: str = "Titans",
        urgency: NotificationUrgency = NotificationUrgency.NORMAL,
        timeout: int = 5000,
        icon: Optional[str] = None,
        actions: Optional[List[Tuple[str, str]]] = None,
        category: Optional[NotificationCategory] = None,
    ) -> Tuple[bool, int]:
        """Send a notification.
        
        Args:
            title: Notification title
            body: Notification body/message
            app_name: Application name
            urgency: Urgency level
            timeout: Display timeout in milliseconds
            icon: Icon name or path
            actions: List of (action_id, label) tuples
            category: Notification category
        
        Returns:
            Tuple[bool, int]: (success, notification_id). A zero ID with success
            means that the category was intentionally disabled by the user.
        """
        if category is not None and not self.is_category_enabled(category.value):
            logger.info("Notification suppressed by user preference: %s", category.value)
            return True, 0
        try:
            # Build dbus-send command
            cmd = [
                "dbus-send",
                "--print-reply",
                "--dest=org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications.Notify",
                f"string:{app_name}",
                "uint32:0",  # replaces_id
                f"string:{icon or ''}",
                f"string:{title}",
                f"string:{body}",
            ]
            
            # Add actions
            if actions:
                action_list = []
                for action_id, label in actions:
                    action_list.extend([action_id, label])
                cmd.append(f"array:string:{','.join(action_list)}")
            else:
                cmd.append("array:string:")
            
            # Add hints
            hints = {}
            if urgency:
                hints["urgency"] = f"byte:{urgency.value}"
            if category:
                hints["category"] = f"string:{category.value}"
            
            hint_str = ","
            for key, value in hints.items():
                hint_str += f"{key}:{value},"
            cmd.append(f"dict:string:variant:{hint_str}")
            
            cmd.append(f"int32:{timeout}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                notification_id = self.next_notification_id
                self.next_notification_id += 1
                
                notification = Notification(
                    title=title,
                    body=body,
                    app_name=app_name,
                    urgency=urgency,
                    timeout=timeout,
                    actions=actions,
                    icon=icon,
                    category=category,
                    id=notification_id
                )
                self.notifications[notification_id] = notification
                try:
                    self.history_manager.add_notification(
                        title=title,
                        body=body,
                        category=category.value if category else "general",
                        app_name=app_name,
                    )
                except Exception:
                    logger.exception("Could not save notification %r to history", title)
                
                logger.info(f"Notification sent (ID: {notification_id}): {title}")
                return True, notification_id
            else:
                logger.error(f"Notification failed: {result.stderr}")
                return False, 0
        
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False, 0

    def is_category_enabled(self, category: str) -> bool:
        """Return whether a notification category is enabled for this user."""
        return self.preferences.is_enabled(category)

    def set_category_enabled(self, category: str, enabled: bool) -> None:
        """Persist whether a notification category should be delivered."""
        self.preferences.set_enabled(category, enabled)
    
    def close_notification(self, notification_id: int) -> Tuple[bool, str]:
        """Close a notification.
        
        Args:
            notification_id: Notification ID
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                [
                    "dbus-send",
                    "--print-reply",
                    "--dest=org.freedesktop.Notifications",
                    "/org/freedesktop/Notifications",
                    "org.freedesktop.Notifications.CloseNotification",
                    f"uint32:{notification_id}",
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                if notification_id in self.notifications:
                    del self.notifications[notification_id]
                logger.info(f"Notification closed (ID: {notification_id})")
                return True, "Notification closed"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error closing notification: {e}")
            return False, str(e)
    
    def notify_device_connected(self, device_name: str) -> Tuple[bool, int]:
        """Notify about a connected device.
        
        Args:
            device_name: Device name
        
        Returns:
            Tuple[bool, int]: (success, notification_id)
        """
        return self.send_notification(
            title="Device Connected",
            body=f"{device_name} has been connected",
            urgency=NotificationUrgency.NORMAL,
            icon="device-connected",
            category=NotificationCategory.DEVICE_ADDED,
        )
    
    def notify_device_disconnected(self, device_name: str) -> Tuple[bool, int]:
        """Notify about a disconnected device.
        
        Args:
            device_name: Device name
        
        Returns:
            Tuple[bool, int]: (success, notification_id)
        """
        return self.send_notification(
            title="Device Disconnected",
            body=f"{device_name} has been disconnected",
            urgency=NotificationUrgency.NORMAL,
            icon="device-disconnected",
            category=NotificationCategory.DEVICE,
        )
    
    def notify_network_connected(self, network_name: str) -> Tuple[bool, int]:
        """Notify about network connection.
        
        Args:
            network_name: Network name
        
        Returns:
            Tuple[bool, int]: (success, notification_id)
        """
        return self.send_notification(
            title="Connected to Network",
            body=f"Connected to {network_name}",
            urgency=NotificationUrgency.NORMAL,
            icon="network-connected",
            category=NotificationCategory.NETWORK_CONNECTED,
        )
    
    def notify_network_disconnected(self) -> Tuple[bool, int]:
        """Notify about network disconnection.
        
        Returns:
            Tuple[bool, int]: (success, notification_id)
        """
        return self.send_notification(
            title="Disconnected",
            body="Network connection lost",
            urgency=NotificationUrgency.NORMAL,
            icon="network-disconnected",
            category=NotificationCategory.NETWORK_DISCONNECTED,
        )
    
    def notify_battery_low(self, percentage: int) -> Tuple[bool, int]:
        """Notify about low battery.
        
        Args:
            percentage: Battery percentage
        
        Returns:
            Tuple[bool, int]: (success, notification_id)
        """
        return self.send_notification(
            title="Low Battery",
            body=f"Battery level is {percentage}%",
            urgency=NotificationUrgency.NORMAL,
            icon="battery-low",
            category=NotificationCategory.BATTERY_LOW,
        )
    
    def notify_battery_critical(self, percentage: int) -> Tuple[bool, int]:
        """Notify about critical battery.
        
        Args:
            percentage: Battery percentage
        
        Returns:
            Tuple[bool, int]: (success, notification_id)
        """
        return self.send_notification(
            title="Critical Battery",
            body=f"Battery level is {percentage}%. Please save your work.",
            urgency=NotificationUrgency.CRITICAL,
            icon="battery-critical",
            category=NotificationCategory.BATTERY_CRITICAL,
            timeout=0,  # Don't auto-dismiss
        )
    
    def notify_app_crash(self, app_name: str) -> Tuple[bool, int]:
        """Notify about app crash.
        
        Args:
            app_name: Application name
        
        Returns:
            Tuple[bool, int]: (success, notification_id)
        """
        return self.send_notification(
            title="Application Crashed",
            body=f"{app_name} has crashed unexpectedly",
            urgency=NotificationUrgency.CRITICAL,
            icon="application-crash",
            category=NotificationCategory.DEVICE_ERROR,
        )
    
    def notify_system_error(self, error_message: str) -> Tuple[bool, int]:
        """Notify about system error.
        
        Args:
            error_message: Error message
        
        Returns:
            Tuple[bool, int]: (success, notification_id)
        """
        return self.send_notification(
            title="System Error",
            body=error_message,
            urgency=NotificationUrgency.CRITICAL,
            icon="dialog-error",
            category=NotificationCategory.DEVICE_ERROR,
        )
    
    def notify_transfer_complete(self, transfer_name: str) -> Tuple[bool, int]:
        """Notify about transfer completion.
        
        Args:
            transfer_name: Transfer name
        
        Returns:
            Tuple[bool, int]: (success, notification_id)
        """
        return self.send_notification(
            title="Transfer Complete",
            body=f"{transfer_name} has completed",
            urgency=NotificationUrgency.NORMAL,
            icon="transfer-complete",
            category=NotificationCategory.TRANSFER_COMPLETE,
        )
    
    def get_notification_capabilities(self) -> Tuple[bool, List[str]]:
        """Get supported notification capabilities.
        
        Returns:
            Tuple[bool, List[str]]: (success, capabilities)
        """
        try:
            result = subprocess.run(
                [
                    "dbus-send",
                    "--print-reply",
                    "--dest=org.freedesktop.Notifications",
                    "/org/freedesktop/Notifications",
                    "org.freedesktop.Notifications.GetCapabilities",
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Parse capabilities from output
                capabilities = []
                for line in result.stdout.split("\n"):
                    if "string" in line:
                        parts = line.split('"')
                        if len(parts) >= 2:
                            capabilities.append(parts[1])
                return True, capabilities
            
            return False, []
        
        except Exception as e:
            logger.error(f"Error getting capabilities: {e}")
            return False, []
    
    def get_server_info(self) -> Tuple[bool, Dict[str, str]]:
        """Get notification server information.
        
        Returns:
            Tuple[bool, Dict[str, str]]: (success, info)
        """
        try:
            result = subprocess.run(
                [
                    "dbus-send",
                    "--print-reply",
                    "--dest=org.freedesktop.Notifications",
                    "/org/freedesktop/Notifications",
                    "org.freedesktop.Notifications.GetServerInformation",
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                info = {}
                lines = result.stdout.split("\n")
                if len(lines) >= 4:
                    info["name"] = lines[0].strip()
                    info["vendor"] = lines[1].strip()
                    info["version"] = lines[2].strip()
                return True, info
            
            return False, {}
        
        except Exception as e:
            logger.error(f"Error getting server info: {e}")
            return False, {}
    
    def get_notification_status(self) -> Dict[str, Any]:
        """Get notification system status.
        
        Returns:
            Dict[str, Any]: Status information
        """
        _, capabilities = self.get_notification_capabilities()
        _, info = self.get_server_info()
        
        return {
            "active_notifications": len(self.notifications),
            "supported_capabilities": capabilities,
            "server_info": info,
            "notification_ids": list(self.notifications.keys()),
        }
