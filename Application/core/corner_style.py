"""Global Rounded/Sharp corner style.

Widgets set their own stylesheets with fixed ``border-radius`` values, so Sharp
mode rewrites those values whenever a stylesheet is applied. The original
stylesheet is remembered so the style can be switched at runtime.
"""
import re

from PyQt6.QtWidgets import QApplication, QPushButton, QToolButton, QWidget

from Application.core import button_style

ROUNDED = "Rounded"
SHARP = "Sharp"
CORNER_STYLES = (ROUNDED, SHARP)

_RADIUS_RE = re.compile(r"(border(?:-[a-z]+){0,2}-radius\s*:)\s*[^;}]+")
_state = {"sharp": False, "installed": False}
_original_set_style_sheet = QWidget.setStyleSheet


def is_sharp():
    return _state["sharp"]


def sharpen_stylesheet(css):
    return _RADIUS_RE.sub(r"\1 0px", css)


def corner_radius(radius):
    """Radius for custom painting: ``radius`` when rounded, 0 when sharp."""
    return 0 if _state["sharp"] else radius


def _pill_radius(widget):
    # Qt ignores radii larger than half the widget, so tiles need a bigger value than bars.
    return 60 if isinstance(widget, QToolButton) else 22


def _apply(widget, css):
    css = button_style.transform_stylesheet(
        css, isinstance(widget, (QPushButton, QToolButton)), pill_radius=_pill_radius(widget)
    )
    if _state["sharp"] and "radius" in css:
        css = sharpen_stylesheet(css)
    _original_set_style_sheet(widget, css)


def apply_preview(widget, css, accent, shape, style):
    """Style ``widget`` with unsaved button settings (the app-wide state is untouched)."""
    css = button_style.transform_stylesheet(
        css, isinstance(widget, (QPushButton, QToolButton)), accent, shape, style, _pill_radius(widget)
    )
    if _state["sharp"]:
        css = sharpen_stylesheet(css)
    _original_set_style_sheet(widget, css)


def _set_style_sheet(widget, css):
    widget.setProperty("_original_stylesheet", css)
    _apply(widget, css)


def install():
    if not _state["installed"]:
        QWidget.setStyleSheet = _set_style_sheet
        _state["installed"] = True


def set_corner_style(style):
    """Switch style and restyle every existing widget."""
    _state["sharp"] = style == SHARP
    restyle_all()


def restyle_all():
    install()
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.allWidgets():
        original = widget.property("_original_stylesheet")
        if original:
            _apply(widget, original)
        widget.update()
