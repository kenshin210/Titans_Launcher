"""
Recovery Manager for Titans Launcher - KDE Independence Phase 0.

Handles fallback to KDE Plasma when Titans encounters unrecoverable errors.
Manages recovery state and provides recovery UI integration.
"""

import logging
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class RecoveryManager:
    """Manages recovery fallback to KDE Plasma."""

    def __init__(self):
        """Initialize the RecoveryManager."""
        self.user_home = Path.home()
        self.recovery_dir = self.user_home / ".local" / "share" / "titans"
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        
        self.recovery_state_file = self.recovery_dir / "recovery_state.json"
        self.recovery_log_file = self.recovery_dir / "logs" / "recovery.log"
        self.recovery_log_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._initialize_recovery_state()
        logger.info("RecoveryManager initialized")

    def _initialize_recovery_state(self) -> None:
        """Initialize recovery state file if it doesn't exist."""
        if not self.recovery_state_file.exists():
            state = {
                "recovery_active": False,
                "recovery_timestamp": None,
                "recovery_reason": None,
                "restart_attempts": 0,
                "last_recovery": None,
            }
            self._save_recovery_state(state)

    def _load_recovery_state(self) -> Dict[str, Any]:
        """Load current recovery state.
        
        Returns:
            Dict[str, Any]: Recovery state data
        """
        try:
            if self.recovery_state_file.exists():
                return json.loads(self.recovery_state_file.read_text())
        except Exception as e:
            logger.error(f"Failed to load recovery state: {e}")
        
        return {
            "recovery_active": False,
            "recovery_timestamp": None,
            "recovery_reason": None,
            "restart_attempts": 0,
            "last_recovery": None,
        }

    def _save_recovery_state(self, state: Dict[str, Any]) -> None:
        """Save recovery state to file.
        
        Args:
            state: State dictionary to save
        """
        try:
            self.recovery_state_file.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.error(f"Failed to save recovery state: {e}")

    def is_recovery_active(self) -> bool:
        """Check if recovery mode is currently active.
        
        Returns:
            bool: True if recovery active
        """
        state = self._load_recovery_state()
        return state.get("recovery_active", False)

    def activate_recovery(self, reason: str = "Unknown error") -> Tuple[bool, str]:
        """Activate recovery mode and fallback to KDE Plasma.
        
        Args:
            reason: Description of why recovery was triggered
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        logger.critical(f"Activating recovery: {reason}")
        
        try:
            # Update recovery state
            state = self._load_recovery_state()
            state["recovery_active"] = True
            state["recovery_timestamp"] = datetime.now().isoformat()
            state["recovery_reason"] = reason
            state["restart_attempts"] = 0
            state["last_recovery"] = datetime.now().isoformat()
            self._save_recovery_state(state)
            
            # Log to recovery log
            with open(self.recovery_log_file, "a") as f:
                f.write(f"{state['recovery_timestamp']} - {reason}\n")
            
            # Stop Titans session
            logger.info("Stopping Titans session...")
            stopped = subprocess.run(
                ["systemctl", "--user", "stop", "titans-session.target"],
                timeout=10,
                capture_output=True,
                text=True,
                check=False,
            )
            if stopped.returncode != 0:
                detail = stopped.stderr.strip() or "systemctl could not stop the Titans session"
                logger.error("Failed to stop Titans session: %s", detail)
                return False, f"Could not stop Titans session: {detail}"
            
            # Start KDE Plasma
            logger.info("Starting KDE Plasma fallback...")
            success, message = self._start_kde_plasma()
            if not success:
                return False, message
            return True, f"Recovery activated: {reason}"
        
        except subprocess.TimeoutExpired:
            logger.error("Timeout during recovery activation")
            return False, "Timeout during recovery"
        except Exception as e:
            logger.error(f"Error during recovery activation: {e}")
            return False, str(e)

    def _start_kde_plasma(self) -> Tuple[bool, str]:
        """Start KDE Plasma through the current user's systemd manager."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "start", "plasma-workspace.target"],
                timeout=10,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                logger.info("KDE Plasma started via systemd")
                return True, "KDE Plasma started"
            detail = result.stderr.strip()
            if not detail:
                detail = "systemd could not start plasma-workspace.target"
            logger.error("KDE Plasma fallback failed: %s", detail)
            return False, f"KDE Plasma fallback failed: {detail}"
        except subprocess.TimeoutExpired:
            logger.error("Timeout starting KDE Plasma")
            return False, "Timeout starting KDE Plasma"
        except Exception as e:
            logger.error(f"Failed to start KDE Plasma: {e}")
            return False, f"Failed to start KDE Plasma: {e}"

    def deactivate_recovery(self) -> Tuple[bool, str]:
        """Deactivate recovery mode and return to normal operation.
        
        Called when user restarts Titans from recovery UI.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        logger.info("Deactivating recovery mode")
        
        try:
            # Start Titans session
            logger.info("Restarting Titans session...")
            result = subprocess.run(
                ["systemctl", "--user", "start", "titans-session.target"],
                timeout=10,
                capture_output=True,
                text=True,
                check=False,
            )
            
            if result.returncode == 0:
                state = self._load_recovery_state()
                state["recovery_active"] = False
                state["restart_attempts"] = 0
                self._save_recovery_state(state)
                logger.info("Titans session restarted successfully")
                return True, "Recovery deactivated, Titans restarted"
            else:
                detail = result.stderr.strip() or "systemctl could not start the Titans session"
                logger.error(f"Failed to restart Titans: {detail}")
                return False, f"Failed to restart: {detail}"
        
        except subprocess.TimeoutExpired:
            logger.error("Timeout restarting Titans")
            return False, "Timeout during restart"
        except Exception as e:
            logger.error(f"Error deactivating recovery: {e}")
            return False, str(e)

    def get_recovery_info(self) -> Dict[str, Any]:
        """Get current recovery information.
        
        Returns:
            Dict[str, Any]: Recovery state and details
        """
        state = self._load_recovery_state()
        
        # Read crash log
        crash_log_file = self.recovery_dir / "logs" / "crashes.log"
        crash_logs = []
        if crash_log_file.exists():
            crash_logs = crash_log_file.read_text().strip().split("\n")[-10:]  # Last 10
        
        return {
            "is_active": state["recovery_active"],
            "reason": state["recovery_reason"],
            "timestamp": state["recovery_timestamp"],
            "last_recovery": state["last_recovery"],
            "recent_crashes": crash_logs,
        }

    def clear_recovery_state(self) -> None:
        """Clear all recovery state.
        
        Called after successful return to Titans.
        """
        state = {
            "recovery_active": False,
            "recovery_timestamp": None,
            "recovery_reason": None,
            "restart_attempts": 0,
            "last_recovery": None,
        }
        self._save_recovery_state(state)
        logger.info("Recovery state cleared")


class RecoveryUI:
    """Helper class for recovery UI integration with KDE Plasma."""

    @staticmethod
    def show_recovery_notification() -> None:
        """Show notification in KDE that recovery has been activated."""
        try:
            recovery = RecoveryManager()
            info = recovery.get_recovery_info()
            
            message = f"Titans recovered from crash: {info.get('reason', 'Unknown')}"
            
            # Use D-Bus to show notification
            result = subprocess.run(
                ["notify-send", "-u", "critical", "Titans Launcher", message],
                timeout=5,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                logger.warning(
                    "Recovery notification failed: %s",
                    result.stderr.strip() or "notify-send returned an error",
                )
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")

    @staticmethod
    def get_recovery_status() -> Dict[str, Any]:
        """Get recovery status for UI display.
        
        Returns:
            Dict[str, Any]: Status info for recovery screen
        """
        recovery = RecoveryManager()
        return recovery.get_recovery_info()

    @staticmethod
    def restart_titans() -> Tuple[bool, str]:
        """Restart Titans from recovery mode.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        recovery = RecoveryManager()
        return recovery.deactivate_recovery()

    @staticmethod
    def view_crash_details() -> str:
        """Get detailed crash information for display.
        
        Returns:
            str: Formatted crash details
        """
        recovery = RecoveryManager()
        info = recovery.get_recovery_info()
        
        details = f"""
Titans Recovery Status
======================

Status: {'ACTIVE' if info['is_active'] else 'Inactive'}
Reason: {info['reason']}
Time: {info['timestamp']}

Recent Crashes:
{chr(10).join(info['recent_crashes'])}

Actions:
- [Restart Titans] - Try running Titans again
- [View Logs] - See detailed error logs
- [Exit to KDE] - Stay in KDE Plasma
"""
        return details


def run_recovery_ui():
    """Show the recovery notification from the fallback desktop session."""
    try:
        RecoveryUI.show_recovery_notification()
    except Exception as e:
        logger.error(f"Failed to run recovery UI: {e}")


if __name__ == "__main__":
    run_recovery_ui()
