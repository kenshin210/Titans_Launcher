import fnmatch
import os
import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PAGE_SIZE = 8
FILTER_PATTERN = re.compile(r"^(.*?)\s*\((.*)\)\s*$")


def resolve_theme_color(widget):
    """Theme colour of the launcher window that owns `widget`, if it can be found."""
    window = widget.window() if widget is not None else None
    getter = getattr(window, "get_theme_color", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            pass
    return "#DC143C"


def parse_filters(filter_text):
    """Qt filter string -> [(label, [patterns])]; always has at least one entry."""
    filters = []
    for part in (filter_text or "").split(";;"):
        part = part.strip()
        if not part:
            continue
        match = FILTER_PATTERN.match(part)
        if match:
            patterns = match.group(2).split() or ["*"]
            filters.append((part, patterns))
        else:
            filters.append((part, [part]))
    return filters or [("All Files (*)", ["*"])]


def matches_patterns(name, patterns):
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pattern.lower()) for pattern in patterns)


def list_directory(directory, patterns, show_hidden):
    """(directories, files) in `directory`, sorted case-insensitively; raises OSError."""
    directories, files = [], []
    with os.scandir(directory) as entries:
        for entry in entries:
            if not show_hidden and entry.name.startswith("."):
                continue
            try:
                is_directory = entry.is_dir()
            except OSError:
                continue
            if is_directory:
                directories.append(entry.name)
            elif matches_patterns(entry.name, patterns):
                files.append(entry.name)
    directories.sort(key=str.lower)
    files.sort(key=str.lower)
    return directories, files


def format_size(size):
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def drive_locations():
    user = os.environ.get("USER") or Path.home().name
    candidates = [Path("/run/media") / user, Path("/media") / user, Path("/mnt"), Path("/run/media")]
    return next((path for path in candidates if path.is_dir()), Path("/"))


