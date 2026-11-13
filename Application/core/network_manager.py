"""
Network Manager for Titans Launcher - Phase 2 System Integration.

Manages network connectivity, WiFi connections, Ethernet, and VPN
without requiring command-line access.
"""

import logging
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class NetworkState(Enum):
    """Network connection states."""
    UNKNOWN = "unknown"
    ASLEEP = "asleep"
    DISCONNECTED = "disconnected"
    DISCONNECTING = "disconnecting"
    CONNECTING = "connecting"
    CONNECTED_SITE = "connected_site"
    CONNECTED_GLOBAL = "connected_global"


class ConnectionType(Enum):
    """Network connection types."""
    ETHERNET = "ethernet"
    WIFI = "wifi"
    MOBILE = "mobile"
    VPN = "vpn"
    BRIDGE = "bridge"


@dataclass
class NetworkDevice:
    """Information about a network device."""
    id: str
    name: str
    device_type: str  # "ethernet", "wifi", etc.
    is_connected: bool = False
    ip_address: Optional[str] = None
    gateway: Optional[str] = None
    dns_servers: Optional[List[str]] = None


@dataclass
class WiFiNetwork:
    """Information about a WiFi network."""
    ssid: str
    bssid: str
    strength: int  # 0-100
    security: str  # "open", "wep", "wpa", "wpa2", "wpa3"
    is_connected: bool = False


class NetworkManager:
    """Manages network connectivity via NetworkManager."""
    
    def __init__(self):
        """Initialize the NetworkManager."""
        self.user_home = Path.home()
        self.config_dir = self.user_home / ".local" / "share" / "titans"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.devices: Dict[str, NetworkDevice] = {}
        self.wifi_networks: List[WiFiNetwork] = []
        self.system_state = NetworkState.UNKNOWN
        
        logger.info("NetworkManager initialized")
    
    def get_connectivity_status(self) -> Tuple[bool, str]:
        """Get overall connectivity status.
        
        Returns:
            Tuple[bool, str]: (is_connected, status_message)
        """
        try:
            result = subprocess.run(
                ["nmcli", "g", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    # Second line has connectivity info
                    status_line = lines[1].split()
                    if len(status_line) >= 1:
                        state = status_line[0]
                        is_connected = state in ("connected", "connected (site)", "connected (global)")
                        return is_connected, state
            
            return False, "Unable to determine status"
        
        except Exception as e:
            logger.error(f"Error getting connectivity status: {e}")
            return False, str(e)
    
    def list_devices(self) -> Tuple[bool, List[NetworkDevice]]:
        """List all network devices.
        
        Returns:
            Tuple[bool, List[NetworkDevice]]: (success, devices)
        """
        try:
            result = subprocess.run(
                ["nmcli", "d"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            devices = []
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                # Skip header
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 3:
                        device_name = parts[0]
                        device_type = parts[1]
                        state = parts[2]
                        is_connected = state in ("connected", "connecting")
                        
                        device = NetworkDevice(
                            id=device_name,
                            name=device_name,
                            device_type=device_type,
                            is_connected=is_connected
                        )
                        devices.append(device)
                        self.devices[device_name] = device
            
            return True, devices
        
        except Exception as e:
            logger.error(f"Error listing devices: {e}")
            return False, []
    
    def scan_wifi_networks(self, device: Optional[str] = None) -> Tuple[bool, List[WiFiNetwork]]:
        """Scan for available WiFi networks.
        
        Args:
            device: WiFi device name (optional)
        
        Returns:
            Tuple[bool, List[WiFiNetwork]]: (success, networks)
        """
        try:
            # First request scan
            subprocess.run(
                ["nmcli", "dev", "wifi", "rescan"],
                capture_output=True,
                timeout=10
            )
            
            # Get results
            result = subprocess.run(
                ["nmcli", "dev", "wifi", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            networks = []
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                # Skip header
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 3:
                        # Format: IN SSID MODE CHAN RATE SIGNAL BARS SECURITY
                        is_connected = "*" in parts[0]
                        ssid = parts[1] if len(parts) > 1 else "Unknown"
                        security = " ".join(parts[-1:]) if len(parts) > 1 else "open"
                        
                        network = WiFiNetwork(
                            ssid=ssid,
                            bssid="",
                            strength=50,  # Default, would need parsing
                            security=security,
                            is_connected=is_connected
                        )
                        networks.append(network)
            
            self.wifi_networks = networks
            return True, networks
        
        except Exception as e:
            logger.error(f"Error scanning WiFi: {e}")
            return False, []
    
    def connect_wifi(self, ssid: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """Connect to a WiFi network.
        
        Args:
            ssid: Network SSID
            password: Network password (optional for open networks)
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            if password:
                result = subprocess.run(
                    ["nmcli", "dev", "wifi", "connect", ssid, "password", password],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
            else:
                result = subprocess.run(
                    ["nmcli", "dev", "wifi", "connect", ssid],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
            
            if result.returncode == 0:
                logger.info(f"Connected to WiFi: {ssid}")
                return True, f"Connected to {ssid}"
            else:
                logger.error(f"WiFi connection failed: {result.stderr}")
                return False, result.stderr
        
        except subprocess.TimeoutExpired:
            logger.error("WiFi connection timeout")
            return False, "Connection timeout"
        except Exception as e:
            logger.error(f"Error connecting to WiFi: {e}")
            return False, str(e)
    
    def disconnect_wifi(self) -> Tuple[bool, str]:
        """Disconnect from WiFi.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["nmcli", "dev", "disconnect"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info("Disconnected from WiFi")
                return True, "Disconnected"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            return False, str(e)
    
    def get_connection_info(self, device: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a connection.
        
        Args:
            device: Device name
        
        Returns:
            Optional[Dict[str, Any]]: Connection info or None
        """
        try:
            result = subprocess.run(
                ["nmcli", "dev", "show", device],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                info = {}
                for line in result.stdout.strip().split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        info[key.strip()] = value.strip()
                return info
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting connection info: {e}")
            return None
    
    def get_network_status(self) -> Dict[str, Any]:
        """Get current network status.
        
        Returns:
            Dict[str, Any]: Network status information
        """
        is_connected, status = self.get_connectivity_status()
        
        return {
            "is_connected": is_connected,
            "status": status,
            "devices": len(self.devices),
            "wifi_networks": len(self.wifi_networks),
        }
    
    def enable_networking(self) -> Tuple[bool, str]:
        """Enable networking.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["nmcli", "n", "on"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info("Networking enabled")
                return True, "Networking enabled"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error enabling networking: {e}")
            return False, str(e)
    
    def disable_networking(self) -> Tuple[bool, str]:
        """Disable networking.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            result = subprocess.run(
                ["nmcli", "n", "off"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info("Networking disabled")
                return True, "Networking disabled"
            else:
                return False, result.stderr
        
        except Exception as e:
            logger.error(f"Error disabling networking: {e}")
            return False, str(e)
