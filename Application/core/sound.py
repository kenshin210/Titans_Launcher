import time
from pathlib import Path

from Application.core.config import ASSETS_DIR
from Application.ui.Settings.Logger import log_warning

try:
    import pygame
except ImportError:
    pygame = None

SOUNDS_DIR = ASSETS_DIR / "Sounds"
BUILTIN_SOUNDS = {
    "Tick": "tick.wav",
    "Blip": "blip.wav",
    "Soft Click": "soft_click.wav",
}
CUSTOM_CHOICE = "Custom file"
SOUND_FILE_FILTER = "Audio Files (*.wav *.ogg *.mp3 *.flac);;All Files (*)"
MIN_INTERVAL_SECONDS = 0.04


def resolve_sound_path(config):
    choice = config.get("_nav_sound_choice", "Tick")
    if choice == CUSTOM_CHOICE:
        custom = str(config.get("_nav_sound_custom_path", "")).strip()
        return Path(custom) if custom else None
    return SOUNDS_DIR / BUILTIN_SOUNDS.get(choice, BUILTIN_SOUNDS["Tick"])


class NavigationSoundPlayer:
    """Plays the tile-to-tile navigation sound using pygame's mixer."""

    def __init__(self, config):
        self.config = config
        self._sounds = {}
        self._mixer_failed = False
        self._warned_paths = set()
        self._last_played = 0.0

    def _ensure_mixer(self):
        if pygame is None or self._mixer_failed:
            return False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            return True
        except Exception as error:
            self._mixer_failed = True
            log_warning(f"Navigation sound disabled, audio mixer unavailable: {error}")
            return False

    def _load(self, path):
        key = str(path)
        if key in self._sounds:
            return self._sounds[key]
        sound = None
        try:
            sound = pygame.mixer.Sound(key)
        except Exception as error:
            if key not in self._warned_paths:
                self._warned_paths.add(key)
                log_warning(f"Could not load navigation sound {key}: {error}")
        self._sounds[key] = sound
        return sound

    def play(self, force=False):
        """Play the configured sound. `force` ignores the enabled toggle (for previews)."""
        if not force and not self.config.get("_nav_sound_enabled", True):
            return False
        now = time.monotonic()
        if not force and now - self._last_played < MIN_INTERVAL_SECONDS:
            return False
        path = resolve_sound_path(self.config)
        if path is None or not path.is_file() or not self._ensure_mixer():
            return False
        sound = self._load(path)
        if sound is None:
            return False
        try:
            volume = max(0, min(100, int(self.config.get("_nav_sound_volume", 60))))
            sound.set_volume(volume / 100)
            sound.play()
        except Exception as error:
            log_warning(f"Could not play navigation sound: {error}")
            return False
        self._last_played = now
        return True

    def forget(self, path=None):
        """Drop cached sounds so an edited file on disk is reloaded."""
        if path is None:
            self._sounds.clear()
        else:
            self._sounds.pop(str(path), None)
