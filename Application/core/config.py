import json
from pathlib import Path

from Application.ui.Settings.Logger import log_error, log_info


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "Assets"
CONFIG_PATH = Path.home() / ".config" / "Titans-launcher" / "profiles.json"
DEFAULT_VIDEO_PATH = ASSETS_DIR / "Videos" / "background.mp4"
CONTROLLER_INPUTS_DIR = ASSETS_DIR / "Inputs"
DEFAULT_APP_ICONS = {
    "Youtube": str(ASSETS_DIR / "Icons" / "youtube.svg"),
    "Google TV": str(ASSETS_DIR / "Icons" / "google-tv.png"),
}
DEFAULT_CONTROLLER_BINDINGS = {
    "up": ["hat:up", "axis:1:negative"],
    "down": ["hat:down", "axis:1:positive"],
    "left": ["hat:left", "axis:0:negative"],
    "right": ["hat:right", "axis:0:positive"],
    "select": ["button:0"],
    "back": ["button:1"],
    "previous_tab": ["button:4"],
    "next_tab": ["button:5"],
    "control_centre": [],
    "close_app": ["button:8"],
}

DEFAULT_CONFIG = {
    "_advanced_mode": False,
    "_background_path": str(DEFAULT_VIDEO_PATH),
    "_startup_image_path": "",
    "_startup_background_color": "#141414",
    "_startup_loading_text": "Starting Titans...",
    "_startup_image_fit": "Fit",
    "_theme": "Crimson Red",
    "_button_shape": "Rounded Square",
    "_corner_style": "Rounded",
    "_button_style": {"border_width": 2, "border_color": "Subtle", "fill": "Translucent", "hover": "Accent Border"},
    "_enable_animations": True,
    "_reduce_motion": False,
    "_high_contrast": False,
    "_large_text": False,
    "_show_focus_indicators": True,
    "_text_scale": 100,
    "_focus_indicator": "Standard",
    "_control_centre_shortcut": "Ctrl+Shift+Space",
    "_show_control_centre_button": False,
    "_browser_cursor_sensitivity": 18,
    "_keyboard_background_color": "#141414",
    "_keyboard_background_image": "",
    "_keyboard_background_opacity": 96,
    "_keyboard_key_color": "#30343c",
    "_keyboard_special_key_color": "#464c56",
    "_keyboard_key_text_color": "#ffffff",
    "_launcher_update_branch": "Stable",
    "_launcher_custom_repository": "",
    "_launcher_custom_branch": "main",
    "_active_home_profile": "Default",
    "_home_profiles": {"Default": {"order": [], "hidden": []}},
    "_enable_glitch": False,
    "_ntp_server": "nz.pool.ntp.org",
    "_ntp_country": "New Zealand",
    "_ntp_offset": 12,
    "_weather_city": "",
    "_weather_country": "",
    "_weather_temperature_unit": "Celsius",
    "_module_applications": False,
    "_proxy_mode": "Off",
    "_proxy_http": "",
    "_proxy_https": "",
    "_proxy_socks": "",
    "_proxy_no_proxy": "",
    "_ntp_dst": False,
    "_ntp_auto_dst": True,
    "_ntp_timezone": "",
    "_time_format": "12-Hour (AM/PM)",
    "_sudo_cache_enabled": False,
    "_sudo_cache_ttl_minutes": 15,
    "_privilege_prefer_polkit": True,
    "_power_command": "systemctl poweroff",
    "_sleep_command": "systemctl suspend",
    "_restart_command": "systemctl reboot",
    "_power_icon_path": "",
    "_nav_sound_enabled": True,
    "_nav_sound_choice": "Tick",
    "_nav_sound_custom_path": "",
    "_nav_sound_volume": 60,
    "_battery_device_address": "",
    "_battery_device_name": "",
    "_battery_short_name": "",
    "_custom_colors": {
        "Crimson Red": "#DC143C",
        "Cyberpunk Blue": "#00F0FF",
        "Emerald Green": "#00C853",
        "Purple Neon": "#AA00FF",
        "Colorblind Blue": "#0072B2",
        "Colorblind Orange": "#E69F00",
        "Colorblind Purple": "#CC79A7",
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
        "icon_path": DEFAULT_APP_ICONS["Youtube"],
    },
    "Google TV": {
        "command": "firefox",
        "arguments": "--kiosk https://tv.google/",
        "type": "website",
        "website_url": "https://tv.google/",
        "manage_antimicrox": True,
        "profile": "",
        "controller_close_enabled": False,
        "icon_path": DEFAULT_APP_ICONS["Google TV"],
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
            "_startup_image_path": "",
            "_startup_background_color": "#141414",
            "_startup_loading_text": "Starting Titans...",
            "_startup_image_fit": "Fit",
            "_theme": "Crimson Red",
            "_button_shape": "Rounded Square",
            "_corner_style": "Rounded",
            "_button_style": {"border_width": 2, "border_color": "Subtle", "fill": "Translucent", "hover": "Accent Border"},
            "_enable_animations": True,
            "_reduce_motion": False,
            "_high_contrast": False,
            "_large_text": False,
            "_show_focus_indicators": True,
            "_control_centre_shortcut": "Ctrl+Shift+Space",
            "_show_control_centre_button": False,
            "_browser_cursor_sensitivity": 18,
            "_keyboard_background_color": "#141414",
            "_keyboard_background_image": "",
            "_keyboard_background_opacity": 96,
            "_keyboard_key_color": "#30343c",
            "_keyboard_special_key_color": "#464c56",
            "_keyboard_key_text_color": "#ffffff",
            "_launcher_update_branch": "Stable",
            "_launcher_custom_repository": "",
            "_launcher_custom_branch": "main",
            "_active_home_profile": "Default",
            "_home_profiles": {"Default": {"order": [], "hidden": []}},
            "_enable_glitch": False,
            "_ntp_server": "nz.pool.ntp.org",
            "_ntp_country": "New Zealand",
            "_ntp_offset": 12,
            "_weather_city": "",
            "_weather_country": "",
            "_weather_temperature_unit": "Celsius",
            "_module_applications": False,
            "_proxy_mode": "Off",
            "_proxy_http": "",
            "_proxy_https": "",
            "_proxy_socks": "",
            "_proxy_no_proxy": "",
            "_ntp_dst": False,
            "_ntp_auto_dst": True,
            "_ntp_timezone": "",
            "_time_format": "12-Hour (AM/PM)",
            "_power_command": "systemctl poweroff",
            "_sleep_command": "systemctl suspend",
            "_restart_command": "systemctl reboot",
            "_power_icon_path": "",
            "_nav_sound_enabled": True,
            "_nav_sound_choice": "Tick",
            "_nav_sound_custom_path": "",
            "_nav_sound_volume": 60,
            "_battery_device_address": "",
            "_battery_device_name": "",
            "_battery_short_name": "",
        }
        for key, value in migration_defaults.items():
            if key not in data or (key == "_theme" and data[key] == "Netflix Red"):
                data[key] = value
        data["_custom_colors"] = {
            **DEFAULT_CONFIG["_custom_colors"],
            **(data.get("_custom_colors") if isinstance(data.get("_custom_colors"), dict) else {}),
        }

        for key, value in data.items():
            if not key.startswith("_") and isinstance(value, dict):
                value.setdefault("arguments", "")
                if key in DEFAULT_APP_ICONS and not value.get("icon_path"):
                    value["icon_path"] = DEFAULT_APP_ICONS[key]
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
