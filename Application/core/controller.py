import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from .config import CONTROLLER_INPUTS_DIR, DEFAULT_CONTROLLER_BINDINGS

from Application.ui.Settings.Logger import log_error, log_info, log_warning

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    pygame = None
    PYGAME_AVAILABLE = False


@contextmanager
def _background_joystick_events():
    name = "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"
    previous = os.environ.get(name)
    os.environ[name] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


class PygameControllerThread(QThread):
    raw_input = pyqtSignal(str)
    keyboard_shortcut = pyqtSignal()
    browser_pointer = pyqtSignal(float, float, float, float)
    browser_pointer_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._browser_pointer_enabled = threading.Event()

    def set_browser_pointer_enabled(self, enabled):
        if enabled:
            self._browser_pointer_enabled.set()
        else:
            self._browser_pointer_enabled.clear()

    def stop(self):
        self._stop_event.set()
        self.requestInterruption()

    def run(self):
        if not PYGAME_AVAILABLE or pygame is None:
            log_warning("pygame-ce module not available. Gamepad input disabled.")
            return

        try:
            with _background_joystick_events():
                pygame.init()
                pygame.joystick.init()
        except Exception as error:
            log_error(f"Failed to initialize pygame joystick subsystem: {error}")
            return

        joysticks = {}
        active_axes = {}
        pointer_poller = None
        pointer_error_reported = False
        shortcuts = ControllerShortcut()

        while not self._stop_event.is_set() and not self.isInterruptionRequested():
            try:
                if not pygame.joystick.get_init():
                    with _background_joystick_events():
                        pygame.joystick.init()
                    joysticks.clear()
                    active_axes.clear()
                    log_info("Reinitialized pygame joystick subsystem.")

                pygame.event.pump()

                if pointer_poller is None and not pointer_error_reported:
                    try:
                        from pygame._sdl2 import controller as sdl_controller
                        sdl_controller.init()
                        pointer_poller = BrowserPointerPoller(pygame, sdl_controller)
                    except (ImportError, pygame.error) as error:
                        log_error(f"Controller shortcut and browser mouse unavailable: {error}")
                        self.browser_pointer_error.emit(str(error))
                        pointer_error_reported = True
                if pointer_poller is not None:
                    pointer_poller.sync()

                for joystick_index in range(pygame.joystick.get_count()):
                    if joystick_index not in joysticks:
                        joystick = pygame.joystick.Joystick(joystick_index)
                        joystick.init()
                        joysticks[joystick_index] = joystick
                        log_info(
                            f"Pygame-ce detected controller: {joystick.get_name()} "
                            f"(ID: {joystick_index})"
                        )

                for event in pygame.event.get():
                    if event.type == pygame.JOYBUTTONDOWN:
                        mapping = pointer_poller.button_mapping(event.instance_id) if pointer_poller else None
                        inputs, activate = shortcuts.button(event.instance_id, event.button, True, mapping)
                        for input_name in inputs:
                            self.raw_input.emit(input_name)
                        if activate:
                            self.keyboard_shortcut.emit()
                    elif event.type == pygame.JOYBUTTONUP:
                        mapping = pointer_poller.button_mapping(event.instance_id) if pointer_poller else None
                        inputs, activate = shortcuts.button(event.instance_id, event.button, False, mapping)
                        for input_name in inputs:
                            self.raw_input.emit(input_name)
                        if activate:
                            self.keyboard_shortcut.emit()
                    elif event.type == pygame.JOYDEVICEREMOVED:
                        shortcuts.remove(event.instance_id)
                    elif event.type == pygame.JOYHATMOTION:
                        hat_x, hat_y = event.value
                        if hat_x == 1:
                            self.raw_input.emit("hat:right")
                        elif hat_x == -1:
                            self.raw_input.emit("hat:left")
                        if hat_y == 1:
                            self.raw_input.emit("hat:up")
                        elif hat_y == -1:
                            self.raw_input.emit("hat:down")
                    elif event.type == pygame.JOYAXISMOTION:
                        axis_key = (event.joy, event.axis)
                        if event.value <= -0.5:
                            axis_input = f"axis:{event.axis}:negative"
                        elif event.value >= 0.5:
                            axis_input = f"axis:{event.axis}:positive"
                        else:
                            axis_input = None

                        if axis_input and active_axes.get(axis_key) != axis_input:
                            self.raw_input.emit(axis_input)
                            active_axes[axis_key] = axis_input
                        elif axis_input is None:
                            active_axes.pop(axis_key, None)

                if self._browser_pointer_enabled.is_set():
                    if pointer_poller is not None:
                        self.browser_pointer.emit(*pointer_poller.sample())

                self._stop_event.wait(0.03)
            except Exception as error:
                if self._stop_event.is_set() or self.isInterruptionRequested():
                    break
                if self._browser_pointer_enabled.is_set():
                    self.browser_pointer.emit(0.0, 0.0, 0.0, 0.0)
                log_warning(f"Pygame controller polling error: {error}")
                if not pygame.joystick.get_init():
                    try:
                        with _background_joystick_events():
                            pygame.joystick.init()
                        joysticks.clear()
                        log_info("Recovered pygame joystick subsystem after polling error.")
                    except Exception as init_error:
                        log_error(f"Failed to recover pygame joystick subsystem: {init_error}")
                self._stop_event.wait(2)

        if pointer_poller is not None:
            pointer_poller.close()
        pygame.quit()


