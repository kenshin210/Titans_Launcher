import re

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QTabBar, QWidget

from Application.core.accessibility import (
    FOCUS_BOLD,
    FOCUS_OFF,
    FOCUS_SUBTLE,
    focus_indicator_mode,
)
from Application.core.corner_style import corner_radius


_RADIUS_RE = re.compile(r"(?<![-\w])border-radius\s*:\s*([\d.]+)(px|%)")


def widget_corner_radius(widget, default=6):
    """Corner radius of a styled widget so the focus ring follows its shape."""
    match = _RADIUS_RE.search(widget.styleSheet()) if widget is not None else None
    if match is None:
        return corner_radius(default)
    value = float(match.group(1))
    if match.group(2) == "%":
        value = min(widget.width(), widget.height()) * value / 100
    return min(value, min(widget.width(), widget.height()) / 2)


def has_own_focus_style(widget):
    """True when the widget (or an inherited sheet) already styles :focus itself."""
    sheets = [QApplication.instance().styleSheet()]
    ancestor = widget
    while ancestor is not None:
        sheets.append(ancestor.styleSheet())
        ancestor = ancestor.parentWidget()
    name = widget.objectName()
    for sheet in sheets:
        if not sheet:
            continue
        if not name and ":focus" in sheet and sheet is widget.styleSheet():
            return True
        if name and f"#{name}:focus" in sheet:
            return True
    return False


class SettingsFocusOverlay(QWidget):
    """Draw a focus cue above an interface scope without changing its styles."""

    def __init__(self, settings, scope=None):
        super().__init__(settings)
        self.settings = settings
        self.scope = scope or getattr(settings, "pages", settings)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.radius = 6
        self.hide()
        QApplication.instance().focusChanged.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(100)

    def refresh(self, *_args):
        focused = QApplication.focusWidget()
        launcher = self.settings
        if not hasattr(launcher, "get_theme_color"):
            launcher = getattr(self.settings, "launcher", launcher)
        config = getattr(launcher, "config", {})
        if (
            focused is None
            or not self.settings.isVisible()
            or not self.scope.isAncestorOf(focused)
            or not focused.isVisible()
            or has_own_focus_style(focused)
            or focus_indicator_mode(config or {}) == FOCUS_OFF
        ):
            self.hide()
            return

        rect = focused.rect()
        if isinstance(focused, QTabBar):
            rect = focused.tabRect(focused.currentIndex())
        rect.moveTopLeft(focused.mapTo(self.settings, rect.topLeft()))
        visible = QRect(rect)
        ancestor = focused.parentWidget()
        while ancestor is not None and ancestor is not self.settings:
            bounds = QRect(ancestor.mapTo(self.settings, ancestor.rect().topLeft()), ancestor.size())
            visible = visible.intersected(bounds)
            ancestor = ancestor.parentWidget()
        if visible.isEmpty():
            self.hide()
            return

        self.radius = widget_corner_radius(focused)
        geometry = visible.adjusted(-5, -5, 5, 5).intersected(self.settings.rect())
        changed = self.geometry() != geometry or self.isHidden()
        if self.geometry() != geometry:
            self.setGeometry(geometry)
        if self.isHidden():
            self.show()
        if changed or _args:
            self.raise_()
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        launcher = self.settings
        if not hasattr(launcher, "get_theme_color"):
            launcher = getattr(self.settings, "launcher", launcher)
        config = getattr(launcher, "config", {})
        color = (
            QColor("#FFFF00")
            if config.get("_high_contrast", False)
            else QColor(getattr(launcher, "get_theme_color", lambda: "#DC143C")())
        )
        mode = focus_indicator_mode(config)
        if mode == FOCUS_BOLD:
            for inset, alpha in ((1, 25), (2, 45), (3, 75)):
                ring = QColor(color)
                ring.setAlpha(alpha)
                painter.setPen(QPen(ring, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(
                    self.rect().adjusted(inset, inset, -inset - 1, -inset - 1),
                    self.radius + 5 - inset,
                    self.radius + 5 - inset,
                )
            ring = QColor(color)
            ring.setAlpha(235)
            painter.setPen(QPen(ring, 3))
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.drawRoundedRect(self.rect().adjusted(5, 5, -6, -6), self.radius, self.radius)
            return
        # Subtle and Standard draw one thin ring just outside the widget edge.
        gap = 1 if mode == FOCUS_SUBTLE else 2
        ring = QColor(color)
        ring.setAlpha(190 if mode == FOCUS_SUBTLE else 235)
        painter.setPen(QPen(ring, 1.5 if mode == FOCUS_SUBTLE else 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            self.rect().adjusted(5 - gap, 5 - gap, gap - 6, gap - 6),
            self.radius + gap,
            self.radius + gap,
        )
