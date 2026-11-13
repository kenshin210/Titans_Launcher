"""
Storage Manager for Titans Launcher - Phase 2 System Integration.

Manages storage devices, mounts, disk usage, and file operations
via D-Bus without requiring command-line access.
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


@dataclass
class DiskInfo:
    """Information about a disk."""
    path: str
    name: str
    size: int  # bytes
    used: int  # bytes
    available: int  # bytes
    is_mounted: bool = False
    mount_point: Optional[str] = None
    filesystem: Optional[str] = None
    is_removable: bool = False


@dataclass
class MountPoint:
    """Information about a mount point."""
    path: str
    device: str
    filesystem: str
    total_size: int  # bytes
    used_space: int  # bytes
    available_space: int  # bytes
    is_readonly: bool = False


@dataclass(frozen=True)
class StorageVolume:
    """A partition and its mounted filesystems as reported by lsblk."""

    path: str
    name: str
    size: int
    filesystem: Optional[str]
    mount_points: List[str]
    parent_device: str
    is_removable: bool = False


class StorageManager:
    """Manages storage devices and mounts."""
    
    def __init__(self):
        """Initialize the StorageManager."""
        self.user_home = Path.home()
        self.config_dir = self.user_home / ".local" / "share" / "titans"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.disks: Dict[str, DiskInfo] = {}
        self.mount_points: Dict[str, MountPoint] = {}
        self.volumes: Dict[str, StorageVolume] = {}
        
        logger.info("StorageManager initialized")
    
    def list_disks(self) -> Tuple[bool, List[DiskInfo]]:
        """List all storage devices.
        
        Returns:
            Tuple[bool, List[DiskInfo]]: (success, disks)
        """
        try:
            result = subprocess.run(
                ["lsblk", "-d", "-n", "-o", "NAME,SIZE,TYPE,RM"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            disks = []
            if result.returncode != 0:
                logger.error("Disk enumeration failed: %s", result.stderr.strip())
                return False, disks
            self.disks.clear()
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) < 3:
                    logger.warning("Ignoring malformed lsblk disk entry: %r", line)
                    continue
                name, size_str = parts[:2]
                is_removable = len(parts) > 3 and parts[3] == "1"
                disk = DiskInfo(
                    path=f"/dev/{name}",
                    name=name,
                    size=self._parse_size(size_str),
                    used=0,
                    available=self._parse_size(size_str),
                    is_removable=is_removable,
                )
                disks.append(disk)
                self.disks[name] = disk
            
            return True, disks
        
        except Exception as e:
            logger.error(f"Error listing disks: {e}")
            return False, []

    def list_volumes(self) -> Tuple[bool, List[StorageVolume]]:
        """List partitions and their mount points using lsblk's JSON output."""
        try:
            result = subprocess.run(
                [
                    "lsblk", "--json", "--paths", "--output",
                    "PATH,NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,RM",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.error("Volume enumeration failed: %s", error)
            return False, []
        if result.returncode != 0:
            logger.error("Volume enumeration failed: %s", result.stderr.strip())
            return False, []
        try:
            devices = json.loads(result.stdout)["blockdevices"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            logger.error("Could not parse lsblk volume data: %s", error)
            return False, []

        volumes = []

        def walk(device, parent_path=None, parent_removable=False):
            path = device.get("path")
            removable = str(device.get("rm", "0")).lower() in {"1", "true", "yes"}
            device_type = device.get("type")
            if device_type == "disk":
                parent_path = path
                parent_removable = removable
            elif device_type == "part" and path:
                raw_mounts = device.get("mountpoints")
                if raw_mounts is None:
                    raw_mounts = device.get("mountpoint")
                if isinstance(raw_mounts, str):
                    mount_points = [raw_mounts] if raw_mounts else []
                elif isinstance(raw_mounts, list):
                    mount_points = [item for item in raw_mounts if isinstance(item, str) and item]
                else:
                    mount_points = []
                volumes.append(StorageVolume(
                    path=path,
                    name=device.get("name") or Path(path).name,
                    size=self._parse_size(str(device.get("size") or "0")),
                    filesystem=device.get("fstype"),
                    mount_points=mount_points,
                    parent_device=parent_path or path,
                    is_removable=removable or parent_removable,
                ))
            for child in device.get("children") or []:
                if isinstance(child, dict):
                    walk(child, parent_path, parent_removable)

        for device in devices:
            if isinstance(device, dict):
                walk(device)
        self.volumes = {volume.path: volume for volume in volumes}
        return True, volumes
    
    def list_mount_points(self) -> Tuple[bool, List[MountPoint]]:
        """List all mount points.
        
        Returns:
            Tuple[bool, List[MountPoint]]: (success, mount_points)
        """
        try:
            result = subprocess.run(
                ["mount"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            mount_points = []
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    
                    parts = line.split()
                    if len(parts) >= 6:
                        device = parts[0]
                        mount_path = parts[2]
                        filesystem = parts[4]
                        
                        # Get disk usage
                        usage = self._get_mount_usage(mount_path)
                        
                        mount_point = MountPoint(
                            path=mount_path,
                            device=device,
                            filesystem=filesystem,
                            total_size=usage[0],
                            used_space=usage[1],
                            available_space=usage[2],
                            is_readonly="ro" in line
                        )
                        mount_points.append(mount_point)
                        self.mount_points[mount_path] = mount_point
            
            return True, mount_points
        
        except Exception as e:
            logger.error(f"Error listing mount points: {e}")
            return False, []
    
    def _get_mount_usage(self, path: str) -> Tuple[int, int, int]:
        """Get disk usage for a mount point.
        
        Args:
            path: Mount point path
        
        Returns:
            Tuple[int, int, int]: (total, used, available) in bytes
        """
        try:
            result = subprocess.run(
                ["df", "-B", "1", path],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 4:
                        total = int(parts[1])
                        used = int(parts[2])
                        available = int(parts[3])
                        return total, used, available
            
            return 0, 0, 0
        
        except Exception as e:
            logger.debug(f"Error getting mount usage for {path}: {e}")
            return 0, 0, 0
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size string to bytes.
        
        Args:
            size_str: Size string (e.g., "500G", "10T")
        
        Returns:
            int: Size in bytes
        """
        try:
            multipliers = {
                'K': 1024,
                'M': 1024 ** 2,
                'G': 1024 ** 3,
                'T': 1024 ** 4,
            }
            
            for unit, multiplier in multipliers.items():
                if size_str.endswith(unit):
                    return int(float(size_str[:-1]) * multiplier)
            
            return int(float(size_str))
        
        except Exception:
            return 0
    
    def get_disk_usage(self, path: str) -> Optional[Dict[str, Any]]:
        """Get disk usage for a specific path.
        
        Args:
            path: Directory or mount point path
        
        Returns:
            Optional[Dict[str, Any]]: Usage information or None
        """
        try:
            result = subprocess.run(
                ["du", "-sh", path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                size_str = result.stdout.strip().split()[0]
                size_bytes = self._parse_size(size_str)
                
                return {
                    "path": path,
                    "size": size_bytes,
                    "size_human": size_str,
                }
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return None
    
    def mount_device(self, device: str) -> Tuple[bool, str]:
        """Mount a known filesystem partition through UDisks.
        
        Args:
            device: Block-device path reported by lsblk.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._is_valid_device_path(device):
            return False, "Invalid block-device path"
        success, volumes = self.list_volumes()
        if not success:
            return False, "Could not verify the selected storage volume"
        volume = next((item for item in volumes if item.path == device), None)
        if volume is None or not volume.filesystem:
            return False, "The selected filesystem partition is unavailable"
        if volume.mount_points:
            return False, "The selected volume is already mounted"
        return self._run_udisks(["mount", "-b", device], f"Mounted {device}")
    
    def unmount_device(self, device: str) -> Tuple[bool, str]:
        """Unmount a currently mounted filesystem partition through UDisks.
        
        Args:
            device: Block-device path reported by lsblk.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._is_valid_device_path(device):
            return False, "Invalid block-device path"
        success, volumes = self.list_volumes()
        if not success:
            return False, "Could not verify the selected storage volume"
        volume = next((item for item in volumes if item.path == device), None)
        if volume is None or not volume.mount_points:
            return False, "The selected volume is not mounted"
        return self._run_udisks(["unmount", "-b", device], f"Unmounted {device}")
    
    def eject_device(self, device: str) -> Tuple[bool, str]:
        """Eject a removable device.
        
        Args:
            device: Device path (e.g., /dev/sdb)
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._is_valid_device_path(device):
            return False, "Invalid block-device path"
        success, disks = self.list_disks()
        if not success:
            return False, "Could not verify the selected storage device"
        disk = next((item for item in disks if item.path == device), None)
        if disk is None or not disk.is_removable:
            return False, "Only detected removable devices can be ejected"
        success, volumes = self.list_volumes()
        if not success:
            return False, "Could not verify whether the device is mounted"
        if any(volume.parent_device == device and volume.mount_points for volume in volumes):
            return False, "Unmount all volumes on this device before ejecting it"
        return self._run_udisks(["power-off", "-b", device], f"Ejected {device}")

    @staticmethod
    def _is_valid_device_path(device: str) -> bool:
        if not isinstance(device, str) or re.fullmatch(
            r"/dev/[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*", device
        ) is None:
            return False
        return all(part not in {".", ".."} for part in Path(device).parts)

    @staticmethod
    def _run_udisks(arguments: List[str], success_message: str) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ["udisksctl", *arguments],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.error("UDisks operation failed: %s", error)
            return False, str(error)
        if result.returncode != 0:
            detail = result.stderr.strip() or "udisksctl returned an error"
            logger.error("UDisks operation failed: %s", detail)
            return False, detail
        logger.info(success_message)
        return True, result.stdout.strip() or success_message
    
    def get_filesystem_info(self, device: str) -> Optional[Dict[str, str]]:
        """Get filesystem information for a device.
        
        Args:
            device: Device path
        
        Returns:
            Optional[Dict[str, str]]: Filesystem information
        """
        try:
            result = subprocess.run(
                ["blkid", device],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                info = {}
                for part in result.stdout.strip().split():
                    if "=" in part:
                        key, value = part.split("=", 1)
                        info[key] = value.strip('"')
                return info
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting filesystem info: {e}")
            return None
    
    def get_storage_status(self) -> Dict[str, Any]:
        """Get comprehensive storage status.
        
        Returns:
            Dict[str, Any]: Storage information
        """
        self.list_disks()
        self.list_mount_points()
        
        return {
            "disk_count": len(self.disks),
            "mount_points": len(self.mount_points),
            "disks": [
                {
                    "name": disk.name,
                    "size": disk.size,
                    "removable": disk.is_removable,
                }
                for disk in self.disks.values()
            ],
            "mounts": [
                {
                    "path": mp.path,
                    "device": mp.device,
                    "filesystem": mp.filesystem,
                    "used": mp.used_space,
                    "available": mp.available_space,
                }
                for mp in self.mount_points.values()
            ],
        }
