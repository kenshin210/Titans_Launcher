"""Global button style (shape, border, fill, hover) driven by one setting.

Button stylesheets are written all over the UI, so instead of editing each one
the declarations that define a button's look are rewritten when a stylesheet is
applied (see ``corner_style``). The accent colour is never overridden.
"""
import re

DEFAULT_BUTTON_STYLE = {
    "border_width": 2,
    "border_color": "Subtle",
    "fill": "Translucent",
    "hover": "Accent Border",
}
SHAPES = ("Rounded Square", "Pill", "Circle", "Sharp")
BORDER_COLORS = ("Subtle", "Accent", "White", "None")
FILLS = ("Translucent", "Solid", "Outline")
HOVERS = ("Accent Border", "Brighten", "Accent Fill")
BORDER_WIDTHS = (1, 2, 3, 4)

_SUBTLE = "rgba(255, 255, 255, 25)"
_STATE_RE = re.compile(r":(hover|focus|pressed|checked|on)\b")
_RULE_RE = re.compile(r"([^{}]*)\{([^{}]*)\}")
_RADIUS_RE = re.compile(r"(?<![-\w])border-radius\s*:\s*([^;}]+)")
_BORDER_RE = re.compile(r"(?<![-\w])border\s*:\s*(\d+)px\s+solid\s+([^;}]+)")
_BG_RE = re.compile(r"(?<![-\w])background-color\s*:\s*rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
_BUTTON_SELECTOR = re.compile(r"Button")

_state = {"shape": "Rounded Square", "style": dict(DEFAULT_BUTTON_STYLE), "accent": "#DC143C"}


def normalize_style(style):
    merged = dict(DEFAULT_BUTTON_STYLE)
    if isinstance(style, dict):
        merged.update({key: style[key] for key in DEFAULT_BUTTON_STYLE if key in style})
    if merged["border_color"] not in BORDER_COLORS:
        merged["border_color"] = DEFAULT_BUTTON_STYLE["border_color"]
    if merged["fill"] not in FILLS:
        merged["fill"] = DEFAULT_BUTTON_STYLE["fill"]
    if merged["hover"] not in HOVERS:
        merged["hover"] = DEFAULT_BUTTON_STYLE["hover"]
    try:
        merged["border_width"] = min(max(int(merged["border_width"]), 1), 4)
    except (TypeError, ValueError):
        merged["border_width"] = DEFAULT_BUTTON_STYLE["border_width"]
    return merged


def set_button_style(shape, style, accent=None):
    if accent:
        _state["accent"] = accent
    _state["shape"] = shape if shape in SHAPES else "Rounded Square"
    _state["style"] = normalize_style(style)


def current():
    return _state["shape"], dict(_state["style"])


def tile_radius(shape):
    """Radius for launcher tiles and the main bar buttons."""
    return {"Circle": "50%", "Sharp": "0px", "Pill": "60px"}.get(shape, "28px")


def bar_radius(shape):
    """Use a radius that fits the short, text-bearing launcher buttons."""
    return {"Circle": "22px", "Sharp": "0px", "Pill": "22px"}.get(shape, "12px")


def _is_accent(color, accent):
    return color.strip().lower() == accent.lower()


def _neutral_dark(r, g, b):
    return max(r, g, b) <= 90 and max(r, g, b) - min(r, g, b) <= 12


def _accent_rgba(accent, alpha):
    accent = accent.lstrip("#")
    if len(accent) != 6:
        return f"rgba(220, 20, 60, {alpha})"
    return "rgba({}, {}, {}, {})".format(*(int(accent[i:i + 2], 16) for i in (0, 2, 4)), alpha)


def _rewrite_declarations(body, is_state, shape, style, accent, pill_radius):
    def radius(match):
        value = match.group(1).strip()
        if shape == "Sharp":
            return "border-radius: 0px"
        if shape == "Pill" and "%" not in value:
            return f"border-radius: {pill_radius}px"
        return match.group(0)

    def border(match):
        width, color = int(match.group(1)), match.group(2).strip()
        if is_state:
            if _is_accent(color, accent):
                return f"border: {style['border_width'] + 1}px solid {color}"
            return match.group(0)
        if _is_accent(color, accent):
            return match.group(0)
        chosen = {
            "Subtle": _SUBTLE,
            "Accent": accent,
            "White": "rgba(255, 255, 255, 90)",
            "None": "transparent",
        }[style["border_color"]]
        return f"border: {style['border_width']}px solid {chosen}"

    def background(match):
        r, g, b, a = (int(group) for group in match.groups())
        if not _neutral_dark(r, g, b):
            return match.group(0)
        if is_state:
            if style["fill"] == "Outline":
                return "background-color: rgba(255, 255, 255, 20)"
            if style["hover"] == "Accent Fill":
                return f"background-color: {_accent_rgba(accent, 110)}"
            return match.group(0)
        if style["fill"] == "Outline":
            return "background-color: transparent"
        if style["fill"] == "Solid":
            return f"background-color: rgba({r}, {g}, {b}, 255)"
        return match.group(0)

    body = _RADIUS_RE.sub(radius, body)
    body = _BORDER_RE.sub(border, body)
    return _BG_RE.sub(background, body)


def transform_stylesheet(css, is_button, accent=None, shape=None, style=None, pill_radius=22):
    """Return ``css`` rewritten for the button style (defaults to current)."""
    accent = accent or _state["accent"]
    shape = shape or _state["shape"]
    style = normalize_style(style) if style is not None else _state["style"]
    if "{" not in css:
        if not is_button:
            return css
        return _rewrite_declarations(css, False, shape, style, accent, pill_radius)

    def rule(match):
        selector, body = match.group(1), match.group(2)
        if not (is_button or _BUTTON_SELECTOR.search(selector)):
            return match.group(0)
        is_state = bool(_STATE_RE.search(selector))
        return f"{selector}{{{_rewrite_declarations(body, is_state, shape, style, accent, pill_radius)}}}"

    return _RULE_RE.sub(rule, css)
