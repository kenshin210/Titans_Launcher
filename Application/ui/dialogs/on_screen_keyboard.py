from PyQt6.QtCore import Qt, pyqtSignal
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

KEY_ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl'"),
    list("zxcvbnm,.-"),
    list("@_/:;!?#%&"),
    list("[](){}$^*="),
]
SHIFT_SYMBOLS = {
    **dict(zip("1234567890", "!@#$%^&*()")),
    "'": '"', ",": "<", ".": ">", "-": "+", "/": "\\", ":": "=",
    ";": "*", "_": "~", "[": "{", "]": "}",
}


class OnScreenKeyboard(QDialog):
    """Controller-driven text entry.

    D-pad moves over the keys, A types, LB deletes, RB adds a space, B cancels.
    A physical keyboard also works.
    """

    input_failed = pyqtSignal(object)

    def __init__(
        self, parent=None, title="Enter text", text="", password=False, theme_color=None,
        target_field=None, input_device=None,
    ):
        super().__init__(parent)
        theme_color = theme_color or resolve_theme_color(parent)
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
        self.setMinimumSize(860, 560)
        self.resize(860, 560)
        self.setStyleSheet(f"""
            QWidget#keyboardCard {{
                background-color: rgba(20, 20, 20, 245);
                border: 2px solid {theme_color};
                border-radius: 14px;
            }}
            QLabel#keyboardTitle {{ color: #FFFFFF; font-size: 22px; font-weight: bold; }}
            QLabel#keyboardHint {{ color: #888888; font-size: 13px; }}
            QLineEdit {{
                background-color: rgba(40, 40, 40, 220);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 8px;
                padding: 10px;
                font-size: 20px;
            }}
            QPushButton {{
                background-color: rgba(50, 50, 50, 220);
                color: #FFFFFF;
                border: 2px solid transparent;
                border-radius: 8px;
                padding: 10px 0;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:checked {{ background-color: {theme_color}; }}
            QPushButton:focus, QPushButton:hover {{ border: 2px solid {theme_color}; }}
            QPushButton[controllerSelected="true"] {{ border: 2px solid {theme_color}; }}
        """)

        self.shift = False
        self.non_activating = False
        self.result_text = text

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget(self)
        card.setObjectName("keyboardCard")
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

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
        grid = QGridLayout()
        grid.setSpacing(6)
        for row_index, row in enumerate(KEY_ROWS):
            buttons = []
            for column, key in enumerate(row):
                button = QPushButton(key)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.clicked.connect(lambda _checked, b=button: self.type_key(b))
                grid.addWidget(button, row_index, column)
                buttons.append(button)
                self.key_buttons.append(button)
            self.rows.append(buttons)
        layout.addLayout(grid)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.shift_button = QPushButton("Shift")
        self.shift_button.setCheckable(True)
        self.shift_button.clicked.connect(self.toggle_shift)
        space_button = QPushButton("Space")
        space_button.clicked.connect(lambda: self.insert(" "))
        backspace_button = QPushButton("⌫ Delete")
        backspace_button.clicked.connect(self.backspace)
        cancel_button = QPushButton("Close" if input_device is not None else "Cancel")
        cancel_button.clicked.connect(self.reject)
        done_button = QPushButton("Done")
        done_button.clicked.connect(self.finish)
        action_buttons = [self.shift_button, space_button, backspace_button, cancel_button, done_button]
        for button in action_buttons:
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            action_row.addWidget(button, stretch=2 if button is space_button else 1)
        layout.addLayout(action_row)
        self.rows.append(action_buttons)

        cancel_hint = "close" if input_device is not None else "cancel"
        hint = QLabel(f"D-pad / stick: move    A: type    LB: delete    RB: space    B: {cancel_hint}")
        hint.setObjectName("keyboardHint")
        layout.addWidget(hint)

        self.cursor_row = 1
        self.cursor_column = 0
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
        self.shift = self.shift_button.isChecked()
        for button, key in zip(self.key_buttons, [key for row in KEY_ROWS for key in row]):
            button.setText(self._key_text(key))

    def type_key(self, button):
        self.insert(button.text())
        if self.shift:
            self.shift_button.setChecked(False)
            self.toggle_shift()

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
