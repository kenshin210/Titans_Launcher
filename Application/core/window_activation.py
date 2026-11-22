"""Window activation helpers for X11 and KWin Wayland sessions."""

import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class WindowActivationManager:
    """Activate a managed application's window through the available compositor."""

    def activate(self, pid: int) -> Tuple[bool, str]:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return False, "Invalid process identifier"

        wayland_session = (
            os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or bool(os.environ.get("WAYLAND_DISPLAY"))
        )
        wmctrl_error = None
        wmctrl = shutil.which("wmctrl")
        if wmctrl:
            success, message = self._activate_with_wmctrl(wmctrl, pid)
            if success:
                return True, message
            wmctrl_error = message
            if not wayland_session:
                return False, message

        if wayland_session:
            success, message = self._activate_with_kwin(pid)
            if success:
                return True, message
            if wmctrl_error:
                return False, f"{wmctrl_error} KWin activation also failed: {message}"
            return False, message

        if wmctrl_error:
            return False, wmctrl_error
        return False, "Window activation requires wmctrl on X11 or KWin on Wayland"

    @staticmethod
    def _activate_with_wmctrl(wmctrl: str, pid: int) -> Tuple[bool, str]:
        try:
            windows = subprocess.run(
                [wmctrl, "-lp"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if windows.returncode != 0:
                return False, windows.stderr.strip() or "wmctrl could not list windows"
            window_id = next(
                (
                    fields[0]
                    for line in windows.stdout.splitlines()
                    if len(fields := line.split(maxsplit=3)) >= 3
                    and fields[0].startswith("0x")
                    and fields[2].isdigit()
                    and int(fields[2]) == pid
                ),
                None,
            )
            if window_id is None:
                return False, "No matching X11/XWayland window was found"
            result = subprocess.run(
                [wmctrl, "-ia", window_id],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or "wmctrl could not activate the window"
            return True, "Window activated"
        except (OSError, subprocess.SubprocessError) as error:
            return False, str(error)

    @staticmethod
    def _activate_with_kwin(pid: int) -> Tuple[bool, str]:
        qdbus = next(
            (
                executable
                for name in ("qdbus6", "qdbus-qt6", "qdbus", "qdbus-qt5")
                if (executable := shutil.which(name))
            ),
            None,
        )
        if qdbus is None:
            return False, "KWin Wayland activation requires a qdbus executable"

        script_name = f"titans-window-activation-{uuid.uuid4().hex}"
        script_id: Optional[str] = None
        script_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".js",
                prefix="titans-window-",
                delete=False,
            ) as script:
                script_path = Path(script.name)
                script.write(
                    "var targetPid = "
                    f"{pid};\n"
                    "var windows = workspace.stackingOrder;\n"
                    "if (!windows && typeof workspace.clientList === 'function') "
                    "windows = workspace.clientList();\n"
                    "if (windows) {\n"
                    "  for (var i = 0; i < windows.length; i++) {\n"
                    "    var window = windows[i];\n"
                    "    if (window && Number(window.pid) === targetPid) {\n"
                    "      if (typeof workspace.activateWindow === 'function') "
                    "workspace.activateWindow(window);\n"
                    "      else workspace.activeClient = window;\n"
                    "      break;\n"
                    "    }\n"
                    "  }\n"
                    "}\n"
                )

            loaded = subprocess.run(
                [
                    qdbus, "org.kde.KWin", "/Scripting", "loadScript",
                    str(script_path), script_name,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if loaded.returncode != 0:
                return False, loaded.stderr.strip() or "KWin could not load the activation script"
            script_id = loaded.stdout.strip()
            if not script_id.isdecimal():
                return False, "KWin returned an invalid activation script identifier"

            ran = subprocess.run(
                [
                    qdbus, "org.kde.KWin",
                    f"/Scripting/Script{script_id}", "run",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if ran.returncode != 0:
                return False, ran.stderr.strip() or "KWin could not run the activation script"
            return True, "Window activation requested through KWin"
        except (OSError, subprocess.SubprocessError) as error:
            return False, str(error)
        finally:
            if script_id and qdbus:
                try:
                    unloaded = subprocess.run(
                        [
                            qdbus, "org.kde.KWin", "/Scripting", "unloadScript",
                            script_name,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    if unloaded.returncode != 0:
                        logger.warning(
                            "Could not unload temporary KWin activation script: %s",
                            unloaded.stderr.strip() or "qdbus returned an error",
                        )
                except (OSError, subprocess.SubprocessError) as error:
                    logger.warning("Could not unload temporary KWin activation script: %s", error)
            if script_path is not None:
                try:
                    script_path.unlink(missing_ok=True)
                except OSError as error:
                    logger.warning("Could not remove temporary KWin script: %s", error)
