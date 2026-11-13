from PyQt6.QtCore import QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from Application.ui.dialogs.file_picker import resolve_theme_color
from Application.ui.Settings.Logger import log_warning

KEYBOARD_PAGES = {
    "letters": [
        list("qwertyuiop"),
        list("asdfghjkl"),
        ["SHIFT", *list("zxcvbnm"), "BACKSPACE"],
        ["PAGE_SYMBOLS", ",", "SPACE", ".", "ENTER"],
    ],
    "symbols": [
        list("1234567890"),
        list("@#$%&-+()"),
        ["*", '"', "'", ":", ";", "!", "?", "BACKSPACE"],
        ["PAGE_SYMBOLS_MORE", ",", "SPACE", ".", "ENTER"],
    ],
    "symbols_more": [
        ["[", "]", "{", "}", "<", ">", "\\", "|", "~", "`"],
        ["_", "^", "%", "&", "*", "-", "+", "=", "/", ";"],
        ["#", "$", "'", '"', ":", "!", "?", "BACKSPACE"],
        ["PAGE_LETTERS", ",", "SPACE", ".", "ENTER"],
    ],
}
SPECIAL_KEY_TOKENS = {
    "SHIFT", "BACKSPACE", "SPACE", "ENTER",
    "PAGE_SYMBOLS", "PAGE_SYMBOLS_MORE", "PAGE_LETTERS",
}
SHIFT_SYMBOLS = {
    **dict(zip("1234567890", "!@#$%^&*()")),
    "'": '"', ",": "<", ".": ">", "-": "+", "/": "\\", ":": "=",
    ";": "*", "_": "~", "[": "{", "]": "}",
}


def _keyboard_config(parent):
    widget = parent
    while widget is not None:
        owner = getattr(widget, "launcher", widget)
        config = getattr(owner, "config", None)
        if isinstance(config, dict):
            return config
        widget = widget.parentWidget()
    return {}


def _keyboard_color(config, key, default):
    try:
        color = QColor(config.get(key, default))
    except TypeError:
        color = QColor()
    if not color.isValid():
        log_warning(f"Invalid keyboard color for {key}; using {default}.")
        return QColor(default)
    return color


class KeyboardCard(QWidget):
    def __init__(self, image, color, opacity, parent=None):
        super().__init__(parent)
        self.image = image
        self.color = color
        self.opacity = opacity

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.image.isNull():
            return
        canvas = QPixmap(self.size())
        canvas.fill(self.color)
        image = self.image.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(canvas)
        painter.drawPixmap((self.width() - image.width()) // 2, (self.height() - image.height()) // 2, image)
        painter.end()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 12, 12)
        painter.setClipPath(clip)
        painter.setOpacity(self.opacity / 255)
        painter.drawPixmap(0, 0, canvas)


