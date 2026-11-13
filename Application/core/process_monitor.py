"""
Process Monitor for Titans Launcher - KDE Independence Phase 0.

Monitors the Titans Launcher process for crashes, hangs, and other failures.
Integrates with systemd for automatic restart and recovery management.
"""

import logging
import os
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ProcessMonitor:
    """Monitors Titans Launcher process health and crash recovery."""

    def __init__(self):
        """Initialize the ProcessMonitor."""
        self.user_home = Path.home()
        self.monitor_dir = self.user_home / ".local" / "share" / "titans"
        self.monitor_dir.mkdir(parents=True, exist_ok=True)
        
        self.heartbeat_file = self.monitor_dir / "heartbeat"
        self.crash_log_file = self.monitor_dir / "logs" / "crashes.log"
        self.crash_log_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file = self.monitor_dir / "monitor_state.json"
        
        self.is_running = True
        self.last_heartbeat = time.time()
        self.heartbeat_timeout = 5.0  # seconds
        self.crash_history = self._load_crash_history()
        self._stale_incident_active = False
        self._recovery_attempted = False
        
        logger.info("ProcessMonitor initialized")

    def _load_crash_history(self) -> Dict[str, Any]:
        """Load crash history from previous runs.
        
        Returns:
            Dict[str, Any]: Crash history data
        """
        try:
            if self.state_file.exists():
                return json.loads(self.state_file.read_text())
        except Exception as e:
            logger.error(f"Failed to load crash history: {e}")
        
        return {
            "crashes": [],
            "last_crash": None,
            "total_crashes": 0,
        }

    def _save_crash_history(self) -> None:
        """Save crash history to file."""
        try:
            self.state_file.write_text(json.dumps(self.crash_history, indent=2))
        except Exception as e:
            logger.error(f"Failed to save crash history: {e}")

    def update_heartbeat(self, timestamp: Optional[float] = None) -> None:
        """Update the heartbeat timestamp.
        
        Args:
            timestamp: Optional timestamp (defaults to current time)
        """
        try:
            ts = timestamp or time.time()
            self.heartbeat_file.write_text(str(ts))
            self.last_heartbeat = ts
        except Exception as e:
            logger.error(f"Failed to update heartbeat: {e}")

    def get_heartbeat_age(self) -> float:
        """Get the age of the last heartbeat in seconds.
        
        Returns:
            float: Age in seconds, or -1 if no heartbeat exists
        """
        try:
            if not self.heartbeat_file.exists():
                return -1
            
            last_ts = float(self.heartbeat_file.read_text().strip())
            return time.time() - last_ts
        except Exception as e:
            logger.error(f"Failed to get heartbeat age: {e}")
            return -1

    def is_responsive(self) -> bool:
        """Check if Titans process is responsive.
        
        Returns:
            bool: True if recent heartbeat exists
        """
        age = self.get_heartbeat_age()
        return 0 <= age < self.heartbeat_timeout

    def detect_crash(self) -> bool:
        """Detect if a crash has occurred.
        
        A crash is detected if the heartbeat is stale (no update for timeout period).
        
        Returns:
            bool: True if crash detected
        """
        age = self.get_heartbeat_age()
        
        if age < 0:
            # No heartbeat file - possible first run
            return False

        if age >= self.heartbeat_timeout:
            # Heartbeat is stale - crash detected
            return True
        
        return False

    def _record_stale_incident_once(self) -> None:
        """Record one crash for each stale-heartbeat period."""
        age = self.get_heartbeat_age()
        stale = age >= self.heartbeat_timeout
        if not stale:
            self._stale_incident_active = False
            return
        if not self._stale_incident_active:
            self.record_crash("Process not responsive")
            self._stale_incident_active = True

    def record_crash(self, crash_reason: str = "Unknown") -> None:
        """Record a crash event.
        
        Args:
            crash_reason: Description of crash reason
        """
        try:
            crash_info = {
                "timestamp": datetime.now().isoformat(),
                "reason": crash_reason,
                "pid": os.getpid(),
            }
            
            self.crash_history["crashes"].append(crash_info)
            self.crash_history["last_crash"] = crash_info["timestamp"]
            self.crash_history["total_crashes"] += 1
            
            # Keep only last 100 crashes
            if len(self.crash_history["crashes"]) > 100:
                self.crash_history["crashes"] = self.crash_history["crashes"][-100:]
            
            # Log to file
            with open(self.crash_log_file, "a") as f:
                f.write(f"{crash_info['timestamp']} - {crash_reason}\n")
            
            self._save_crash_history()
            logger.warning(f"Crash recorded: {crash_reason}")
        
        except Exception as e:
            logger.error(f"Failed to record crash: {e}")

    def count_recent_crashes(self, seconds: int = 30) -> int:
        """Count crashes in the last N seconds.
        
        Args:
            seconds: Time window in seconds
        
        Returns:
            int: Number of crashes in window
        """
        cutoff = datetime.now() - timedelta(seconds=seconds)
        cutoff_iso = cutoff.isoformat()
        
        count = 0
        for crash in self.crash_history["crashes"]:
            if crash["timestamp"] > cutoff_iso:
                count += 1
        
        return count

    def should_trigger_recovery(self) -> bool:
        """Determine if recovery manager should be triggered.
        
        Recovery is triggered if:
        - 3+ crashes in last 30 seconds, OR
        - Process not responsive for >10 seconds
        
        Returns:
            bool: True if recovery should be triggered
        """
        # Check for repeated crashes
        recent_crashes = self.count_recent_crashes(seconds=30)
        if recent_crashes >= 3:
            logger.warning(f"Recovery triggered: {recent_crashes} crashes in 30s")
            return True
        
        # Check for hang
        age = self.get_heartbeat_age()
        if age > 10.0:
            logger.warning(f"Recovery triggered: Heartbeat stale for {age:.1f}s")
            return True
        
        return False

    def start_monitoring(self, check_interval: float = 2.0) -> None:
        """Start monitoring loop (blocking).
        
        Args:
            check_interval: Seconds between checks
        """
        logger.info("ProcessMonitor starting monitoring loop")
        
        try:
            while self.is_running:
                time.sleep(check_interval)
                
                self._record_stale_incident_once()
                
                if self.should_trigger_recovery():
                    logger.critical("Recovery conditions met")
                    self._trigger_recovery()
                    self.is_running = False
        
        except KeyboardInterrupt:
            logger.info("ProcessMonitor interrupted")
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
        finally:
            self.is_running = False

    def _trigger_recovery(self) -> None:
        """Trigger the recovery manager to activate KDE fallback."""
        if self._recovery_attempted:
            return
        self._recovery_attempted = True
        try:
            from Application.core.recovery_manager import RecoveryManager
            recovery = RecoveryManager()
            if recovery.is_recovery_active():
                logger.warning("Recovery is already active; not triggering it again")
                return
            success, message = recovery.activate_recovery("Repeated launcher failure")
            if not success:
                logger.error("Recovery activation failed: %s", message)
        except Exception as e:
            logger.error(f"Failed to trigger recovery: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current monitor status.
        
        Returns:
            Dict[str, Any]: Status information
        """
        return {
            "is_responsive": self.is_responsive(),
            "heartbeat_age": self.get_heartbeat_age(),
            "recent_crashes": self.count_recent_crashes(30),
            "total_crashes": self.crash_history["total_crashes"],
            "last_crash": self.crash_history["last_crash"],
            "should_recover": self.should_trigger_recovery(),
        }

    def stop(self) -> None:
        """Stop monitoring."""
        self.is_running = False
        logger.info("ProcessMonitor stopped")


def run_monitor():
    """Entry point for process monitor daemon."""
    import logging.config
    
    # Configure logging
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
        },
        "handlers": {
            "default": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "standard",
            },
            "file": {
                "level": "DEBUG",
                "class": "logging.FileHandler",
                "filename": str(Path.home() / ".local/share/titans/logs/monitor.log"),
                "formatter": "standard",
            },
        },
        "loggers": {
            "": {
                "handlers": ["default", "file"],
                "level": "INFO",
                "propagate": True,
            }
        }
    }
    
    logging.config.dictConfig(log_config)
    
    monitor = ProcessMonitor()
    monitor.start_monitoring()


if __name__ == "__main__":
    run_monitor()
