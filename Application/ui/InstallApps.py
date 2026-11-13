"""Install Apps tab on the launcher home page: search the pacman repositories and install."""
import hashlib

from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from Application.core.packages import (
    featured_packages, install_command, installed_names, removable_packages, search_packages,
)
from Application.core.corner_style import corner_radius
from Application.styles import load_stylesheet
from Application.ui.dialogs.themed_message_box import ThemedMessageBox
from Application.ui.Settings.AsyncTask import TaskRunnerMixin, command_error, run_command
from Application.ui.Settings.Logger import log_info, log_warning

CARD_WIDTH = 230
CARD_HEIGHT = 250
GRID_SPACING = 14
ICON_SIZE = 72


def package_icon(name):
    """Theme icon when the package ships one, otherwise a coloured letter badge."""
    themed = QIcon.fromTheme(name)
    if not themed.isNull():
        return themed.pixmap(ICON_SIZE, ICON_SIZE)

    digest = hashlib.md5(name.encode("utf-8")).digest()
    colour = QColor.fromHsv(digest[0] * 359 // 255, 150, 190)
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(colour)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, ICON_SIZE, ICON_SIZE, corner_radius(16), corner_radius(16))
    painter.setPen(QColor("white"))
    font = QFont()
    font.setBold(True)
    font.setPixelSize(38)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, name[:1].upper())
    painter.end()
    return pixmap


class InstallAppsWidget(QWidget, TaskRunnerMixin):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("soundDisplaySettings")
        self.setStyleSheet(load_stylesheet(theme_color=launcher.get_theme_color()))
        self._search_id = 0
        self._loaded = False
        self._installing = False
        self._card_buttons = {}
        self._apps = []
        self._columns = 0
        self._empty_message = "Nothing to show."
        self._result_label = "Results"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 10)
        layout.setSpacing(12)

        title = QLabel("Install Apps")
        title.setObjectName("soundDisplayTitle")
        layout.addWidget(title)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search the Arch repositories (for example: vlc, emulator, browser)")
        self.search_input.setStyleSheet(
            "background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; "
            "border-radius: 6px; font-size: 15px; border: 1px solid rgba(255, 255, 255, 25);"
        )
        self.search_input.returnPressed.connect(self.search)
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("soundDisplayButton")
        self.search_button.clicked.connect(self.search)
        search_row.addWidget(self.search_input, stretch=1)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)

        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.results_widget = QWidget()
        self.results_widget.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.results_widget)
        self.grid.setSpacing(GRID_SPACING)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.results_widget)
        layout.addWidget(self.scroll, stretch=1)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.show_featured()

    def _run_listing(self, work, description):
        self._search_id += 1
        search_id = self._search_id
        self.status.setText(description)
        self.search_button.setEnabled(False)

        def done(result):
            if search_id != self._search_id:
                return
            self.search_button.setEnabled(True)
            if isinstance(result, Exception):
                log_warning("Install Apps: package lookup failed.", details=str(result))
                self.status.setText(f"Could not read the package list: {result}")
                self.populate([])
                return
            self.populate(result)

        self.run_async(work, done)

    def show_featured(self):
        def work():
            installed = installed_names()
            return [app for app in featured_packages() if app["name"] not in installed]

        self._run_listing(work, "Loading suggested apps...")
        self._empty_message = "No suggested apps were found. Use the search box to look for an app."
        self._result_label = "Suggested apps"

    def search(self):
        query = self.search_input.text().strip()
        if not query:
            self.show_featured()
            return

        def work():
            installed = installed_names()
            apps = search_packages(query, limit=300)
            return [app for app in apps if not app["installed"] and app["name"] not in installed][:96]

        self._run_listing(work, f"Searching for \"{query}\"...")
        self._empty_message = f"No new packages matched \"{query}\" (installed apps are hidden)."
        self._result_label = f"Results for \"{query}\""

    def _column_count(self):
        width = self.scroll.viewport().width()
        return max(1, (width + GRID_SPACING) // (CARD_WIDTH + GRID_SPACING))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._apps and self._column_count() != self._columns:
            self._layout_cards()

    def populate(self, apps):
        self._apps = apps
        if not apps:
            self.status.setText(self._empty_message)
        else:
            self.status.setText(f"{self._result_label}: {len(apps)} shown")
        self._layout_cards()

    def _layout_cards(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._card_buttons = {}
        self._columns = self._column_count()
        # Cards fill the whole width, so the screen is populated edge to edge.
        for column in range(self._columns):
            self.grid.setColumnStretch(column, 1)
        for index, app in enumerate(self._apps):
            self.grid.addWidget(
                self._build_card(app), index // self._columns, index % self._columns,
                Qt.AlignmentFlag.AlignCenter,
            )

    def _build_card(self, app):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        card.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        icon = QLabel()
        icon.setPixmap(package_icon(app["name"]))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon)

        name = QLabel(app["name"])
        name.setObjectName("soundDisplaySectionTitle")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)

        meta = QLabel(f"{app['version']}  ·  {app['repo']}")
        meta.setObjectName("soundDisplayStatus")
        meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(meta)

        description = QLabel(app["description"])
        description.setObjectName("soundDisplayDescription")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        description.setToolTip(app["description"])
        description.setFixedHeight(54)
        layout.addWidget(description)

        button = QPushButton("Installed" if app["installed"] else "Install")
        button.setObjectName("soundDisplayButton")
        button.setEnabled(not app["installed"])
        button.clicked.connect(lambda _checked=False, pkg=app["name"]: self.install(pkg))
        layout.addWidget(button)
        self._card_buttons[app["name"]] = button
        return card

    def install(self, name):
        if self._installing:
            self.status.setText("Another install is already running.")
            return
        command = install_command(name)
        if command is None:
            self.status.setText("Installing needs pkexec or sudo, and neither was found.")
            return
        dialog = ThemedMessageBox(
            self.window(), title="Install App",
            message=f"Install {name} and its dependencies?",
            theme_color=self.launcher.get_theme_color(),
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        self._installing = True
        button = self._card_buttons.get(name)

        def set_button(enabled, text):
            # The card may have been replaced by a new search while installing.
            if button is not None and not sip.isdeleted(button):
                button.setEnabled(enabled)
                button.setText(text)

        set_button(False, "Installing...")
        self.status.setText(f"Installing {name}... this can take a few minutes.")

        def work():
            return run_command(command, timeout=1800)

        def done(result):
            self._installing = False
            failed = isinstance(result, Exception) or result.returncode != 0
            if failed:
                message = str(result) if isinstance(result, Exception) else command_error(result)
                log_warning(f"Install Apps: failed to install {name}.", details=message)
                self.status.setText(f"Could not install {name}: {message}")
                set_button(True, "Install")
                return
            log_info(f"Install Apps: installed {name}")
            self.status.setText(f"{name} was installed.")
            set_button(False, "Installed")

        self.run_async(work, done)


class InstalledAppsWidget(QWidget, TaskRunnerMixin):
    """Read-only list of the apps already installed on the device (system packages excluded)."""

    def __init__(self, launcher):
        super().__init__()
        self.setObjectName("soundDisplaySettings")
        self.setStyleSheet(load_stylesheet(theme_color=launcher.get_theme_color()))
        self._apps = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 10)
        layout.setSpacing(12)

        title = QLabel("Installed Apps")
        title.setObjectName("soundDisplayTitle")
        layout.addWidget(title)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter installed apps")
        self.filter_input.setStyleSheet(
            "background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; "
            "border-radius: 6px; font-size: 15px; border: 1px solid rgba(255, 255, 255, 25);"
        )
        self.filter_input.textChanged.connect(self.apply_filter)
        layout.addWidget(self.filter_input)

        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "background-color: rgba(30, 30, 30, 200); color: white; font-size: 15px; "
            "border: 1px solid rgba(255, 255, 255, 30); border-radius: 8px; padding: 6px;"
        )
        layout.addWidget(self.list_widget, stretch=1)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        self.status.setText("Reading installed apps...")

        def done(result):
            if isinstance(result, Exception):
                log_warning("Installed Apps: could not read installed packages.", details=str(result))
                self.status.setText(f"Could not read installed apps: {result}")
                self._apps = []
            else:
                self._apps = result[0]
                self.status.setText(f"{len(self._apps)} installed apps")
            self.apply_filter()

        self.run_async(removable_packages, done)

    def apply_filter(self):
        needle = self.filter_input.text().strip().lower()
        self.list_widget.clear()
        for app in self._apps:
            if needle and needle not in app["name"].lower() and needle not in app["description"].lower():
                continue
            label = f"{app['name']}  {app['version']}"
            if app["size"]:
                label += f"  ·  {app['size']}"
            item = QListWidgetItem(label)
            item.setToolTip(app["description"])
            self.list_widget.addItem(item)


