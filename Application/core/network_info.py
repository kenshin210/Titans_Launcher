import ipaddress
import re
from pathlib import Path

MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

WIFI_STANDARDS = (
    ("EHT", "Wi-Fi 7 (802.11be)"),
    ("HE", "Wi-Fi 6 (802.11ax)"),
    ("VHT", "Wi-Fi 5 (802.11ac)"),
    ("MCS", "Wi-Fi 4 (802.11n)"),
)


def split_terse(line):
    """Split an nmcli terse (-t) line on unescaped colons."""
    fields = re.split(r"(?<!\\):", line)
    return [field.replace("\\:", ":").replace("\\\\", "\\") for field in fields]


def parse_device_show(output):
    """Parse `nmcli -t device show DEV` into a dict (numbered keys like IP4.ADDRESS[1] keep first value)."""
    values = {}
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = re.sub(r"\[\d+\]$", "", key)
        value = value.replace("\\:", ":").strip()
        if value and key not in values:
            values[key] = value
    return values


def prefix_to_netmask(prefix):
    return str(ipaddress.IPv4Network(f"0.0.0.0/{int(prefix)}").netmask)


def split_cidr(address):
    """'192.168.1.5/24' -> ('192.168.1.5', '255.255.255.0')."""
    if not address:
        return "", ""
    ip_text, _, prefix = address.partition("/")
    try:
        return ip_text, prefix_to_netmask(prefix) if prefix else ""
    except ValueError:
        return ip_text, ""


def parse_subnet(text):
    """Accept '255.255.255.0' or '24' (optionally '/24') and return the prefix length."""
    text = text.strip().lstrip("/")
    if text.isdigit():
        prefix = int(text)
        if 0 <= prefix <= 32:
            return prefix
        raise ValueError("Subnet prefix must be between 0 and 32.")
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{text}").prefixlen
    except ValueError:
        raise ValueError("Subnet mask is not valid (for example 255.255.255.0).") from None


def wifi_standard_from_bitrate(link_text):
    """Work out the Wi-Fi generation from `iw dev X link` output."""
    for marker, name in WIFI_STANDARDS:
        if re.search(rf"\b{marker}", link_text):
            return name
    return ""


def parse_iw_link(link_text):
    """Return (standard, signal_dbm, bitrate) from `iw dev X link`."""
    signal = re.search(r"signal:\s*(-?\d+)\s*dBm", link_text)
    bitrate = re.search(r"tx bitrate:\s*([\d.]+\s*\S+)", link_text)
    return (
        wifi_standard_from_bitrate(link_text),
        f"{signal.group(1)} dBm" if signal else "",
        bitrate.group(1) if bitrate else "",
    )


def band_from_frequency(freq_text):
    match = re.search(r"(\d+)", freq_text or "")
    if not match:
        return ""
    mhz = int(match.group(1))
    if mhz < 3000:
        return "2.4 GHz"
    if mhz < 5925:
        return "5 GHz"
    return "6 GHz"


def wired_speed(device):
    try:
        speed = int((Path("/sys/class/net") / device / "speed").read_text().strip())
    except (OSError, ValueError):
        return ""
    return f"{speed} Mbit/s" if speed > 0 else ""


def validate_network_settings(method, ip_text, subnet_text, gateway_text, mac_text=None):
    """Return (settings, error). A mac_text of None leaves the MAC address untouched."""
    settings = {"method": method, "mac": None}
    if mac_text is not None:
        mac_text = mac_text.strip()
        if mac_text and not MAC_PATTERN.match(mac_text):
            return None, "MAC address must look like AA:BB:CC:DD:EE:FF."
        settings["mac"] = mac_text.upper()
    if method == "manual":
        try:
            ip = ipaddress.IPv4Address(ip_text.strip())
        except ValueError:
            return None, "IP address is not a valid IPv4 address."
        try:
            prefix = parse_subnet(subnet_text)
        except ValueError as error:
            return None, str(error)
        gateway = gateway_text.strip()
        if gateway:
            try:
                gateway_ip = ipaddress.IPv4Address(gateway)
            except ValueError:
                return None, "Default route address is not a valid IPv4 address."
            network = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
            if gateway_ip not in network:
                return None, "Default route address must be inside the same subnet as the IP address."
        settings.update(address=f"{ip}/{prefix}", gateway=gateway)
    return settings, ""


def build_modify_command(nmcli, uuid, connection_type, settings):
    """nmcli arguments that apply the validated settings to a saved connection."""
    mac_property = (
        "802-11-wireless.cloned-mac-address" if connection_type == "802-11-wireless"
        else "802-3-ethernet.cloned-mac-address"
    )
    command = [nmcli, "connection", "modify", "uuid", uuid]
    if settings.get("mac") is not None:
        command += [mac_property, settings["mac"]]
    if settings["method"] == "manual":
        command += [
            "ipv4.method", "manual",
            "ipv4.addresses", settings["address"],
            "ipv4.gateway", settings["gateway"],
        ]
    else:
        command += ["ipv4.method", "auto", "ipv4.addresses", "", "ipv4.gateway", ""]
    return command
