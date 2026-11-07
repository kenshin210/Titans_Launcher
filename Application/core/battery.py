import re
import shutil
import subprocess
from pathlib import Path

POWER_SUPPLY_DIR = Path("/sys/class/power_supply")
BLUEZ_BATTERY = re.compile(r"Battery Percentage:\s*0x[0-9a-fA-F]+\s*\((\d+)\)")
CONTROLLER_SHORT_NAMES = (
    ("dualsense", "ps5"),
    ("dualshock", "ps4"),
    ("pro controller", "switch"),
    ("joy-con", "joycon"),
    ("xbox", "xbone"),
    ("wireless controller", "ps4"),
    ("8bitdo", "8bitdo"),
)


def suggest_short_name(device_name):
    lowered = (device_name or "").lower()
    for needle, short in CONTROLLER_SHORT_NAMES:
        if needle in lowered:
            return short
    words = re.findall(r"[a-z0-9]+", lowered)
    return (words[0] if words else "device")[:8]


def _hex_only(text):
    return re.sub(r"[^0-9a-f]", "", text.lower())


def _run(command, timeout=4):
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _from_bluez(address):
    bluetoothctl = shutil.which("bluetoothctl")
    if not bluetoothctl:
        return None
    result = _run([bluetoothctl, "info", address])
    if result is None or result.returncode != 0:
        return None
    connected = "Connected: yes" in result.stdout
    match = BLUEZ_BATTERY.search(result.stdout)
    return {
        "connected": connected,
        "percent": int(match.group(1)) if match else None,
        "charging": False,
    }


def _from_sysfs(address):
    wanted = _hex_only(address)
    if not POWER_SUPPLY_DIR.is_dir():
        return None
    for supply in POWER_SUPPLY_DIR.iterdir():
        identity = supply.name + _read(supply / "serial_number") + _read(supply / "uevent")
        if wanted not in _hex_only(identity):
            continue
        capacity = _read(supply / "capacity")
        if capacity.isdigit():
            return {
                "percent": int(capacity),
                "charging": _read(supply / "status").lower() == "charging",
            }
    return None


def _from_upower(address):
    upower = shutil.which("upower")
    if not upower:
        return None
    listing = _run([upower, "-e"])
    if listing is None:
        return None
    wanted = _hex_only(address)
    for path in listing.stdout.split():
        info = _run([upower, "-i", path])
        if info is None or wanted not in _hex_only(info.stdout):
            continue
        percent = re.search(r"percentage:\s*(\d+)", info.stdout)
        state = re.search(r"state:\s*(\S+)", info.stdout)
        if percent:
            return {
                "percent": int(percent.group(1)),
                "charging": bool(state and state.group(1) in ("charging", "pending-charge")),
            }
    return None


def read_battery(address):
    """Best-effort battery state for a Bluetooth device.

    Returns {"connected": bool | None, "percent": int | None, "charging": bool}.
    Sources are tried in order: BlueZ, the kernel power_supply class, UPower.
    """
    state = {"connected": None, "percent": None, "charging": False}
    bluez = _from_bluez(address)
    if bluez:
        state.update(bluez)
        if state["connected"] is False:
            return state
    if state["percent"] is None:
        for source in (_from_sysfs, _from_upower):
            found = source(address)
            if found:
                state.update(found)
                if state["connected"] is None:
                    state["connected"] = True
                break
    return state
