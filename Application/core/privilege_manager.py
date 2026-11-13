"""Centralized privilege escalation management for Titans Launcher.

Handles:
- Detection of available privilege escalation methods (polkit, sudo)
- Polkit policy file generation and installation
- Execution of privileged commands with proper error handling
- Transparent user interaction for privilege requests
"""

import grp
import os
import pwd
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from Application.core.privilege_audit import PrivilegeAuditError, PrivilegeAuditLog
from Application.ui.Settings.Logger import log_error, log_info, log_warning


PRIVILEGE_OPERATIONS = {
    "package_check": {
        "minimum_role": "operator",
        "requires_elevation": True,
    },
    "system_update": {
        "minimum_role": "administrator",
        "requires_elevation": True,
    },
    "package_repair": {
        "minimum_role": "administrator",
        "requires_elevation": True,
    },
}


class PolkitPolicy:
    """Manages polkit authorization policies for Titans Launcher."""

    POLICY_NAME = "org.titans.launcher"
    POLICY_DIR = Path("/etc/polkit-1/rules.d")
    POLICY_FILE = POLICY_DIR / "99-titans-launcher.rules"

    POLICY_CONTENT = '''// Titans Launcher privilege escalation policy
// Allows Titans Launcher to perform system operations without repeated password prompts

polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.titans.launcher.") == 0) {
        if (subject.isInGroup("wheel") || subject.isInGroup("sudo")) {
            return polkit.Result.YES;
        }
    }
});

polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.titans.launcher.") == 0) {
        if (subject.user == "root") {
            return polkit.Result.YES;
        }
    }
});
'''

    @staticmethod
    def install():
        """Install polkit policy file if not already present."""
        if PolkitPolicy.POLICY_FILE.exists():
            log_info("Polkit policy already installed")
            return True

        if not PolkitPolicy.POLICY_DIR.exists():
            log_warning(f"Polkit rules directory {PolkitPolicy.POLICY_DIR} does not exist")
            return False

        try:
            # Write policy file
            PolkitPolicy.POLICY_FILE.write_text(PolkitPolicy.POLICY_CONTENT)
            PolkitPolicy.POLICY_FILE.chmod(0o644)
            log_info(f"Installed polkit policy at {PolkitPolicy.POLICY_FILE}")
            return True
        except (OSError, PermissionError) as e:
            log_error(f"Failed to install polkit policy: {e}")
            return False

    @staticmethod
    def is_installed() -> bool:
        """Check if polkit policy is installed."""
        return PolkitPolicy.POLICY_FILE.exists()


