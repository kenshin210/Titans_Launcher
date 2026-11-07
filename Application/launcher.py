# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import threading
import time
import shutil
import shlex
from datetime import datetime, timedelta
from pathlib import Path
import cv2
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QLabel,
    QDialog, QMessageBox, QToolButton, QMenu,
    QStackedWidget, QGraphicsOpacityEffect, QTabWidget
)
from PyQt6.QtCore import (
    Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve, QRect,
    pyqtSignal, QPoint, QParallelAnimationGroup
)
from PyQt6.QtGui import QImage, QPixmap, QIcon, QAction
from .styles import load_stylesheet

from Application.ui.Settings.Logger import (
    install_excepthook,
    log_critical,
    log_error,
    log_info,
    log_warning,
)

install_excepthook()

from .core.config import (
    CONFIG_PATH,
    DEFAULT_CONFIG,
    DEFAULT_CONTROLLER_BINDINGS,
    DEFAULT_VIDEO_PATH,
    load_config,
    save_config,
)
from .core.controller import (
    PYGAME_AVAILABLE,
    PygameControllerThread,
    load_controller_bindings,
    map_raw_input,
)
from .core.browser_controller import BrowserController
from .core.proxy import proxy_environment
from .core.sound import NavigationSoundPlayer
from .core.time_sync import fetch_ntp_time, start_ntp_sync_thread
from .core.weather import fetch_current_weather
from .ui.InstallApps import AppsHubWidget
from .ui.Settings.tab_style import tab_widget_stylesheet
from .ui.Settings.AsyncTask import TaskRunnerMixin, cleanup_all_tasks
from .ui.controller_navigation import (
    handle_focused_widget_input,
    handle_home_navigation,
    handle_modal_input,
    handle_popup_input,
    handle_settings_navigation,
)
from .ui.dialogs.app_editor import ApplicationEditorDialog
from .ui.dialogs.themed_message_box import ThemedMessageBox
from .ui.widgets.animated_button import AnimatedLauncherButton
from .ui.widgets.battery_indicator import BatteryIndicator