class ControllerFileDialog(QDialog):
    """File browser that can be driven entirely with a controller.

    The launcher forwards controller actions to `handle_controller_action`:
    up/down move through the list, LB/RB page, A opens or chooses, B cancels.
    """

    def __init__(self, parent=None, caption="Select File", directory="", filter_text="", theme_color=None):
        super().__init__(parent)
        theme_color = theme_color or resolve_theme_color(parent)
        self.setWindowTitle(caption)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(920, 640)
        self.resize(920, 640)
        self.setStyleSheet(f"""
            QWidget#pickerCard {{
                background-color: rgba(20, 20, 20, 245);
                border: 2px solid {theme_color};
                border-radius: 14px;
            }}
            QLabel#pickerTitle {{ color: #FFFFFF; font-size: 22px; font-weight: bold; }}
            QLabel#pickerPath {{ color: #BBBBBB; font-size: 14px; }}
            QLabel#pickerHint {{ color: #888888; font-size: 13px; }}
            QLabel#pickerStatus {{ color: #FFB347; font-size: 13px; }}
            QListWidget {{
                background-color: rgba(35, 35, 35, 200);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
                font-size: 18px;
                outline: none;
            }}
            QListWidget::item {{ padding: 8px 12px; }}
            QListWidget::item:selected {{ background-color: {theme_color}; color: #FFFFFF; }}
            QPushButton {{
                background-color: rgba(50, 50, 50, 220);
                color: #FFFFFF;
                border: 2px solid transparent;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:focus, QPushButton:hover {{ border: 2px solid {theme_color}; }}
        """)

        self.filters = parse_filters(filter_text)
        self.filter_index = 0
        self.show_hidden = False
        self.selected_path = ""
        self.current_directory = Path.home()

        start = Path(directory).expanduser() if directory else Path.home()
        if start.is_file():
            start = start.parent
        if start.is_dir():
            self.current_directory = start

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget(self)
        card.setObjectName("pickerCard")
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel(caption)
        title.setObjectName("pickerTitle")
        layout.addWidget(title)
        self.path_label = QLabel()
        self.path_label.setObjectName("pickerPath")
        layout.addWidget(self.path_label)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.activate_item)
        layout.addWidget(self.list_widget, stretch=1)

        self.status = QLabel()
        self.status.setObjectName("pickerStatus")
        layout.addWidget(self.status)

        self.buttons = []
        button_row = QHBoxLayout()
        for text, handler in (
            ("Home", lambda: self.go_to(Path.home())),
            ("Root /", lambda: self.go_to(Path("/"))),
            ("Drives", lambda: self.go_to(drive_locations())),
            ("Hidden: Off", self.toggle_hidden),
            ("Filter", self.cycle_filter),
            ("Cancel", self.reject),
        ):
            button = QPushButton(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(handler)
            button_row.addWidget(button)
            self.buttons.append(button)
        self.hidden_button = self.buttons[3]
        self.filter_button = self.buttons[4]
        layout.addLayout(button_row)

        hint = QLabel("D-pad / stick: move    A: open or choose    B: cancel    LB / RB: page up / down")
        hint.setObjectName("pickerHint")
        layout.addWidget(hint)

        self.list_widget.setFocus()
        self.refresh()

    @property
    def patterns(self):
        return self.filters[self.filter_index][1]

    def refresh(self, keep_name=None):
        self.path_label.setText(str(self.current_directory))
        self.filter_button.setText(f"Filter: {self.filters[self.filter_index][0].split('(')[0].strip() or 'All'}")
        self.list_widget.clear()
        self.status.setText("")
        parent = self.current_directory.parent
        if parent != self.current_directory:
            up_item = QListWidgetItem("⬆  .. (parent folder)")
            up_item.setData(Qt.ItemDataRole.UserRole, ("up", str(parent)))
            self.list_widget.addItem(up_item)
        try:
            directories, files = list_directory(self.current_directory, self.patterns, self.show_hidden)
        except OSError as error:
            directories, files = [], []
            self.status.setText(f"Cannot read this folder: {error.strerror or error}")
        for name in directories:
            item = QListWidgetItem(f"📁  {name}")
            item.setData(Qt.ItemDataRole.UserRole, ("dir", str(self.current_directory / name)))
            self.list_widget.addItem(item)
        for name in files:
            path = self.current_directory / name
            try:
                size = format_size(path.stat().st_size)
            except OSError:
                size = ""
            item = QListWidgetItem(f"📄  {name}    {size}")
            item.setData(Qt.ItemDataRole.UserRole, ("file", str(path)))
            self.list_widget.addItem(item)
        if not directories and not files and not self.status.text():
            self.status.setText("No matching files in this folder.")

        target_row = 0
        if keep_name:
            for row in range(self.list_widget.count()):
                if Path(self.list_widget.item(row).data(Qt.ItemDataRole.UserRole)[1]).name == keep_name:
                    target_row = row
                    break
        elif self.list_widget.count() > 1 and self.list_widget.item(0).data(Qt.ItemDataRole.UserRole)[0] == "up":
            target_row = 1
        if self.list_widget.count():
            self.list_widget.setCurrentRow(target_row)

    def go_to(self, directory):
        directory = Path(directory)
        if directory.is_dir():
            previous = self.current_directory
            self.current_directory = directory
            self.refresh(keep_name=previous.name if previous.parent == directory else None)
        else:
            self.status.setText(f"{directory} does not exist.")
        self.list_widget.setFocus()

    def toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        self.hidden_button.setText(f"Hidden: {'On' if self.show_hidden else 'Off'}")
        self.refresh()

    def cycle_filter(self):
        self.filter_index = (self.filter_index + 1) % len(self.filters)
        self.refresh()

    def activate_item(self, item=None):
        item = item or self.list_widget.currentItem()
        if item is None:
            return
        kind, path = item.data(Qt.ItemDataRole.UserRole)
        if kind in ("up", "dir"):
            self.go_to(path)
        else:
            self.selected_path = path
            self.accept()

    def selected_filter(self):
        return self.filters[self.filter_index][0]

    def _move_row(self, delta):
        count = self.list_widget.count()
        if count:
            row = min(max(self.list_widget.currentRow() + delta, 0), count - 1)
            self.list_widget.setCurrentRow(row)

    def _move_button_focus(self, delta):
        focused = QApplication.focusWidget()
        index = self.buttons.index(focused) if focused in self.buttons else -1
        self.buttons[(index + delta) % len(self.buttons)].setFocus()

    def handle_controller_action(self, action):
        on_list = QApplication.focusWidget() is self.list_widget or QApplication.focusWidget() not in self.buttons
        if action == "back":
            self.reject()
        elif action in ("previous_tab", "next_tab"):
            self._move_row(-PAGE_SIZE if action == "previous_tab" else PAGE_SIZE)
        elif action in ("up", "down"):
            if on_list:
                self._move_row(-1 if action == "up" else 1)
            elif action == "up":
                self.list_widget.setFocus()
        elif action in ("left", "right"):
            if on_list:
                self.buttons[0 if action == "right" else -1].setFocus()
            else:
                self._move_button_focus(1 if action == "right" else -1)
        elif action == "select":
            if on_list:
                self.activate_item()
            else:
                QApplication.focusWidget().click()
        return True

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.list_widget.hasFocus():
            self.activate_item()
        elif event.key() == Qt.Key.Key_Backspace and self.list_widget.hasFocus():
            self.go_to(self.current_directory.parent)
        else:
            super().keyPressEvent(event)

    @staticmethod
    def get_open_file_name(parent=None, caption="Select File", directory="", filter_text=""):
        """Drop-in for QFileDialog.getOpenFileName: returns (path, selected_filter)."""
        dialog = ControllerFileDialog(parent, caption, directory, filter_text)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_path:
            return dialog.selected_path, dialog.selected_filter()
        return "", ""