class ControllerShortcut:
    """Reserve guide while held; replay it unless a keyboard shortcut was used."""

    def __init__(self):
        self.held_guide = {}

    def button(self, instance_id, button, pressed, mapping):
        guide, x, b = mapping if mapping else (None, None, None)
        if button == guide:
            if pressed:
                self.held_guide[instance_id] = False
                return [], False
            used = self.held_guide.pop(instance_id, None)
            return ([f"button:{button}"] if used is False else []), False
        if pressed and button in (x, b) and instance_id in self.held_guide:
            if not self.held_guide[instance_id]:
                self.held_guide[instance_id] = True
                return [], True
            return [], False
        return ([f"button:{button}"] if pressed else []), False

    def remove(self, instance_id):
        self.held_guide.pop(instance_id, None)


class BrowserPointerPoller:
    """Read SDL-mapped axes, which are independent of raw joystick axis numbers."""

    def __init__(self, pygame_module, controller_module):
        self.pygame = pygame_module
        self.controller_module = controller_module
        self.controllers = {}
        self.unsupported = set()

    def sync(self):
        connected = set()
        for index in range(self.pygame.joystick.get_count()):
            joystick = self.pygame.joystick.Joystick(index)
            if not joystick.get_init():
                joystick.init()
            instance_id = joystick.get_instance_id()
            connected.add(instance_id)
            if instance_id not in self.controllers and instance_id not in self.unsupported:
                if self.controller_module.is_controller(index):
                    self.controllers[instance_id] = self.controller_module.Controller(index)
                else:
                    self.unsupported.add(instance_id)
                    log_warning(f"Controller '{joystick.get_name()}' has no SDL gamepad mapping; browser mouse unavailable.")

        for instance_id in set(self.controllers) - connected:
            self.controllers.pop(instance_id).quit()
        self.unsupported.intersection_update(connected)

    def button_mapping(self, instance_id):
        controller = self.controllers.get(instance_id)
        if controller is None or not controller.attached():
            return None
        mapping = controller.get_mapping()
        names = (mapping.get("guide", ""), mapping.get("x", ""), mapping.get("b", ""))
        if not names[0].startswith("b") or not names[0][1:].isdigit():
            return None
        buttons = tuple(int(name[1:]) if name.startswith("b") and name[1:].isdigit() else None
                        for name in names)
        return buttons if any(button is not None for button in buttons[1:]) else None

    def sample(self):
        self.sync()
        x = y = left = right = 0.0
        for controller in self.controllers.values():
            if not controller.attached():
                continue
            x += controller.get_axis(self.pygame.CONTROLLER_AXIS_RIGHTX) / 32767.0
            y += controller.get_axis(self.pygame.CONTROLLER_AXIS_RIGHTY) / 32767.0
            left = max(left, controller.get_axis(self.pygame.CONTROLLER_AXIS_TRIGGERLEFT) / 32767.0)
            right = max(right, controller.get_axis(self.pygame.CONTROLLER_AXIS_TRIGGERRIGHT) / 32767.0)
        return tuple(max(-1.0, min(1.0, value)) for value in (x, y, left, right))

    def close(self):
        for controller in self.controllers.values():
            controller.quit()
        self.controllers.clear()


def load_controller_bindings(profile_name):
    profile_path = CONTROLLER_INPUTS_DIR / Path(profile_name).name
    bindings = DEFAULT_CONTROLLER_BINDINGS
    try:
        if not profile_path.exists():
            CONTROLLER_INPUTS_DIR.mkdir(parents=True, exist_ok=True)
            with profile_path.open("w", encoding="utf-8") as profile_file:
                json.dump(
                    {"name": profile_path.stem, "bindings": DEFAULT_CONTROLLER_BINDINGS},
                    profile_file,
                    indent=4,
                )
                profile_file.write("\n")
            log_info(f"Created default controller profile at {profile_path}")

        with profile_path.open("r", encoding="utf-8") as profile_file:
            profile_data = json.load(profile_file)
        if isinstance(profile_data, dict) and isinstance(profile_data.get("bindings"), dict):
            bindings = {**DEFAULT_CONTROLLER_BINDINGS, **profile_data["bindings"]}
    except json.JSONDecodeError as error:
        backup_path = profile_path.with_name(
            f"{profile_path.stem}.invalid-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}{profile_path.suffix}"
        )
        try:
            profile_path.replace(backup_path)
            with profile_path.open("w", encoding="utf-8") as profile_file:
                json.dump(
                    {"name": profile_path.stem, "bindings": DEFAULT_CONTROLLER_BINDINGS},
                    profile_file,
                    indent=4,
                )
                profile_file.write("\n")
            log_warning(
                f"Invalid controller profile {profile_path} was reset to defaults.",
                details=f"{error}; original backed up to {backup_path}",
            )
        except OSError as repair_error:
            log_warning(
                f"Could not repair controller profile {profile_path}; using default bindings.",
                details=f"{error}; {repair_error}",
            )
    except OSError as error:
        log_warning(
            f"Could not load controller profile {profile_path}; using default bindings.",
            details=str(error),
        )

    controller_bindings = {}
    for action, input_names in bindings.items():
        if not isinstance(action, str):
            continue
        if isinstance(input_names, str):
            input_names = [input_names]
            if action in ("up", "down", "left", "right"):
                default_axis_input = DEFAULT_CONTROLLER_BINDINGS[action][1]
                if default_axis_input not in input_names:
                    input_names.append(default_axis_input)
        if not isinstance(input_names, list):
            continue
        for input_name in input_names:
            if isinstance(input_name, str) and input_name:
                controller_bindings[input_name] = action
    return controller_bindings


def map_raw_input(input_name, controller_bindings):
    return controller_bindings.get(input_name)