class MainApp(QWidget, TaskRunnerMixin):
    app_finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        log_info("Starting Titans HTPC Launcher...")
        self.config = load_config()
        self.controller_capture_active = False
        self.active_app_process = None
        self.active_app_controller_close_enabled = False
        self.browser_controller = None
        self.browser_controller_error = None
        self.launcher_sleeping = False
        self.controller_back_suppressed_until = 0.0
        self.reload_controller_profile()
        self.cap = None
        self.background_video_active = False
        self.current_ntp_time = datetime.now()

        self.app_finished_signal.connect(self.on_app_finished)

        self.nav_sound = NavigationSoundPlayer(self.config)
        self.initUI()
        QApplication.instance().focusChanged.connect(self.on_focus_changed)
        self.start_ntp_sync_thread()

        if PYGAME_AVAILABLE:
            self.controller_thread = PygameControllerThread(self)
            self.controller_thread.raw_input.connect(self.handle_controller_input)
            self.controller_thread.start()

    def reload_controller_profile(self):
        profile_name = self.config.get("_controller_profile", "Xbox Controller.json")
        self.controller_bindings = load_controller_bindings(profile_name)

    def handle_controller_input(self, input_name):
        if self.controller_capture_active:
            return
        action = map_raw_input(input_name, self.controller_bindings)
        if self.launcher_sleeping or self.isHidden():
            if (
                action == "close_app"
                and self.active_app_controller_close_enabled
                and self.active_app_process is not None
            ):
                if self.active_app_process.poll() is None:
                    log_info("Closing the launched application from controller close-app input.")
                    try:
                        self.active_app_process.terminate()
                    except OSError as error:
                        log_error(f"Failed to close launched application: {error}", details=str(error))
            elif action and self.browser_controller:
                try:
                    self.browser_controller.handle_action(action)
                except OSError as error:
                    log_error(f"Browser controller input failed: {error}")
                    self.browser_controller_error = str(error)
                    self.browser_controller.close()
                    self.browser_controller = None
            return
        if action == "back" and time.monotonic() < self.controller_back_suppressed_until:
            return
        if self.handle_power_menu_input(action):
            return
        if handle_popup_input(action, ignore=self.power_menu):
            return
        if handle_modal_input(action):
            return
        if self.handle_confirmation_dialog_input(action):
            return
        if action and self.stacked_widget.currentWidget() == self.settings_page:
            settings_widget = getattr(self, "current_settings_widget", None)
            if settings_widget and handle_settings_navigation(settings_widget, action):
                return
        if action and self.stacked_widget.currentWidget() == self.home_page:
            if handle_home_navigation(self, action):
                return
        if action and handle_focused_widget_input(action):
            return
        if action in ("right", "down"):
            self.focusNextChild()
        elif action in ("left", "up"):
            self.focusPreviousChild()
        elif action in ("previous_tab", "next_tab"):
            settings_widget = getattr(self, "current_settings_widget", None)
            direction = -1 if action == "previous_tab" else 1
            if self.stacked_widget.currentWidget() == self.settings_page and settings_widget:
                settings_widget.navigate_embedded_tabs(direction)
            elif self.stacked_widget.currentWidget() == self.home_page and self.applications_module_enabled():
                self.home_tabs.setCurrentIndex((self.home_tabs.currentIndex() + direction) % self.home_tabs.count())
        elif action == "select":
            focused = QApplication.focusWidget()
            if isinstance(focused, (QPushButton, QToolButton, AnimatedLauncherButton)):
                focused.click()
        elif action == "back":
            modal_dialog = QApplication.activeModalWidget()
            if modal_dialog:
                modal_dialog.reject()
            elif hasattr(self, 'stacked_widget') and self.stacked_widget.currentWidget() == self.settings_page:
                self.show_home_page()
            else:
                self.exit_launcher()

    def handle_confirmation_dialog_input(self, action):
        if action not in ("left", "right"):
            return False

        dialog = QApplication.activeModalWidget()
        if dialog is None:
            return False

        if isinstance(dialog, ThemedMessageBox):
            (dialog.no_btn if action == "left" else dialog.yes_btn).setFocus()
            return True

        if isinstance(dialog, QMessageBox):
            no_button = dialog.button(QMessageBox.StandardButton.No)
            yes_button = dialog.button(QMessageBox.StandardButton.Yes)
            if no_button and yes_button:
                (no_button if action == "left" else yes_button).setFocus()
                return True

            buttons = dialog.buttons()
            if len(buttons) > 1:
                current_button = QApplication.focusWidget()
                current_index = buttons.index(current_button) if current_button in buttons else 0
                direction = -1 if action == "left" else 1
                buttons[(current_index + direction) % len(buttons)].setFocus()
            return True

        return True

    def handle_power_menu_input(self, action):
        if not self.power_menu.isVisible():
            return False

        available_actions = [
            menu_action for menu_action in self.power_menu.actions()
            if menu_action.isEnabled() and not menu_action.isSeparator()
        ]
        if not available_actions:
            return True

        if action in ("up", "left", "down", "right"):
            current_action = self.power_menu.activeAction()
            current_index = available_actions.index(current_action) if current_action in available_actions else 0
            direction = -1 if action in ("up", "left") else 1
            next_index = (current_index + direction) % len(available_actions)
            self.power_menu.setActiveAction(available_actions[next_index])
        elif action == "select":
            selected_action = self.power_menu.activeAction()
            if selected_action in available_actions:
                self.power_menu.close()
                selected_action.trigger()
        elif action == "back":
            self.power_menu.close()
        return True

    def applications_module_enabled(self):
        return bool(self.config.get("_module_applications", False))

    def apply_applications_module(self):
        """Show the Home / Applications tabs only while the Applications module is enabled."""
        enabled = self.applications_module_enabled()
        self.home_tabs.setTabVisible(1, enabled)
        self.home_tabs.tabBar().setVisible(enabled)
        if not enabled:
            self.home_tabs.setCurrentIndex(0)

    def save_config_file(self):
        save_config(self.config)

    def on_focus_changed(self, old_widget, new_widget):
        # Skip the initial focus grab so the sound only marks real movement.
        if old_widget is None or new_widget is None:
            return
        if self.launcher_sleeping or self.isHidden():
            return
        if isinstance(new_widget, (QPushButton, QToolButton)):
            self.nav_sound.play()

    def refresh_battery_indicator(self):
        if hasattr(self, "battery_indicator"):
            self.battery_indicator.reload()

    def initUI(self):
        self.setWindowTitle("Application Launcher")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.showFullScreen()

        self.bg_label = QLabel(self)
        self.bg_label.setObjectName("launcherBackground")
        self.bg_label.setGeometry(self.rect())
        self.bg_label.setScaledContents(True)
        self.bg_label.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.bg_label.setStyleSheet(load_stylesheet())
        self.bg_label.show()

        self.init_video_background()

        self.content_widget = QWidget(self)
        self.content_widget.setObjectName("contentWidget")
        self.content_widget.setGeometry(self.rect())
        self.update_content_background()
        self.content_widget.show()

        root_layout = QVBoxLayout(self.content_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.stacked_widget = QStackedWidget(self.content_widget)
        root_layout.addWidget(self.stacked_widget)

        # ================= PAGE 0: HOME LAUNCHER PAGE =================
        self.home_page = QWidget()
        self.home_page.setObjectName("homePage")
        self.home_page.setStyleSheet(load_stylesheet())
        home_page_layout = QVBoxLayout(self.home_page)
        home_page_layout.setContentsMargins(0, 0, 0, 0)

        # "Home" keeps the original launcher view; "Applications" browses the pacman repositories.
        self.home_tabs = QTabWidget()
        self.home_tabs.setObjectName("homeTabs")
        self.home_tabs.setStyleSheet(
            tab_widget_stylesheet(self.get_theme_color())
            + "QTabWidget#homeTabs::pane { background: transparent; border: none; }"
            + "QTabWidget#homeTabs::tab-bar { alignment: center; }"
        )
        self.home_tab = QWidget()
        self.home_tab.setObjectName("homeTab")
        self.home_tab.setStyleSheet(load_stylesheet())
        self.home_tabs.addTab(self.home_tab, "Home")
        self.install_apps_widget = AppsHubWidget(self)
        self.home_tabs.addTab(self.install_apps_widget, "Applications")
        home_page_layout.addWidget(self.home_tabs)
        self.apply_applications_module()

        self.main_layout = QVBoxLayout(self.home_tab)
        self.main_layout.setContentsMargins(40, 40, 40, 40)

        top_layout = QHBoxLayout()
        top_layout.addStretch()

        self.power_btn = QToolButton(self)
        self.power_btn.setFixedSize(65, 65)
        self.power_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self.power_menu = QMenu(self)
        self.power_menu.setObjectName("powerMenu")
        self.power_menu.setStyleSheet(load_stylesheet(theme_color=self.get_theme_color()))

        action_exit = QAction("Exit Launcher", self)
        action_exit.triggered.connect(self.exit_launcher)

        action_sleep = QAction("Sleep", self)
        action_sleep.triggered.connect(self.trigger_sleep)

        action_restart = QAction("Restart", self)
        action_restart.triggered.connect(self.trigger_restart)

        action_shutdown = QAction("Shutdown", self)
        action_shutdown.triggered.connect(self.trigger_shutdown)

        self.power_menu.addAction(action_exit)
        self.power_menu.addAction(action_sleep)
        self.power_menu.addAction(action_restart)
        self.power_menu.addAction(action_shutdown)
        self.power_menu.aboutToShow.connect(
            lambda: self.power_menu.setActiveAction(self.power_menu.actions()[0])
        )

        self.power_btn.setMenu(self.power_menu)
        self.update_power_button_display()
        self.battery_indicator = BatteryIndicator(self.config, self)
        top_layout.addWidget(self.battery_indicator, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        top_layout.addSpacing(15)
        top_layout.addWidget(self.power_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self.main_layout.addLayout(top_layout)

        self.title_label = QLabel("Choose Application:")
        self.title_label.setObjectName("launcherTitle")
        self.title_label.setStyleSheet(load_stylesheet())
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        self.main_layout.addStretch()

        bottom_layout = QHBoxLayout()

        # Flat buttons keep the text looking like plain labels while staying clickable and focusable.
        flat_style = (
            "QPushButton {"
            "background: transparent; border: none; padding: 0px;"
            "color: #AAAAAA; font-size: 15px; font-weight: bold; text-align: left;"
            "}"
            "QPushButton:hover, QPushButton:focus { color: #FFFFFF; }"
        )

        self.weather_label = QPushButton("Current weather\nSet a city and country in Settings > Weather")
        self.weather_label.setObjectName("launcherWeather")
        self.weather_label.setFlat(True)
        self.weather_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.weather_label.setStyleSheet(flat_style)
        self.weather_label.clicked.connect(lambda: self.show_settings_page("weather"))

        self.clock_label = QPushButton("Loading Time...")
        self.clock_label.setObjectName("launcherClock")
        self.clock_label.setFlat(True)
        self.clock_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clock_label.setStyleSheet(flat_style)
        self.clock_label.clicked.connect(lambda: self.show_settings_page("ntp"))

        date_time_layout = QVBoxLayout()
        date_time_layout.setSpacing(8)
        date_time_layout.addWidget(self.weather_label)
        date_time_layout.addWidget(self.clock_label)
        bottom_layout.addLayout(date_time_layout)

        self.config_btn = QPushButton("⚙ Settings")
        self.config_btn.setObjectName("launcherSettingsButton")
        self.update_settings_button_style()
        self.config_btn.clicked.connect(self.show_settings_page)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.config_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self.apps_layout = QHBoxLayout()
        self.apps_layout.setSpacing(35)
        self.apps_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addLayout(self.apps_layout)

        self.refresh_applications_view()

        self.main_layout.addStretch()
        self.main_layout.addLayout(bottom_layout)

        # ================= PAGE 1: INTEGRATED SETTINGS PAGE =================
        self.settings_page = QWidget()
        self.settings_page.setObjectName("settingsPage")
        self.settings_page.setStyleSheet(load_stylesheet())
        self.settings_page_layout = QVBoxLayout(self.settings_page)
        self.settings_page_layout.setContentsMargins(40, 30, 40, 30)

        self.settings_container = QVBoxLayout()
        self.settings_container.setContentsMargins(0, 0, 0, 0)
        self.settings_page_layout.addLayout(self.settings_container)

        self.stacked_widget.addWidget(self.home_page)
        self.stacked_widget.addWidget(self.settings_page)

        self.content_widget.raise_()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock_display)
        self.clock_timer.start(1000)

        self.weather_timer = QTimer(self)
        self.weather_timer.timeout.connect(self.refresh_weather)
        self.weather_timer.start(30 * 60 * 1000)
        self.refresh_weather()

    def exit_launcher(self):
        theme_color = self.get_theme_color()
        dialog = ThemedMessageBox(
            self,
            title="Exit Launcher",
            message="Are you sure you want to exit the launcher?",
            theme_color=theme_color
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            log_info("User initiated exit. Stopping background video and closing launcher.")
            self.close()

    def show_error_overlay(self, title, message):
        dialog = ThemedMessageBox(
            self,
            title=title,
            message=message,
            theme_color=self.get_theme_color()
        )
        dialog.no_btn.hide()
        dialog.yes_btn.setText("OK")
        dialog.exec()

    def closeEvent(self, event):
        log_info("Checking async tasks before launcher shutdown.")
        if not cleanup_all_tasks(timeout_ms=3000):
            self.show_error_overlay(
                "Tasks Still Running",
                "A background task is still running. Wait for it to finish, then close the launcher again."
            )
            event.ignore()
            return

        controller_thread = getattr(self, "controller_thread", None)
        if controller_thread is not None and controller_thread.isRunning():
            log_info("Stopping controller polling thread during launcher shutdown.")
            controller_thread.stop()
            if not controller_thread.wait(5000):
                log_warning("Controller thread did not stop within timeout; launcher shutdown postponed.")
                self.show_error_overlay(
                    "Controller Still Stopping",
                    "The controller is still shutting down. Wait a moment, then close the launcher again."
                )
                event.ignore()
                return

        if hasattr(self, "clock_timer"):
            self.clock_timer.stop()
        if hasattr(self, "weather_timer"):
            self.weather_timer.stop()
        if hasattr(self, "video_timer"):
            self.video_timer.stop()
        if self.browser_controller:
            self.browser_controller.close()
            self.browser_controller = None
        if self.cap:
            self.cap.release()
            self.cap = None

        ntp_stop_event = getattr(self, "_ntp_stop_event", None)
        if ntp_stop_event is not None:
            ntp_stop_event.set()

        event.accept()

    def trigger_sleep(self):
        theme_color = self.get_theme_color()
        dialog = ThemedMessageBox(
            self,
            title="Sleep System",
            message="Are you sure you want to put the system to sleep?",
            theme_color=theme_color
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            sleep_cmd = self.config.get("_sleep_command", "systemctl suspend")
            log_info(f"Executing system sleep command: '{sleep_cmd}'")
            try:
                subprocess.Popen(sleep_cmd.split())
            except Exception as e:
                log_error(f"Failed to execute sleep command '{sleep_cmd}': {e}", details=str(e))
                self.show_error_overlay("Sleep Failed", f"Could not execute sleep command:\n{e}")

    def trigger_restart(self):
        theme_color = self.get_theme_color()
        dialog = ThemedMessageBox(
            self,
            title="Restart System",
            message="Are you sure you want to restart the system?",
            theme_color=theme_color
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            restart_cmd = self.config.get("_restart_command", "systemctl reboot")
            log_info(f"Executing system restart command: '{restart_cmd}'")
            try:
                subprocess.Popen(restart_cmd.split())
                self.close()
            except Exception as e:
                log_error(f"Failed to execute restart command '{restart_cmd}': {e}", details=str(e))
                self.show_error_overlay("Restart Failed", f"Could not execute restart command:\n{e}")

    def trigger_shutdown(self):
        theme_color = self.get_theme_color()
        dialog = ThemedMessageBox(
            self,
            title="Shutdown System",
            message="Are you sure you want to shut down the system?",
            theme_color=theme_color
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            power_cmd = self.config.get("_power_command", "systemctl poweroff")
            log_info(f"Executing system shutdown command: '{power_cmd}'")
            try:
                subprocess.Popen(power_cmd.split())
                self.close()
            except Exception as e:
                log_error(f"Failed to execute power command '{power_cmd}': {e}", details=str(e))
                self.show_error_overlay("Shutdown Failed", f"Could not execute power command:\n{e}")

    def update_power_button_display(self):
        if not hasattr(self, 'power_btn'):
            return
        power_icon_path = self.config.get("_power_icon_path", "")
        if power_icon_path and Path(power_icon_path).exists():
            self.power_btn.setText("")
            self.power_btn.setIcon(QIcon(power_icon_path))
            self.power_btn.setIconSize(QSize(32, 32))
        else:
            self.power_btn.setIcon(QIcon())
            self.power_btn.setText("⏻")

    def start_ntp_sync_thread(self):
        self._ntp_stop_event = threading.Event()
        self._ntp_thread = start_ntp_sync_thread(
            self.config,
            self._ntp_stop_event,
            self._update_ntp_time,
        )

    def _update_ntp_time(self, ntp_time):
        self.current_ntp_time = ntp_time

    def update_clock_display(self):
        self.current_ntp_time = self.current_ntp_time + timedelta(seconds=1)
        country = self.config.get("_ntp_country", "New Zealand")
        time_format = self.config.get("_time_format", "12-Hour (AM/PM)")

        if time_format == "24-Hour":
            time_str = self.current_ntp_time.strftime("%H:%M:%S")
        else:
            time_str = self.current_ntp_time.strftime("%I:%M:%S %p")

        formatted_time = f"{self.current_ntp_time.strftime('%A, %d %B %Y')}  –  {time_str} ({country})"
        self.clock_label.setText(formatted_time)

    def refresh_weather(self):
        city = self.config.get("_weather_city", "").strip()
        country = self.config.get("_weather_country", "").strip()
        if not city and not country:
            self.weather_label.setText(
                "Current weather\nSet a city and country in Settings > Weather"
            )
            return
        if not city or not country:
            self.weather_label.setText("Current weather\nComplete your location in Settings > Weather")
            return

        temperature_unit = self.config.get("_weather_temperature_unit", "Celsius")
        self.weather_label.setText(f"Current weather\nLoading {city}, {country}...")

        def update_weather(result):
            if isinstance(result, Exception):
                log_warning(f"Weather lookup failed for {city}, {country}.", details=str(result))
                self.weather_label.setText(f"Current weather unavailable\n{city}, {country}")
                return

            feels_like = (
                f" · Feels like {result['feels_like']}{result['unit']}"
                if result["feels_like"] is not None else ""
            )
            self.weather_label.setText(
                f"{result['icon']} {result['temperature']}{result['unit']} · "
                f"{result['description']}{feels_like}\n"
                f"{result['city']}, {result['country']}"
            )

        self.run_async(
            lambda: fetch_current_weather(city, country, temperature_unit),
            update_weather,
        )

    def get_theme_color(self):
        theme = self.config.get("_theme", "Crimson Red")
        custom_colors = self.config.get("_custom_colors", {})
        return custom_colors.get(theme, "#DC143C")

    def get_border_radius(self):
        shape = self.config.get("_button_shape", "Rounded Square")
        if shape == "Circle":
            return "50%"
        return "28px"

    def update_back_button_style(self):
        theme_color = self.get_theme_color()
        if hasattr(self, 'back_btn'):
            self.back_btn.setObjectName("launcherBackButton")
            self.back_btn.setStyleSheet(load_stylesheet(theme_color=theme_color))

    def update_settings_button_style(self):
        theme_color = self.get_theme_color()
        border_radius = self.get_border_radius()
        self.update_back_button_style()

        if hasattr(self, 'config_btn'):
            self.config_btn.setStyleSheet(
                load_stylesheet(theme_color=theme_color, border_radius=border_radius)
            )

        if hasattr(self, 'power_btn'):
            self.power_btn.setObjectName("launcherPowerButton")
            self.power_btn.setStyleSheet(
                load_stylesheet(theme_color=theme_color, border_radius=border_radius)
            )

        if hasattr(self, 'power_menu'):
            self.power_menu.setStyleSheet(load_stylesheet(theme_color=theme_color))
        if hasattr(self, "home_tabs"):
            self.home_tabs.setStyleSheet(
                tab_widget_stylesheet(theme_color)
                + "QTabWidget#homeTabs::pane { background: transparent; border: none; }"
                + "QTabWidget#homeTabs::tab-bar { alignment: center; }"
            )

    def init_video_background(self):
        if hasattr(self, 'video_timer') and self.video_timer.isActive():
            self.video_timer.stop()
        if self.cap:
            self.cap.release()
        self.background_video_active = False

        video_path = Path(self.config.get("_background_path", str(DEFAULT_VIDEO_PATH)))
        if video_path.exists():
            self.cap = cv2.VideoCapture(str(video_path))
            if self.cap.isOpened():
                self.background_video_active = True
                log_info(f"Background video opened successfully: {video_path}")
                self.video_timer = QTimer(self)
                self.video_timer.timeout.connect(self.update_video_frame)
                self.video_timer.start(33)
            else:
                log_error(f"Failed to open background video file (codec or format error): {video_path}")
        else:
            log_warning(f"Background video file not found at: {video_path}")
        self.update_content_background()

    def update_content_background(self):
        if not hasattr(self, "content_widget"):
            return
        background_color = (
            "rgba(20, 20, 20, 160)"
            if self.background_video_active else "#141414"
        )
        self.content_widget.setStyleSheet(
            load_stylesheet(
                theme_color=self.get_theme_color(),
                border_radius=self.get_border_radius(),
                background_color=background_color,
            )
        )
        self.content_widget.update()

    def update_video_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            if ret:
                if not self.background_video_active:
                    self.background_video_active = True
                    self.update_content_background()
                if self.width() > 0 and self.height() > 0:
                    frame = cv2.resize(frame, (self.width(), self.height()))

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                qt_image = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
                self.bg_label.setPixmap(QPixmap.fromImage(qt_image))
            elif self.background_video_active:
                self.background_video_active = False
                self.update_content_background()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'bg_label'):
            self.bg_label.setGeometry(self.rect())
        if hasattr(self, 'content_widget'):
            self.content_widget.setGeometry(self.rect())
        QTimer.singleShot(50, self.refresh_button_geometries)

    def refresh_button_geometries(self):
        for i in range(self.apps_layout.count()):
            item = self.apps_layout.itemAt(i)
            if item and item.widget():
                btn = item.widget()
                if isinstance(btn, AnimatedLauncherButton):
                    btn.set_original_geometry(btn.geometry())

    def refresh_applications_view(self):
        while self.apps_layout.count():
            item = self.apps_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        theme_color = self.get_theme_color()
        border_radius = self.get_border_radius()
        enable_anim = self.config.get("_enable_animations", True)
        enable_glitch = self.config.get("_enable_glitch", False)
        self.update_settings_button_style()

        first_app_btn = None

        for name, data in self.config.items():
            if name.startswith("_"):
                continue

            btn = AnimatedLauncherButton(self, enable_animations=enable_anim, enable_glitch=enable_glitch, theme_color=theme_color)
            btn.setText(name)

            icon_path = data.get("icon_path", "")
            if icon_path and Path(icon_path).exists():
                btn.setIcon(QIcon(icon_path))
            else:
                btn.setIcon(QIcon())

            btn.setIconSize(QSize(115, 115))
            btn.setObjectName("applicationTile")
            btn.setStyleSheet(
                load_stylesheet(theme_color=theme_color, border_radius=border_radius)
            )

            btn.clicked.connect(lambda checked, b=btn, app_data=data: b.play_click_animation(lambda: self.launch_app(app_data)))
            self.apps_layout.addWidget(btn)

            if first_app_btn is None:
                first_app_btn = btn

        if first_app_btn is not None:
            first_app_btn.setFocus()

        QTimer.singleShot(100, self.refresh_button_geometries)

    def launch_app(self, data):
        executable = data.get("command", "").strip()
        arguments_str = data.get("arguments", "").strip()

        if not executable:
            log_warning("Launch cancelled: No executable or command specified for application.")
            self.show_error_overlay("Missing Executable", "No executable or command is configured for this application.")
            return

        if Path(executable).is_absolute() or "/" in executable or "\\" in executable:
            if not Path(executable).exists():
                log_error(f"Application launch failed: Executable file not found on disk at '{executable}'")
                self.show_error_overlay("Application Not Found", f"The executable could not be found:\n{executable}")
                return
        else:
            if shutil.which(executable) is None:
                log_error(f"Application launch failed: Command '{executable}' not found in system PATH or as executable file.")
                self.show_error_overlay("Command Not Found", f"The command could not be found:\n{executable}")
                return

        executable_name = Path(executable).name.lower()
        is_website = data.get("type") == "website"
        use_browser_controller = (
            is_website
            and executable_name in ("firefox", "firefox-esr")
            and not (data.get("manage_antimicrox", False) and data.get("profile", ""))
        )
        if data.get("manage_antimicrox", False) and not use_browser_controller:
            log_info("Managing AntiMicroX: Terminating existing antimicrox instances.")
            subprocess.run(["pkill", "-f", "antimicrox"])

            profile_path = data.get("profile", "")
            if profile_path and Path(profile_path).exists():
                log_info(f"Applying AntiMicroX profile: {profile_path}")
                subprocess.Popen([
                    "antimicrox",
                    "--profile", profile_path,
                    "--hidden",
                    "--eventgen", "uinput"
                ])
            elif profile_path:
                log_warning(f"AntiMicroX profile specified but not found on disk: {profile_path}")
                self.show_error_overlay(
                    "AntiMicroX Profile Not Found",
                    f"The specified AntiMicroX profile could not be found:\n{profile_path}"
                )

        cmd_list = [executable]
        arguments = shlex.split(arguments_str)
        if executable_name in ("firefox", "firefox-esr") and not is_website:
            arguments = [argument for argument in arguments if argument != "--kiosk"]

        url_index = next(
            (index for index, argument in enumerate(arguments) if argument.startswith(("http://", "https://"))),
            None
        )
        controller_close_enabled = data.get("controller_close_enabled", False)
        if (
            (is_website or controller_close_enabled)
            and executable_name in ("firefox", "firefox-esr")
            and url_index is not None
        ):
            if not any(
                argument in ("--new-window", "-new-window", "--new-tab", "-new-tab")
                for argument in arguments
            ):
                arguments.insert(url_index, "--new-window")

            arguments.extend(["--no-remote"])
            has_explicit_profile = any(
                argument in ("--profile", "-profile", "-P") or argument.startswith("--profile=")
                for argument in arguments
            )
            if has_explicit_profile:
                log_warning(
                    "Firefox URL launch uses an explicitly configured profile; "
                    "the launcher cannot guarantee that Firefox will use an isolated profile."
                )
            else:
                firefox_profile = CONFIG_PATH.parent / "firefox-app-profile"
                try:
                    firefox_profile.mkdir(parents=True, exist_ok=True)
                except OSError as error:
                    log_error(f"Could not create the dedicated Firefox profile at {firefox_profile}: {error}")
                    self.show_error_overlay(
                        "Firefox Profile Error",
                        f"Could not create a dedicated Firefox profile:\n{error}"
                    )
                    return
                arguments[0:0] = ["--profile", str(firefox_profile)]
        cmd_list.extend(arguments)

        if use_browser_controller:
            if not PYGAME_AVAILABLE:
                log_warning("Firefox controller navigation requires pygame-ce.")
                self.show_error_overlay("Controller Unavailable", "Install pygame-ce to use the controller in Firefox.")
            else:
                try:
                    self.browser_controller = BrowserController()
                except (ImportError, OSError) as error:
                    log_error(f"Could not enable Firefox controller navigation: {error}")
                    self.show_error_overlay(
                        "Controller Unavailable",
                        f"Firefox controller navigation requires python-evdev and write access to /dev/uinput:\n{error}"
                    )

        try:
            log_info(f"Spawning application process: {' '.join(cmd_list)}")
            proc = subprocess.Popen(cmd_list, env={**os.environ, **proxy_environment(self.config)})
            self.active_app_process = proc
            self.active_app_controller_close_enabled = controller_close_enabled
            log_info(f"Application '{executable}' running (PID: {proc.pid})")
        except Exception as e:
            if self.browser_controller:
                self.browser_controller.close()
                self.browser_controller = None
            log_critical(f"Failed to execute process '{executable}': {e}", details=str(e))
            self.show_error_overlay("Launch Failed", f"Could not launch {executable}:\n{e}")
            return

        self.enter_sleep_state()

        def wait_and_restore():
            proc.wait()
            log_info(f"Application '{executable}' process exited with returncode {proc.returncode}")
            self.app_finished_signal.emit()

        threading.Thread(target=wait_and_restore, daemon=True).start()

    def enter_sleep_state(self):
        log_info("Putting launcher to sleep while the application is running.")
        self.launcher_sleeping = True
        if hasattr(self, "clock_timer"):
            self.clock_timer.stop()
        if hasattr(self, "video_timer"):
            self.video_timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        self.hide()

    def on_app_finished(self):
        log_info("Restoring launcher interface after application exit.")
        if self.browser_controller:
            self.browser_controller.close()
            self.browser_controller = None
        self.active_app_process = None
        self.active_app_controller_close_enabled = False
        self.launcher_sleeping = False
        self.controller_back_suppressed_until = time.monotonic() + 1.0
        self.showFullScreen()
        if hasattr(self, "clock_timer"):
            self.clock_timer.start(1000)
        self.update_clock_display()
        self.init_video_background()
        if self.browser_controller_error:
            error = self.browser_controller_error
            self.browser_controller_error = None
            self.show_error_overlay("Controller Input Failed", f"Firefox controller input stopped working:\n{error}")

    def show_settings_page(self, section=None):
        if getattr(self, 'is_animating', False):
            return

        # The clicked-signal's bool argument is not a section name.
        self._pending_settings_section = section if isinstance(section, str) else None

        log_info("Opening Settings view.")
        enable_anim = self.config.get("_enable_animations", True)
        if not enable_anim:
            try:
                self.build_settings_view(self.config.get("_advanced_mode", False))
                self.stacked_widget.setCurrentWidget(self.settings_page)
                if hasattr(self, 'current_settings_widget') and hasattr(self.current_settings_widget, 'focus_current_menu_item'):
                    self.current_settings_widget.focus_current_menu_item()
                elif hasattr(self, 'back_btn'):
                    self.back_btn.setFocus()
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                log_critical(f"CRASH in show_settings_page: {e}", details=tb)
                traceback.print_exc()
            return

        self.animate_transition_to_settings()

    def show_home_page(self):
        if getattr(self, 'is_animating', False):
            return

        log_info("Returning to Home Launcher view.")
        enable_anim = self.config.get("_enable_animations", True)
        if not enable_anim:
            self.stacked_widget.setCurrentWidget(self.home_page)
            self.refresh_applications_view()
            return

        self.animate_transition_to_home()

    def animate_transition_to_settings(self):
        self.is_animating = True

        home_widgets = []
        if hasattr(self, 'title_label') and self.title_label.isVisible():
            home_widgets.append(self.title_label)
        if hasattr(self, 'power_btn') and self.power_btn.isVisible():
            home_widgets.append(self.power_btn)
        if hasattr(self, 'battery_indicator') and self.battery_indicator.isVisible():
            home_widgets.append(self.battery_indicator)

        if hasattr(self, 'apps_layout'):
            for i in range(self.apps_layout.count()):
                item = self.apps_layout.itemAt(i)
                if item and item.widget() and item.widget().isVisible():
                    home_widgets.append(item.widget())

        if hasattr(self, 'clock_label') and self.clock_label.isVisible():
            home_widgets.append(self.clock_label)
        if hasattr(self, 'weather_label') and self.weather_label.isVisible():
            home_widgets.append(self.weather_label)
        if hasattr(self, 'config_btn') and self.config_btn.isVisible():
            home_widgets.append(self.config_btn)

        proxies = []
        target_corner = QRect(0, self.content_widget.height(), 0, 0)
        disintegrate_group = QParallelAnimationGroup(self)

        for w in home_widgets:
            pixmap = QPixmap(w.size())
            pixmap.fill(Qt.GlobalColor.transparent)
            w.render(pixmap)
            if pixmap.isNull():
                pixmap = w.grab()

            global_pos = w.mapToGlobal(QPoint(0, 0))
            local_pos = self.content_widget.mapFromGlobal(global_pos)
            start_rect = QRect(local_pos.x(), local_pos.y(), w.width(), w.height())

            proxy = QLabel(self.content_widget)
            proxy.setObjectName("transitionProxy")
            proxy.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            proxy.setStyleSheet(load_stylesheet())
            proxy.setPixmap(pixmap)
            proxy.setScaledContents(True)
            proxy.setGeometry(start_rect)
            proxy.show()
            proxy.raise_()

            op_effect = QGraphicsOpacityEffect(proxy)
            proxy.setGraphicsEffect(op_effect)

            proxies.append(proxy)

            anim_geom = QPropertyAnimation(proxy, b"geometry")
            anim_geom.setDuration(330)
            anim_geom.setStartValue(start_rect)
            anim_geom.setEndValue(target_corner)
            anim_geom.setEasingCurve(QEasingCurve.Type.InCubic)

            anim_op = QPropertyAnimation(op_effect, b"opacity")
            anim_op.setDuration(330)
            anim_op.setStartValue(1.0)
            anim_op.setEndValue(0.0)

            disintegrate_group.addAnimation(anim_geom)
            disintegrate_group.addAnimation(anim_op)

        self.stacked_widget.setVisible(False)
        self.build_settings_view(self.config.get("_advanced_mode", False))

        def on_disintegrate_done():
            for p in proxies:
                p.hide()
                p.clear()
                p.deleteLater()

            def start_expand_settings():
                corner_rect = QRect(0, self.content_widget.height(), 0, 0)
                full_rect = QRect(0, 0, self.content_widget.width(), self.content_widget.height())

                self.stacked_widget.setCurrentWidget(self.settings_page)
                self.settings_page.resize(self.content_widget.size())
                self.settings_page.ensurePolished()

                settings_pixmap = QPixmap(self.content_widget.size())
                settings_pixmap.fill(Qt.GlobalColor.transparent)
                self.settings_page.render(settings_pixmap)

                if settings_pixmap.isNull() or settings_pixmap.width() == 0:
                    settings_pixmap = self.settings_page.grab()

                settings_proxy = QLabel(self.content_widget)
                settings_proxy.setObjectName("transitionProxy")
                settings_proxy.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                settings_proxy.setStyleSheet(load_stylesheet())
                settings_proxy.setPixmap(settings_pixmap)
                settings_proxy.setScaledContents(True)
                settings_proxy.setGeometry(corner_rect)
                settings_proxy.show()
                settings_proxy.raise_()

                settings_op = QGraphicsOpacityEffect(settings_proxy)
                settings_proxy.setGraphicsEffect(settings_op)
                settings_op.setOpacity(0.0)

                expand_group = QParallelAnimationGroup(self)

                anim_s_geom = QPropertyAnimation(settings_proxy, b"geometry")
                anim_s_geom.setDuration(360)
                anim_s_geom.setStartValue(corner_rect)
                anim_s_geom.setEndValue(full_rect)
                anim_s_geom.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_s_op = QPropertyAnimation(settings_op, b"opacity")
                anim_s_op.setDuration(360)
                anim_s_op.setStartValue(0.0)
                anim_s_op.setEndValue(1.0)

                expand_group.addAnimation(anim_s_geom)
                expand_group.addAnimation(anim_s_op)

                def on_expand_done():
                    self.stacked_widget.setVisible(True)
                    self.settings_page.show()
                    settings_proxy.hide()
                    settings_proxy.clear()
                    settings_proxy.deleteLater()
                    self.is_animating = False
                    self.update()
                    self.stacked_widget.update()
                    if hasattr(self, 'current_settings_widget') and hasattr(self.current_settings_widget, 'focus_current_menu_item'):
                        self.current_settings_widget.focus_current_menu_item()
                    elif hasattr(self, 'back_btn'):
                        self.back_btn.setFocus()

                expand_group.finished.connect(on_expand_done)
                self._active_anim = expand_group
                expand_group.start()

            start_expand_settings()

        disintegrate_group.finished.connect(on_disintegrate_done)
        self._active_anim = disintegrate_group
        disintegrate_group.start()

    def animate_transition_to_home(self):
        self.is_animating = True

        full_rect = QRect(0, 0, self.content_widget.width(), self.content_widget.height())
        corner_rect = QRect(0, self.content_widget.height(), 0, 0)

        settings_pixmap = QPixmap(self.content_widget.size())
        settings_pixmap.fill(Qt.GlobalColor.transparent)
        self.settings_page.render(settings_pixmap)
        if settings_pixmap.isNull():
            settings_pixmap = self.settings_page.grab()

        settings_proxy = QLabel(self.content_widget)
        settings_proxy.setObjectName("transitionProxy")
        settings_proxy.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        settings_proxy.setStyleSheet(load_stylesheet())
        settings_proxy.setPixmap(settings_pixmap)
        settings_proxy.setScaledContents(True)
        settings_proxy.setGeometry(full_rect)
        settings_proxy.show()
        settings_proxy.raise_()

        self.stacked_widget.setVisible(False)

        settings_op = QGraphicsOpacityEffect(settings_proxy)
        settings_proxy.setGraphicsEffect(settings_op)

        collapse_group = QParallelAnimationGroup(self)

        anim_s_geom = QPropertyAnimation(settings_proxy, b"geometry")
        anim_s_geom.setDuration(290)
        anim_s_geom.setStartValue(full_rect)
        anim_s_geom.setEndValue(corner_rect)
        anim_s_geom.setEasingCurve(QEasingCurve.Type.InCubic)

        anim_s_op = QPropertyAnimation(settings_op, b"opacity")
        anim_s_op.setDuration(290)
        anim_s_op.setStartValue(1.0)
        anim_s_op.setEndValue(0.0)

        collapse_group.addAnimation(anim_s_geom)
        collapse_group.addAnimation(anim_s_op)

        def on_collapse_done():
            settings_proxy.hide()
            settings_proxy.clear()
            settings_proxy.deleteLater()

            def start_restore_home():
                self.refresh_applications_view()
                self.stacked_widget.setCurrentWidget(self.home_page)
                self.home_page.resize(self.content_widget.size())
                self.home_page.ensurePolished()

                home_pixmap = QPixmap(self.content_widget.size())
                home_pixmap.fill(Qt.GlobalColor.transparent)
                self.home_page.render(home_pixmap)

                if home_pixmap.isNull() or home_pixmap.width() == 0:
                    home_pixmap = self.home_page.grab()

                home_proxy = QLabel(self.content_widget)
                home_proxy.setObjectName("transitionProxy")
                home_proxy.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                home_proxy.setStyleSheet(load_stylesheet())
                home_proxy.setPixmap(home_pixmap)
                home_proxy.setScaledContents(True)
                home_proxy.setGeometry(corner_rect)
                home_proxy.show()
                home_proxy.raise_()

                home_op = QGraphicsOpacityEffect(home_proxy)
                home_proxy.setGraphicsEffect(home_op)
                home_op.setOpacity(0.0)

                restore_group = QParallelAnimationGroup(self)

                anim_geom = QPropertyAnimation(home_proxy, b"geometry")
                anim_geom.setDuration(340)
                anim_geom.setStartValue(corner_rect)
                anim_geom.setEndValue(full_rect)
                anim_geom.setEasingCurve(QEasingCurve.Type.OutCubic)

                anim_op = QPropertyAnimation(home_op, b"opacity")
                anim_op.setDuration(340)
                anim_op.setStartValue(0.0)
                anim_op.setEndValue(1.0)

                restore_group.addAnimation(anim_geom)
                restore_group.addAnimation(anim_op)

                def on_restore_done():
                    self.stacked_widget.setVisible(True)
                    self.home_page.show()
                    home_proxy.hide()
                    home_proxy.clear()
                    home_proxy.deleteLater()
                    self.is_animating = False
                    self.update()
                    self.stacked_widget.update()

                restore_group.finished.connect(on_restore_done)
                self._active_anim = restore_group
                restore_group.start()

            start_restore_home()

        collapse_group.finished.connect(on_collapse_done)
        self._active_anim = collapse_group
        collapse_group.start()

    def open_configurator(self):
        self.show_settings_page()

    def build_settings_view(self, is_advanced):
        selected_section = getattr(self, "current_settings_widget", None)
        selected_section = getattr(selected_section, "current_section", "general")
        requested_section = getattr(self, "_pending_settings_section", None)
        self._pending_settings_section = None
        if requested_section:
            selected_section = requested_section
            # Date/time (NTP) settings only exist in the Advanced menu.
            if requested_section == "ntp":
                is_advanced = True

        while self.settings_container.count():
            item = self.settings_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        def on_toggle_advanced(checked):
            log_info(f"Toggled settings advanced mode: {checked}")
            self.config["_advanced_mode"] = checked
            self.save_config_file()
            self.build_settings_view(checked)
            self.current_settings_widget.focus_current_menu_item()

        try:
            if is_advanced:
                from Application.ui.Settings.Settings_Advanced import AdvancedSettingsWidget
                self.current_settings_widget = AdvancedSettingsWidget(
                    self, self, on_toggle_advanced, initial_section=selected_section
                )
            else:
                from Application.ui.Settings.Settings_Basic import BasicSettingsWidget
                self.current_settings_widget = BasicSettingsWidget(
                    self, self, on_toggle_advanced, initial_section=selected_section
                )
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log_critical(f"Failed to load {'Advanced' if is_advanced else 'Basic'} settings widget: {e}", details=tb)
            raise

        if hasattr(self.current_settings_widget, 'back_btn'):
            self.back_btn = self.current_settings_widget.back_btn

        self.settings_container.addWidget(self.current_settings_widget)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if hasattr(self, 'stacked_widget') and self.stacked_widget.currentWidget() == self.settings_page:
                self.show_home_page()
                return
        super().keyPressEvent(event)

def main():
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
