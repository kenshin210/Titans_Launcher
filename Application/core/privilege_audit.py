"""Private, persistent audit log for privileged launcher operations."""

import fcntl
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


class PrivilegeAuditError(OSError):
    """Raised when an audit event cannot be durably written."""


class PrivilegeAuditLog:
    """Append structured events without recording commands or credentials."""

    def __init__(self, path=None, max_bytes=1_048_576, backups=4):
        state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        self.path = Path(path) if path is not None else (
            state_home / "Titans-launcher" / "privilege-audit.jsonl"
        )
        self.max_bytes = max_bytes
        self.backups = backups
        self._lock = threading.Lock()

    def append(self, event):
        record = {
            **event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        flags |= getattr(os, "O_NOFOLLOW", 0)

        with self._lock:
            lock_descriptor = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                self.path.parent.chmod(0o700)
                lock_path = Path(f"{self.path}.lock")
                lock_descriptor = os.open(lock_path, flags, 0o600)
                os.fchmod(lock_descriptor, 0o600)
                fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
                if self.path.exists() and self.path.stat().st_size + len(payload) > self.max_bytes:
                    self._rotate()

                descriptor = os.open(self.path, flags, 0o600)
                try:
                    os.fchmod(descriptor, 0o600)
                    remaining = memoryview(payload)
                    while remaining:
                        written = os.write(descriptor, remaining)
                        if written <= 0:
                            raise OSError("Audit log write made no progress")
                        remaining = remaining[written:]
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except OSError as error:
                raise PrivilegeAuditError(f"Could not write privilege audit log: {error}") from error
            finally:
                if lock_descriptor is not None:
                    try:
                        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
                    finally:
                        os.close(lock_descriptor)

    def _rotate(self):
        oldest = Path(f"{self.path}.{self.backups}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backups - 1, 0, -1):
            source = Path(f"{self.path}.{index}")
            if source.exists():
                os.replace(source, Path(f"{self.path}.{index + 1}"))
        if self.path.exists():
            os.replace(self.path, Path(f"{self.path}.1"))
