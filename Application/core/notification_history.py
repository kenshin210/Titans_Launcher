"""
Notification History Manager for Titans Launcher.

Stores and manages notification history in SQLite database with persistent storage
at ~/.local/share/titans/notifications.db
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """Represents a single notification."""
    id: int
    title: str
    body: str
    timestamp: str
    category: str
    read: bool
    app_name: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert notification to dictionary."""
        return asdict(self)


class NotificationHistoryManager:
    """Manages notification history in SQLite database."""

    MAX_NOTIFICATIONS = 100
    DB_VERSION = 1

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the notification history manager.

        Args:
            db_path: Path to the SQLite database file. Defaults to
                     ~/.local/share/titans/notifications.db
        """
        if db_path is None:
            db_path = Path.home() / ".local" / "share" / "titans" / "notifications.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _init_database(self):
        """Initialize the database schema."""
        try:
            with self._connection() as conn:
                cursor = conn.cursor()

                # Create schema version table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Get current schema version
                cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
                result = cursor.fetchone()
                current_version = result[0] if result else 0

                # Create notifications table if needed
                if current_version < self.DB_VERSION:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS notifications (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT NOT NULL,
                            body TEXT NOT NULL,
                            timestamp DATETIME NOT NULL,
                            category TEXT NOT NULL,
                            read BOOLEAN DEFAULT 0,
                            app_name TEXT
                        )
                    """)

                    # Update schema version
                    if current_version == 0:
                        cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (self.DB_VERSION,))

                    conn.commit()
                    logger.info(f"Initialized notification database at {self.db_path}")

        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def add_notification(self, title: str, body: str, category: str,
                        app_name: str = "Titans", timestamp: Optional[str] = None) -> int:
        """Add a notification to the database.

        Args:
            title: Notification title
            body: Notification body/message
            category: Notification category (e.g., 'device', 'network', 'power')
            app_name: Name of the application that triggered the notification
            timestamp: ISO format timestamp. Defaults to current time.

        Returns:
            The ID of the inserted notification
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()

        try:
            with self._connection() as conn:
                cursor = conn.cursor()

                # Insert notification
                cursor.execute("""
                    INSERT INTO notifications (title, body, timestamp, category, read, app_name)
                    VALUES (?, ?, ?, ?, 0, ?)
                """, (title, body, timestamp, category, app_name))

                notification_id = cursor.lastrowid

                # Clean up old notifications if over limit
                cursor.execute("""
                    DELETE FROM notifications WHERE id IN (
                        SELECT id FROM notifications
                        ORDER BY timestamp DESC, id DESC
                        LIMIT -1 OFFSET ?
                    )
                """, (self.MAX_NOTIFICATIONS,))

                conn.commit()
                logger.debug(f"Added notification: {title} (ID: {notification_id})")
                return notification_id

        except sqlite3.Error as e:
            logger.error(f"Error adding notification: {e}")
            raise

    def get_notifications(self, limit: Optional[int] = None,
                         category: Optional[str] = None,
                         unread_only: bool = False) -> List[Notification]:
        """Retrieve notifications from the database.

        Args:
            limit: Maximum number of notifications to return. None for all.
            category: Filter by category. None for all categories.
            unread_only: Only return unread notifications.

        Returns:
            List of Notification objects sorted by timestamp (newest first)
        """
        try:
            with self._connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = "SELECT * FROM notifications WHERE 1=1"
                params = []

                if category:
                    query += " AND category = ?"
                    params.append(category)

                if unread_only:
                    query += " AND read = 0"

                query += " ORDER BY timestamp DESC, id DESC"

                if limit is not None:
                    query += " LIMIT ?"
                    params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                notifications = []
                for row in rows:
                    notifications.append(Notification(
                        id=row['id'],
                        title=row['title'],
                        body=row['body'],
                        timestamp=row['timestamp'],
                        category=row['category'],
                        read=bool(row['read']),
                        app_name=row['app_name']
                    ))

                return notifications

        except sqlite3.Error as e:
            logger.error(f"Error retrieving notifications: {e}")
            return []

    def mark_as_read(self, notification_id: int) -> bool:
        """Mark a notification as read.

        Args:
            notification_id: ID of the notification to mark as read

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))
                conn.commit()
                return cursor.rowcount > 0

        except sqlite3.Error as e:
            logger.error(f"Error marking notification as read: {e}")
            return False

    def mark_as_unread(self, notification_id: int) -> bool:
        """Mark a notification as unread.

        Args:
            notification_id: ID of the notification to mark as unread

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE notifications SET read = 0 WHERE id = ?", (notification_id,))
                conn.commit()
                return cursor.rowcount > 0

        except sqlite3.Error as e:
            logger.error(f"Error marking notification as unread: {e}")
            return False

    def mark_all_as_read(self) -> bool:
        """Mark all notifications as read.

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE notifications SET read = 1")
                conn.commit()
                return True

        except sqlite3.Error as e:
            logger.error(f"Error marking all notifications as read: {e}")
            return False

    def clear_all(self) -> bool:
        """Clear all notifications from the database.

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM notifications")
                conn.commit()
                logger.info("Cleared all notifications")
                return True

        except sqlite3.Error as e:
            logger.error(f"Error clearing notifications: {e}")
            return False

    def delete_notification(self, notification_id: int) -> bool:
        """Delete a specific notification.

        Args:
            notification_id: ID of the notification to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
                conn.commit()
                return cursor.rowcount > 0

        except sqlite3.Error as e:
            logger.error(f"Error deleting notification: {e}")
            return False

    def get_unread_count(self) -> int:
        """Get count of unread notifications.

        Returns:
            Number of unread notifications
        """
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM notifications WHERE read = 0")
                result = cursor.fetchone()
                return result[0] if result else 0

        except sqlite3.Error as e:
            logger.error(f"Error getting unread count: {e}")
            return 0

    def get_total_count(self) -> int:
        """Get total count of notifications.

        Returns:
            Total number of notifications
        """
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM notifications")
                result = cursor.fetchone()
                return result[0] if result else 0

        except sqlite3.Error as e:
            logger.error(f"Error getting total count: {e}")
            return 0

    def get_categories(self) -> List[str]:
        """Get list of all notification categories in the database.

        Returns:
            List of unique category names
        """
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT category FROM notifications ORDER BY category")
                rows = cursor.fetchall()
                return [row[0] for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Error getting categories: {e}")
            return []
