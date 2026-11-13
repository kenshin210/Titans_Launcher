import json
import re
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QWidget
)

from Application.ui.dialogs.on_screen_keyboard import OnScreenKeyboard
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
    "next_tab": ["button:5"]
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(18)

        title = QLabel("Controller")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel("Choose a controller profile and bind buttons, D-pad, sticks, or bumpers to launcher actions.")
        description.setWordWrap(True)
        description.setStyleSheet("color: #888888; font-size: 14px;")
        layout.addWidget(description)

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
            "next_tab": "Right Bumper (Next Tab)"
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
