"""Discover local accounts and switch between their login sessions."""

import logging
import os
import pwd
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PyQt6.QtDBus import QDBus, QDBusConnection, QDBusMessage, QDBusObjectPath

logger = logging.getLogger(__name__)

_VALID_SESSION_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_VALID_USERNAME = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
class UserManagerError(RuntimeError):
    """Raised when account/session discovery or switching fails."""


def current_user_display_name():
    try:
        entry = pwd.getpwuid(os.getuid())
    except (KeyError, OSError) as error:
        logger.warning("Could not read the current Linux account: %s", error)
        return "Unavailable"
    name = "".join(
        character for character in entry.pw_gecos.split(",", 1)[0].strip()
        if character.isprintable()
    )[:100]
    return name or entry.pw_name


@dataclass(frozen=True)
class UserAccount:
    """A local login account suitable for interactive desktop use."""

    username: str
    display_name: str
    uid: int
    home: str
    is_current: bool


@dataclass(frozen=True)
class UserSession:
    """A login session reported by logind."""

    session_id: str
    username: str
    uid: int
    seat: str
    terminal: str


class UserManager:
    """Manage local accounts via system services and switch login sessions."""

    def __init__(self, uid_min: Optional[int] = None):
        self.uid_min = self._read_uid_min() if uid_min is None else uid_min

    @staticmethod
    def create_account(username: str, display_name: str, password: str) -> None:
        """Create a standard account with administrator authorization."""
        if not isinstance(username, str) or not _VALID_USERNAME.fullmatch(username):
            raise UserManagerError("Use a lowercase Linux username containing only letters, digits, _ or -.")
        if not isinstance(display_name, str) or len(display_name) > 100 or any(
            not character.isprintable() or character in ",:" for character in display_name
        ):
            raise UserManagerError("Display name contains unsupported characters or is too long.")
        if not isinstance(password, str) or not password or any(c in password for c in "\x00\r\n"):
            raise UserManagerError("Enter a non-empty password without line breaks.")
        try:
            password_length = len(password.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise UserManagerError("Password contains unsupported characters.") from error
        if password_length > 128:
            raise UserManagerError("Password must be at most 128 UTF-8 bytes.")
        try:
            result = subprocess.run(
                ["openssl", "passwd", "-6", "-stdin"],
                input=password + "\n", text=True, capture_output=True, timeout=10, check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise UserManagerError("Could not prepare the password; check that OpenSSL is installed.") from error
        hashed = result.stdout.strip()
        if result.returncode != 0 or not hashed.startswith("$6$") or "\n" in hashed:
            raise UserManagerError("Could not prepare the password using OpenSSL.")
        bus = QDBusConnection.systemBus()
        if not bus.isConnected():
            raise UserManagerError("The system D-Bus is unavailable; no account was requested.")

        def call(path, interface, method, arguments):
            message = QDBusMessage.createMethodCall(
                "org.freedesktop.Accounts", path, interface, method,
            )
            message.setArguments(arguments)
            message.setInteractiveAuthorizationAllowed(True)
            try:
                reply = bus.call(message, QDBus.CallMode.Block, 120000)
            except (RuntimeError, TypeError) as error:
                raise UserManagerError("D-Bus communication failed") from error
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                raise UserManagerError(reply.errorName() or "system service error")
            return reply.arguments()

        try:
            response = call(
                "/org/freedesktop/Accounts", "org.freedesktop.Accounts", "CreateUser",
                [username, display_name or username, 0],
            )
        except UserManagerError as error:
            raise UserManagerError(
                f"Account creation failed ({error}). If the request timed out, check system "
                "account settings before trying again."
            ) from error
        if len(response) != 1 or not isinstance(response[0], QDBusObjectPath):
            raise UserManagerError(
                "The account service returned an unexpected response. Check system account "
                "settings before trying again."
            )
        try:
            call(response[0].path(), "org.freedesktop.Accounts.User", "SetPassword", [hashed, ""])
        except UserManagerError as error:
            raise UserManagerError(
                f"The account '{username}' was created, but its password could not be confirmed "
                f"({error}). Use system account settings to set a password or remove it."
            ) from error

    @staticmethod
    def _read_uid_min() -> int:
        try:
            for line in Path("/etc/login.defs").read_text(encoding="utf-8").splitlines():
                fields = line.split("#", 1)[0].split()
                if len(fields) == 2 and fields[0] == "UID_MIN":
                    return int(fields[1])
        except (OSError, ValueError):
            logger.warning("Could not read UID_MIN from /etc/login.defs; using 1000")
        return 1000

    def list_accounts(self) -> List[UserAccount]:
        """Return local human accounts with usable homes and login shells."""
        accounts = []
        current_uid = os.getuid()
        try:
            entries = pwd.getpwall()
        except OSError as error:
            raise UserManagerError(f"Could not read local account database: {error}") from error

        for entry in entries:
            if entry.pw_uid < self.uid_min and entry.pw_uid != current_uid:
                continue
            if not entry.pw_name or Path(entry.pw_shell).name in {"nologin", "false"}:
                continue
            home = Path(entry.pw_dir)
            if not home.is_dir():
                continue
            gecos_name = "".join(
                character
                for character in entry.pw_gecos.split(",", 1)[0].strip()
                if character.isprintable()
            )[:100]
            accounts.append(UserAccount(
                username=entry.pw_name,
                display_name=gecos_name or entry.pw_name,
                uid=entry.pw_uid,
                home=str(home),
                is_current=entry.pw_uid == current_uid,
            ))
        return sorted(accounts, key=lambda account: (not account.is_current, account.display_name.casefold()))

    def list_sessions(self) -> List[UserSession]:
        """Return interactive-user sessions reported by systemd-logind."""
        if shutil.which("loginctl") is None:
            raise UserManagerError("systemd-logind is unavailable (loginctl was not found)")
        try:
            result = subprocess.run(
                ["loginctl", "list-sessions", "--no-legend", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise UserManagerError(f"Could not query login sessions: {error}") from error
        if result.returncode != 0:
            detail = result.stderr.strip() or "loginctl returned an error"
            raise UserManagerError(f"Could not query login sessions: {detail}")

        accounts = {account.username: account for account in self.list_accounts()}
        sessions = []
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 3:
                continue
            session_id, uid_text, username = fields[:3]
            if not _VALID_SESSION_ID.fullmatch(session_id) or username not in accounts:
                continue
            try:
                uid = int(uid_text)
            except ValueError:
                logger.warning("Ignoring invalid loginctl session record: %r", line)
                continue
            if uid != accounts[username].uid:
                logger.warning("Ignoring inconsistent loginctl session record: %r", line)
                continue
            sessions.append(UserSession(
                session_id=session_id,
                username=username,
                uid=uid,
                seat=fields[3] if len(fields) > 3 and fields[3] != "-" else "—",
                terminal=fields[4] if len(fields) > 4 and fields[4] != "-" else "",
            ))
        return sessions

    def activate_session(self, session_id: str) -> None:
        """Activate an existing login session after verifying its current owner."""
        if not isinstance(session_id, str) or not _VALID_SESSION_ID.fullmatch(session_id):
            raise UserManagerError("Invalid session identifier")
        sessions = self.list_sessions()
        if not any(session.session_id == session_id for session in sessions):
            raise UserManagerError("The selected session is no longer available")
        self._run_switch_command(["loginctl", "activate", session_id])

    def switch_to_login_screen(self) -> None:
        """Ask a supported display manager to show its authenticated greeter."""
        if shutil.which("dm-tool") is not None:
            self._run_switch_command(["dm-tool", "switch-to-greeter"])
            return
        if shutil.which("gdmflexiserver") is not None:
            self._run_switch_command(["gdmflexiserver", "--new"])
            return
        raise UserManagerError(
            "This display manager does not expose a supported user-switch command. "
            "Use the system menu to log out or switch users."
        )

    @staticmethod
    def _run_switch_command(command: List[str]) -> None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise UserManagerError(f"Could not switch sessions: {error}") from error
        if result.returncode != 0:
            detail = result.stderr.strip() or "the system command returned an error"
            raise UserManagerError(f"Could not switch sessions: {detail}")
