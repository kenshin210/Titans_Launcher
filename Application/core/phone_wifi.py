"""Temporary, launcher-owned Wi-Fi onboarding hotspot."""

import asyncio
import ipaddress
import secrets
import socket
import socketserver
import subprocess
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from dbus_next import BusType, Message, MessageFlag, MessageType, Variant
from dbus_next.aio import MessageBus


SERVICE = "org.freedesktop.NetworkManager"
ROOT = "/org/freedesktop/NetworkManager"
MANAGER = SERVICE
DEVICE = SERVICE + ".Device"
WIRELESS = DEVICE + ".Wireless"
PROPERTIES = "org.freedesktop.DBus.Properties"
LIFETIME = 300


class PhoneWifiError(RuntimeError):
    pass


def _validate_credentials(ssid, password):
    if not ssid or len(ssid.encode("utf-8")) > 32 or any(c in ssid for c in "\x00\r\n"):
        raise ValueError("Enter a network name of 1 to 32 UTF-8 bytes.")
    if any(c in password for c in "\x00\r\n") or len(password.encode("utf-8")) > 64:
        raise ValueError("The password is invalid.")
    if password and not (8 <= len(password.encode("utf-8")) <= 63 or
                         len(password) == 64 and all(c in "0123456789abcdefABCDEF" for c in password)):
        raise ValueError("Use a WPA password of 8 to 63 bytes, or leave it empty for an open network.")


class SetupServer(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, token, network):
        self.token = token
        self.network = network
        self.credentials = None
        self.closed = False
        self.lock = threading.Lock()
        self.request_slots = threading.BoundedSemaphore(4)
        super().__init__(address, SetupHandler)
        self.timeout = 0.5

    def verify_request(self, request, client_address):
        try:
            return ipaddress.ip_address(client_address[0]) in self.network
        except ValueError:
            return False

    def process_request(self, request, client_address):
        if not self.request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_slots.release()

    def server_close(self):
        with self.lock:
            self.closed = True
        super().server_close()


class SetupHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(3)
        self.request_deadline = threading.Timer(5, self._expire_connection)
        self.request_deadline.daemon = True
        self.request_deadline.start()

    def _expire_connection(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def finish(self):
        self.request_deadline.cancel()
        super().finish()

    def _respond(self, status, content):
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        host, port = self.server.server_address
        with self.server.lock:
            return (
                self.path == "/" + self.server.token
                and self.headers.get("Host") == f"{host}:{port}"
                and self.server.credentials is None
                and not self.server.closed
            )

    def do_GET(self):
        if not self._authorized():
            self.send_error(404)
            return
        self._respond(200, (
            "<!doctype html><meta name='viewport' content='width=device-width'>"
            "<title>Titans Wi-Fi setup</title><h1>Titans Wi-Fi setup</h1>"
            "<p>Enter the Wi-Fi network for Titans to join.</p>"
            "<form method='post'><label>Network name <input name='ssid' required></label><br>"
            "<label>Password <input name='password' type='password'></label><br>"
            "<button type='submit'>Connect</button></form>"
        ))

    def do_POST(self):
        host, port = self.server.server_address
        if not self._authorized() or self.headers.get("Origin") != f"http://{host}:{port}":
            self.send_error(403)
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/x-www-form-urlencoded":
            self.send_error(415)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if not 0 < length <= 2048 or self.headers.get("Transfer-Encoding"):
                raise ValueError
            data = self.rfile.read(length).decode("utf-8", errors="strict")
            fields = urllib.parse.parse_qs(data, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
            if set(fields) != {"ssid", "password"} or any(len(values) != 1 for values in fields.values()):
                raise ValueError
            ssid, password = fields["ssid"][0], fields["password"][0]
            _validate_credentials(ssid, password)
        except (ValueError, UnicodeError, TimeoutError):
            self._respond(400, "Invalid network name or password. Return to the setup page and try again.")
            return
        with self.server.lock:
            if self.server.closed or self.server.credentials is not None:
                self.send_error(403)
                return
            self.server.credentials = (ssid, password)
        self._respond(200, "Details received. Titans will close the hotspot and connect to your Wi-Fi.")


class PhoneWifiSetup:
    def __init__(self, interface, nmcli, cancel, ready):
        self.interface = interface
        self.nmcli = nmcli
        self.cancel = cancel
        self.ready = ready
        self.hotspot_name = "Titans-Setup-" + secrets.token_hex(3)
        self.hotspot_password = secrets.token_urlsafe(18)
        self.token = secrets.token_urlsafe(24)
        self.connection_id = str(uuid.uuid4())

    async def _call(self, path, interface, member, signature="", body=None, timeout=30):
        try:
            reply = await asyncio.wait_for(self.bus.call(Message(
                destination=SERVICE, path=path, interface=interface, member=member,
                signature=signature, body=body or [],
                flags=MessageFlag.ALLOW_INTERACTIVE_AUTHORIZATION,
            )), timeout)
        except asyncio.TimeoutError as error:
            raise PhoneWifiError(f"NetworkManager timed out during {member}.") from error
        if reply.message_type == MessageType.ERROR:
            raise PhoneWifiError(f"NetworkManager rejected {member}: {reply.error_name}")
        return reply.body

    async def _property(self, path, interface, name):
        result = await self._call(path, PROPERTIES, "Get", "ss", [interface, name])
        return result[0].value

    async def _wait_for_hotspot(self, device):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and not self.cancel.is_set():
            state = await self._property(device, DEVICE, "State")
            if state == 100:
                ip_path = await self._property(device, DEVICE, "Ip4Config")
                if ip_path != "/":
                    addresses = await self._property(ip_path, SERVICE + ".IP4Config", "AddressData")
                    for entry in addresses:
                        address = ipaddress.IPv4Interface(
                            f'{entry["address"].value}/{entry["prefix"].value}'
                        )
                        if address.ip.is_private:
                            return address
            if state == 120:
                raise PhoneWifiError("The Wi-Fi adapter could not activate the hotspot.")
            await asyncio.sleep(0.5)
        if self.cancel.is_set():
            return None
        raise PhoneWifiError("Timed out waiting for the hotspot.")

    async def run(self):
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        checkpoint = None
        try:
            device = (await self._call(ROOT, MANAGER, "GetDeviceByIpIface", "s", [self.interface]))[0]
            capabilities = await self._property(device, WIRELESS, "WirelessCapabilities")
            if capabilities & 0x68 != 0x68:
                raise PhoneWifiError("This Wi-Fi adapter does not support WPA2 access point mode.")
            if self.cancel.is_set():
                return False
            checkpoint = (await self._call(ROOT, MANAGER, "CheckpointCreate", "aouu", [[device], LIFETIME + 180, 0]))[0]
            settings = {
                "connection": {
                    "id": Variant("s", self.hotspot_name),
                    "uuid": Variant("s", self.connection_id),
                    "type": Variant("s", "802-11-wireless"),
                    "autoconnect": Variant("b", False),
                },
                "802-11-wireless": {
                    "ssid": Variant("ay", self.hotspot_name.encode()),
                    "mode": Variant("s", "ap"),
                },
                "802-11-wireless-security": {
                    "key-mgmt": Variant("s", "wpa-psk"),
                    "psk": Variant("s", self.hotspot_password),
                    "proto": Variant("as", ["rsn"]),
                    "pairwise": Variant("as", ["ccmp"]),
                },
                "ipv4": {"method": Variant("s", "shared")},
                "ipv6": {"method": Variant("s", "disabled")},
            }
            options = {"persist": Variant("s", "volatile"), "bind-activation": Variant("s", "dbus-client")}
            await self._call(ROOT, MANAGER, "AddAndActivateConnection2", "a{sa{sv}}ooa{sv}",
                             [settings, device, "/", options], timeout=45)
            address = await self._wait_for_hotspot(device)
            if address is None:
                return False
            with SetupServer((str(address.ip), 0), self.token, address.network) as server:
                host, port = server.server_address
                url = f"http://{host}:{port}/{self.token}"
                self.ready(self.hotspot_name, self.hotspot_password, url)
                deadline = time.monotonic() + LIFETIME
                while server.credentials is None and not self.cancel.is_set() and time.monotonic() < deadline:
                    server.handle_request()
                credentials = server.credentials
            if credentials is None:
                if self.cancel.is_set():
                    return False
                raise PhoneWifiError("Phone setup expired without receiving Wi-Fi details.")
            result = await self._call(ROOT, MANAGER, "CheckpointRollback", "o", [checkpoint], timeout=45)
            checkpoint = None
            if result and any(code != 0 for code in result[0].values()):
                raise PhoneWifiError("Could not restore the previous network after closing the hotspot.")
            if self.cancel.is_set():
                return False
            checkpoint = (await self._call(ROOT, MANAGER, "CheckpointCreate", "aouu", [[device], 120, 0]))[0]
            ssid, password = credentials
            try:
                outcome = await asyncio.to_thread(subprocess.run, [
                    self.nmcli, "--ask", "device", "wifi", "connect", ssid, "ifname", self.interface,
                ], input=password + "\n", text=True, capture_output=True, timeout=50, check=False)
            except (OSError, subprocess.SubprocessError) as error:
                raise PhoneWifiError("Could not run NetworkManager to connect to the target Wi-Fi.") from error
            if outcome.returncode:
                raise PhoneWifiError("Could not connect to the supplied Wi-Fi. Check the name and password.")
            if self.cancel.is_set():
                return False
            await self._call(ROOT, MANAGER, "CheckpointDestroy", "o", [checkpoint])
            checkpoint = None
            return True
        finally:
            try:
                if checkpoint is not None:
                    result = await self._call(ROOT, MANAGER, "CheckpointRollback", "o", [checkpoint], timeout=45)
                    if result and any(code != 0 for code in result[0].values()):
                        raise PhoneWifiError("Hotspot cleanup could not restore the previous network.")
            finally:
                self.bus.disconnect()
