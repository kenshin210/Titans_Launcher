from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QTabBar, QWidget


class SettingsFocusOverlay(QWidget):
    """Draw a focus cue above settings controls without changing their styles."""

    def __init__(self, settings):
        super().__init__(settings)
        self.settings = settings
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()
        QApplication.instance().focusChanged.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(100)

    def refresh(self, *_args):
        focused = QApplication.focusWidget()
        pages = self.settings.pages
        if (
            focused is None
            or not self.settings.isVisible()
            or not pages.isAncestorOf(focused)
            or not focused.isVisible()
        ):
            self.hide()
            return

        rect = focused.rect()
        if isinstance(focused, QTabBar):
            rect = focused.tabRect(focused.currentIndex())
        rect.moveTopLeft(focused.mapTo(self.settings, rect.topLeft()))
        visible = QRect(rect)
        ancestor = focused.parentWidget()
        while ancestor is not None and ancestor is not self.settings:
            bounds = QRect(ancestor.mapTo(self.settings, ancestor.rect().topLeft()), ancestor.size())
            visible = visible.intersected(bounds)
            ancestor = ancestor.parentWidget()
        if visible.isEmpty():
            self.hide()
            return

        geometry = visible.adjusted(-5, -5, 5, 5).intersected(self.settings.rect())
        changed = self.geometry() != geometry or self.isHidden()
        if self.geometry() != geometry:
            self.setGeometry(geometry)
        if self.isHidden():
            self.show()
        if changed or _args:
            self.raise_()
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for inset, alpha in ((1, 25), (2, 45), (3, 75)):
            painter.setPen(QPen(QColor(220, 20, 60, alpha), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(inset, inset, -inset - 1, -inset - 1), 6, 6)
        painter.setPen(QPen(QColor(255, 55, 75, 235), 2))
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawRoundedRect(self.rect().adjusted(5, 5, -6, -6), 4, 4)
