"""
Session Manager for Titans Launcher - KDE Independence Phase 0.

Handles the creation and lifecycle management of Titans as an independent
Wayland session. Manages startup, shutdown, and integration with systemd
user sessions and display managers.
"""

import logging
import os
import sys
import subprocess
import shlex
import shutil
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages Titans Launcher as an independent Wayland session."""

    def __init__(self):
        """Initialize the SessionManager."""
        self.user_home = Path.home()
        self.session_dir = self.user_home / ".local" / "share" / "titans"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.project_root = Path(__file__).resolve().parents[2]
        
        self.systemd_user_dir = self.user_home / ".config" / "systemd" / "user"
        self.systemd_user_dir.mkdir(parents=True, exist_ok=True)
        
        self.session_state_file = self.session_dir / "session_state.json"
        self.heartbeat_file = self.session_dir / "heartbeat"
        
        logger.info("SessionManager initialized")

    def get_wayland_display(self) -> str:
        """Get the current WAYLAND_DISPLAY value.
        
        Returns:
            str: WAYLAND_DISPLAY value, e.g., "wayland-0"
        """
        return os.environ.get("WAYLAND_DISPLAY", "wayland-0")

    def get_xdg_runtime_dir(self) -> str:
        """Get XDG_RUNTIME_DIR for socket paths.
        
        Returns:
            str: Path to XDG runtime directory
        """
        return os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

    def get_display_server(self) -> Optional[str]:
        """Get the current display server.
        
        Returns:
            Optional[str]: "wayland" or "x11" or None
        """
        xdg_session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if xdg_session_type in ("wayland", "x11"):
            return xdg_session_type
        
        # Fallback: check for WAYLAND_DISPLAY
        if os.environ.get("WAYLAND_DISPLAY"):
            return "wayland"
        
        if os.environ.get("DISPLAY"):
            return "x11"
        
        return None

    def ensure_compositor_running(self) -> bool:
        """Ensure KWin compositor is running.
        
        Returns:
            bool: True if compositor is running or started successfully
        """
        # Check if KWin is already running
        result = subprocess.run(
            ["pgrep", "-f", "kwin_wayland"],
            capture_output=True
        )
        
        if result.returncode == 0:
            logger.info("KWin compositor already running")
            return True
        
        logger.info("Starting KWin compositor...")
        try:
            subprocess.Popen(
                ["kwin_wayland"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(2)  # Give compositor time to start
            logger.info("KWin compositor started")
            return True
        except Exception as e:
            logger.error(f"Failed to start KWin: {e}")
            return False

    def create_systemd_units(self) -> Tuple[bool, str]:
        """Create systemd user units for Titans session.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        units = {
            "titans-launcher.service": self._get_launcher_unit(),
            "titans-monitor.service": self._get_monitor_unit(),
            "titans-session.target": self._get_session_target(),
        }
        
        try:
            for unit_name, unit_content in units.items():
                unit_path = self.systemd_user_dir / unit_name
                unit_path.write_text(unit_content)
                unit_path.chmod(0o600)
                logger.info(f"Created systemd unit: {unit_path}")
            
            # Reload systemd configuration
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=True
            )
            logger.info("Systemd daemon reloaded")
            return True, "Systemd units created successfully"
        except Exception as e:
            logger.error(f"Failed to create systemd units: {e}")
            return False, str(e)

    def _get_launcher_unit(self) -> str:
        """Get the content of titans-launcher.service.
        
        Returns:
            str: systemd unit file content
        """
        executable = self._unit_argument(sys.executable)
        project_root = self._unit_path(str(self.project_root))
        return f"""[Unit]
Description=Titans Launcher Application
After=graphical-session-pre.target graphical-session.target
PartOf=titans-session.target graphical-session.target

[Service]
Type=simple
ExecStart={executable} -m Application.launcher
WorkingDirectory={project_root}
Restart=on-failure
RestartSec=5
StartLimitInterval=30
StartLimitBurst=3
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
"""

    def _get_monitor_unit(self) -> str:
        """Get the content of titans-monitor.service.
        
        Returns:
            str: systemd unit file content
        """
        executable = self._unit_argument(sys.executable)
        project_root = self._unit_path(str(self.project_root))
        return f"""[Unit]
Description=Titans Process Monitor
After=graphical-session.target
PartOf=titans-session.target graphical-session.target

[Service]
Type=simple
ExecStart={executable} -m Application.core.process_monitor
WorkingDirectory={project_root}
Restart=on-failure
RestartSec=2
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
"""

    def _get_session_target(self) -> str:
        """Get the content of titans-session.target.
        
        Returns:
            str: systemd unit file content
        """
        return """[Unit]
Description=Titans Session
RefuseManualStart=no
StopWhenUnneeded=no
Wants=titans-launcher.service titans-monitor.service
After=graphical-session.target
"""

    @staticmethod
    def _unit_argument(value: str) -> str:
        """Quote a literal argument for a systemd unit directive."""
        if not value or any(not character.isprintable() for character in value):
            raise ValueError("systemd unit arguments must be printable and non-empty")
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("%", "%%")
            .replace("$", "$$")
        )
        return f'"{escaped}"'

    @staticmethod
    def _unit_path(value: str) -> str:
        """Escape a filesystem path for a systemd path directive."""
        if not value or not Path(value).is_absolute():
            raise ValueError("systemd working directories must be absolute")
        escaped = []
        for character in value:
            if not character.isprintable():
                raise ValueError("systemd paths must be printable")
            if character == "\\":
                escaped.append("\\\\")
            elif character == "%":
                escaped.append("%%")
            elif character in {'"', "$"} or character.isspace():
                code = ord(character)
                if code > 0xFF:
                    raise ValueError("systemd paths cannot contain non-ASCII whitespace")
                escaped.append(f"\\x{code:02x}")
            else:
                escaped.append(character)
        return "".join(escaped)

    def create_desktop_session_file(self) -> Tuple[bool, str]:
        """Generate a per-user KWin Wayland session entry for SDDM.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        dbus_run_session = shutil.which("dbus-run-session")
        kwin_wayland = shutil.which("kwin_wayland")
        if not dbus_run_session or not kwin_wayland:
            return False, "Generating a Titans session requires dbus-run-session and kwin_wayland"

        try:
            launcher_script = self.session_dir / "session-launcher.sh"
            launcher_script.write_text(
                "#!/bin/sh\n"
                f"cd -- {shlex.quote(str(self.project_root))} || exit 1\n"
                f"exec {shlex.quote(sys.executable)} -m Application.launcher\n",
                encoding="utf-8",
            )
            launcher_script.chmod(0o700)

            session_directory = self.session_dir / "wayland-sessions"
            session_directory.mkdir(parents=True, exist_ok=True)
            session_file_path = session_directory / "titans.desktop"
            command = (
                dbus_run_session,
                "--",
                kwin_wayland,
                "--xwayland",
                f"--exit-with-session={launcher_script}",
            )
            content = f"""[Desktop Entry]
