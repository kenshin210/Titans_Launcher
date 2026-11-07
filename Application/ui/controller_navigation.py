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
        text, accepted = OnScreenKeyboard.get_text(
            field.window(),
            field.placeholderText() or "Enter text",
            field.text(),
            field.echoMode() != QLineEdit.EchoMode.Normal,
        )
        if accepted:
            field.setText(text)
        return True

    if isinstance(widget, QAbstractScrollArea) and action in ("up", "down"):
        bar = widget.verticalScrollBar()
        if bar.maximum() > bar.minimum():
            before = bar.value()
            bar.setValue(before + (bar.singleStep() * 3) * (1 if action == "down" else -1))
            return bar.value() != before
    return False