class OnScreenKeyboard(QDialog):
    """Controller-driven text entry.

    D-pad moves over the rounded keys, A types, LB deletes, and RB adds a space.
    The page key switches between letters and symbols; a physical keyboard also works.
    """

    input_failed = pyqtSignal(object)

    def __init__(
        self, parent=None, title="Enter text", text="", password=False, theme_color=None,
        target_field=None, input_device=None, background_color=None, appearance=None,
    ):
        super().__init__(parent)
        theme_color = theme_color or resolve_theme_color(parent)
        config = appearance if isinstance(appearance, dict) else _keyboard_config(parent)
        if background_color is None:
            card_color = _keyboard_color(config, "_keyboard_background_color", "#141414")
        else:
            card_color = _keyboard_color({"color": background_color}, "color", "#141414")
        try:
            opacity = max(0, min(100, int(config.get("_keyboard_background_opacity", 96))))
        except (TypeError, ValueError, OverflowError):
            log_warning("Invalid keyboard background opacity; using 96%.")
            opacity = 96
        opacity_alpha = round(opacity * 255 / 100)
        image_path = config.get("_keyboard_background_image", "")
        if not isinstance(image_path, str):
            log_warning("Invalid keyboard background image setting; using background color.")
            image_path = ""
        image = QPixmap(image_path) if image_path else QPixmap()
        if image_path and image.isNull():
            log_warning(f"Could not load keyboard background image: {image_path}")
        key_color = _keyboard_color(config, "_keyboard_key_color", "#30343c")
        special_color = _keyboard_color(config, "_keyboard_special_key_color", "#464c56")
        key_text_color = _keyboard_color(config, "_keyboard_key_text_color", "#ffffff")
        title_color = "#FFFFFF" if not image.isNull() else (
            "#111111" if card_color.lightness() > 128 else "#FFFFFF"
        )
        title_background = "rgba(0, 0, 0, 170)" if not image.isNull() else "transparent"
        card_background = (
            "transparent" if not image.isNull() else
            f"rgba({card_color.red()}, {card_color.green()}, {card_color.blue()}, {opacity_alpha})"
        )
        self.target_field = target_field
        self.input_device = input_device
        self.initial_text = text
        self.current_text = text
        self.input_error = None
        self._initial_cursor_position = target_field.cursorPosition() if target_field is not None else None
        self._initial_selection_start = target_field.selectionStart() if target_field is not None else -1
        self._initial_selection_length = len(target_field.selectedText()) if target_field is not None else 0
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(860, 520)
        self.setStyleSheet(f"""
            QWidget#keyboardCard {{
                background-color: {card_background};
                border: 2px solid {theme_color};
                border-radius: 14px;
            }}
            QLabel#keyboardTitle {{ color: {title_color}; background-color: {title_background}; font-size: 22px; font-weight: bold; }}
            QLabel#keyboardHint {{ color: {title_color}; background-color: {title_background}; font-size: 13px; }}
            QLineEdit {{
                background-color: rgba(40, 40, 40, 220);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 8px;
                padding: 10px;
                font-size: 20px;
            }}
            QPushButton {{
                background-color: rgba({key_color.red()}, {key_color.green()}, {key_color.blue()}, 245);
                color: {key_text_color.name()};
                border: 2px solid transparent;
                border-radius: 11px;
                padding: 6px 0;
                font-size: 18px;
                font-weight: bold;
                min-height: 34px;
            }}
            QPushButton[keyboardRole="special"] {{ background-color: rgba({special_color.red()}, {special_color.green()}, {special_color.blue()}, 245); }}
            QPushButton[keyboardRole="page"] {{ background-color: {theme_color}; }}
            QPushButton[keyboardRole="space"] {{ font-size: 14px; }}
            QPushButton:focus, QPushButton:hover {{ border: 2px solid {theme_color}; }}
            QPushButton[controllerSelected="true"] {{ border: 2px solid {theme_color}; }}
        """)

        self.shift = False
        self.non_activating = False
        self.current_page = "letters"
        self.result_text = text

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = KeyboardCard(image, card_color, opacity_alpha, self)
        card.setObjectName("keyboardCard")
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)

        heading = QLabel(title)
        heading.setObjectName("keyboardTitle")
        layout.addWidget(heading)

        self.display = target_field
        if target_field is None and input_device is None:
            self.display = QLineEdit(text)
            if password:
                self.display.setEchoMode(QLineEdit.EchoMode.Password)
            self.display.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout.addWidget(self.display)

        self.rows = []
        self.key_buttons = []
        self.grid = QGridLayout()
        self.grid.setSpacing(7)
        layout.addLayout(self.grid)

        self.cancel_button = QPushButton("Close" if input_device is not None else "Cancel")
        self.cancel_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cancel_button.setProperty("keyboardRole", "special")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignRight)

        cancel_hint = "close" if input_device is not None else "cancel"
        hint = QLabel(f"D-pad / stick: move    A: type    LB: delete    RB: space    B: {cancel_hint}")
        hint.setObjectName("keyboardHint")
        layout.addWidget(hint)

        self.cursor_row = 0
        self.cursor_column = 0
        self._render_page()
        self._focus_cursor()

    def _render_page(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.rows = []
        self.key_buttons = []
        page_buttons = {"PAGE_SYMBOLS", "PAGE_SYMBOLS_MORE", "PAGE_LETTERS"}
        special_buttons = {"SHIFT", "BACKSPACE", "ENTER"}
        spans = {
            "BACKSPACE": 2, "ENTER": 2, "PAGE_SYMBOLS": 2,
            "PAGE_SYMBOLS_MORE": 2, "PAGE_LETTERS": 2, "SPACE": 4,
        }
        for row_index, tokens in enumerate(KEYBOARD_PAGES[self.current_page]):
            row_buttons = []
            column = 0
            for token in tokens:
                button = QPushButton(self._key_caption(token))
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.setProperty("keyToken", token)
                if token in page_buttons:
                    role = "page"
                elif token in special_buttons or token == "SPACE":
                    role = "special" if token != "SPACE" else "space"
                else:
                    role = "character"
                    self.key_buttons.append(button)
                button.setProperty("keyboardRole", role)
                button.clicked.connect(
                    lambda _checked=False, key=token: self._activate_key(key)
                )
                span = spans.get(token, 1)
                self.grid.addWidget(button, row_index, column, 1, span)
                column += span
                row_buttons.append(button)
            self.rows.append(row_buttons)
        self.rows.append([self.cancel_button])

    def _key_caption(self, token):
        captions = {
            "SHIFT": "⇧",
            "BACKSPACE": "⌫",
            "SPACE": "Space",
            "ENTER": "Done",
            "PAGE_SYMBOLS": "?123",
            "PAGE_SYMBOLS_MORE": "=\\<",
            "PAGE_LETTERS": "ABC",
        }
        return captions.get(token, self._key_text(token))

    def _activate_key(self, token):
        if token == "SHIFT":
            self.toggle_shift()
        elif token == "BACKSPACE":
            self.backspace()
        elif token == "SPACE":
            self.insert(" ")
        elif token == "ENTER":
            self.finish()
        elif token == "PAGE_SYMBOLS":
            self.set_page("symbols")
        elif token == "PAGE_SYMBOLS_MORE":
            self.set_page("symbols_more")
        elif token == "PAGE_LETTERS":
            self.set_page("letters")
        else:
            self.insert(self._key_text(token))
            if self.shift and self.current_page == "letters":
                self.toggle_shift()

    def set_page(self, page):
        if page not in KEYBOARD_PAGES or page == self.current_page:
            return
        self.current_page = page
        self.shift = False
        self.cursor_row = 0
        self.cursor_column = 0
        self._render_page()
        self._focus_cursor()

    def _focus_cursor(self):
        row = self.rows[self.cursor_row]
        self.cursor_column = min(self.cursor_column, len(row) - 1)
        if self.non_activating:
            for buttons in self.rows:
                for button in buttons:
                    selected = button is row[self.cursor_column]
                    button.setProperty("controllerSelected", selected)
                    button.style().unpolish(button)
                    button.style().polish(button)
                    button.update()
            return
        for index, button in enumerate(row):
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus if index == self.cursor_column else Qt.FocusPolicy.NoFocus)
        row[self.cursor_column].setFocus()

    def show_without_focus(self):
        self.non_activating = True
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._focus_cursor()
        self.show()

    def showEvent(self, event):
        super().showEvent(event)
        if self.target_field is None and self.input_device is None:
            return

        target_rect = None
        if self.target_field is not None:
            target_rect = QRect(
                self.target_field.mapToGlobal(self.target_field.rect().topLeft()),
                self.target_field.size(),
            )
            screen = QApplication.screenAt(target_rect.center())
        else:
            screen = QApplication.screenAt(QCursor.pos())
        screen = screen or self.screen()
        if screen is None:
            return

        available = screen.availableGeometry()
        width = min(860, available.width())
        height = min(520, available.height())
        place_above = False
        if target_rect is not None and available.intersects(target_rect):
            above = max(0, target_rect.top() - available.top())
            below = max(0, available.bottom() - target_rect.bottom())
            place_above = above > below
            space = above if place_above else below
            if space >= self.layout().minimumSize().height():
                height = min(height, space)

        self.resize(width, height)
        x = available.x() + max(0, (available.width() - self.width()) // 2)
        y = available.top() if place_above else available.bottom() - self.height() + 1
        self.move(x, y)

    def _key_text(self, key):
        if not self.shift:
            return key
        return SHIFT_SYMBOLS.get(key, key.upper())

    def insert(self, text):
        if self.input_error is not None:
            return
        if self.target_field is not None:
            self.target_field.insert(text)
            self.current_text = self.target_field.text()
        elif self.input_device is not None:
            if self._send_input(self.input_device.type_text, text):
                self.current_text += text
        else:
            self.display.insert(text)
            self.current_text = self.display.text()

    def backspace(self):
        if self.input_error is not None:
            return
        if self.target_field is not None:
            self.target_field.backspace()
            self.current_text = self.target_field.text()
        elif self.input_device is not None:
            if self._send_input(self.input_device.backspace):
                self.current_text = self.current_text[:-1]
        else:
            self.display.backspace()
            self.current_text = self.display.text()

    def _send_input(self, send, *args):
        try:
            send(*args)
        except (OSError, ValueError) as error:
            self.input_error = error
            self.input_failed.emit(error)
            return False
        return True

    def toggle_shift(self):
        self.shift = not self.shift
        for button in self.key_buttons:
            button.setText(self._key_text(button.property("keyToken")))

    def type_key(self, button):
        self._activate_key(button.property("keyToken"))

    def finish(self):
        self.result_text = self.target_field.text() if self.target_field is not None else self.current_text
        self.accept()

    def reject(self):
        if self.target_field is not None:
            self.target_field.setText(self.initial_text)
            if self._initial_selection_start >= 0:
                self.target_field.setSelection(
                    self._initial_selection_start, self._initial_selection_length
                )
            elif self._initial_cursor_position is not None:
                self.target_field.setCursorPosition(self._initial_cursor_position)
        super().reject()

    def handle_controller_action(self, action):
        if action == "back":
            self.reject()
        elif action == "previous_tab":
            self.backspace()
        elif action == "next_tab":
            self.insert(" ")
        elif action == "up":
            self.cursor_row = (self.cursor_row - 1) % len(self.rows)
            self._focus_cursor()
        elif action == "down":
            self.cursor_row = (self.cursor_row + 1) % len(self.rows)
            self._focus_cursor()
        elif action in ("left", "right"):
            row = self.rows[self.cursor_row]
            self.cursor_column = (self.cursor_column + (1 if action == "right" else -1)) % len(row)
            self._focus_cursor()
        elif action == "select":
            self.rows[self.cursor_row][self.cursor_column].click()
        return True

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish()
        elif key == Qt.Key.Key_Backspace:
            self.backspace()
        elif event.text() and event.text().isprintable():
            self.insert(event.text())
        else:
            super().keyPressEvent(event)

    @staticmethod
    def get_text(parent=None, title="Enter text", text="", password=False, target_field=None):
        """Returns (text, accepted), like QInputDialog.getText."""
        dialog = OnScreenKeyboard(parent, title, text, password, target_field=target_field)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.result_text, True
        return text, False


def focused_text_field():
    """The editable QLineEdit with focus that is not part of a spin box or combo box."""
    widget = QApplication.focusWidget()
    if not isinstance(widget, QLineEdit) or widget.isReadOnly():
        return None
    parent = widget.parentWidget()
    if isinstance(parent, (QAbstractSpinBox, QComboBox)):
        return None
    return widget
