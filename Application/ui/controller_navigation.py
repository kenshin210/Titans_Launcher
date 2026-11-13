"""Controller handling for standard Qt widgets, so every screen is usable without a mouse."""

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QMenu,
    QTabBar,
    QTabWidget,
)

from Application.ui.dialogs.on_screen_keyboard import OnScreenKeyboard, focused_text_field

POPUP_KEYS = {
    "up": Qt.Key.Key_Up,
    "down": Qt.Key.Key_Down,
    "select": Qt.Key.Key_Return,
    "back": Qt.Key.Key_Escape,
}


def _send_key(target, key):
    for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(target, QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier))


def handle_popup_input(action, ignore=None):
    """Drive an open combo box list or context menu. Returns True when consumed."""
    popup = QApplication.activePopupWidget()
    if popup is None or popup is ignore:
        return False
    key = POPUP_KEYS.get(action)
    if key is None:
        return True
    target = popup
    if not isinstance(popup, QMenu):
        views = popup.findChildren(QAbstractItemView)
        if views:
            target = views[0]
    _send_key(target, key)
    return True


def handle_modal_input(action):
    """Let a modal dialog handle controller actions itself, or fall back to focus movement."""
    dialog = QApplication.activeModalWidget()
    if dialog is None:
        return False
    handler = getattr(dialog, "handle_controller_action", None)
    if callable(handler):
        return bool(handler(action))
    if action == "up":
        dialog.focusPreviousChild()
        return True
    if action == "down":
        dialog.focusNextChild()
        return True
    return False


def handle_home_navigation(launcher, action):
    """Navigate the home screen by row while retaining a horizontal cycle."""
    if action not in ("up", "down", "left", "right"):
        return False
    if launcher.home_tabs.currentWidget() is not launcher.home_tab:
        return False

    def available(widget):
        return (
            widget is not None
            and widget.isVisible()
            and widget.isEnabled()
            and bool(widget.focusPolicy() & Qt.FocusPolicy.TabFocus)
        )

    tiles = [
        launcher.apps_layout.itemAt(index).widget()
        for index in range(launcher.apps_layout.count())
    ]
    tiles = [tile for tile in tiles if available(tile)]
    power = [launcher.power_btn] if available(launcher.power_btn) else []
    weather = launcher.weather_label if available(launcher.weather_label) else None
    clock = launcher.clock_label if available(launcher.clock_label) else None
    settings = launcher.config_btn if available(launcher.config_btn) else None
    bottom = [widget for widget in (weather, clock, settings) if widget is not None]
    sequence = power + tiles + bottom
    focused = QApplication.focusWidget()
    if focused not in sequence:
        return False

    if action in ("left", "right"):
        direction = 1 if action == "right" else -1
        sequence[(sequence.index(focused) + direction) % len(sequence)].setFocus()
        return True

    def nearest_horizontal(candidates):
        x = focused.mapToGlobal(focused.rect().center()).x()
        return min(candidates, key=lambda widget: abs(widget.mapToGlobal(widget.rect().center()).x() - x))

    if focused is weather and action == "down" and clock is not None:
        target = clock
    elif focused is clock and action == "up" and weather is not None:
        target = weather
    elif focused in power:
        candidates = tiles or bottom
        target = nearest_horizontal(candidates) if action == "down" and candidates else None
    elif focused in tiles:
        first_bottom = weather if weather is not None else clock
        candidates = power if action == "up" else [
            widget for widget in (first_bottom, settings) if widget is not None
        ]
        target = nearest_horizontal(candidates) if candidates else None
    else:
        candidates = tiles or power
        target = nearest_horizontal(candidates) if action == "up" and candidates else None
    if target is not None:
        target.setFocus()
    return True


