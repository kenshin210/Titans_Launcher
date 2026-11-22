from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImageReader
from PyQt6.QtWidgets import (
    QColorDialog, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from Application.ui.dialogs.file_picker import ControllerFileDialog
from Application.ui.Settings.Logger import log_warning


class StartupScreenSettingsWidget(QWidget):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("settingsCard")
        self.setStyleSheet("""
            QWidget#settingsCard {
                background-color: rgba(22, 22, 22, 200);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(18)
        title = QLabel("Startup Screen")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold; border: none;")
        layout.addWidget(title)
        description = QLabel("Customize the loading screen shown the next time Titans starts.")
        description.setWordWrap(True)
        layout.addWidget(description)

        config = launcher.config
        path = config.get("_startup_image_path", "")
        if not isinstance(path, str):
            log_warning("Invalid startup image path; using an empty path.")
            path = ""
        self.image_path = QLineEdit(path)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.choose_image)
        clear = QPushButton("Remove")
        clear.clicked.connect(self.image_path.clear)
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_path, stretch=1)
        image_row.addWidget(browse)
        image_row.addWidget(clear)

        try:
            self.background_color = QColor(config.get("_startup_background_color", "#141414"))
        except TypeError:
            self.background_color = QColor()
        if not self.background_color.isValid():
            log_warning("Invalid startup background color; using the default.")
            self.background_color = QColor("#141414")
        color_button = QPushButton("Choose Color")
        color_button.clicked.connect(self.choose_color)
        self.color_swatch = QLabel()
        self.color_swatch.setFixedSize(48, 28)
        self._refresh_swatch()
        color_row = QHBoxLayout()
        color_row.addWidget(color_button)
        color_row.addWidget(self.color_swatch)
        color_row.addStretch()

        text = config.get("_startup_loading_text", "Starting Titans...")
        if not isinstance(text, str):
            log_warning("Invalid startup loading text; using the default.")
            text = "Starting Titans..."
        self.loading_text = QLineEdit(text)
        self.image_fit = QComboBox()
        self.image_fit.addItems(["Fit", "Fill", "Stretch"])
        fit = config.get("_startup_image_fit", "Fit")
        if fit not in ("Fit", "Fill", "Stretch"):
            log_warning("Invalid startup image fit; using Fit.")
            fit = "Fit"
        self.image_fit.setCurrentText(fit)
        form = QFormLayout()
        form.addRow("GIF or image:", image_row)
        form.addRow("Background color:", color_row)
        form.addRow("Loading text:", self.loading_text)
        form.addRow("Image fit:", self.image_fit)
        layout.addLayout(form)
        save = QPushButton("Save Startup Screen")
        save.clicked.connect(self.save)
        layout.addWidget(save, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

    def choose_image(self):
        path, _ = ControllerFileDialog.get_open_file_name(
            self, "Select Startup Image", str(Path.home()),
            "Images (*.gif *.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if path:
            self.image_path.setText(path)

    def choose_color(self):
        color = QColorDialog.getColor(self.background_color, self, "Startup Background")
        if color.isValid():
            self.background_color = color
            self._refresh_swatch()

    def _refresh_swatch(self):
        self.color_swatch.setStyleSheet(
            f"background-color: {self.background_color.name()}; "
            "border: 1px solid rgba(255, 255, 255, 80); border-radius: 4px;"
        )

    def save(self):
        path = self.image_path.text().strip()
        if path and QImageReader(path).read().isNull():
            QMessageBox.warning(self, "Invalid image", "Could not read the selected startup image.")
            return
        self.launcher.config.update({
            "_startup_image_path": path,
            "_startup_background_color": self.background_color.name(),
            "_startup_loading_text": self.loading_text.text(),
            "_startup_image_fit": self.image_fit.currentText(),
        })
        self.launcher.save_config_file()
        QMessageBox.information(self, "Startup Screen", "Saved. The startup screen changes on the next launch.")
