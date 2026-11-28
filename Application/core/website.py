"""Display modes for Firefox website shortcuts."""

WEBSITE_DISPLAY_MODES = {
    "windowed": "Normal window",
    "maximized": "Maximized window",
    "fullscreen": "Fullscreen (KDE Wayland)",
    "kiosk": "Kiosk",
}


def website_arguments(mode, url):
    if not isinstance(mode, str) or mode not in WEBSITE_DISPLAY_MODES:
        raise ValueError(f"Unknown website display mode: {mode!r}")
    flags = {
        "windowed": [],
        "maximized": ["--start-maximized"],
        "fullscreen": [],
        "kiosk": ["--kiosk"],
    }
    return [*flags[mode], url]
