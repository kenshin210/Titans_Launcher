"""
Notification Inbox Widget for Titans Launcher Settings UI.

Displays notification history with filtering by category and read status.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt

from Application.core.notification_history import NotificationHistoryManager
from Application.ui.Settings.Logger import log_info, log_error


class NotificationItemWidget(QWidget):
    """Widget representing a single notification in the list."""

    def __init__(self, notification, parent=None):
        super().__init__(parent)
        self.notification = notification

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Title with read status indicator
        title_layout = QHBoxLayout()
        title_label = QLabel(notification.title)
        title_label.setStyleSheet("font-weight: bold; color: #ffffff;")
        title_layout.addWidget(title_label)

        if notification.read:
            status_label = QLabel("✓")
            status_label.setStyleSheet("color: #90EE90;")
        else:
            status_label = QLabel("●")
            status_label.setStyleSheet("color: #FFD700;")

        title_layout.addStretch()
        title_layout.addWidget(status_label)
        layout.addLayout(title_layout)

        # Body text
        body_label = QLabel(notification.body)
        body_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        body_label.setWordWrap(True)
        layout.addWidget(body_label)

        # Metadata row (category, app, time)
        meta_layout = QHBoxLayout()

        if notification.category:
            category_label = QLabel(f"[{notification.category}]")
            category_label.setStyleSheet("color: #888888; font-size: 10px;")
            meta_layout.addWidget(category_label)

        if notification.app_name:
            app_label = QLabel(notification.app_name)
            app_label.setStyleSheet("color: #888888; font-size: 10px;")
            meta_layout.addWidget(app_label)

        meta_layout.addStretch()

        time_label = QLabel(notification.timestamp)
        time_label.setStyleSheet("color: #666666; font-size: 10px;")
        meta_layout.addWidget(time_label)

        layout.addLayout(meta_layout)

        self.setStyleSheet("""
            NotificationItemWidget {
                background-color: #222222;
                border: 1px solid #444444;
                border-radius: 4px;
                margin: 4px;
            }
            NotificationItemWidget:hover {
                background-color: #2a2a2a;
                border: 1px solid #555555;
            }
        """)


class NotificationInboxWidget(QWidget):
    """Notification inbox display and management widget for Settings."""

    def __init__(self, launcher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.notification_manager = NotificationHistoryManager()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QLabel("Notification History")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        # Info label
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        layout.addWidget(self.info_label)

        # Filter controls
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        filter_label = QLabel("Filter by category:")
        filter_label.setStyleSheet("color: #ffffff;")
        filter_layout.addWidget(filter_label)

        self.category_filter = QComboBox()
        self.category_filter.setFixedWidth(200)
        self.category_filter.addItem("All")
        self.category_filter.setStyleSheet("""
            QComboBox {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        self.category_filter.currentTextChanged.connect(self.refresh_notifications)
        filter_layout.addWidget(self.category_filter)

        self.unread_only_check = QPushButton("Unread Only")
        self.unread_only_check.setCheckable(True)
        self.unread_only_check.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:checked {
                background-color: #DC143C;
                border: 1px solid #DC143C;
            }
        """)
        self.unread_only_check.clicked.connect(self.refresh_notifications)
        filter_layout.addWidget(self.unread_only_check)

        filter_layout.addStretch()

        layout.addLayout(filter_layout)

        # Notifications list
        self.notifications_list = QListWidget()
        self.notifications_list.setStyleSheet("""
            QListWidget {
                background-color: #1a1a1a;
                border: 1px solid #444444;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #2a2a2a;
            }
            QListWidget::item:selected {
                background-color: #333333;
            }
        """)
        self.notifications_list.setMinimumHeight(300)
        self.notifications_list.itemSelectionChanged.connect(
            self.on_notification_selection_changed
        )
        layout.addWidget(self.notifications_list)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.mark_read_button = QPushButton("Mark as Read")
        self.mark_read_button.setEnabled(False)
        self.mark_read_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #444444;
            }
            QPushButton:disabled {
                color: #666666;
                background-color: #222222;
            }
        """)
        self.mark_read_button.clicked.connect(self.mark_selected_as_read)
        button_layout.addWidget(self.mark_read_button)

        self.mark_all_read_button = QPushButton("Mark All as Read")
        self.mark_all_read_button.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #444444;
            }
        """)
        self.mark_all_read_button.clicked.connect(self.mark_all_as_read)
        button_layout.addWidget(self.mark_all_read_button)

        button_layout.addStretch()

        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.setEnabled(False)
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: #8B0000;
                color: #ffffff;
                border: 1px solid #A00000;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #A00000;
            }
            QPushButton:disabled {
                color: #666666;
                background-color: #222222;
            }
        """)
        self.delete_button.clicked.connect(self.delete_selected)
        button_layout.addWidget(self.delete_button)

        self.clear_all_button = QPushButton("Clear All")
        self.clear_all_button.setStyleSheet("""
            QPushButton {
                background-color: #8B0000;
                color: #ffffff;
                border: 1px solid #A00000;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover:!pressed {
                background-color: #A00000;
            }
        """)
        self.clear_all_button.clicked.connect(self.clear_all_notifications)
        button_layout.addWidget(self.clear_all_button)

        layout.addLayout(button_layout)

        self.selected_notification = None
        self.refresh_notifications()

    def refresh_notifications(self):
        """Refresh the notification list based on current filters."""
        self.notifications_list.clear()

        category_filter = self.category_filter.currentText()
        if category_filter == "All":
            category_filter = None

        unread_only = self.unread_only_check.isChecked()

        notifications = self.notification_manager.get_notifications(
            category=category_filter,
            unread_only=unread_only
        )

        # Update info label
        total = self.notification_manager.get_total_count()
        unread = self.notification_manager.get_unread_count()
        self.info_label.setText(f"Total: {total} | Unread: {unread}")

        # Update category filter
        current_category = self.category_filter.currentText()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All")

        categories = self.notification_manager.get_categories()
        self.category_filter.addItems(categories)

        if current_category in [self.category_filter.itemText(i) for i in range(self.category_filter.count())]:
            self.category_filter.setCurrentText(current_category)

        self.category_filter.blockSignals(False)

        # Populate list
        for notification in notifications:
            item = QListWidgetItem(self.notifications_list)
            widget = NotificationItemWidget(notification, self.notifications_list)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, notification.id)
            self.notifications_list.addItem(item)
            self.notifications_list.setItemWidget(item, widget)

        self.selected_notification = None
        self.update_button_states()

    def on_notification_selected(self, item):
        """Handle notification selection."""
        self.selected_notification = item.data(Qt.ItemDataRole.UserRole)
        self.update_button_states()

    def on_notification_selection_changed(self):
        """Track the selected notification for mouse and keyboard navigation."""
        selected_items = self.notifications_list.selectedItems()
        self.selected_notification = (
            selected_items[0].data(Qt.ItemDataRole.UserRole) if selected_items else None
        )
        self.update_button_states()

    def update_button_states(self):
        """Update button enabled states based on selection."""
        self.mark_read_button.setEnabled(self.selected_notification is not None)
        self.delete_button.setEnabled(self.selected_notification is not None)

    def mark_selected_as_read(self):
        """Mark the selected notification as read."""
        if self.selected_notification is None:
            return

        if self.notification_manager.mark_as_read(self.selected_notification):
            log_info("Notification marked as read")
            self.refresh_notifications()
        else:
            log_error("Failed to mark notification as read")

    def mark_all_as_read(self):
        """Mark all notifications as read."""
        if self.notification_manager.mark_all_as_read():
            log_info("All notifications marked as read")
            self.refresh_notifications()
        else:
            log_error("Failed to mark all notifications as read")

    def delete_selected(self):
        """Delete the selected notification."""
        if self.selected_notification is None:
            return

        reply = QMessageBox.question(
            self,
            "Delete Notification",
            "Delete this notification?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.notification_manager.delete_notification(self.selected_notification):
                log_info("Notification deleted")
                self.refresh_notifications()
            else:
                log_error("Failed to delete notification")

    def clear_all_notifications(self):
        """Clear all notifications with confirmation."""
        reply = QMessageBox.question(
            self,
            "Clear All Notifications",
            "Clear all notifications? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.notification_manager.clear_all():
                log_info("All notifications cleared")
                self.refresh_notifications()
            else:
                log_error("Failed to clear notifications")
