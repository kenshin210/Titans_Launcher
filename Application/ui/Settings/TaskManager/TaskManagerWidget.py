from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from Application.ui.Settings.tab_style import tab_widget_stylesheet
from Application.ui.Settings.TaskManager.ApplicationsTab import ApplicationsTab
from Application.ui.Settings.TaskManager.NetworkTab import NetworkTab
from Application.ui.Settings.TaskManager.Overview import OverviewWidget


class TaskManagerWidget(QWidget):
    def __init__(self, launcher=None, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        theme_color = launcher.get_theme_color() if launcher and hasattr(launcher, "get_theme_color") else "#DC143C"
        self.setStyleSheet("color: white;")

        root_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(tab_widget_stylesheet(theme_color))
        root_layout.addWidget(self.tabs)

        self.tabs.addTab(OverviewWidget(launcher), "Overview")
        self.tabs.addTab(ApplicationsTab(launcher), "Applications")
        self.tabs.addTab(NetworkTab(launcher), "Network")
