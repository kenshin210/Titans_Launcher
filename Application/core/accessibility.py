"""Accessibility preference helpers shared by the launcher and settings pages."""

TEXT_SCALES = (100, 110, 125, 150, 175, 200)
FOCUS_OFF, FOCUS_SUBTLE, FOCUS_STANDARD, FOCUS_BOLD = "Off", "Subtle", "Standard", "Bold"
FOCUS_MODES = (FOCUS_OFF, FOCUS_SUBTLE, FOCUS_STANDARD, FOCUS_BOLD)
LEGACY_LARGE_TEXT_SCALE = 125


def text_scale_percent(config):
    """Interface text scale in percent, honouring the legacy large-text flag."""
    value = config.get("_text_scale")
    if value is None:
        return LEGACY_LARGE_TEXT_SCALE if config.get("_large_text", False) else 100
    try:
        return max(50, min(300, int(value)))
    except (TypeError, ValueError):
        return 100


def focus_indicator_mode(config):
    """Focus indicator style, honouring the legacy on/off flag."""
    value = config.get("_focus_indicator")
    if value in FOCUS_MODES:
        return value
    return FOCUS_STANDARD if config.get("_show_focus_indicators", True) else FOCUS_OFF
