import socket
import struct
import threading
from datetime import datetime, timedelta, timezone

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


def start_ntp_sync_thread(config, stop_event, on_time_updated):
    def sync_worker():
        while not stop_event.is_set():
            server = config.get("_ntp_server", "nz.pool.ntp.org")
            offset = float(config.get("_ntp_offset", 12))
            ntp_time = fetch_ntp_time(server, offset)
            if ntp_time:
                on_time_updated(ntp_time)
            stop_event.wait(1800)

    sync_thread = threading.Thread(target=sync_worker, daemon=True)
    sync_thread.start()
    return sync_thread
