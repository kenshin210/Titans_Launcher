import json
import threading
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


class PygameControllerThread(QThread):
    raw_input = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()
        self.requestInterruption()

    def run(self):
        if not PYGAME_AVAILABLE or pygame is None:
            log_warning("pygame-ce module not available. Gamepad input disabled.")
            return

        try:
            pygame.init()
            pygame.joystick.init()
        except Exception as error:
            log_error(f"Failed to initialize pygame joystick subsystem: {error}")
            return

        joysticks = {}
        active_axes = {}

        while not self._stop_event.is_set() and not self.isInterruptionRequested():
            try:
                if not pygame.joystick.get_init():
                    pygame.joystick.init()
                    joysticks.clear()
                    active_axes.clear()
                    log_info("Reinitialized pygame joystick subsystem.")

                pygame.event.pump()

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
                        self.raw_input.emit(f"button:{event.button}")
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

                self._stop_event.wait(0.03)
            except Exception as error:
                if self._stop_event.is_set() or self.isInterruptionRequested():
                    break
                log_warning(f"Pygame controller polling error: {error}")
                if not pygame.joystick.get_init():
                    try:
                        pygame.joystick.init()
                        joysticks.clear()
                        log_info("Recovered pygame joystick subsystem after polling error.")
                    except Exception as init_error:
                        log_error(f"Failed to recover pygame joystick subsystem: {init_error}")
                self._stop_event.wait(2)

        pygame.quit()


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
