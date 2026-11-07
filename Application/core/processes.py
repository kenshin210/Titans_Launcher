import os
import re
import shutil
import subprocess
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

PSUTIL_AVAILABLE = psutil is not None
NVIDIA_SMI = shutil.which("nvidia-smi")

STATUS_LABELS = {
    "running": "Running",
    "sleeping": "Running",
    "idle": "Running",
    "disk-sleep": "Waiting on I/O",
    "stopped": "Suspended",
    "tracing-stop": "Suspended",
    "zombie": "Zombie",
    "dead": "Zombie",
}
# Worst state wins when several processes of one application are grouped.
STATUS_SEVERITY = {"Running": 0, "Waiting on I/O": 1, "Suspended": 2, "Zombie": 3}


def format_bytes(value):
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"


def format_rate(value):
    return f"{format_bytes(value)}/s"


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _swap_bytes(pid):
    match = re.search(r"^VmSwap:\s*(\d+)\s*kB", _read_text(f"/proc/{pid}/status"), re.MULTILINE)
    return int(match.group(1)) * 1024 if match else 0


def _drm_usage(pid):
    """Per-engine busy nanoseconds and VRAM bytes from DRM fdinfo (amdgpu, i915, xe, nouveau)."""
    engines = {}
    vram = 0
    seen_clients = set()
    try:
        entries = list(Path(f"/proc/{pid}/fdinfo").iterdir())
    except OSError:
        return engines, vram
    for entry in entries:
        text = _read_text(entry)
        if "drm-driver:" not in text:
            continue
        client = re.search(r"^drm-client-id:\s*(\d+)", text, re.MULTILINE)
        if client:
            if client.group(1) in seen_clients:
                continue
            seen_clients.add(client.group(1))
        for name, value in re.findall(r"^drm-engine-(?!capacity)([\w-]+):\s*(\d+)\s*ns", text, re.MULTILINE):
            engines[name] = engines.get(name, 0) + int(value)
        memory = re.findall(
            r"^drm-(?:memory-vram|total-vram\d*|total-local\d*):\s*(\d+)\s*(KiB|MiB|B)?",
            text, re.MULTILINE,
        )
        scale = {"KiB": 1024, "MiB": 1024 ** 2, "B": 1, "": 1024}
        vram += sum(int(amount) * scale.get(unit, 1024) for amount, unit in memory)
    return engines, vram