class AppsHubWidget(QWidget):
    """Install Apps tab: side navigation (Install Apps / Uninstall Apps) next to the matching page."""

    def __init__(self, launcher):
        super().__init__()
        from PyQt6.QtWidgets import QStackedWidget
        from Application.ui.Settings.UninstallApps import UninstallAppsWidget

        theme_color = launcher.get_theme_color()
        root = QHBoxLayout(self)
        root.setContentsMargins(30, 10, 30, 20)
        root.setSpacing(20)

        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet(
            "QFrame { background-color: rgba(22, 22, 22, 200); border: 1px solid rgba(255, 255, 255, 30); "
            "border-radius: 14px; }"
        )
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(14, 18, 14, 18)
        side_layout.setSpacing(8)

        header = QLabel("APPS")
        header.setStyleSheet(
            "color: rgba(255, 255, 255, 140); font-size: 13px; font-weight: bold; "
            "letter-spacing: 2px; border: none; background: transparent;"
        )
        side_layout.addWidget(header)

        self.pages = QStackedWidget()
        self.pages.setStyleSheet("background: transparent;")
        self.installed_page = InstalledAppsWidget(launcher)
        self.install_page = InstallAppsWidget(launcher)
        self.uninstall_page = UninstallAppsWidget(launcher)
        self.pages.addWidget(self.installed_page)
        self.pages.addWidget(self.install_page)
        self.pages.addWidget(self.uninstall_page)

        self.nav_buttons = []
        for index, label in enumerate(("Installed Apps", "Install Apps", "Uninstall Apps")):
            button = QPushButton(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, i=index: self.select(i))
            side_layout.addWidget(button)
            self.nav_buttons.append(button)
        side_layout.addStretch()

        self._theme_color = theme_color
        root.addWidget(sidebar)
        root.addWidget(self.pages, stretch=1)
        self.select(1)

    def select(self, index):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            selected = i == index
            button.setStyleSheet(
                "QPushButton {"
                f"background-color: {'rgba(65, 65, 65, 220)' if selected else 'transparent'};"
                f"color: {'#FFFFFF' if selected else '#AAAAAA'}; font-size: 16px; font-weight: bold;"
                f"padding: 12px 14px; text-align: left; border-radius: 8px;"
                f"border: 2px solid {self._theme_color if selected else 'transparent'};"
                "}"
                f"QPushButton:hover, QPushButton:focus {{ color: #FFFFFF; border: 2px solid {self._theme_color}; }}"
            )
