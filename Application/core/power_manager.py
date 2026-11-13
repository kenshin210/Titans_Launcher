"""
Power Manager for Titans Launcher - Phase 2 System Integration.

Manages power settings, sleep modes, CPU frequency scaling, and battery
status without requiring command-line access.
"""

import logging
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PowerProfile(Enum):
    """Power profiles for CPU frequency scaling."""
    PERFORMANCE = "performance"
    BALANCED = "balanced"
    POWER_SAVING = "power-saver"


@dataclass
class BatteryInfo:
    """Information about system battery."""
    present: bool = False
    percentage: int = 100
    status: str = "unknown"  # "charging", "discharging", "full", "empty"
    time_to_empty: Optional[str] = None
    time_to_full: Optional[str] = None
    power_draw: float = 0.0  # watts


@dataclass
class CPUInfo:
    """Information about CPU."""
    current_frequency: float = 0.0  # GHz
    max_frequency: float = 0.0
    min_frequency: float = 0.0
    temperature: float = 0.0  # Celsius
    cores: int = 1


class PowerManager:
    """Manages power settings and energy consumption."""
    
    def __init__(self):
        """Initialize the PowerManager."""
        self.user_home = Path.home()
        self.config_dir = self.user_home / ".local" / "share" / "titans"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.battery_info = BatteryInfo()
        self.cpu_info = CPUInfo()
        self.current_profile = PowerProfile.BALANCED
        
        self._load_battery_info()
        logger.info("PowerManager initialized")
    
    def _load_battery_info(self) -> None:
        """Load battery information from system."""
        try:
            # Try to get battery info via upower
            result = subprocess.run(
                ["upower", "-d"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self._parse_upower_output(result.stdout)
        except Exception as e:
            logger.debug(f"Could not load battery info: {e}")
    
    def _parse_upower_output(self, output: str) -> None:
        """Parse upower output for battery info."""
        try:
            for line in output.split("\n"):
                if "percentage:" in line.lower():
                    parts = line.split(":")
                    if len(parts) > 1:
                        self.battery_info.percentage = int(parts[1].strip().rstrip("%"))
                elif "state:" in line.lower():
                    parts = line.split(":")
                    if len(parts) > 1:
                        self.battery_info.status = parts[1].strip().lower()
        except Exception as e:
            logger.debug(f"Error parsing upower: {e}")
    
    def get_battery_status(self) -> Dict[str, Any]:
        """Get current battery status.
        
        Returns:
            Dict[str, Any]: Battery information
        """
        try:
            result = subprocess.run(
                ["upower", "-e"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self._parse_upower_output(result.stdout)
        except Exception:
            pass
        
        return {
            "present": self.battery_info.present,
            "percentage": self.battery_info.percentage,
            "status": self.battery_info.status,
            "time_to_empty": self.battery_info.time_to_empty,
            "time_to_full": self.battery_info.time_to_full,
        }
    
    def get_power_profile(self) -> Tuple[bool, str]:
        """Get current power profile.
        
        Returns:
            Tuple[bool, str]: (success, profile_name)
        """
        try:
            result = subprocess.run(
                ["powerprofilesctl", "get"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                profile = result.stdout.strip()
                return True, profile
            
            return False, "Unknown"
        
        except Exception as e:
            logger.error(f"Error getting power profile: {e}")
            return False, "Error"
    
    def set_power_profile(self, profile: PowerProfile) -> Tuple[bool, str]:
        """Set power profile.
        
        Args:
            profile: PowerProfile to set
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["powerprofilesctl", "set", profile.value],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self.current_profile = profile
                logger.info(f"Set power profile to {profile.value}")
                return True, f"Power profile set to {profile.value}"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error setting power profile: {e}")
            return False, str(e)
    
    def list_available_profiles(self) -> List[str]:
        """List available power profiles.
        
        Returns:
            List[str]: Available profile names
        """
        return [profile.value for profile in PowerProfile]
    
    def get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU information.
        
        Returns:
            Dict[str, Any]: CPU details
        """
        try:
            # Try to get CPU frequency
            result = subprocess.run(
                ["lscpu"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "CPU max MHz" in line:
                        parts = line.split(":")
                        if len(parts) > 1:
                            try:
                                self.cpu_info.max_frequency = float(parts[1].strip()) / 1000
                            except ValueError:
                                pass
                    elif "CPU(s):" in line:
                        parts = line.split(":")
                        if len(parts) > 1:
                            try:
                                self.cpu_info.cores = int(parts[1].strip())
                            except ValueError:
                                pass
        except Exception as e:
            logger.debug(f"Error getting CPU info: {e}")
        
        return {
            "cores": self.cpu_info.cores,
            "max_frequency": self.cpu_info.max_frequency,
            "current_frequency": self.cpu_info.current_frequency,
            "temperature": self.cpu_info.temperature,
        }
    
    def suspend_system(self) -> Tuple[bool, str]:
        """Suspend the system.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["systemctl", "suspend"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info("System suspend initiated")
                return True, "System suspended"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error suspending system: {e}")
            return False, str(e)
    
    def hibernate_system(self) -> Tuple[bool, str]:
        """Hibernate the system.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["systemctl", "hibernate"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info("System hibernation initiated")
                return True, "System hibernated"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error hibernating system: {e}")
            return False, str(e)
    
    def reboot_system(self) -> Tuple[bool, str]:
        """Reboot the system.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["systemctl", "reboot"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info("System reboot initiated")
                return True, "System rebooting"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error rebooting system: {e}")
            return False, str(e)
    
    def shutdown_system(self) -> Tuple[bool, str]:
        """Shut down the system.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["systemctl", "poweroff"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info("System shutdown initiated")
                return True, "System shutting down"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error shutting down system: {e}")
            return False, str(e)
    
    def set_screen_timeout(self, seconds: int) -> Tuple[bool, str]:
        """Set display timeout (blank screen).
        
        Args:
            seconds: Seconds until display blanks (0 to disable)
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            if seconds <= 0:
                # Disable timeout (set to never)
                timeout_ms = 0
            else:
                timeout_ms = seconds * 1000
            
            # Use xset if available (X11) or brightnessctl for Wayland
            result = subprocess.run(
                ["xset", "dpms", str(seconds), str(seconds), str(seconds)],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info(f"Display timeout set to {seconds}s")
                return True, f"Display timeout set to {seconds}s"
            
            return False, "Display timeout not supported on this system"
        
        except Exception as e:
            logger.error(f"Error setting display timeout: {e}")
            return False, str(e)
    
    def get_power_status(self) -> Dict[str, Any]:
        """Get comprehensive power system status.
        
        Returns:
            Dict[str, Any]: Power status information
        """
        return {
            "battery": self.get_battery_status(),
            "cpu": self.get_cpu_info(),
            "profile": self.current_profile.value,
            "available_profiles": self.list_available_profiles(),
        }
