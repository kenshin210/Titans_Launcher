from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from Application.core import processes
from Application.core.processes import format_bytes, format_rate
from Application.styles import load_stylesheet
from Application.ui.Settings.AsyncTask import TaskRunnerMixin
from Application.ui.Settings.Logger import log_info, log_warning

REFRESH_INTERVAL_MS = 2000

# (header, sort key, alignment-right?)
COLUMNS = [
    ("Application", "name", False),
    ("Status", "status", False),
    ("CPU", "cpu", True),
    ("RAM", "ram", True),
    ("Swap", "swap", True),
    ("Disk I/O", "disk", True),
    ("GPU", "gpu", True),
    ("GPU Memory", "gpu_mem", True),
]
SORT_KEYS = [(header, key) for header, key, _right in COLUMNS if key != "status"]


def format_cell(key, group):
    value = group[key]
    if key == "name":
        count = len(group["pids"])
        return f"{value}  ({count})" if count > 1 else value
    if key in ("cpu", "gpu"):
        return f"{value:.1f}%"
    if key == "disk":
        return format_rate(value)
    if key in ("ram", "swap", "gpu_mem"):
        return format_bytes(value) if value else "—"
    return str(value)


class ApplicationsTab(QWidget, TaskRunnerMixin):
    """Running applications with sortable resource usage and a way to close unresponsive ones."""

    def __init__(self, launcher=None):
        super().__init__()
        self.launcher = launcher
        theme_color = launcher.get_theme_color() if launcher and hasattr(launcher, "get_theme_color") else "#DC143C"
        self.setStyleSheet(load_stylesheet(theme_color=theme_color))
        self.sampler = processes.ProcessSampler() if processes.PSUTIL_AVAILABLE else None
        self.groups = []
        self.sort_key = "cpu"
        self.sort_descending = True
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        self.summary = QLabel()
        self.summary.setObjectName("soundDisplayStatus")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        controls = QHBoxLayout()
        sort_label = QLabel("Sort by:")
        sort_label.setObjectName("soundDisplayValue")
        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("soundDisplayControl")
        for header, key in SORT_KEYS:
            self.sort_combo.addItem(header, key)
        self.sort_combo.setCurrentIndex(self.sort_combo.findData(self.sort_key))
        self.order_button = QPushButton()
        self.order_button.setObjectName("soundDisplayButton")
        self.all_users_checkbox = QCheckBox("Show other users' processes")
        controls.addWidget(sort_label)
        controls.addWidget(self.sort_combo)
        controls.addWidget(self.order_button)
        controls.addSpacing(12)
        controls.addWidget(self.all_users_checkbox)
        controls.addStretch()
        layout.addLayout(controls)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("taskTable")
        self.table.setHorizontalHeaderLabels([header for header, _key, _right in COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)
        layout.addWidget(self.table, stretch=1)

        actions = QHBoxLayout()
        self.end_button = QPushButton("End Task")
        self.kill_button = QPushButton("Force Kill")
        for button in (self.end_button, self.kill_button):
            button.setObjectName("soundDisplayButton")
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)

        self.sort_combo.currentIndexChanged.connect(self._on_sort_combo)
        self.order_button.clicked.connect(self._toggle_order)
        header.sectionClicked.connect(self._on_header_clicked)
        self.all_users_checkbox.toggled.connect(lambda _checked: self._reset_and_refresh())
        self.end_button.clicked.connect(lambda: self.close_selected(force=False))
        self.kill_button.clicked.connect(lambda: self.close_selected(force=True))
        self._update_order_ui()

        if self.sampler is None:
            self.summary.setText("The task manager needs the psutil Python module (pip install psutil).")
            for widget in (self.sort_combo, self.order_button, self.table, self.end_button,
                           self.kill_button, self.all_users_checkbox):
                widget.setEnabled(False)

    # ---- lifecycle: only sample while visible ----
    def showEvent(self, event):
        super().showEvent(event)
        if self.sampler is not None:
            self.sampler.reset()
            self.refresh()
            self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _reset_and_refresh(self):
        self.sampler.reset()
        self.refresh()

    # ---- sorting ----
    def _update_order_ui(self):
        self.order_button.setText("Highest First" if self.sort_descending else "Lowest First")
        column = next(i for i, (_h, key, _r) in enumerate(COLUMNS) if key == self.sort_key)
        order = Qt.SortOrder.DescendingOrder if self.sort_descending else Qt.SortOrder.AscendingOrder
        self.table.horizontalHeader().setSortIndicator(column, order)

    def _set_sort(self, key):
        if key == self.sort_key:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_key = key
            # Names read naturally A-Z; every numeric column starts with the largest.
            self.sort_descending = key != "name"
        self.sort_combo.blockSignals(True)
        index = self.sort_combo.findData(self.sort_key)
        if index >= 0:
            self.sort_combo.setCurrentIndex(index)
        self.sort_combo.blockSignals(False)
        self._update_order_ui()
        self._populate()

    def _on_sort_combo(self, _index):
        key = self.sort_combo.currentData()
        self.sort_key = key
        self.sort_descending = key != "name"
        self._update_order_ui()
        self._populate()

    def _toggle_order(self):
        self.sort_descending = not self.sort_descending
        self._update_order_ui()
        self._populate()

    def _on_header_clicked(self, column):
        self._set_sort(COLUMNS[column][1])

    # ---- sampling ----
    def refresh(self):
        if self.sampler is None or self._busy:
            return
        self._busy = True
        all_users = self.all_users_checkbox.isChecked()

        def work():
            return self.sampler.sample(all_users), self.sampler.system_totals()

        def done(result):
            self._busy = False
            if isinstance(result, Exception):
                log_warning(f"Task manager sampling failed: {result}")
                self.status.setText(f"Could not read process information: {result}")
                return
            self.groups, totals = result
            self.summary.setText(
                f"CPU {totals['cpu']:.0f}%   •   "
                f"RAM {format_bytes(totals['ram_used'])} / {format_bytes(totals['ram_total'])} ({totals['ram_percent']:.0f}%)   •   "
                f"Swap {format_bytes(totals['swap_used'])} / {format_bytes(totals['swap_total'])}   •   "
                f"Drive {format_bytes(totals['disk_used'])} / {format_bytes(totals['disk_total'])} ({totals['disk_percent']:.0f}%)"
            )
            self._populate()

        self.run_async(work, done)

    def _populate(self):
        selected = self._selected_name()
        scroll = self.table.verticalScrollBar().value()
        key = self.sort_key
        rows = sorted(
            self.groups,
            key=lambda group: group[key].lower() if key in ("name", "status") else group[key],
            reverse=self.sort_descending,
        )
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        for row, group in enumerate(rows):
            for column, (_header, column_key, right) in enumerate(COLUMNS):
                item = self.table.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.table.setItem(row, column, item)
                item.setText(format_cell(column_key, group))
                if right:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, group)
        if selected is not None:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)["name"] == selected:
                    self.table.selectRow(row)
                    break
        self.table.verticalScrollBar().setValue(scroll)
        self.table.setUpdatesEnabled(True)

    def _selected_group(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_name(self):
        group = self._selected_group()
        return group["name"] if group else None

    # ---- closing applications ----
    def close_selected(self, force):
        group = self._selected_group()
        if group is None:
            self.status.setText("Select an application first.")
            return
        count = len(group["pids"])
        verb = "force kill" if force else "end"
        answer = QMessageBox.question(
            self,
            "Force kill" if force else "End task",
            f"Do you want to {verb} {group['name']}"
            f"{f' and its {count} processes' if count > 1 else ''}?\n\n"
            "Unsaved data in that application will be lost.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        pids = list(group["pids"])
        name = group["name"]

        def done(errors):
            if isinstance(errors, Exception):
                errors = [str(errors)]
            if errors:
                log_warning(f"Could not close {name}: {'; '.join(errors)}")
                self.status.setText(f"Could not close {name}: {'; '.join(errors)}")
            else:
                log_info(f"{'Force killed' if force else 'Ended'} application {name}.")
                self.status.setText(f"{'Force killed' if force else 'Sent close request to'} {name}.")
            self.refresh()

        self.run_async(lambda: processes.kill_application(pids, force), done)
