import socket
import struct
import threading
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo, available_timezones
except ImportError:  # no tz database on this system
    ZoneInfo = None

    def available_timezones():
        return set()

from Application.ui.Settings.Logger import log_info, log_warning


def fetch_ntp_time(server_address, offset_hours):
    port = 123
    data = b"\x1b" + 47 * b"\0"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2.0)
            sock.sendto(data, (server_address, port))
            response, _ = sock.recvfrom(1024)
        if response:
            unpacked = struct.unpack("!12I", response)[10]
            unix_time = unpacked - 2208988800
            utc_time = datetime.fromtimestamp(unix_time, tz=timezone.utc)
            result = utc_time.astimezone(timezone(timedelta(hours=offset_hours)))
            log_info(
                f"NTP sync successful with {server_address}: "
                f"{result.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return result
    except Exception as error:
        log_warning(
            f"NTP sync timed out/failed for {server_address}. Using system clock.",
            details=str(error),
        )
    return datetime.now(timezone(timedelta(hours=offset_hours)))


COUNTRY_TIMEZONES = {
    "New Zealand": "Pacific/Auckland", "Australia": "Australia/Sydney",
    "United States": "America/New_York", "United Kingdom": "Europe/London",
    "Canada": "America/Toronto", "Germany": "Europe/Berlin", "France": "Europe/Paris",
    "Japan": "Asia/Tokyo", "Singapore": "Asia/Singapore", "Brazil": "America/Sao_Paulo",
    "India": "Asia/Kolkata", "South Africa": "Africa/Johannesburg",
    "Argentina": "America/Argentina/Buenos_Aires", "Austria": "Europe/Vienna",
    "Belgium": "Europe/Brussels", "China": "Asia/Shanghai", "Denmark": "Europe/Copenhagen",
    "Fiji": "Pacific/Fiji", "Finland": "Europe/Helsinki", "Greece": "Europe/Athens",
    "Hong Kong": "Asia/Hong_Kong", "Ireland": "Europe/Dublin", "Italy": "Europe/Rome",
    "Malaysia": "Asia/Kuala_Lumpur", "Mexico": "America/Mexico_City",
    "Netherlands": "Europe/Amsterdam", "Norway": "Europe/Oslo",
    "Philippines": "Asia/Manila", "Poland": "Europe/Warsaw", "Portugal": "Europe/Lisbon",
    "Russia": "Europe/Moscow", "South Korea": "Asia/Seoul", "Spain": "Europe/Madrid",
    "Sweden": "Europe/Stockholm", "Switzerland": "Europe/Zurich", "Taiwan": "Asia/Taipei",
    "Thailand": "Asia/Bangkok", "Turkey": "Europe/Istanbul", "Ukraine": "Europe/Kyiv",
    "United Arab Emirates": "Asia/Dubai",
}


def timezone_offset_hours(zone_name, when_utc=None):
    """Current UTC offset (DST included) of an IANA zone, or None if unknown."""
    if not ZoneInfo or not zone_name:
        return None
    try:
        moment = when_utc or datetime.now(timezone.utc)
        return moment.astimezone(ZoneInfo(zone_name)).utcoffset().total_seconds() / 3600
    except Exception:
        return None


def configured_timezone(config):
    """Chosen time zone, falling back to the one for the selected country."""
    return config.get("_ntp_timezone") or COUNTRY_TIMEZONES.get(config.get("_ntp_country", ""), "")


def effective_offset(config):
    """UTC offset in hours for the clock.

    Automatic mode follows the chosen time zone's daylight saving rules; otherwise
    the manual offset is used, plus one hour while the manual DST box is ticked.
    """
    if config.get("_ntp_auto_dst", True):
        automatic = timezone_offset_hours(configured_timezone(config))
        if automatic is not None:
            return automatic
    offset = float(config.get("_ntp_offset", 12))
    return offset + 1 if config.get("_ntp_dst", False) else offset


def start_ntp_sync_thread(config, stop_event, on_time_updated):
    def sync_worker():
        while not stop_event.is_set():
            server = config.get("_ntp_server", "nz.pool.ntp.org")
            offset = effective_offset(config)
            ntp_time = fetch_ntp_time(server, offset)
            if ntp_time:
                on_time_updated(ntp_time)
            stop_event.wait(1800)

    sync_thread = threading.Thread(target=sync_worker, daemon=True)
    sync_thread.start()
    return sync_thread
