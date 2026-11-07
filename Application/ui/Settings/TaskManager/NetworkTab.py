from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from Application.core.netstats import NetworkSampler
from Application.core.processes import format_bytes, format_rate
from Application.styles import load_stylesheet
from Application.ui.Settings.AsyncTask import TaskRunnerMixin
from Application.ui.Settings.Logger import log_warning

REFRESH_INTERVAL_MS = 2000


def _make_table(headers, stretch_first=True):
    table = QTableWidget(0, len(headers))
    table.setObjectName("taskTable")
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch if stretch_first else QHeaderView.ResizeMode.ResizeToContents)
    for column in range(1, len(headers)):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    return table


def _fill(table, rows):
    table.setUpdatesEnabled(False)
    table.setRowCount(len(rows))
    for row, cells in enumerate(rows):
        for column, text in enumerate(cells):
            item = table.item(row, column)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, column, item)
            item.setText(text)
            if column > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    table.setUpdatesEnabled(True)


class NetworkTab(QWidget, TaskRunnerMixin):
    """Upload and download rates for each network interface and each application."""

    STATUS_TEXT = (
        "Speeds are measured from TCP connections owned by your user, sorted by download. "
        "UDP traffic (e.g. QUIC video) can't be measured per application, so only its socket count is shown."
    )

    def __init__(self, launcher=None):
        super().__init__()
        theme_color = launcher.get_theme_color() if launcher and hasattr(launcher, "get_theme_color") else "#DC143C"
        self.setStyleSheet(load_stylesheet(theme_color=theme_color))
        self.sampler = NetworkSampler()
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        interfaces_title = QLabel("Network Interfaces")
        interfaces_title.setObjectName("soundDisplaySectionTitle")
        layout.addWidget(interfaces_title)
        self.interface_table = _make_table(["Interface", "Upload", "Download", "Total Sent", "Total Received"])
        self.interface_table.setMaximumHeight(150)
        layout.addWidget(self.interface_table)

        apps_title = QLabel("Applications")
        apps_title.setObjectName("soundDisplaySectionTitle")
        layout.addWidget(apps_title)
        self.app_table = _make_table(["Application", "TCP", "UDP", "Upload", "Download"])
        self.app_table.setMinimumHeight(220)
        layout.addWidget(self.app_table, stretch=1)

        self.status = QLabel(self.STATUS_TEXT)
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)

    def showEvent(self, event):
        super().showEvent(event)
        self.sampler.reset()
        self.refresh()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self):
        if self._busy:
            return
        self._busy = True

        def done(result):
            self._busy = False
            if isinstance(result, Exception):
                log_warning(f"Network sampling failed: {result}")
                self.status.setText(f"Could not read network information: {result}")
                return
            interfaces = sorted(result["interfaces"], key=lambda row: row["download"] + row["upload"], reverse=True)
            _fill(self.interface_table, [
                [row["name"], format_rate(row["upload"]), format_rate(row["download"]),
                 format_bytes(row["total_sent"]), format_bytes(row["total_received"])]
                for row in interfaces
            ])
            if not result["per_app_available"]:
                self.status.setText("Per-application activity needs the `ss` tool (iproute2).")
            else:
                self.status.setText(self.STATUS_TEXT)
            apps = sorted(
                result["applications"],
                key=lambda row: (row["download"], row["upload"]),
                reverse=True,
            )
            _fill(self.app_table, [
                [row["name"], str(row["connections"]), str(row["udp"]), format_rate(row["upload"]), format_rate(row["download"])]
                for row in apps
            ])

        self.run_async(self.sampler.sample, done)
