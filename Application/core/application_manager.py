"""
Application Manager for Titans Launcher - KDE Independence Phase 1.

Manages multiple concurrent applications, including launch, lifecycle tracking,
crash isolation, and app switching UI integration.
"""

import logging
import os
import re
import shlex
import subprocess
import tempfile
import time
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Sequence, Union
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

_VALID_APP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class AppState(Enum):
    """Application lifecycle states."""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"
    HUNG = "hung"


@dataclass
class AppInfo:
    """Information about a managed application."""
    app_id: str
    name: str
    command: str
    working_dir: Optional[str] = None
    environment: Optional[Dict[str, str]] = None
    pid: Optional[int] = None
    state: str = AppState.IDLE.value
    launched_at: Optional[str] = None
    terminated_at: Optional[str] = None
    crashes: int = 0
    heartbeat_file: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class ApplicationManager:
    """Manages application lifecycle and multi-app support."""

    def __init__(self):
        """Initialize the ApplicationManager."""
        self.user_home = Path.home()
        self.apps_dir = self.user_home / ".local" / "share" / "titans" / "apps"
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = self.apps_dir / "apps_state.json"
        self.log_dir = self.user_home / ".local" / "share" / "titans" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.running_apps: Dict[str, AppInfo] = {}
        self._processes: Dict[str, subprocess.Popen] = {}
        self.max_concurrent_apps = 5
        self.app_check_interval = 2.0
        
        self._load_app_state()
        logger.info("ApplicationManager initialized")

    def _load_app_state(self) -> None:
        """Load saved application state from previous session."""
        try:
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text())
                # Convert saved data back to AppInfo objects
                for app_id, app_data in data.items():
                    if not _VALID_APP_ID.fullmatch(app_id) or not isinstance(app_data, dict):
                        logger.warning("Ignoring invalid persisted app state for %r", app_id)
                        continue
                    app = AppInfo(**app_data)
                    if app.state in (AppState.RUNNING.value, AppState.STARTING.value, AppState.STOPPING.value):
                        app.state = AppState.STOPPED.value
                        app.pid = None
                        app.heartbeat_file = None
                        app.terminated_at = datetime.now().isoformat()
                    self.running_apps[app_id] = app
                logger.info(f"Loaded state for {len(self.running_apps)} apps")
                self._save_app_state()
        except Exception as e:
            logger.error(f"Failed to load app state: {e}")

    def _save_app_state(self) -> None:
        """Save current application state."""
        temporary_path = None
        try:
            data = {
                app_id: app.to_dict() 
                for app_id, app in self.running_apps.items()
            }
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.state_file.parent,
                prefix=f".{self.state_file.name}.",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(json.dumps(data, indent=2) + "\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            temporary_path.chmod(0o600)
            os.replace(temporary_path, self.state_file)
        except (OSError, TypeError, ValueError) as e:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    logger.warning(f"Failed to remove temporary app state file: {cleanup_error}")
            logger.error(f"Failed to save app state: {e}")

    def launch_app(
        self,
        app_id: str,
        name: str,
        command: Union[str, Sequence[str]],
        working_dir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str, Optional[int]]:
        """Launch an application.
        
        Args:
            app_id: Unique application identifier
            name: Display name for the application
            command: Command text (parsed with shlex) or an argument sequence.
                Commands are never passed to a shell.
            working_dir: Working directory for the app
            environment: Environment variables to set
        
        Returns:
            Tuple[bool, str, int]: (success, message, pid)
        """
        try:
            if not isinstance(app_id, str) or not _VALID_APP_ID.fullmatch(app_id):
                return False, "Invalid application identifier", None
            if (
                not isinstance(name, str) or not name.strip() or len(name) > 128
                or any(not character.isprintable() for character in name)
            ):
                return False, "Invalid application name", None
            if isinstance(command, str):
                if len(command) > 8192:
                    return False, "Command is too long", None
                argv = shlex.split(command)
            elif isinstance(command, Sequence) and not isinstance(command, (bytes, bytearray)):
                argv = list(command)
            else:
                return False, "Command must be text or a sequence of arguments", None
            if not argv or not all(isinstance(argument, str) and "\0" not in argument for argument in argv):
                return False, "Command contains invalid arguments", None
            if not argv[0].strip():
                return False, "Command executable cannot be empty", None
            if environment is not None and any(
                not isinstance(key, str) or not key or "=" in key or "\0" in key
                or not isinstance(value, str) or "\0" in value
                for key, value in environment.items()
            ):
                return False, "Environment contains invalid entries", None

            # Check if app already running
            if app_id in self.running_apps:
                app = self.running_apps[app_id]
                if app.state == AppState.RUNNING.value:
                    return False, f"App {name} already running", None
            
            # Check concurrent app limit
            running_count = sum(
                1 for app in self.running_apps.values()
                if app.state == AppState.RUNNING.value
            )
            if running_count >= self.max_concurrent_apps:
                return False, f"Maximum concurrent apps ({self.max_concurrent_apps}) reached", None
            
            # Prepare app info
            app_info = AppInfo(
                app_id=app_id,
                name=name,
                command=shlex.join(argv),
                working_dir=working_dir or str(Path.home()),
                environment=environment or {},
                state=AppState.STARTING.value,
                launched_at=datetime.now().isoformat(),
            )
            
            # Create heartbeat file for crash detection
            app_info.heartbeat_file = str(self.apps_dir / f"{app_id}_heartbeat")
            
            # Set up environment
            env = os.environ.copy()
            if environment:
                env.update(environment)
            
            # Redirect output to log file
            log_file = self.log_dir / f"{app_id}.log"
            log_descriptor = os.open(
                log_file,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            os.fchmod(log_descriptor, 0o600)
            with os.fdopen(log_descriptor, "a", encoding="utf-8") as log_fd:
                process = subprocess.Popen(
                    argv,
                    cwd=working_dir,
                    env=env,
                    stdout=log_fd,
                    stderr=log_fd,
                    start_new_session=True,
                )
            
            app_info.pid = process.pid
            app_info.state = AppState.RUNNING.value
            
            self.running_apps[app_id] = app_info
            self._processes[app_id] = process
            self._save_app_state()
            
            logger.info(f"Launched app {name} (PID: {process.pid})")
            return True, f"App {name} launched successfully", process.pid
        
        except Exception as e:
            logger.error(f"Failed to launch app {name}: {e}")
            return False, f"Failed to launch app: {str(e)}", None

    def terminate_app(self, app_id: str, force: bool = False) -> Tuple[bool, str]:
        """Terminate a running application.
        
        Args:
            app_id: Application identifier
            force: Use SIGKILL instead of SIGTERM
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            if app_id not in self.running_apps:
                return False, f"App {app_id} not found"
            
            app = self.running_apps[app_id]
            
            if not app.pid:
                return False, f"No PID for app {app.name}"

            process = self._processes.get(app_id)
            if process is None:
                return False, f"App {app.name} is not running in this launcher session"
            
            # Send signal to process group (since we used start_new_session)
            import signal
            sig = signal.SIGKILL if force else signal.SIGTERM
            
            try:
                if process.poll() is None:
                    os.killpg(process.pid, sig)
                logger.info(f"Terminated app {app.name} (PID: {app.pid})")
            except ProcessLookupError:
                # Process already terminated
                pass
            
            app.state = AppState.STOPPING.value
            app.terminated_at = datetime.now().isoformat()
            try:
                process.wait(timeout=2 if force else 5)
            except subprocess.TimeoutExpired:
                if force:
                    return False, f"App {app.name} did not exit after SIGKILL"
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    return False, f"App {app.name} did not exit after forced termination"
            
            app.state = AppState.STOPPED.value
            self._processes.pop(app_id, None)
            self._save_app_state()
            
            return True, f"App {app.name} terminated"
        
        except Exception as e:
            logger.error(f"Failed to terminate app {app_id}: {e}")
            return False, str(e)

    def check_app_health(self, app_id: str) -> Tuple[bool, str]:
        """Check if an application is still running and healthy.
        
        Args:
            app_id: Application identifier
        
        Returns:
            Tuple[bool, str]: (is_healthy, status_message)
        """
        try:
            if app_id not in self.running_apps:
                return False, "App not found"
            
            app = self.running_apps[app_id]
            
            if not app.pid:
                return False, "No PID"
            
            process = self._processes.get(app_id)
            if process is None:
                return False, "Process is not managed by this launcher session"
            if process.poll() is None:
                app.state = AppState.RUNNING.value
                return True, "Running"
            app.state = AppState.STOPPED.value
            app.terminated_at = datetime.now().isoformat()
            self._processes.pop(app_id, None)
            self._save_app_state()
            return False, "Process exited"
        
        except Exception as e:
            logger.error(f"Error checking app health: {e}")
            return False, f"Error: {str(e)}"

    def update_app_heartbeat(self, app_id: str) -> None:
        """Update heartbeat for an application (for hang detection).
        
        Args:
            app_id: Application identifier
        """
        try:
            if app_id not in self.running_apps:
                return
            
            app = self.running_apps[app_id]
            if app.heartbeat_file:
                Path(app.heartbeat_file).write_text(str(time.time()))
        
        except Exception as e:
            logger.error(f"Failed to update heartbeat for {app_id}: {e}")

    def record_app_crash(self, app_id: str, reason: str = "Unknown") -> None:
        """Record an application crash.
        
        Args:
            app_id: Application identifier
            reason: Description of crash
        """
        try:
            if app_id not in self.running_apps:
                return
            
            app = self.running_apps[app_id]
            app.crashes += 1
            app.state = AppState.CRASHED.value
            app.terminated_at = datetime.now().isoformat()
            
            # Log crash
            crash_log = self.log_dir / "app_crashes.log"
            with open(crash_log, "a") as f:
                f.write(f"{datetime.now().isoformat()} - {app.name} ({app_id}): {reason}\n")
            
            self._save_app_state()
            logger.warning(f"App {app.name} crashed: {reason}")
            
            # Don't automatically restart - let Titans UI decide
        
        except Exception as e:
            logger.error(f"Failed to record crash for {app_id}: {e}")

    def get_running_apps(self) -> List[AppInfo]:
        """Get list of all running applications.
        
        Returns:
            List[AppInfo]: List of running apps
        """
        return [
            app for app in self.running_apps.values()
            if app.state == AppState.RUNNING.value
        ]

    def get_all_apps(self) -> Dict[str, AppInfo]:
        """Get all managed applications.
        
        Returns:
            Dict[str, AppInfo]: All apps indexed by app_id
        """
        return self.running_apps.copy()

    def get_app_info(self, app_id: str) -> Optional[AppInfo]:
        """Get information about a specific application.
        
        Args:
            app_id: Application identifier
        
        Returns:
            Optional[AppInfo]: App info or None if not found
        """
        return self.running_apps.get(app_id)

    def cleanup_stopped_apps(self) -> int:
        """Clean up stopped and crashed applications from tracking.
        
        Returns:
            int: Number of apps cleaned up
        """
        to_remove = [
            app_id for app_id, app in self.running_apps.items()
            if app.state in (AppState.STOPPED.value, AppState.CRASHED.value)
        ]
        
        for app_id in to_remove:
            del self.running_apps[app_id]
        
        if to_remove:
            self._save_app_state()
            logger.info(f"Cleaned up {len(to_remove)} stopped apps")
        
        return len(to_remove)

    def monitor_apps(self, check_interval: float = 2.0, duration: Optional[float] = None) -> None:
        """Monitor running applications for crashes and hangs.
        
        Args:
            check_interval: Seconds between checks
            duration: Run for this many seconds (None = infinite)
        """
        start_time = time.time()
        
        while True:
            try:
                # Check for timeout
                if duration and (time.time() - start_time) > duration:
                    break
                
                time.sleep(check_interval)
                
                # Check each app
                for app_id in list(self.running_apps.keys()):
                    is_healthy, status = self.check_app_health(app_id)
                    
                    if not is_healthy and self.running_apps[app_id].state == AppState.RUNNING.value:
                        self.record_app_crash(app_id, status)
                
                # Periodically clean up
                if int(time.time()) % 60 == 0:
                    self.cleanup_stopped_apps()
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in app monitoring: {e}")


def run_app_monitor():
    """Entry point for application monitoring daemon."""
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
            "file": {
                "level": "DEBUG",
                "class": "logging.FileHandler",
                "filename": str(Path.home() / ".local/share/titans/logs/app_manager.log"),
                "formatter": "standard",
            },
        },
        "loggers": {
            "": {
                "handlers": ["file"],
                "level": "INFO",
                "propagate": True,
            }
        }
    }
    
    logging.config.dictConfig(log_config)
    
    manager = ApplicationManager()
    manager.monitor_apps()


if __name__ == "__main__":
    run_app_monitor()
