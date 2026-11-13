"""Match a configured key combination from Linux keyboard input devices."""

import select
import threading
import time
from dataclasses import dataclass

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence

from Application.ui.Settings.Logger import log_error, log_warning


_MODIFIERS = (
    (Qt.KeyboardModifier.ControlModifier, ("KEY_LEFTCTRL", "KEY_RIGHTCTRL")),
    (Qt.KeyboardModifier.ShiftModifier, ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT")),
    (Qt.KeyboardModifier.AltModifier, ("KEY_LEFTALT", "KEY_RIGHTALT")),
    (Qt.KeyboardModifier.MetaModifier, ("KEY_LEFTMETA", "KEY_RIGHTMETA")),
)
_KEY_ALIASES = {
    "ESCAPE": "ESC",
    "RETURN": "ENTER",
    "BACKTAB": "TAB",
    "PRINT": "SYSRQ",
    "QUOTELEFT": "GRAVE",
    "BRACKETLEFT": "LEFTBRACE",
    "BRACKETRIGHT": "RIGHTBRACE",
}


@dataclass(frozen=True)
class ShortcutChord:
    key_code: int
    modifier_groups: tuple[frozenset[int], ...]
    required_modifiers: frozenset[frozenset[int]]


def parse_shortcut(sequence, ecodes):
    """Translate a one-chord Qt sequence into Linux input key codes."""
    key_sequence = QKeySequence(sequence)
    if key_sequence.count() != 1:
        return None

    combination = key_sequence[0]
    qt_key = Qt.Key(combination.key())
    if qt_key.name is None:
        return None
    key_name = qt_key.name.removeprefix("Key_").upper()
    key_name = _KEY_ALIASES.get(key_name, key_name)
    key_code = ecodes.ecodes.get(f"KEY_{key_name}")
    if key_code is None:
        return None

    modifier_groups = tuple(
        frozenset(
            ecodes.ecodes[name]
            for name in names
            if name in ecodes.ecodes
        )
        for _modifier, names in _MODIFIERS
    )
    required_modifiers = frozenset(
        group
        for (modifier, _names), group in zip(_MODIFIERS, modifier_groups)
        if combination.keyboardModifiers() & modifier
    )
    if any(not group for group in required_modifiers):
        return None
    if key_code in set().union(*modifier_groups):
        return None

    return ShortcutChord(key_code, modifier_groups, required_modifiers)


def matches_shortcut(pressed_keys, chord):
    """Return whether pressed keys exactly match the chord's modifiers and key."""
    if chord is None or chord.key_code not in pressed_keys:
        return False
    return all(
        bool(pressed_keys.intersection(group)) == (group in chord.required_modifiers)
        for group in chord.modifier_groups
    )


class GlobalShortcutListener(QThread):
    """Watch only for the configured chord; never retain or log other key input."""

    shortcut_activated = pyqtSignal()

    def __init__(self, sequence, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._sequence_lock = threading.Lock()
        self._sequence = sequence
        self._sequence_version = 0

    def set_shortcut(self, sequence):
        with self._sequence_lock:
            self._sequence = sequence
            self._sequence_version += 1

    def stop(self):
        self._stop_event.set()

    def _sequence_snapshot(self):
        with self._sequence_lock:
            return self._sequence_version, self._sequence

    def run(self):
        try:
            import evdev
        except ImportError as error:
            log_error(
                "Global keyboard shortcut unavailable because python-evdev is not installed.",
                details=str(error),
            )
            return

        devices = {}
        pressed_by_device = {}
        last_version = -1
        chord = None
        tracked_codes = set()
        next_scan = 0.0
        warned_access = False

        def close_device(path):
            device = devices.pop(path, None)
            pressed_by_device.pop(path, None)
            if device is not None:
                try:
                    device.close()
                except OSError:
                    pass

        try:
            while not self._stop_event.is_set():
                version, sequence = self._sequence_snapshot()
                if version != last_version:
                    last_version = version
                    chord = parse_shortcut(sequence, evdev.ecodes) if sequence else None
                    tracked_codes = {chord.key_code} if chord is not None else set()
                    if chord is not None:
                        tracked_codes.update(
                            code
                            for group in chord.modifier_groups
                            for code in group
                        )
                    for device_keys in pressed_by_device.values():
                        device_keys.clear()
                    if sequence and chord is None:
                        log_warning(
                            "Global shortcut requires one supported key combination."
                        )

                if chord is None:
                    for path in list(devices):
                        close_device(path)
                    self._stop_event.wait(0.2)
                    continue

                now = time.monotonic()
                if now >= next_scan:
                    try:
                        available_paths = set(evdev.list_devices())
                    except OSError as error:
                        if not warned_access:
                            log_warning(
                                "Could not enumerate keyboard input devices; "
                                "the global shortcut may be unavailable.",
                                details=str(error),
                            )
                            warned_access = True
                        self._stop_event.wait(0.5)
                        continue

                    for path in set(devices) - available_paths:
                        close_device(path)
                    access_errors = []
                    for path in available_paths - set(devices):
                        try:
                            device = evdev.InputDevice(path)
                            capabilities = device.capabilities()
                            key_codes = capabilities.get(evdev.ecodes.EV_KEY, ())
                            if evdev.ecodes.KEY_A not in key_codes:
                                device.close()
                                continue
                            devices[path] = device
                            pressed_by_device[path] = set()
                        except OSError as error:
                            access_errors.append(error)
                    if not devices and access_errors and not warned_access:
                        log_warning(
                            "Global shortcut requires read access to keyboard "
                            "devices under /dev/input.",
                            details=str(access_errors[0]),
                        )
                        warned_access = True
                    next_scan = now + 1.0

                if not devices:
                    self._stop_event.wait(0.2)
                    continue

                try:
                    readable, _writable, _exceptional = select.select(
                        list(devices.values()), [], [], 0.2
                    )
                except InterruptedError:
                    continue
                except (OSError, ValueError) as error:
                    if not warned_access:
                        log_warning(
                            "Global shortcut could not monitor keyboard input devices.",
                            details=str(error),
                        )
                        warned_access = True
                    for path in list(devices):
                        close_device(path)
                    next_scan = 0.0
                    continue

                for device in readable:
                    path = device.path
                    try:
                        events = device.read()
                    except OSError:
                        close_device(path)
                        continue
                    for event in events:
                        if (
                            event.type != evdev.ecodes.EV_KEY
                            or event.value not in (0, 1)
                            or event.code not in tracked_codes
                        ):
                            continue
                        pressed_keys = set().union(*pressed_by_device.values())
                        was_pressed = event.code in pressed_keys
                        device_keys = pressed_by_device[path]
                        if event.value:
                            device_keys.add(event.code)
                        else:
                            device_keys.discard(event.code)
                        if event.value and not was_pressed:
                            pressed_keys.add(event.code)
                            if matches_shortcut(pressed_keys, chord):
                                self.shortcut_activated.emit()
        finally:
            for path in list(devices):
                close_device(path)