def handle_settings_navigation(settings, action):
    """Keep sidebar navigation separate from controls on the selected page."""
    focused = QApplication.focusWidget()
    sidebar = [*settings.nav_buttons, settings.mode_toggle_btn, settings.back_btn]
    if focused in sidebar:
        index = sidebar.index(focused)
        if action in ("up", "down"):
            index = max(0, min(len(sidebar) - 1, index + (1 if action == "down" else -1)))
            sidebar[index].setFocus()
            if index < len(settings.nav_buttons):
                settings.switch_tab(index)
            return True
        if action == "right":
            page = settings.pages.currentWidget()
            if isinstance(page, QTabWidget) and page.count() > 1:
                page.tabBar().setFocus()
                return True
            widget = page
            while True:
                widget = widget.nextInFocusChain()
                if widget is page:
                    break
                if (
                    page.isAncestorOf(widget)
                    and widget.isVisibleTo(page)
                    and widget.isEnabled()
                    and widget.focusPolicy() & Qt.FocusPolicy.TabFocus
                    and not isinstance(widget, QTabBar)
                ):
                    widget.setFocus()
                    if QApplication.focusWidget() is not focused:
                        break
            return True
    elif focused is not None and settings.pages.isAncestorOf(focused):
        if action in ("left", "right", "up", "down") and handle_focused_widget_input(action):
            return True
        if action in ("left", "back"):
            settings.focus_current_menu_item()
            return True
        if action in ("up", "down", "right"):
            page = settings.pages.currentWidget()
            widget = focused
            while True:
                widget = widget.previousInFocusChain() if action == "up" else widget.nextInFocusChain()
                if widget is focused:
                    break
                if (
                    page.isAncestorOf(widget)
                    and widget.isVisibleTo(page)
                    and widget.isEnabled()
                    and widget.focusPolicy() & Qt.FocusPolicy.TabFocus
                ):
                    widget.setFocus()
                    if QApplication.focusWidget() is not focused:
                        break
            return True
    return False


def _move_in_view(view, step):
    """Move the current row; False when already at the edge so focus can move on."""
    model = view.model()
    if model is None or model.rowCount() == 0:
        return False
    current = view.currentIndex()
    if not current.isValid():
        view.setCurrentIndex(model.index(0, 0))
        return True
    row = current.row() + step
    if row < 0 or row >= model.rowCount():
        return False
    view.setCurrentIndex(model.index(row, current.column()))
    view.scrollTo(view.currentIndex())
    return True


def handle_focused_widget_input(action):
    """Controller behaviour for the focused widget. Returns True when it consumed the action."""
    widget = QApplication.focusWidget()
    if widget is None:
        return False

    if isinstance(widget, QTabBar) and action in ("left", "right"):
        key = Qt.Key.Key_Left if action == "left" else Qt.Key.Key_Right
        _send_key(widget, key)
        return True

    # Item views live inside a scroll-area viewport, so the focus widget is the view itself.
    if isinstance(widget, QAbstractItemView):
        if action in ("up", "down"):
            return _move_in_view(widget, -1 if action == "up" else 1)
        if action == "select":
            index = widget.currentIndex()
            if index.isValid():
                widget.activated.emit(index)
                widget.doubleClicked.emit(index)
                return True
        return False

    if isinstance(widget, QAbstractSlider):
        if action in ("left", "right"):
            widget.setValue(widget.value() + (widget.singleStep() or 1) * (1 if action == "right" else -1))
            return True
        return False

    if isinstance(widget, QAbstractSpinBox):
        if action in ("left", "right"):
            widget.stepBy(1 if action == "right" else -1)
            return True
        return False

    if isinstance(widget, QComboBox):
        if action == "select":
            widget.showPopup()
            return True
        if action in ("left", "right"):
            count = widget.count()
            if count:
                widget.setCurrentIndex((widget.currentIndex() + (1 if action == "right" else -1)) % count)
                return True
        return False

    if isinstance(widget, QAbstractButton):
        if action == "select":
            widget.click()
            return True
        return False

    field = focused_text_field()
    if field is not None and action == "select":
        _, accepted = OnScreenKeyboard.get_text(
            field.window(),
            field.placeholderText() or "Enter text",
            field.text(),
            field.echoMode() != QLineEdit.EchoMode.Normal,
            target_field=field,
        )
        return True

    if isinstance(widget, QAbstractScrollArea) and action in ("up", "down"):
        bar = widget.verticalScrollBar()
        if bar.maximum() > bar.minimum():
            before = bar.value()
            bar.setValue(before + (bar.singleStep() * 3) * (1 if action == "down" else -1))
            return bar.value() != before
    return False
