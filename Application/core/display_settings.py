"""
Display Settings Manager for Titans Launcher - Phase 2 System Integration.

Manages display configuration including resolution, refresh rate, color depth,
and multi-monitor support. Integrates with KWin and D-Bus.
"""

import logging
import subprocess
import json
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RefreshRate(Enum):
    """Common refresh rate values."""
    HZ_24 = 24
    HZ_30 = 30
    HZ_50 = 50
    HZ_59 = 59
    HZ_60 = 60
    HZ_75 = 75
    HZ_100 = 100
    HZ_120 = 120
    HZ_144 = 144
    HZ_165 = 165
    HZ_240 = 240


class ColorDepth(Enum):
    """Color depth values."""
    BIT_16 = 16
    BIT_24 = 24
    BIT_32 = 32


@dataclass
class DisplayMode:
    """Represents a display mode/resolution."""
    width: int
    height: int
    refresh_rate: int
    color_depth: int = 24
    
    def __str__(self) -> str:
        return f"{self.width}x{self.height}@{self.refresh_rate}Hz"


@dataclass
class DisplayInfo:
    """Information about a connected display."""
    name: str
    connected: bool
    primary: bool
    x_pos: int = 0
    y_pos: int = 0
    width: int = 0
    height: int = 0
    refresh_rate: int = 60
    modes: List[DisplayMode] = None
    
    def __post_init__(self):
        if self.modes is None:
            self.modes = []


