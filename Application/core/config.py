import json
from pathlib import Path

try:
    from Settings.Logger import log_error, log_info
except ImportError:
    from Logger import log_error, log_info


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path.home() / ".config" / "Titans-launcher" / "profiles.json"
DEFAULT_VIDEO_PATH = Path.home() / ".config" / "Titans-launcher" / "background.mp4"
CONTROLLER_INPUTS_DIR = PROJECT_ROOT / "Settings" / "Inputs"
DEFAULT_CONTROLLER_BINDINGS = {
    "up": ["hat:up", "axis:1:negative"],
    "down": ["hat:down", "axis:1:positive"],
    "left": ["hat:left", "axis:0:negative"],
    "right": ["hat:right", "axis:0:positive"],
    "select": ["button:0"],
    "back": ["button:1"],
    "previous_tab": ["button:4"],
    "next_tab": ["button:5"],
    "close_app": ["button:8"],
}

DEFAULT_CONFIG = {
    "_advanced_mode": False,
    "_background_path": str(DEFAULT_VIDEO_PATH),
    "_theme": "Crimson Red",
    "_button_shape": "Rounded Square",
    "_enable_animations": True,
    "_enable_glitch": False,
    "_ntp_server": "nz.pool.ntp.org",
    "_ntp_country": "New Zealand",
    "_ntp_offset": 12,
    "_time_format": "12-Hour (AM/PM)",
    "_power_command": "systemctl poweroff",
    "_sleep_command": "systemctl suspend",
    "_restart_command": "systemctl reboot",
    "_power_icon_path": "",
    "_custom_colors": {
        "Crimson Red": "#DC143C",
        "Cyberpunk Blue": "#00F0FF",
        "Emerald Green": "#00C853",
        "Purple Neon": "#AA00FF",
    },
    "Jellyfin": {
        "command": "Jellyfin",
        "arguments": "",
        "manage_antimicrox": True,
        "profile": str(Path.home() / ".config/antimicrox/retro.amxp"),
        "icon_path": "",
    },
    "Moonlight": {
        "command": "moonlight",
        "arguments": "",
        "manage_antimicrox": False,
        "profile": "",
        "icon_path": "",
    },
    "Youtube": {
        "command": "firefox",
        "arguments": "--kiosk https://www.youtube.com",
        "type": "website",
        "website_url": "https://www.youtube.com",
        "manage_antimicrox": True,
        "profile": "",
        "controller_close_enabled": False,
        "icon_path": "",
    },
    "Google TV": {
        "command": "firefox",
        "arguments": "--kiosk https://tv.google/",
        "type": "website",
        "website_url": "https://tv.google/",
        "manage_antimicrox": True,
        "profile": "",
        "controller_close_enabled": False,
        "icon_path": "",
    },
}


def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG)
        log_info(f"Initialized default configuration at {CONFIG_PATH}")
        return DEFAULT_CONFIG
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
        migration_defaults = {
            "_advanced_mode": False,
            "_background_path": str(DEFAULT_VIDEO_PATH),
            "_theme": "Crimson Red",
            "_button_shape": "Rounded Square",
            "_enable_animations": True,
            "_enable_glitch": False,
            "_ntp_server": "nz.pool.ntp.org",
            "_ntp_country": "New Zealand",
            "_ntp_offset": 12,
            "_time_format": "12-Hour (AM/PM)",
            "_power_command": "systemctl poweroff",
            "_sleep_command": "systemctl suspend",
            "_restart_command": "systemctl reboot",
            "_power_icon_path": "",
            "_custom_colors": DEFAULT_CONFIG["_custom_colors"],
        }
        for key, value in migration_defaults.items():
            if key not in data or (key == "_theme" and data[key] == "Netflix Red"):
                data[key] = value

        for key, value in data.items():
            if not key.startswith("_") and isinstance(value, dict):
                value.setdefault("arguments", "")
        log_info(f"Loaded configuration successfully from {CONFIG_PATH}")
        return data
    except Exception as error:
        log_error(f"Error parsing configuration file {CONFIG_PATH}: {error}", details=str(error))
        return DEFAULT_CONFIG


def save_config(data):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
            json.dump(data, config_file, indent=4)
        log_info(f"Configuration saved to {CONFIG_PATH}")
    except Exception as error:
        log_error(f"Failed to save configuration: {error}", details=str(error))
