from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
from PyQt6.QtWidgets import QToolButton


class AnimatedLauncherButton(QToolButton):
    def __init__(self, parent=None, enable_animations=True, enable_glitch=False, theme_color="#DC143C"):
        super().__init__(parent)
        self.enable_animations = enable_animations
        self.enable_glitch = enable_glitch
        self.theme_color = theme_color
        self.setFixedSize(225, 235)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.original_rect = QRect()

    def set_original_geometry(self, rect: QRect):
        self.original_rect = rect
        self.setGeometry(rect)

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.enable_animations and not self.original_rect.isEmpty():
            target_width, target_height = 235, 245
            center_x = self.original_rect.x() + self.original_rect.width() // 2
            center_y = self.original_rect.y() + self.original_rect.height() // 2
            glitch_x_offset = 3 if self.enable_glitch else 0
            glitch_y_offset = -2 if self.enable_glitch else 0
            self.animate_to(
                QRect(
                    center_x - target_width // 2 + glitch_x_offset,
                    center_y - target_height // 2 + glitch_y_offset,
                    target_width,
                    target_height,
                )
            )

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.enable_animations and not self.original_rect.isEmpty():
            self.animate_to(self.original_rect)

    def animate_to(self, target_rect: QRect):
        if hasattr(self, "anim") and self.anim.state() == QPropertyAnimation.State.Running:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(120)
        self.anim.setEndValue(target_rect)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.anim.start()

    def play_click_animation(self, callback):
        if not self.enable_animations:
            callback()
            return

        self.click_anim = QPropertyAnimation(self, b"geometry")
        self.click_anim.setDuration(80)
        small_width, small_height = 210, 220
        center_x = self.original_rect.x() + self.original_rect.width() // 2
        center_y = self.original_rect.y() + self.original_rect.height() // 2
        glitch_x_offset = -4 if self.enable_glitch else 0
        glitch_y_offset = 4 if self.enable_glitch else 0
        self.click_anim.setEndValue(
            QRect(
                center_x - small_width // 2 + glitch_x_offset,
                center_y - small_height // 2 + glitch_y_offset,
                small_width,
                small_height,
            )
        )
        self.click_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self.click_anim.finished.connect(callback)
        self.click_anim.start()