class DisplaySettingsManager:
    """Manages display configuration."""
    
    def __init__(self):
        """Initialize the DisplaySettingsManager."""
        self.user_home = Path.home()
        self.settings_dir = self.user_home / ".local" / "share" / "titans"
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.settings_dir / "display_settings.json"
        
        self.displays: Dict[str, DisplayInfo] = {}
        self._load_settings()
        logger.info("DisplaySettingsManager initialized")
    
    def _load_settings(self) -> None:
        """Load saved display settings."""
        try:
            if self.settings_file.exists():
                data = json.loads(self.settings_file.read_text())
                # Parse saved display configurations
                for display_name, display_data in data.items():
                    self.displays[display_name] = DisplayInfo(
                        name=display_name,
                        connected=display_data.get("connected", True),
                        primary=display_data.get("primary", False),
                        x_pos=display_data.get("x_pos", 0),
                        y_pos=display_data.get("y_pos", 0),
                        width=display_data.get("width", 1920),
                        height=display_data.get("height", 1080),
                        refresh_rate=display_data.get("refresh_rate", 60),
                    )
                logger.info(f"Loaded settings for {len(self.displays)} displays")
        except Exception as e:
            logger.error(f"Failed to load display settings: {e}")
    
    def _save_settings(self) -> None:
        """Save current display settings."""
        try:
            data = {}
            for name, display in self.displays.items():
                data[name] = {
                    "connected": display.connected,
                    "primary": display.primary,
                    "x_pos": display.x_pos,
                    "y_pos": display.y_pos,
                    "width": display.width,
                    "height": display.height,
                    "refresh_rate": display.refresh_rate,
                }
            self.settings_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save display settings: {e}")
    
    def detect_displays(self) -> Tuple[bool, List[DisplayInfo]]:
        """Detect connected displays using EDID/kernel info.
        
        Returns:
            Tuple[bool, List[DisplayInfo]]: (success, list of displays)
        """
        try:
            displays = []
            
            # Try using wlr-randr (Wayland)
            result = subprocess.run(
                ["wlr-randr"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                displays = self._parse_wlr_randr(result.stdout)
                logger.info(f"Detected {len(displays)} displays via wlr-randr")
                return True, displays
            
            # Fallback: parse /sys/class/drm
            displays = self._detect_displays_sysfs()
            logger.info(f"Detected {len(displays)} displays via sysfs")
            return True, displays
        
        except Exception as e:
            logger.error(f"Failed to detect displays: {e}")
            return False, []
    
    def _parse_wlr_randr(self, output: str) -> List[DisplayInfo]:
        """Parse wlr-randr output.
        
        Args:
            output: wlr-randr command output
        
        Returns:
            List[DisplayInfo]: Parsed display information
        """
        displays = []
        current_display = None

        for line in output.splitlines():
            if line and not line[0].isspace():
                display_name = line.split()[0]
                current_display = DisplayInfo(name=display_name, connected=False)
                displays.append(current_display)
                continue

            if current_display is None:
                continue
            stripped = line.strip()
            if stripped.startswith("Enabled:"):
                current_display.connected = stripped.partition(":")[2].strip().lower() == "yes"

            mode = re.search(
                r"(\d+)x(\d+)\s+px,\s*([\d.]+)\s*Hz(.*)",
                stripped,
            )
            if mode:
                width, height, rate = mode.groups()[:3]
                display_mode = DisplayMode(int(width), int(height), round(float(rate)))
                current_display.modes.append(display_mode)
                if "current" in mode.group(4).lower():
                    current_display.width = display_mode.width
                    current_display.height = display_mode.height
                    current_display.refresh_rate = display_mode.refresh_rate

        return displays
    
    def _detect_displays_sysfs(self) -> List[DisplayInfo]:
        """Detect displays via /sys/class/drm.
        
        Returns:
            List[DisplayInfo]: Detected displays
        """
        displays = []
        drm_path = Path("/sys/class/drm")
        
        if not drm_path.exists():
            return displays
        
        for card_dir in drm_path.glob("card*-*"):
            try:
                status_file = card_dir / "status"
                if status_file.exists():
                    status = status_file.read_text().strip()
                    is_connected = status.lower() == "connected"
                    
                    display = DisplayInfo(
                        name=card_dir.name,
                        connected=is_connected,
                        primary=False,
                    )
                    displays.append(display)
            except Exception as e:
                logger.debug(f"Error reading {card_dir}: {e}")
        
        return displays
    
    def set_resolution(
        self,
        display_name: str,
        width: int,
        height: int,
        refresh_rate: int = 60
    ) -> Tuple[bool, str]:
        """Set display resolution and refresh rate.
        
        Args:
            display_name: Name of display
            width: Width in pixels
            height: Height in pixels
            refresh_rate: Refresh rate in Hz
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # Try wlr-randr (Wayland)
            cmd = [
                "wlr-randr",
                "--output", display_name,
                "--mode", f"{width}x{height}@{refresh_rate}Hz"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                # Update internal state
                if display_name in self.displays:
                    self.displays[display_name].width = width
                    self.displays[display_name].height = height
                    self.displays[display_name].refresh_rate = refresh_rate
                self._save_settings()
                
                logger.info(f"Set {display_name} to {width}x{height}@{refresh_rate}Hz")
                return True, f"Resolution set to {width}x{height}@{refresh_rate}Hz"
            else:
                logger.error(f"Failed to set resolution: {result.stderr}")
                return False, result.stderr
        
        except subprocess.TimeoutExpired:
            logger.error("Timeout setting resolution")
            return False, "Timeout"
        except Exception as e:
            logger.error(f"Error setting resolution: {e}")
            return False, str(e)

    def set_scale(self, display_name: str, scale: float) -> Tuple[bool, str]:
        """Set a Wayland output's scale using wlr-randr."""
        if scale <= 0:
            return False, "Scale must be greater than zero"
        try:
            result = subprocess.run(
                ["wlr-randr", "--output", display_name, "--scale", str(scale)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.error("Failed to set display scale: %s", result.stderr)
                return False, result.stderr
            return True, f"Display scale set to {scale}"
        except Exception as e:
            logger.error("Error setting display scale: %s", e)
            return False, str(e)
    
    def set_primary_display(self, display_name: str) -> Tuple[bool, str]:
        """Set the primary display.
        
        Args:
            display_name: Name of display to make primary
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # Update internal state
            for display in self.displays.values():
                display.primary = (display.name == display_name)
            self._save_settings()
            
            # Try to set via wlr-randr
            cmd = ["wlr-randr", "--output", display_name, "--on"]
            subprocess.run(cmd, timeout=5)
            
            logger.info(f"Set primary display to {display_name}")
            return True, f"Primary display set to {display_name}"
        
        except Exception as e:
            logger.error(f"Error setting primary display: {e}")
            return False, str(e)
    
    def get_available_modes(self, display_name: str) -> List[DisplayMode]:
        """Get available display modes for a display.
        
        Returns:
            List[DisplayMode]: Available modes
        """
        try:
            result = subprocess.run(
                ["wlr-randr"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            modes = []
            if result.returncode == 0:
                in_display = False
                for line in result.stdout.split("\n"):
                    if display_name in line:
                        in_display = True
                    elif in_display and line and not line.startswith(" "):
                        break
                    elif in_display and "x" in line:
                        try:
                            parts = line.strip().split()
                            if parts:
                                res_info = parts[0]
                                if "x" in res_info:
                                    width_height = res_info.split("@")[0]
                                    w, h = map(int, width_height.split("x"))
                                    rate = 60
                                    if "@" in res_info:
                                        rate = int(float(res_info.split("@")[1].split("Hz")[0]))
                                    modes.append(DisplayMode(w, h, rate))
                        except (ValueError, IndexError):
                            pass
            
            return modes
        
        except Exception as e:
            logger.error(f"Error getting display modes: {e}")
            return []
    
    def enable_display(self, display_name: str) -> Tuple[bool, str]:
        """Enable a display.
        
        Args:
            display_name: Name of display
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["wlr-randr", "--output", display_name, "--on"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                if display_name in self.displays:
                    self.displays[display_name].connected = True
                self._save_settings()
                logger.info(f"Enabled display: {display_name}")
                return True, f"Display {display_name} enabled"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error enabling display: {e}")
            return False, str(e)
    
    def disable_display(self, display_name: str) -> Tuple[bool, str]:
        """Disable a display.
        
        Args:
            display_name: Name of display
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["wlr-randr", "--output", display_name, "--off"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                if display_name in self.displays:
                    self.displays[display_name].connected = False
                self._save_settings()
                logger.info(f"Disabled display: {display_name}")
                return True, f"Display {display_name} disabled"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error disabling display: {e}")
            return False, str(e)
    
    def get_display_info(self, display_name: str) -> Optional[DisplayInfo]:
        """Get information about a display.
        
        Args:
            display_name: Name of display
        
        Returns:
            Optional[DisplayInfo]: Display information or None
        """
        return self.displays.get(display_name)
    
    def get_all_displays(self) -> Dict[str, DisplayInfo]:
        """Get all displays.
        
        Returns:
            Dict[str, DisplayInfo]: All displays
        """
        return self.displays.copy()
    
    def get_primary_display(self) -> Optional[DisplayInfo]:
        """Get the primary display.
        
        Returns:
            Optional[DisplayInfo]: Primary display or None
        """
        for display in self.displays.values():
            if display.primary:
                return display
        
        # Default to first connected
        for display in self.displays.values():
            if display.connected:
                return display
        
        return None