def _nvidia_usage():
    """pid -> (sm percent, memory bytes) from `nvidia-smi pmon`, if an NVIDIA GPU is present."""
    if not NVIDIA_SMI:
        return {}
    try:
        result = subprocess.run(
            [NVIDIA_SMI, "pmon", "-c", "1", "-s", "um"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    columns = []
    usage = {}
    for line in result.stdout.splitlines():
        if line.startswith("# gpu"):
            columns = line.lstrip("# ").split()
            continue
        if line.startswith("#") or not columns:
            continue
        fields = line.split()
        row = dict(zip(columns, fields))
        try:
            pid = int(row["pid"])
        except (KeyError, ValueError):
            continue
        sm = int(row["sm"]) if row.get("sm", "-").isdigit() else 0
        framebuffer = int(row["fb"]) * 1024 ** 2 if row.get("fb", "-").isdigit() else 0
        old_sm, old_fb = usage.get(pid, (0, 0))
        usage[pid] = (max(old_sm, sm), old_fb + framebuffer)
    return usage


class ProcessSampler:
    """Collects per-application CPU, RAM, swap, disk I/O and GPU figures.

    Rates are computed between consecutive calls, so the first call after a
    pause reports zero rates. Must be driven from one thread at a time.
    """

    def __init__(self):
        self._uid = os.getuid()
        self._own_pid = os.getpid()
        self._previous_time = None
        self._previous_io = {}
        self._previous_gpu = {}

    def reset(self):
        self._previous_time = None
        self._previous_io.clear()
        self._previous_gpu.clear()

    def sample(self, all_users=False):
        now = time.monotonic()
        elapsed = (now - self._previous_time) if self._previous_time else None
        nvidia = _nvidia_usage()
        groups = {}
        io_now = {}
        gpu_now = {}

        for proc in psutil.process_iter():
            try:
                with proc.oneshot():
                    if not all_users and proc.uids().real != self._uid:
                        continue
                    pid = proc.pid
                    name = proc.name()
                    status = STATUS_LABELS.get(proc.status(), "Running")
                    cpu = proc.cpu_percent(None)
                    rss = proc.memory_info().rss
                    try:
                        counters = proc.io_counters()
                        io_total = counters.read_bytes + counters.write_bytes
                    except (psutil.AccessDenied, AttributeError):
                        io_total = None
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                continue

            io_rate = 0.0
            if io_total is not None:
                io_now[pid] = io_total
                if elapsed and pid in self._previous_io:
                    io_rate = max(0, io_total - self._previous_io[pid]) / elapsed

            engines, vram = _drm_usage(pid)
            gpu_now[pid] = engines
            gpu_percent = 0.0
            if elapsed and engines:
                previous = self._previous_gpu.get(pid, {})
                busy = [
                    max(0, ns - previous.get(engine, ns)) / (elapsed * 1e9) * 100
                    for engine, ns in engines.items()
                ]
                gpu_percent = min(100.0, max(busy, default=0.0))
            if pid in nvidia:
                gpu_percent = max(gpu_percent, float(nvidia[pid][0]))
                vram = max(vram, nvidia[pid][1])

            group = groups.setdefault(name, {
                "name": name, "pids": [], "status": "Running", "cpu": 0.0, "ram": 0,
                "swap": 0, "disk": 0.0, "gpu": 0.0, "gpu_mem": 0,
            })
            group["pids"].append(pid)
            if STATUS_SEVERITY[status] > STATUS_SEVERITY[group["status"]]:
                group["status"] = status
            group["cpu"] += cpu
            group["ram"] += rss
            group["swap"] += _swap_bytes(pid)
            group["disk"] += io_rate
            group["gpu"] += gpu_percent
            group["gpu_mem"] += vram

        self._previous_io = io_now
        self._previous_gpu = gpu_now
        self._previous_time = now
        return list(groups.values())

    @staticmethod
    def system_totals():
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        try:
            disk = psutil.disk_usage("/")
            disk_percent, disk_used, disk_total = disk.percent, disk.used, disk.total
        except OSError:
            disk_percent = disk_used = disk_total = 0
        return {
            "cpu": psutil.cpu_percent(None),
            "ram_percent": memory.percent, "ram_used": memory.used, "ram_total": memory.total,
            "swap_percent": swap.percent, "swap_used": swap.used, "swap_total": swap.total,
            "disk_percent": disk_percent, "disk_used": disk_used, "disk_total": disk_total,
        }


def protected_pids():
    """The launcher itself and everything above it must never be killed from the UI."""
    protected = {os.getpid()}
    try:
        protected.update(parent.pid for parent in psutil.Process().parents())
    except psutil.Error:
        pass
    return protected


def kill_application(pids, force=False):
    """Terminate (or force-kill) processes and their children. Returns a list of error strings."""
    protected = protected_pids()
    targets = []
    errors = []
    skipped_protected = False
    for pid in pids:
        if pid in protected:
            skipped_protected = True
            continue
        try:
            proc = psutil.Process(pid)
            targets.extend([proc, *proc.children(recursive=True)])
        except psutil.NoSuchProcess:
            continue
        except psutil.Error as error:
            errors.append(f"{pid}: {error}")
    unique = {proc.pid: proc for proc in targets if proc.pid not in protected}
    if skipped_protected and not unique:
        return ["This process is part of the launcher and cannot be closed from here."]
    for proc in unique.values():
        try:
            proc.kill() if force else proc.terminate()
        except psutil.NoSuchProcess:
            continue
        except psutil.Error as error:
            errors.append(f"{proc.pid}: {error}")
    return errors