Name=Titans Launcher
Comment=Start Titans in a KWin Wayland session
Exec={self._desktop_exec(command)}
Type=Application
DesktopNames=KDE;
"""
            session_file_path.write_text(content, encoding="utf-8")
            session_file_path.chmod(0o600)
            logger.info("Generated per-user Wayland session entry: %s", session_file_path)
            return (
                True,
                f"Generated {session_file_path}. To list it in SDDM, install this file "
                "as /usr/share/wayland-sessions/titans.desktop.",
            )
        
        except Exception as e:
            logger.error(f"Failed to create desktop session file: {e}")
            return False, str(e)

    @staticmethod
    def _desktop_exec(arguments: Tuple[str, ...]) -> str:
        """Encode arguments for the Desktop Entry Exec key."""
        reserved = " \t\n\"'\\><~|&;$*?#()`"
        encoded = []
        for argument in arguments:
            if any(not character.isprintable() for character in argument):
                raise ValueError("Desktop entry arguments must be printable")
            needs_quotes = any(character in reserved for character in argument)
            escaped = (
                argument.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("`", "\\`")
                .replace("$", "\\$")
                .replace("%", "%%")
            )
            if needs_quotes:
                escaped = f'"{escaped}"'
            encoded.append(escaped)
        return " ".join(encoded)

    def start_session(self) -> Tuple[bool, str]:
        """Start the Titans session.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # Ensure compositor is running
            if not self.ensure_compositor_running():
                return False, "Failed to start KWin compositor"
            
            environment_names = (
                "DISPLAY",
                "WAYLAND_DISPLAY",
                "XDG_RUNTIME_DIR",
                "XDG_SESSION_TYPE",
                "XDG_CURRENT_DESKTOP",
                "DBUS_SESSION_BUS_ADDRESS",
                "QT_QPA_PLATFORM",
            )
            imported_names = [name for name in environment_names if os.environ.get(name)]
            if imported_names:
                imported = subprocess.run(
                    ["systemctl", "--user", "import-environment", *imported_names],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if imported.returncode != 0:
                    detail = imported.stderr.strip() or "Could not import graphical session environment"
                    logger.error("Failed to import session environment: %s", detail)
                    return False, detail

            # Start session units
            result = subprocess.run(
                ["systemctl", "--user", "start", "titans-session.target"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("Titans session started successfully")
                return True, "Session started"
            else:
                logger.error(f"Failed to start session: {result.stderr}")
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error starting session: {e}")
            return False, str(e)

    def stop_session(self) -> Tuple[bool, str]:
        """Stop the Titans session.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["systemctl", "--user", "stop", "titans-session.target"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("Titans session stopped")
                return True, "Session stopped"
            else:
                logger.error(f"Failed to stop session: {result.stderr}")
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error stopping session: {e}")
            return False, str(e)

    def update_heartbeat(self) -> None:
        """Update the heartbeat file to indicate the session is responsive.
        
        Called regularly from the main event loop to signal health status.
        """
        try:
            self.heartbeat_file.write_text(str(time.time()))
        except Exception as e:
            logger.error(f"Failed to update heartbeat: {e}")

    def is_session_healthy(self, timeout: float = 5.0) -> bool:
        """Check if the session is healthy (has recent heartbeat).
        
        Args:
            timeout: Maximum age of heartbeat in seconds
        
        Returns:
            bool: True if heartbeat is recent
        """
        try:
            if not self.heartbeat_file.exists():
                return False
            
            last_update = float(self.heartbeat_file.read_text().strip())
            elapsed = time.time() - last_update
            return elapsed < timeout
        except Exception as e:
            logger.error(f"Error checking session health: {e}")
            return False
