"""Loading screen, run in its own process so animation continues during startup."""
import os
import sys
from contextlib import redirect_stdout

from PyQt6.QtCore import QRectF, QSocketNotifier, Qt
from PyQt6.QtGui import QColor, QImageReader, QMovie, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class StartupArtwork(QWidget):
    def __init__(self, path, fit, animate, parent=None):
        super().__init__(parent)
        self.fit = fit
        self.movie = None
        self.pixmap = QPixmap()
        if not path:
            return
        reader = QImageReader(path)
        if not reader.canRead():
            print(f"Could not load startup image: {path}", file=sys.stderr)
            return
        if reader.supportsAnimation() and animate:
            self.movie = QMovie(path, parent=self)
            if not self.movie.isValid():
                print(f"Could not load startup animation: {path}", file=sys.stderr)
                self.movie = None
                return
            self.movie.frameChanged.connect(self.update)
            self.movie.finished.connect(self._restart_movie)
            self.movie.start()
        else:
            self.pixmap = QPixmap.fromImage(reader.read())
            if self.pixmap.isNull():
                print(f"Could not load startup image: {path}", file=sys.stderr)

    def _restart_movie(self):
        if self.movie is not None and self.movie.frameCount() != 1:
            self.movie.start()

    def paintEvent(self, event):
        super().paintEvent(event)
        pixmap = self.movie.currentPixmap() if self.movie is not None else self.pixmap
        if pixmap.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        if self.fit == "Stretch":
            target = QRectF(self.rect())
        else:
            mode = (Qt.AspectRatioMode.KeepAspectRatioByExpanding
                    if self.fit == "Fill" else Qt.AspectRatioMode.KeepAspectRatio)
            size = pixmap.size().scaled(self.size(), mode)
            target = QRectF(
                (self.width() - size.width()) / 2,
                (self.height() - size.height()) / 2,
                size.width(), size.height(),
            )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))


class StartupScreen(QWidget):
    def __init__(self, config):
        super().__init__()
        self.setWindowTitle("Titans Launcher - Starting")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        try:
            color = QColor(config.get("_startup_background_color", "#141414"))
        except TypeError:
            color = QColor()
        if not color.isValid():
            print("Invalid startup background color; using the default.", file=sys.stderr)
            color = QColor("#141414")
        text_color = "#111111" if color.lightness() > 128 else "#ffffff"
        self.setStyleSheet(f"StartupScreen {{ background-color: {color.name()}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        title = QLabel("TITANS LAUNCHER")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {text_color}; font-size: 30px; font-weight: bold;")
        layout.addWidget(title)
        path = config.get("_startup_image_path", "")
        if not isinstance(path, str):
            print("Invalid startup image path; using the default screen.", file=sys.stderr)
            path = ""
        fit = config.get("_startup_image_fit", "Fit")
        if fit not in ("Fit", "Fill", "Stretch"):
            print("Invalid startup image fit; using Fit.", file=sys.stderr)
            fit = "Fit"
        self.artwork = StartupArtwork(
            path, fit,
            config.get("_enable_animations", True) and not config.get("_reduce_motion", False),
        )
        layout.addWidget(self.artwork, stretch=1)
        text = config.get("_startup_loading_text", "Starting Titans...")
        if not isinstance(text, str):
            print("Invalid startup loading text; using the default.", file=sys.stderr)
            text = "Starting Titans..."
        loading = QLabel(text)
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setWordWrap(True)
        loading.setStyleSheet(f"color: {text_color}; font-size: 20px;")
        layout.addWidget(loading)


def main():
    with redirect_stdout(sys.stderr):
        from Application.core.config import load_config
        config = load_config()
        app = QApplication(sys.argv)
        screen = StartupScreen(config)
        screen.showFullScreen()
        app.processEvents()
    notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read)

    def dismiss():
        os.read(sys.stdin.fileno(), 1)
        notifier.setEnabled(False)
        app.quit()

    notifier.activated.connect(dismiss)
    print("READY", flush=True)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
