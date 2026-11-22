from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from Application.ui.dialogs.file_picker import ControllerFileDialog
from Application.core.sound import (
    BUILTIN_SOUNDS,
    CUSTOM_CHOICE,
    SOUND_FILE_FILTER,
)
from Application.styles import load_stylesheet


class NavigationSoundCard(QFrame):
    """General-settings card for the sound played when moving between tiles."""

    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("soundDisplayCard")
        theme_color = launcher.get_theme_color() if hasattr(launcher, "get_theme_color") else "#DC143C"
        self.setStyleSheet(load_stylesheet(theme_color=theme_color))

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self._save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Navigation Sound")
        title.setObjectName("soundDisplaySectionTitle")
        layout.addWidget(title)

        description = QLabel("Sound played when you move between tiles and buttons.")
        description.setObjectName("soundDisplayDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.enabled_checkbox = QCheckBox("Enable navigation sound")
        layout.addWidget(self.enabled_checkbox)

        form = QFormLayout()
        self.sound_combo = QComboBox()
        self.sound_combo.setObjectName("soundDisplayControl")
        self.sound_combo.addItems([*BUILTIN_SOUNDS, CUSTOM_CHOICE])
        form.addRow("Sound:", self.sound_combo)

        custom_row = QHBoxLayout()
        self.custom_path_input = QLineEdit()
        self.custom_path_input.setReadOnly(True)
        self.custom_path_input.setPlaceholderText("Choose a .wav, .ogg, .mp3 or .flac file")
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setObjectName("soundDisplayButton")
        custom_row.addWidget(self.custom_path_input, stretch=1)
        custom_row.addWidget(self.browse_button)
        form.addRow("Custom file:", custom_row)

        volume_row = QHBoxLayout()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("soundDisplaySlider")
        self.volume_slider.setRange(0, 100)
        self.volume_label = QLabel()
        self.volume_label.setObjectName("soundDisplayValue")
        volume_row.addWidget(self.volume_slider, stretch=1)
        volume_row.addWidget(self.volume_label)
        form.addRow("Volume:", volume_row)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.preview_button = QPushButton("Preview")
        self.preview_button.setObjectName("soundDisplayButton")
        actions.addWidget(self.preview_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = QLabel()
        self.status.setObjectName("soundDisplayStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self._load_from_config()
        self.enabled_checkbox.toggled.connect(self._on_changed)
        self.sound_combo.currentTextChanged.connect(self._on_changed)
        self.volume_slider.valueChanged.connect(self._on_changed)
        self.browse_button.clicked.connect(self._browse)
        self.preview_button.clicked.connect(self._preview)

    @property
    def config(self):
        return self.launcher.config

    def _load_from_config(self):
        widgets = (self.enabled_checkbox, self.sound_combo, self.volume_slider)
        for widget in widgets:
            widget.blockSignals(True)
        self.enabled_checkbox.setChecked(bool(self.config.get("_nav_sound_enabled", True)))
        choice = self.config.get("_nav_sound_choice", "Tick")
        index = self.sound_combo.findText(choice)
        self.sound_combo.setCurrentIndex(index if index >= 0 else 0)
        self.volume_slider.setValue(int(self.config.get("_nav_sound_volume", 60)))
        for widget in widgets:
            widget.blockSignals(False)
        self.custom_path_input.setText(self.config.get("_nav_sound_custom_path", ""))
        self._refresh_controls()

    def _refresh_controls(self):
        custom = self.sound_combo.currentText() == CUSTOM_CHOICE
        enabled = self.enabled_checkbox.isChecked()
        self.sound_combo.setEnabled(enabled)
        self.volume_slider.setEnabled(enabled)
        self.browse_button.setEnabled(enabled and custom)
        self.custom_path_input.setEnabled(enabled and custom)
        self.preview_button.setEnabled(enabled)
        self.volume_label.setText(f"{self.volume_slider.value()}%")

    def _on_changed(self, *_args):
        self.config["_nav_sound_enabled"] = self.enabled_checkbox.isChecked()
        self.config["_nav_sound_choice"] = self.sound_combo.currentText()
        self.config["_nav_sound_volume"] = self.volume_slider.value()
        self._refresh_controls()
        self.save_timer.start()

    def _save(self):
        self.launcher.save_config_file()

    def _browse(self):
        start_dir = Path(self.custom_path_input.text()).parent
        file_path, _ = ControllerFileDialog.get_open_file_name(
            self,
            "Select Navigation Sound",
            str(start_dir if start_dir.is_dir() else Path.home()),
            SOUND_FILE_FILTER,
        )
        if not file_path:
            return
        self.custom_path_input.setText(file_path)
        self.config["_nav_sound_custom_path"] = file_path
        self.launcher.nav_sound.forget(file_path)
        self.save_timer.start()
        self._preview()

    def _preview(self):
        player = getattr(self.launcher, "nav_sound", None)
        if player is None:
            self.status.setText("Sound playback is not available.")
            return
        if player.play(force=True):
            self.status.setText("")
        else:
            self.status.setText(
                "Could not play this sound. Check the file and that an audio device is available."
            )
