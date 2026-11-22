import os
import re
import shutil
import subprocess
import time
from pathlib import Path

try:
    import psutil
except ImportError:  # names then fall back to what `ss` reports
    psutil = None

SS = shutil.which("ss")
USERS_PATTERN = re.compile(r'\("([^"]*)",pid=(\d+)')
BYTES_SENT = re.compile(r"\bbytes_sent:(\d+)")
BYTES_RECEIVED = re.compile(r"\bbytes_received:(\d+)")


def read_interface_totals():
    """interface -> (bytes sent, bytes received) from /proc/net/dev."""
    totals = {}
    try:
        lines = Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]
    except OSError:
        return totals
    for line in lines:
        name, separator, counters = line.partition(":")
        values = counters.split()
        if separator and len(values) >= 9:
            totals[name.strip()] = (int(values[8]), int(values[0]))
    return totals


_NAME_CACHE = {}


def application_name(pid, fallback):
    """Executable name for a pid; `ss` reports thread names such as "MainThread"."""
    cached = _NAME_CACHE.get(pid)
    if cached and cached[0] == fallback:
        return cached[1]
    name = fallback
    if psutil:
        try:
            proc = psutil.Process(pid)
            name = os.path.basename(proc.exe()) or proc.name()
        except (psutil.Error, OSError):
            try:
                name = psutil.Process(pid).name()
            except (psutil.Error, OSError):
                pass
    if len(_NAME_CACHE) > 4096:
        _NAME_CACHE.clear()
    _NAME_CACHE[pid] = (fallback, name)
    return name


def count_udp_sockets():
    """application name -> number of UDP sockets (no byte counters exist for UDP)."""
    counts = {}
    if not psutil:
        return counts
    try:
        connections = psutil.net_connections(kind="udp")
    except (psutil.Error, OSError):
        return counts
    for connection in connections:
        if connection.pid:
            name = application_name(connection.pid, "")
            if name:
                counts[name] = counts.get(name, 0) + 1
    return counts


def read_socket_counters():
    """(local, peer, pid) -> (name, bytes sent, bytes received) for TCP sockets.

    `ss` only reports owning processes for the current user unless run as root.
    """
    if not SS:
        return None
    try:
        result = subprocess.run(
            [SS, "-tinpH"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    sockets = {}
    current = None
    for line in result.stdout.splitlines():
        if line and not line[0].isspace():
            fields = line.split()
            owner = USERS_PATTERN.search(line)
            if len(fields) >= 5 and owner:
                pid = int(owner.group(2))
                current = (fields[3], fields[4], pid, application_name(pid, owner.group(1)))
            else:
                current = None
        elif current:
            sent = BYTES_SENT.search(line)
            received = BYTES_RECEIVED.search(line)
            sockets[current[:3]] = (
                current[3],
                int(sent.group(1)) if sent else 0,
                int(received.group(1)) if received else 0,
            )
            current = None
    return sockets


class NetworkSampler:
    """Upload/download rates per interface and per application, between consecutive calls."""

    def __init__(self):
        self._previous_time = None
        self._previous_interfaces = {}
        self._previous_sockets = {}

    def reset(self):
        self._previous_time = None
        self._previous_interfaces = {}
        self._previous_sockets = {}

    def sample(self):
        now = time.monotonic()
        elapsed = (now - self._previous_time) if self._previous_time else None
        interfaces = read_interface_totals()
        sockets = read_socket_counters()

        interface_rows = []
        for name, (sent, received) in interfaces.items():
            if name == "lo":
                continue
            upload = download = 0.0
            if elapsed and name in self._previous_interfaces:
                previous_sent, previous_received = self._previous_interfaces[name]
                upload = max(0, sent - previous_sent) / elapsed
                download = max(0, received - previous_received) / elapsed
            interface_rows.append({
                "name": name, "upload": upload, "download": download,
                "total_sent": sent, "total_received": received,
            })

        applications = {}
        if sockets is not None and elapsed:
            for key, (name, sent, received) in sockets.items():
                previous = self._previous_sockets.get(key)
                # A socket first seen this interval has only moved bytes within it.
                delta_sent = sent - previous[1] if previous else sent
                delta_received = received - previous[2] if previous else received
                entry = applications.setdefault(name, {
                    "name": name, "pids": set(), "upload": 0.0, "download": 0.0, "connections": 0,
                })
                entry["pids"].add(key[2])
                entry["connections"] += 1
                entry["upload"] += max(0, delta_sent) / elapsed
                entry["download"] += max(0, delta_received) / elapsed
        elif sockets is not None:
            for key, (name, _sent, _received) in sockets.items():
                entry = applications.setdefault(name, {
                    "name": name, "pids": set(), "upload": 0.0, "download": 0.0, "connections": 0,
                })
                entry["pids"].add(key[2])
                entry["connections"] += 1

        self._previous_interfaces = interfaces
        self._previous_sockets = sockets or {}
        self._previous_time = now
        for name, count in count_udp_sockets().items():
            entry = applications.setdefault(name, {
                "name": name, "pids": set(), "upload": 0.0, "download": 0.0, "connections": 0,
            })
            entry["udp"] = count
        rows = list(applications.values())
        for row in rows:
            row["pids"] = sorted(row["pids"])
            row.setdefault("udp", 0)
        return {
            "interfaces": interface_rows,
            "applications": rows,
            "per_app_available": sockets is not None,
        }
