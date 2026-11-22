"""
Audio Manager for Titans Launcher - Phase 2 System Integration.

Manages audio input/output, device switching, volume control, and audio
configuration without requiring command-line access.
"""

import logging
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AudioProfile(Enum):
    """Audio device profile types."""
    STEREO = "stereo"
    SURROUND_5_1 = "surround-5.1"
    SURROUND_7_1 = "surround-7.1"
    MONO = "mono"


@dataclass
class AudioDevice:
    """Information about an audio device."""
    id: str
    name: str
    description: str
    device_type: str  # "sink" (output), "source" (input)
    is_default: bool = False
    volume: int = 100  # 0-100
    muted: bool = False
    active_profile: str = "stereo"
    available_profiles: List[str] = None
    
    def __post_init__(self):
        if self.available_profiles is None:
            self.available_profiles = ["stereo"]


class AudioManager:
    """Manages audio configuration via PulseAudio/PipeWire."""
    
    def __init__(self):
        """Initialize the AudioManager."""
        self.user_home = Path.home()
        self.config_dir = self.user_home / ".local" / "share" / "titans"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "audio_settings.json"
        
        self.output_devices: Dict[str, AudioDevice] = {}
        self.input_devices: Dict[str, AudioDevice] = {}
        self.default_output: Optional[str] = None
        self.default_input: Optional[str] = None
        self.master_volume: int = 100
        
        self._load_config()
        logger.info("AudioManager initialized")
    
    def _load_config(self) -> None:
        """Load saved audio configuration."""
        try:
            if self.config_file.exists():
                config = json.loads(self.config_file.read_text())
                self.master_volume = config.get("master_volume", 100)
                self.default_output = config.get("default_output")
                self.default_input = config.get("default_input")
        except Exception as e:
            logger.error(f"Failed to load audio config: {e}")
    
    def _save_config(self) -> None:
        """Save audio configuration."""
        try:
            config = {
                "master_volume": self.master_volume,
                "default_output": self.default_output,
                "default_input": self.default_input,
            }
            self.config_file.write_text(json.dumps(config, indent=2))
        except Exception as e:
            logger.error(f"Failed to save audio config: {e}")
    
    def detect_devices(self) -> Tuple[bool, str]:
        """Detect audio input and output devices.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # Try pactl (PulseAudio)
            result = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self._parse_pactl_sinks(result.stdout)
                self._parse_pactl_sources()
                logger.info(f"Detected {len(self.output_devices)} output, {len(self.input_devices)} input devices")
                return True, "Devices detected"
            
            # Fallback to wpctl (PipeWire)
            result = subprocess.run(
                ["wpctl", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self._parse_wpctl_status(result.stdout)
                logger.info("Devices detected via PipeWire")
                return True, "Devices detected"
            
            return False, "No audio system detected (PulseAudio/PipeWire required)"
        
        except subprocess.TimeoutExpired:
            logger.error("Timeout detecting audio devices")
            return False, "Timeout"
        except Exception as e:
            logger.error(f"Error detecting devices: {e}")
            return False, str(e)
    
    def _parse_pactl_sinks(self, output: str) -> None:
        """Parse pactl output for audio sinks (outputs)."""
        for line in output.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                device_id = parts[0]
                device_name = parts[1]
                device = AudioDevice(
                    id=device_id,
                    name=device_name,
                    description=device_name,
                    device_type="sink"
                )
                self.output_devices[device_id] = device
    
    def _parse_pactl_sources(self) -> None:
        """Parse pactl output for audio sources (inputs)."""
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    device_id = parts[0]
                    device_name = parts[1]
                    device = AudioDevice(
                        id=device_id,
                        name=device_name,
                        description=device_name,
                        device_type="source"
                    )
                    self.input_devices[device_id] = device
        except Exception as e:
            logger.error(f"Error parsing sources: {e}")
    
    def _parse_wpctl_status(self, output: str) -> None:
        """Parse wpctl status output."""
        in_output = False
        for line in output.split("\n"):
            if "Sinks:" in line:
                in_output = True
            elif "Sources:" in line:
                in_output = False
            elif in_output and "●" in line:
                # Parse output device
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        device_id = parts[1].strip(".")
                        device_name = " ".join(parts[2:])
                        device = AudioDevice(
                            id=device_id,
                            name=device_name,
                            description=device_name,
                            device_type="sink"
                        )
                        self.output_devices[device_id] = device
                    except (ValueError, IndexError):
                        pass
    
    def set_default_output(self, device_id: str) -> Tuple[bool, str]:
        """Set default audio output device.
        
        Args:
            device_id: Device ID to set as default
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["pactl", "set-default-sink", device_id],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self.default_output = device_id
                self._save_config()
                logger.info(f"Set default output to {device_id}")
                return True, f"Default output set to {device_id}"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error setting default output: {e}")
            return False, str(e)
    
    def set_volume(self, device_id: str, volume: int) -> Tuple[bool, str]:
        """Set device volume.
        
        Args:
            device_id: Device ID
            volume: Volume level 0-100
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # Clamp volume to 0-100
            volume = max(0, min(100, volume))
            
            # Convert to PAVolume (0-65536)
            pa_volume = int((volume / 100.0) * 65536)
            
            result = subprocess.run(
                ["pactl", "set-sink-volume", device_id, str(pa_volume)],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                if device_id in self.output_devices:
                    self.output_devices[device_id].volume = volume
                logger.info(f"Set {device_id} volume to {volume}%")
                return True, f"Volume set to {volume}%"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error setting volume: {e}")
            return False, str(e)
    
    def set_mute(self, device_id: str, muted: bool) -> Tuple[bool, str]:
        """Set device mute state.
        
        Args:
            device_id: Device ID
            muted: True to mute, False to unmute
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            mute_val = "1" if muted else "0"
            
            result = subprocess.run(
                ["pactl", "set-sink-mute", device_id, mute_val],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                if device_id in self.output_devices:
                    self.output_devices[device_id].muted = muted
                state = "muted" if muted else "unmuted"
                logger.info(f"Device {device_id} {state}")
                return True, f"Device {state}"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error setting mute: {e}")
            return False, str(e)
    
    def get_output_devices(self) -> List[AudioDevice]:
        """Get all output devices.
        
        Returns:
            List[AudioDevice]: Audio output devices
        """
        return list(self.output_devices.values())
    
    def get_input_devices(self) -> List[AudioDevice]:
        """Get all input devices.
        
        Returns:
            List[AudioDevice]: Audio input devices
        """
        return list(self.input_devices.values())
    
    def get_device_info(self, device_id: str) -> Optional[AudioDevice]:
        """Get information about a device.
        
        Args:
            device_id: Device ID
        
        Returns:
            Optional[AudioDevice]: Device info or None
        """
        if device_id in self.output_devices:
            return self.output_devices[device_id]
        return self.input_devices.get(device_id)
    
    def get_audio_status(self) -> Dict[str, Any]:
        """Get current audio system status.
        
        Returns:
            Dict[str, Any]: Status information
        """
        return {
            "output_devices": len(self.output_devices),
            "input_devices": len(self.input_devices),
            "default_output": self.default_output,
            "default_input": self.default_input,
            "master_volume": self.master_volume,
        }