class PrivilegeManager:
    """Centralized privilege escalation for system operations."""

    def __init__(self, audit_log=None):
        self.pkexec = shutil.which("pkexec")
        self.sudo = shutil.which("sudo")
        self.polkit_available = self.pkexec is not None
        self.sudo_available = self.sudo is not None
        self.session_id = uuid.uuid4().hex
        self.username = pwd.getpwuid(os.getuid()).pw_name
        self.role = self._current_os_role()
        self.audit_log = audit_log or PrivilegeAuditLog()
        self._session_ended = False
        self._append_audit_event(
            self.session_id, "privilege_session", "started",
        )

        # Try to install polkit policy
        if self.polkit_available:
            PolkitPolicy.install()

    @staticmethod
    def _current_os_role() -> str:
        """Map the current Unix account to the launcher's advisory RBAC roles."""
        if os.geteuid() == 0:
            return "administrator"

        group_ids = set(os.getgroups())
        group_ids.add(os.getgid())
        for group_id in group_ids:
            try:
                group_name = grp.getgrgid(group_id).gr_name
            except KeyError:
                continue
            if group_name in {"wheel", "sudo"}:
                return "administrator"
        return "operator"

    @staticmethod
    def _role_allows(role: str, minimum_role: str) -> bool:
        role_rank = {"operator": 1, "administrator": 2}
        return role_rank.get(role, 0) >= role_rank[minimum_role]

    def _append_audit_event(self, operation_id, operation, status, **fields):
        try:
            self.audit_log.append({
                "session_id": self.session_id,
                "operation_id": operation_id,
                "username": self.username,
                "role": self.role,
                "operation": operation,
                "status": status,
                **fields,
            })
        except PrivilegeAuditError as error:
            log_error("Privilege operation audit could not be persisted.", details=str(error))
            return False
        return True

    def check_operation_access(self, operation: str) -> Tuple[bool, str]:
        """Check the operation's role and elevation requirements without auditing."""
        policy = PRIVILEGE_OPERATIONS.get(operation)
        if policy is None:
            return False, "This privileged operation is not registered."
        if not self._role_allows(self.role, policy["minimum_role"]):
            return False, f"Requires the {policy['minimum_role']} role."
        if policy["requires_elevation"] and not self.can_elevate():
            return False, "No supported privilege escalation method is available."
        return True, ""

    def authorize_operation(self, operation: str) -> Tuple[bool, str, Optional[str]]:
        """Authorize a known operation and persist its start before elevation."""
        operation_id = uuid.uuid4().hex
        allowed, reason = self.check_operation_access(operation)
        if not allowed:
            audit_operation = operation if operation in PRIVILEGE_OPERATIONS else "unregistered_operation"
            reason_code = (
                "unregistered_operation" if operation not in PRIVILEGE_OPERATIONS
                else "insufficient_role" if "role" in reason
                else "elevation_unavailable"
            )
            if not self._append_audit_event(
                operation_id, audit_operation, "denied", reason=reason_code,
            ):
                return False, "The operation was denied and its audit event could not be saved.", None
            return False, reason, None

        if not self._append_audit_event(operation_id, operation, "started"):
            return False, "The audit log is unavailable; the operation was not started.", None
        return True, "", operation_id

    def complete_operation(self, operation_id: str, operation: str, status: str, return_code=None):
        """Persist the final outcome for a previously authorized operation."""
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ValueError(f"Unsupported privilege operation status: {status}")
        return self._append_audit_event(
            operation_id,
            operation,
            status,
            return_code=return_code,
        )

    def end_session(self):
        """Record the end of this in-memory privilege session once."""
        if self._session_ended:
            return True
        self._session_ended = True
        return self._append_audit_event(
            self.session_id, "privilege_session", "ended",
        )

    def can_elevate(self) -> bool:
        """Check if any privilege escalation method is available."""
        return self.polkit_available or self.sudo_available

    def get_elevation_method(self) -> Optional[str]:
        """Get the preferred elevation method: 'pkexec' > 'sudo' > None."""
        if self.polkit_available:
            return "pkexec"
        if self.sudo_available:
            return "sudo"
        return None

    def build_command(self, command: List[str], use_stdin: bool = False) -> List[str]:
        """Build privilege escalation command prefix.

        Args:
            command: Command and arguments to run
            use_stdin: If True, use sudo -S (for password via stdin)

        Returns:
            Full command with elevation prefix, or original if no elevation needed
        """
        method = self.get_elevation_method()

        if method == "pkexec":
            return ["pkexec"] + command
        elif method == "sudo":
            if use_stdin:
                return ["sudo", "-S"] + command
            else:
                return ["sudo", "-n"] + command  # -n: non-interactive
        else:
            return command

    def execute(
        self,
        command: List[str],
        input_text: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Tuple[int, str, str]:
        """Execute a command with appropriate privilege escalation.

        Args:
            command: Command and arguments to run
            input_text: Text to send to stdin (e.g., password)
            timeout: Command timeout in seconds

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        use_stdin = input_text is not None
        full_command = self.build_command(command, use_stdin=use_stdin)

        try:
            log_info(f"Executing privileged command: {' '.join(command)}")

            result = subprocess.run(
                full_command,
                input=input_text.encode() if input_text else None,
                capture_output=True,
                timeout=timeout,
                text=False,
            )

            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            return result.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            log_error(f"Command timeout: {' '.join(command)}")
            return 1, "", "Command timeout"
        except FileNotFoundError:
            log_error(f"Elevation command not found: {self.get_elevation_method()}")
            return 1, "", "Privilege escalation method not available"
        except Exception as e:
            log_error(f"Command execution error: {e}")
            return 1, "", str(e)

    def test_elevation(self) -> bool:
        """Test if privilege escalation works (non-destructive test)."""
        return_code, _, _ = self.execute(["true"])
        return return_code == 0

    def require_elevation(self) -> bool:
        """Check if elevation is available; raise if not."""
        if not self.can_elevate():
            raise RuntimeError(
                "Privilege escalation not available. "
                "Install polkit (pkexec) or configure passwordless sudo."
            )
        return True


# Global singleton instance
_privilege_manager = None


def get_privilege_manager() -> PrivilegeManager:
    """Get or create the global PrivilegeManager instance."""
    global _privilege_manager
    if _privilege_manager is None:
        _privilege_manager = PrivilegeManager()
    return _privilege_manager
