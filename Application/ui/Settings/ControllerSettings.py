import json
import re
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QColorDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget
)

from Application.ui.dialogs.file_picker import ControllerFileDialog
from Application.ui.dialogs.on_screen_keyboard import OnScreenKeyboard, _keyboard_color
from Application.core.config import CONTROLLER_INPUTS_DIR

INPUTS_DIR = CONTROLLER_INPUTS_DIR
DEFAULT_BINDINGS = {
    "up": ["hat:up", "axis:1:negative"],
    "down": ["hat:down", "axis:1:positive"],
    "left": ["hat:left", "axis:0:negative"],
    "right": ["hat:right", "axis:0:positive"],
    "select": ["button:0"],
    "back": ["button:1"],
    "previous_tab": ["button:4"],
    "next_tab": ["button:5"],
    "control_centre": []
}


class ControllerSettingsWidget(QWidget):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("controllerSettingsCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget#controllerSettingsCard {
                background-color: rgba(22, 22, 22, 200);
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 15);
            }
            QLabel {
                color: white;
                background: transparent;
            }
        """)
        self.profile_data = {}
        self.binding_labels = {}
        self.bind_buttons = {}
        self._capture_slot = None
        self._capture_action = None

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer_layout.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(18)

        title = QLabel("Controller")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel(
            "Choose a controller profile, adjust external cursor speed, and customize the onscreen keyboard."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #888888; font-size: 14px;")
        layout.addWidget(description)

        self.preference_save_timer = QTimer(self)
        self.preference_save_timer.setSingleShot(True)
        self.preference_save_timer.setInterval(300)
        self.preference_save_timer.timeout.connect(self._save_controller_preferences)

        config = getattr(self.launcher, "config", {})
        try:
            sensitivity = int(config.get("_browser_cursor_sensitivity", 18))
        except (TypeError, ValueError):
            sensitivity = 18
        sensitivity = max(1, min(40, sensitivity))

        self.cursor_sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.cursor_sensitivity_slider.setRange(1, 40)
        self.cursor_sensitivity_slider.setValue(sensitivity)
        self.cursor_sensitivity_label = QLabel(str(sensitivity))
        sensitivity_row = QHBoxLayout()
        sensitivity_row.addWidget(self.cursor_sensitivity_slider, stretch=1)
        sensitivity_row.addWidget(self.cursor_sensitivity_label)

        self.keyboard_background_color = _keyboard_color(
            config, "_keyboard_background_color", "#141414"
        ).name()
        self.keyboard_background_button = QPushButton("Choose Color")
        self.keyboard_background_swatch = QLabel()
        self.keyboard_background_swatch.setFixedSize(48, 28)
        self._refresh_keyboard_background_swatch()
        background_row = QHBoxLayout()
        background_row.addWidget(self.keyboard_background_button)
        background_row.addWidget(self.keyboard_background_swatch)
        background_row.addStretch()

        preferences_form = QFormLayout()
        preferences_form.addRow("External cursor sensitivity:", sensitivity_row)
        preferences_form.addRow("Keyboard background:", background_row)

        self.keyboard_image_label = QLabel()
        self.keyboard_image_label.setWordWrap(True)
        self._refresh_keyboard_image_label()
        image_button = QPushButton("Choose Image")
        clear_image_button = QPushButton("Remove Image")
        image_row = QHBoxLayout()
        image_row.addWidget(image_button)
        image_row.addWidget(clear_image_button)
        image_row.addWidget(self.keyboard_image_label, stretch=1)
        preferences_form.addRow("Keyboard background image:", image_row)
        image_button.clicked.connect(self.choose_keyboard_image)
        clear_image_button.clicked.connect(self.clear_keyboard_image)

        self.keyboard_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.keyboard_opacity_slider.setRange(0, 100)
        try:
            opacity = int(config.get("_keyboard_background_opacity", 96))
        except (TypeError, ValueError, OverflowError):
            opacity = 96
        self.keyboard_opacity_slider.setValue(max(0, min(100, opacity)))
        self.keyboard_opacity_label = QLabel(f"{self.keyboard_opacity_slider.value()}%")
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.keyboard_opacity_slider, stretch=1)
        opacity_row.addWidget(self.keyboard_opacity_label)
        preferences_form.addRow("Keyboard background opacity:", opacity_row)
        self.keyboard_opacity_slider.valueChanged.connect(self._keyboard_opacity_changed)

        for label, key, default in (
            ("Keyboard key color:", "_keyboard_key_color", "#30343c"),
            ("Keyboard special key color:", "_keyboard_special_key_color", "#464c56"),
            ("Keyboard key text color:", "_keyboard_key_text_color", "#ffffff"),
        ):
            color = _keyboard_color(config, key, default)
            button = QPushButton("Choose Color")
            swatch = QLabel()
            swatch.setFixedSize(48, 28)
            self._set_color_swatch(swatch, color.name())
            button.clicked.connect(
                lambda _checked=False, name=key, fallback=default, sample=swatch:
                    self._choose_keyboard_color(name, fallback, sample)
            )
            color_row = QHBoxLayout()
            color_row.addWidget(button)
            color_row.addWidget(swatch)
            color_row.addStretch()
            preferences_form.addRow(label, color_row)
        layout.addLayout(preferences_form)

        self.cursor_sensitivity_slider.valueChanged.connect(self._cursor_sensitivity_changed)
        self.keyboard_background_button.clicked.connect(self.choose_keyboard_background)

        self.profile_combo = QComboBox()
        self.profile_combo.setStyleSheet("background-color: rgba(40, 40, 40, 200); color: white; padding: 10px; font-size: 14px;")
        self.profile_combo.currentIndexChanged.connect(self.load_selected_profile)

        add_profile_button = QPushButton("Add Profile")
        add_profile_button.clicked.connect(self.add_profile)
        profile_row = QHBoxLayout()
        profile_row.addWidget(self.profile_combo, stretch=1)
        profile_row.addWidget(add_profile_button)
        layout.addLayout(profile_row)

        self.bindings_form = QFormLayout()
        self.bindings_form.setVerticalSpacing(12)
        layout.addLayout(self.bindings_form)
        self.clear_buttons = {}

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        layout.addWidget(self.status_label)

        save_button = QPushButton("Save Controller Profile")
        save_button.clicked.connect(self.save_profile)
        layout.addWidget(save_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

        action_labels = {
            "previous_tab": "Left Bumper (Previous Tab)",
            "next_tab": "Right Bumper (Next Tab)",
            "control_centre": "Control Centre"
        }
        for action in DEFAULT_BINDINGS:
            row = QHBoxLayout()
            value_label = QLabel()
            value_label.setStyleSheet("color: white; font-size: 14px;")
            bind_button = QPushButton("Add Binding")
            bind_button.clicked.connect(lambda checked=False, name=action: self.capture_binding(name))
            clear_button = QPushButton("Clear")
            clear_button.clicked.connect(lambda checked=False, name=action: self.clear_bindings(name))
            row.addWidget(value_label, stretch=1)
            row.addWidget(bind_button)
            row.addWidget(clear_button)
            label = action_labels.get(action, action.title())
            self.bindings_form.addRow(f"{label}:", row)
            self.binding_labels[action] = value_label
            self.bind_buttons[action] = bind_button
            self.clear_buttons[action] = clear_button

        self.refresh_profiles()

    def _cursor_sensitivity_changed(self, value):
        self.cursor_sensitivity_label.setText(str(value))
        config = getattr(self.launcher, "config", None)
        if isinstance(config, dict):
            config["_browser_cursor_sensitivity"] = value
            self.preference_save_timer.start()

    def choose_keyboard_background(self):
        color = QColorDialog.getColor(
            QColor(self.keyboard_background_color), self, "Keyboard Background"
        )
        if not color.isValid():
            return
        self.keyboard_background_color = color.name()
        self._refresh_keyboard_background_swatch()
        config = getattr(self.launcher, "config", None)
        if isinstance(config, dict):
            config["_keyboard_background_color"] = self.keyboard_background_color
            self.preference_save_timer.start()

    def _refresh_keyboard_background_swatch(self):
        self._set_color_swatch(self.keyboard_background_swatch, self.keyboard_background_color)

    @staticmethod
    def _set_color_swatch(swatch, value):
        color = QColor(value)
        text_color = "#111111" if color.lightness() > 128 else "#FFFFFF"
        swatch.setStyleSheet(
            f"background-color: {color.name()}; color: {text_color}; "
            "border: 1px solid rgba(255, 255, 255, 80); border-radius: 4px;"
        )

    def _choose_keyboard_color(self, key, default, swatch):
        config = self.launcher.config
        color = QColorDialog.getColor(_keyboard_color(config, key, default), self, "Keyboard Color")
        if color.isValid():
            config[key] = color.name()
            self._set_color_swatch(swatch, color.name())
            self.preference_save_timer.start()

    def _keyboard_opacity_changed(self, value):
        self.keyboard_opacity_label.setText(f"{value}%")
        self.launcher.config["_keyboard_background_opacity"] = value
        self.preference_save_timer.start()

    def _refresh_keyboard_image_label(self):
        path = self.launcher.config.get("_keyboard_background_image", "")
        if not isinstance(path, str):
            self.keyboard_image_label.setText("Invalid image setting")
            self.keyboard_image_label.setToolTip("Choose an image or remove the invalid setting.")
            return
        self.keyboard_image_label.setText(Path(path).name if path else "No image")
        self.keyboard_image_label.setToolTip(path)

    def choose_keyboard_image(self):
        path, _ = ControllerFileDialog.get_open_file_name(
            self, "Select Keyboard Background", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not path:
            return
        if QPixmap(path).isNull():
            QMessageBox.warning(self, "Invalid image", "Could not read the selected image.")
            return
        self.launcher.config["_keyboard_background_image"] = path
        self._refresh_keyboard_image_label()
        self.preference_save_timer.start()

    def clear_keyboard_image(self):
        self.launcher.config["_keyboard_background_image"] = ""
        self._refresh_keyboard_image_label()
        self.preference_save_timer.start()

    def _save_controller_preferences(self):
        save_config = getattr(self.launcher, "save_config_file", None)
        if callable(save_config):
            save_config()

    def refresh_profiles(self, selected_name=None):
        INPUTS_DIR.mkdir(parents=True, exist_ok=True)
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        paths = sorted(INPUTS_DIR.glob("*.json"))
        if not paths:
            default_path = INPUTS_DIR / "Xbox Controller.json"
            default_path.write_text(json.dumps({"name": "Xbox Controller", "bindings": DEFAULT_BINDINGS}, indent=4) + "\n")
            paths = [default_path]

        for path in paths:
            label = path.stem
            try:
                with path.open("r", encoding="utf-8") as profile_file:
                    label = json.load(profile_file).get("name", label)
            except (OSError, json.JSONDecodeError, AttributeError):
                pass
            self.profile_combo.addItem(label, str(path))

        preferred = selected_name or self.launcher.config.get("_controller_profile", "Xbox Controller.json")
        index = next((i for i in range(self.profile_combo.count())
                      if Path(self.profile_combo.itemData(i)).name == Path(preferred).name), 0)
        self.profile_combo.setCurrentIndex(index)
        self.profile_combo.blockSignals(False)
        self.load_selected_profile()

    def load_selected_profile(self, _index=None):
        self.stop_capture()
        profile_path = self.profile_combo.currentData()
        if not profile_path:
            return
        try:
            with open(profile_path, "r", encoding="utf-8") as profile_file:
                self.profile_data = json.load(profile_file)
        except (OSError, json.JSONDecodeError):
            self.profile_data = {"name": Path(profile_path).stem, "bindings": {}}
        if not isinstance(self.profile_data, dict):
            self.profile_data = {"name": Path(profile_path).stem, "bindings": {}}
        if not isinstance(self.profile_data.get("bindings"), dict):
            self.profile_data["bindings"] = {}
        stored_bindings = self.profile_data["bindings"]
        normalized_bindings = {}
        for action, default_inputs in DEFAULT_BINDINGS.items():
            inputs = stored_bindings.get(action, default_inputs)
            if isinstance(inputs, str):
                inputs = [inputs]
                if action in ("up", "down", "left", "right"):
                    default_axis_input = default_inputs[1]
                    if default_axis_input not in inputs:
                        inputs.append(default_axis_input)
            if not isinstance(inputs, list):
                inputs = default_inputs
            normalized_bindings[action] = [
                input_name for input_name in inputs
                if isinstance(input_name, str) and input_name
            ]
        for action, inputs in stored_bindings.items():
            if action not in normalized_bindings:
                if isinstance(inputs, str):
                    inputs = [inputs]
                if isinstance(inputs, list):
                    normalized_bindings[action] = [
                        input_name for input_name in inputs
                        if isinstance(input_name, str) and input_name
                    ]
        self.profile_data["bindings"] = normalized_bindings
        self.update_binding_labels()

    def update_binding_labels(self):
        for action, label in self.binding_labels.items():
            bindings = self.profile_data.get("bindings", {}).get(action, [])
            label.setText(" | ".join(bindings) if bindings else "Not assigned")

    def capture_binding(self, action):
        if self._capture_slot:
            self.stop_capture()
            return
        controller_thread = getattr(self.launcher, "controller_thread", None)
        if controller_thread is None:
            QMessageBox.warning(self, "Controller unavailable", "Install pygame-ce and connect a controller before binding inputs.")
            return

        self.launcher.controller_capture_active = True
        self.bind_buttons[action].setText("Cancel")

        self._capture_action = action
        self._capture_slot = self.handle_captured_input
        controller_thread.raw_input.connect(self._capture_slot)
        self.status_label.setText(f"Press a button or D-pad direction, or move a stick for {action}.")

    @pyqtSlot(str)
    def handle_captured_input(self, input_name):
        if self._capture_action is None:
            return
        bindings = self.profile_data["bindings"].setdefault(self._capture_action, [])
        if input_name not in bindings:
            bindings.append(input_name)
        self.stop_capture()
        self.update_binding_labels()

    def clear_bindings(self, action):
        self.profile_data["bindings"][action] = []
        self.update_binding_labels()

    def stop_capture(self):
        if self._capture_slot:
            controller_thread = getattr(self.launcher, "controller_thread", None)
            if controller_thread:
                try:
                    controller_thread.raw_input.disconnect(self._capture_slot)
                except (TypeError, RuntimeError):
                    pass
            self._capture_slot = None
        self._capture_action = None
        self.launcher.controller_capture_active = False
        for button in self.bind_buttons.values():
            button.setText("Bind")
        self.status_label.setText("")

    def add_profile(self):
        name, accepted = OnScreenKeyboard.get_text(self, "Add Controller Profile - enter a profile name")
        if not accepted or not name.strip():
            return
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
        if not safe_name:
            QMessageBox.warning(self, "Invalid name", "Enter a profile name containing letters or numbers.")
            return
        profile_path = INPUTS_DIR / f"{safe_name}.json"
        if profile_path.exists():
            QMessageBox.warning(self, "Profile exists", "A profile with that name already exists.")
            return
        profile_path.write_text(json.dumps({"name": name.strip(), "bindings": DEFAULT_BINDINGS}, indent=4) + "\n", encoding="utf-8")
        self.refresh_profiles(profile_path.name)

    def save_profile(self):
        profile_path = self.profile_combo.currentData()
        if not profile_path:
            return
        try:
            with open(profile_path, "w", encoding="utf-8") as profile_file:
                json.dump(self.profile_data, profile_file, indent=4)
                profile_file.write("\n")
            self.launcher.config["_controller_profile"] = Path(profile_path).name
            self.launcher.save_config_file()
            self.launcher.reload_controller_profile()
            QMessageBox.information(self, "Saved", "Controller profile saved.")
        except OSError as error:
            QMessageBox.critical(self, "Save failed", f"Could not save controller profile: {error}")
