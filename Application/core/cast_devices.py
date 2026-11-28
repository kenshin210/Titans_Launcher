"""Discovery and status for external Google Cast receivers."""

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class CastDevice:
    identifier: str
    name: str


@dataclass(frozen=True)
class CastStatus:
    device: CastDevice
    application: str
    idle: bool


def _browser():
    from pychromecast.discovery import CastBrowser, SimpleCastListener, create_zeroconf

    return CastBrowser(SimpleCastListener(), create_zeroconf())


def scan_cast_devices(selected_id=None):
    """Scan briefly on the local network and optionally read one receiver's status."""
    browser = _browser()
    started = False
    cast = None
    try:
        browser.start_discovery()
        started = True
        threading.Event().wait(5)
        infos = list(browser.devices.values())
        devices = sorted(
            (CastDevice(str(info.uuid), info.friendly_name or "Unnamed Cast device") for info in infos),
            key=lambda device: (device.name.casefold(), device.identifier),
        )
        selected = next((info for info in infos if str(info.uuid) == selected_id), None)
        if selected is None:
            return devices, None
        from pychromecast import get_chromecast_from_cast_info

        cast = get_chromecast_from_cast_info(selected, browser.zc, tries=1, timeout=3)
        cast.wait(timeout=3)
        return devices, CastStatus(
            CastDevice(str(selected.uuid), selected.friendly_name or "Unnamed Cast device"),
            cast.app_display_name or "",
            cast.is_idle,
        )
    finally:
        try:
            if cast is not None and cast.socket_client.is_alive():
                cast.disconnect(timeout=3)
        finally:
            if started:
                browser.stop_discovery()
            elif browser.zc is not None:
                browser.zc.close()
