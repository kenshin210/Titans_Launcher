from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTabWidget

from Application.ui.Settings.Logger import log_warning


def _tab_colors(theme_color):
    color = QColor(theme_color) if isinstance(theme_color, str) else QColor()
    if not color.isValid() or color.alpha() != 255:
        log_warning(f"Invalid or transparent tab theme color {theme_color!r}; using Crimson Red.")
        color = QColor("#DC143C")

    def linear(channel):
        value = channel / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    luminance = (
        0.2126 * linear(color.red())
        + 0.7152 * linear(color.green())
        + 0.0722 * linear(color.blue())
    )
    text_color = "#000000" if (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05) else "#ffffff"
    return color.name(), text_color


def tab_widget_stylesheet(theme_color):
    background, foreground = _tab_colors(theme_color)
    return f"""
        QTabWidget::pane {{
            border: 1px solid rgba(255, 255, 255, 25);
            background: rgba(18, 18, 18, 220);
            border-radius: 10px;
        }}
        QTabBar::tab {{
            background: rgba(35, 35, 35, 180);
            color: #bbb;
            padding: 10px 22px;
            margin-right: 4px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-size: 14px;
            font-weight: bold;
        }}
        QTabBar::tab:selected {{
            background: {background};
            color: {foreground};
        }}
    """


def update_tab_styles(root, theme_color):
    stylesheet = tab_widget_stylesheet(theme_color)
    for tab in root.findChildren(QTabWidget):
        tab.setStyleSheet(stylesheet)
