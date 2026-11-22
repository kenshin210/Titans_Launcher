"""System quick-setting commands used by the Control Centre overlay."""

import logging
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)


class ControlCentreManager:
    """Read and change controls supported by common Linux desktop tools."""

    def _run(self, executable, *arguments):
        path = shutil.which(executable)
        if not path:
            return None
        command = [path, *arguments]
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            logger.error("Could not run %s: %s", executable, error)
            return subprocess.CompletedProcess(command, 127, "", str(error))

    @staticmethod
    def _result(result, missing_message):
        if result is None:
            return False, missing_message
        if result.returncode:
            return False, (result.stderr or result.stdout or "Command failed").strip()
        return True, result.stdout.strip()

    def get_status(self):
        wifi_result = self._run("nmcli", "-t", "-f", "WIFI", "radio")
        wifi_ok, wifi_value = self._result(wifi_result, "nmcli unavailable")

        bluetooth_result = self._run("bluetoothctl", "show")
        bluetooth_ok, bluetooth_output = self._result(bluetooth_result, "bluetoothctl unavailable")
        bluetooth_match = re.search(r"^\s*Powered:\s*(yes|no)\s*$", bluetooth_output, re.MULTILINE)

        volume_result = self._run("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
        volume_ok, volume_output = self._result(volume_result, "wpctl unavailable")
        volume_match = re.search(r"Volume:\s*([0-9.]+)", volume_output)

        brightness_result = self._run("brightnessctl", "-m")
        brightness_ok, brightness_output = self._result(brightness_result, "brightnessctl unavailable")
        brightness_value = None
        if brightness_ok and brightness_output:
            fields = brightness_output.splitlines()[0].split(",")
            if len(fields) >= 5:
                match = re.search(r"(\d+)%", fields[4])
                if match:
                    brightness_value = int(match.group(1))

        network_result = self._run("nmcli", "-t", "-f", "STATE", "general")
        network_ok, network_state = self._result(network_result, "NetworkManager unavailable")

        return {
            "wifi": {
                "available": wifi_ok and wifi_value.lower() in ("enabled", "disabled"),
                "enabled": wifi_value.lower() == "enabled",
                "detail": wifi_value if wifi_ok else wifi_value,
            },
            "bluetooth": {
                "available": bluetooth_ok and bluetooth_match is not None,
                "enabled": bool(bluetooth_match and bluetooth_match.group(1) == "yes"),
                "detail": "Ready" if bluetooth_match else bluetooth_output or "Bluetooth status unavailable",
            },
            "volume": {
                "available": volume_ok and volume_match is not None,
                "value": round(float(volume_match.group(1)) * 100) if volume_match else 0,
                "muted": "MUTED" in volume_output.upper(),
                "detail": "Ready" if volume_match else volume_output or "Audio status unavailable",
            },
            "brightness": {
                "available": brightness_ok and brightness_value is not None,
                "value": brightness_value if brightness_value is not None else 0,
                "detail": "Ready" if brightness_value is not None else brightness_output or "Brightness unavailable",
            },
            "network_status": network_state if network_ok else network_state,
        }

    def set_wifi_enabled(self, enabled):
        return self._set("nmcli", "radio", "wifi", "on" if enabled else "off")

    def set_bluetooth_enabled(self, enabled):
        return self._set("bluetoothctl", "power", "on" if enabled else "off")

    def set_volume(self, value):
        value = max(0, min(100, int(value)))
        return self._set("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{value / 100:.2f}")

    def set_brightness(self, value):
        value = max(0, min(100, int(value)))
        return self._set("brightnessctl", "set", f"{value}%")

    def _set(self, executable, *arguments):
        result = self._run(executable, *arguments)
        success, detail = self._result(result, f"{executable} unavailable")
        if not success:
            logger.error("Quick setting command failed: %s", detail)
        return success, detail
