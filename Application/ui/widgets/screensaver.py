"""Launcher-local idle screensaver with image and video rotation."""

import time
from pathlib import Path

import cv2
from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QCursor, QImage, QImageReader, QMovie, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel

from Application.ui.Settings.Logger import log_warning


VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".avi", ".mov"}


class Screensaver(QObject):
    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher
        self.overlay = QLabel(launcher)
        self.overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay.setStyleSheet("background: black;")
        self.overlay.setMouseTracking(True)
        self.overlay.hide()
        self.movie = None
        self.capture = None
        self.pixmap = QPixmap()
        self.index = -1
        self.last_activity = time.monotonic()
        self.last_cursor_position = QCursor.pos()
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self._tick_video)
        self.rotation_timer = QTimer(self)
        self.rotation_timer.timeout.connect(self._next_item)
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self._check_idle)
        self.idle_timer.start(1000)
        QApplication.instance().installEventFilter(self)

    def _active(self):
        return (
            self.launcher.isVisible()
            and not self.launcher.launcher_sleeping
            and QApplication.activeWindow() is self.launcher
            and QApplication.activeModalWidget() is None
        )

    def _items(self):
        items = self.launcher.config.get("_screensaver_items", [])
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            log_warning("Invalid screensaver media list.")
            return []
        return items

    def _seconds(self, key, default, minimum, maximum):
        value = self.launcher.config.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            log_warning(f"Invalid screensaver setting {key}; using {default}.")
            return default
        return value

    def activity(self):
        was_visible = self.overlay.isVisible()
        self.last_activity = time.monotonic()
        if was_visible:
            self.stop()
        return was_visible

    def _check_idle(self):
        cursor_position = QCursor.pos()
        if cursor_position != self.last_cursor_position:
            self.last_cursor_position = cursor_position
            self.activity()
        if not self._active():
            self.activity()
            return
        if self.overlay.isVisible():
            return
        config = self.launcher.config
        if not config.get("_screensaver_enabled", False) or not self._items():
            return
        delay = self._seconds("_screensaver_idle_seconds", 300, 10, 86400)
        if time.monotonic() - self.last_activity >= delay:
            self.index = -1
            self.overlay.setGeometry(self.launcher.rect())
            if self._next_item():
                self.overlay.show()
                self.overlay.raise_()
                seconds = self._seconds("_screensaver_rotation_seconds", 30, 5, 3600)
                self.rotation_timer.start(seconds * 1000)
            else:
                self.last_activity = time.monotonic()

    def _release_media(self):
        self.frame_timer.stop()
        if self.movie is not None:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def _next_item(self):
        self._release_media()
        items = self._items()
        for _ in range(len(items)):
            self.index = (self.index + 1) % len(items)
            path = items[self.index]
            if Path(path).suffix.lower() in VIDEO_SUFFIXES:
                capture = cv2.VideoCapture(path)
                if capture.isOpened():
                    self.capture = capture
                    if self._video_frame():
                        fps = capture.get(cv2.CAP_PROP_FPS)
                        if not self.launcher.config.get("_reduce_motion", False):
                            self.frame_timer.start(round(1000 / fps) if 1 <= fps <= 60 else 33)
                        return True
                    self._release_media()
                else:
                    capture.release()
            else:
                reader = QImageReader(path)
                image = reader.read()
                if not image.isNull():
                    self.pixmap = QPixmap.fromImage(image)
                    if reader.supportsAnimation() and not self.launcher.config.get("_reduce_motion", False):
                        self.movie = QMovie(path, parent=self)
                        self.movie.frameChanged.connect(self._movie_frame)
                        self.movie.start()
                    self._display()
                    return True
            log_warning(f"Cannot open screensaver media: {path}")
        self.stop()
        return False

    def _movie_frame(self, _frame):
        if self.movie is not None:
            self.pixmap = self.movie.currentPixmap()
            self._display()

    def _video_frame(self):
        if self.capture is None:
            return False
        ok, frame = self.capture.read()
        if not ok:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.capture.read()
        if not ok:
            log_warning("Screensaver video could not be decoded.")
            return False
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = frame.shape
        image = QImage(frame.data, width, height, channels * width, QImage.Format.Format_RGB888).copy()
        self.pixmap = QPixmap.fromImage(image)
        self._display()
        return True

    def _tick_video(self):
        if not self._video_frame():
            self._next_item()

    def _display(self):
        if not self.pixmap.isNull():
            self.overlay.setPixmap(self.pixmap.scaled(
                self.overlay.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def stop(self):
        self.rotation_timer.stop()
        self._release_media()
        self.overlay.hide()
        self.overlay.clear()
        self.pixmap = QPixmap()

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self.launcher and kind == QEvent.Type.Resize:
            self.overlay.setGeometry(self.launcher.rect())
            self._display()
        if watched is self.launcher and kind == QEvent.Type.Hide:
            self.stop()
            self.last_activity = time.monotonic()
        if kind in (QEvent.Type.ApplicationDeactivate, QEvent.Type.WindowDeactivate):
            if watched is self.launcher or kind == QEvent.Type.ApplicationDeactivate:
                self.activity()
        if kind in (
            QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove, QEvent.Type.Wheel, QEvent.Type.TouchBegin,
        ) and self._active():
            if self.activity():
                return True
        return False
