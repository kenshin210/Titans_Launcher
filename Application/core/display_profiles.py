"""
Display Profiles Manager for Titans Launcher.

Manages named display profiles with resolution, refresh rate, scaling, and DPI settings.
Profiles are stored in ~/.local/share/titans/display_profiles.json
"""

import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

from Application.core.display_settings import DisplaySettingsManager

logger = logging.getLogger(__name__)


@dataclass
class DisplayProfile:
    """Represents a display profile with resolution and settings."""
    name: str
    resolution: str
    refresh_rate: int
    scaling: int
    dpi: int
    display_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DisplayProfile':
        """Create profile from dictionary."""
        return cls(
            name=data['name'],
            resolution=data['resolution'],
            refresh_rate=data['refresh_rate'],
            scaling=data['scaling'],
            dpi=data['dpi'],
            display_name=data.get('display_name'),
        )


class DisplayProfilesManager:
    """Manages display profiles for saving and restoring display configurations."""

    MAX_PROFILES = 10
    CONFIG_VERSION = 1

    def __init__(
        self,
        config_path: Optional[Path] = None,
        display_manager: Optional[DisplaySettingsManager] = None,
    ):
        """Initialize the display profiles manager.

        Args:
            config_path: Path to the JSON configuration file. Defaults to
                        ~/.local/share/titans/display_profiles.json
        """
        if config_path is None:
            config_path = Path.home() / ".local" / "share" / "titans" / "display_profiles.json"

        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.display_manager = display_manager or DisplaySettingsManager()

        # Load or initialize configuration
        self._load_config()

    def _load_config(self):
        """Load configuration from file or initialize with defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    self.config = data
                    logger.debug(f"Loaded display profiles from {self.config_path}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error loading config, using defaults: {e}")
                self._init_default_config()
        else:
            self._init_default_config()

    def _init_default_config(self):
        """Initialize configuration with defaults."""
        self.config = {
            "version": self.CONFIG_VERSION,
            "profiles": [],
            "current_profile": None
        }
        self._save_config()

    def _save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
                logger.debug(f"Saved display profiles to {self.config_path}")
        except IOError as e:
            logger.error(f"Error saving config: {e}")

    def add_profile(self, profile: DisplayProfile) -> bool:
        """Add a new display profile.

        Args:
            profile: DisplayProfile object to add

        Returns:
            True if successful, False if max profiles reached or name already exists
        """
        # Check if profile name already exists
        for p in self.config['profiles']:
            if p['name'] == profile.name:
                logger.warning(f"Profile '{profile.name}' already exists")
                return False

        # Check max profiles limit
        if len(self.config['profiles']) >= self.MAX_PROFILES:
            logger.warning(f"Maximum number of profiles ({self.MAX_PROFILES}) reached")
            return False

        self.config['profiles'].append(profile.to_dict())
        self._save_config()
        logger.info(f"Added profile: {profile.name}")
        return True

    def update_profile(self, name: str, profile: DisplayProfile) -> bool:
        """Update an existing display profile.

        Args:
            name: Name of the profile to update
            profile: Updated DisplayProfile object

        Returns:
            True if successful, False if profile not found
        """
        for i, p in enumerate(self.config['profiles']):
            if p['name'] == name:
                self.config['profiles'][i] = profile.to_dict()
                self._save_config()
                logger.info(f"Updated profile: {name}")
                return True

        logger.warning(f"Profile '{name}' not found")
        return False

    def delete_profile(self, name: str) -> bool:
        """Delete a display profile.

        Args:
            name: Name of the profile to delete

        Returns:
            True if successful, False if profile not found
        """
        for i, p in enumerate(self.config['profiles']):
            if p['name'] == name:
                self.config['profiles'].pop(i)
                # Clear current profile if it was the one deleted
                if self.config['current_profile'] == name:
                    self.config['current_profile'] = None
                self._save_config()
                logger.info(f"Deleted profile: {name}")
                return True

        logger.warning(f"Profile '{name}' not found")
        return False

    def get_profile(self, name: str) -> Optional[DisplayProfile]:
        """Get a display profile by name.

        Args:
            name: Name of the profile to retrieve

        Returns:
            DisplayProfile object or None if not found
        """
        for p in self.config['profiles']:
            if p['name'] == name:
                return DisplayProfile.from_dict(p)
        return None

    def get_all_profiles(self) -> List[DisplayProfile]:
        """Get all display profiles.

        Returns:
            List of all DisplayProfile objects
        """
        return [DisplayProfile.from_dict(p) for p in self.config['profiles']]

    def set_current_profile(self, name: str) -> bool:
        """Set the current active profile.

        Args:
            name: Name of the profile to set as current

        Returns:
            True if successful, False if profile not found
        """
        profile = self.get_profile(name)
        if profile is None:
            logger.warning(f"Profile '{name}' not found")
            return False

        self.config['current_profile'] = name
        self._save_config()
        logger.info(f"Set current profile to: {name}")
        return True

    def get_current_profile(self) -> Optional[DisplayProfile]:
        """Get the currently active profile.

        Returns:
            DisplayProfile object or None if no profile is set
        """
        current_name = self.config.get('current_profile')
        if current_name:
            return self.get_profile(current_name)
        return None

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """Rename a display profile.

        Args:
            old_name: Current name of the profile
            new_name: New name for the profile

        Returns:
            True if successful, False if old profile not found or new name exists
        """
        # Check if new name already exists
        if any(p['name'] == new_name for p in self.config['profiles']):
            logger.warning(f"Profile '{new_name}' already exists")
            return False

        # Find and rename
        for p in self.config['profiles']:
            if p['name'] == old_name:
                p['name'] = new_name
                # Update current profile if it was the one renamed
                if self.config['current_profile'] == old_name:
                    self.config['current_profile'] = new_name
                self._save_config()
                logger.info(f"Renamed profile: {old_name} -> {new_name}")
                return True

        logger.warning(f"Profile '{old_name}' not found")
        return False

    def save_current_display_as_profile(self, profile_name: str) -> bool:
        """Save the current display settings as a new profile.

        Args:
            profile_name: Name for the new profile

        Returns:
            True if successful, False otherwise
        """
        try:
            success, displays = self.display_manager.detect_displays()
            if not success:
                logger.error("Could not detect connected displays")
                return False

            connected_displays = [display for display in displays if display.connected]
            if not connected_displays:
                logger.error("No connected display is available to save as a profile")
                return False
            display = next(
                (display for display in connected_displays if display.primary),
                connected_displays[0],
            )
            if display.width <= 0 or display.height <= 0 or display.refresh_rate <= 0:
                logger.error("Current mode is unavailable for display %s", display.name)
                return False

            profile = DisplayProfile(
                name=profile_name,
                resolution=f"{display.width}x{display.height}",
                refresh_rate=display.refresh_rate,
                scaling=100,
                dpi=96,
                display_name=display.name,
            )

            return self.add_profile(profile)

        except (OSError, RuntimeError, ValueError):
            logger.exception("Error saving current display as profile %s", profile_name)
            return False

    def apply_profile(self, name: str) -> bool:
        """Apply a profile's resolution and refresh rate to its display.

        Args:
            name: Name of the profile to apply

        Returns:
            True if successful, False otherwise
        """
        profile = self.get_profile(name)
        if profile is None:
            logger.warning(f"Profile '{name}' not found")
            return False

        try:
            success, displays = self.display_manager.detect_displays()
            if not success:
                logger.error("Could not detect displays while applying profile %s", name)
                return False
            connected_displays = [display for display in displays if display.connected]
            display = next(
                (
                    candidate for candidate in connected_displays
                    if candidate.name == profile.display_name
                ),
                None,
            )
            if display is None:
                display = next(
                    (candidate for candidate in connected_displays if candidate.primary),
                    connected_displays[0] if connected_displays else None,
                )
            if display is None:
                logger.error("No connected display is available to apply profile %s", name)
                return False

            try:
                width, height = (int(value) for value in profile.resolution.split("x", 1))
            except (TypeError, ValueError):
                logger.error("Invalid resolution in display profile %s: %s", name, profile.resolution)
                return False
            if width <= 0 or height <= 0 or profile.refresh_rate <= 0:
                logger.error("Invalid display mode in profile %s", name)
                return False

            applied, message = self.display_manager.set_resolution(
                display.name, width, height, profile.refresh_rate
            )
            if not applied:
                logger.error("Could not apply display profile %s: %s", name, message)
                return False
            applied, message = self.display_manager.set_scale(
                display.name, profile.scaling / 100
            )
            if not applied:
                logger.error("Could not apply display profile scale for %s: %s", name, message)
                return False

            self.config['current_profile'] = name
            self._save_config()
            logger.info(f"Applied profile: {name}")
            return True

        except (OSError, RuntimeError, ValueError):
            logger.exception("Error applying display profile %s", name)
            return False

    def get_profile_count(self) -> int:
        """Get the total number of saved profiles.

        Returns:
            Number of profiles
        """
        return len(self.config['profiles'])

    def has_capacity_for_new_profile(self) -> bool:
        """Check if there's capacity to add a new profile.

        Returns:
            True if below max profiles limit
        """
        return len(self.config['profiles']) < self.MAX_PROFILES
