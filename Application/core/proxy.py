import re
import shutil

from Application.ui.Settings.AsyncTask import run_command

PROXY_ENDPOINT = re.compile(r"^[A-Za-z0-9._\-\[\]:]+:(\d{1,5})$")
PROXY_KINDS = ("http", "https", "socks")


def validate_endpoint(text):
    """Blank is allowed. Otherwise require host:port with a valid port."""
    text = text.strip()
    if not text:
        return ""
    match = PROXY_ENDPOINT.match(text)
    if not match or not 0 < int(match.group(1)) < 65536:
        raise ValueError(f"'{text}' must look like host:port (for example 192.168.1.10:8080).")
    return text


def proxy_environment(config):
    """Proxy variables handed to launched applications (empty when the proxy is off)."""
    if config.get("_proxy_mode", "Off") != "Manual":
        return {}
    environment = {}
    for kind, scheme in (("http", "http"), ("https", "http"), ("socks", "socks5")):
        endpoint = config.get(f"_proxy_{kind}", "").strip()
        if endpoint:
            url = f"{scheme}://{endpoint}"
            name = "all_proxy" if kind == "socks" else f"{kind}_proxy"
            environment[name] = url
            environment[name.upper()] = url
    no_proxy = config.get("_proxy_no_proxy", "").strip()
    if environment and no_proxy:
        environment["no_proxy"] = no_proxy
        environment["NO_PROXY"] = no_proxy
    return environment


def apply_system_proxy(config):
    """Mirror the proxy into GNOME-style system settings when gsettings exists."""
    gsettings = shutil.which("gsettings")
    if not gsettings:
        return False
    manual = config.get("_proxy_mode", "Off") == "Manual"

    def put(schema, key, value):
        return run_command([gsettings, "set", schema, key, value]).returncode == 0

    ok = put("org.gnome.system.proxy", "mode", "'manual'" if manual else "'none'")
    if manual:
        for kind in PROXY_KINDS:
            host, _, port = config.get(f"_proxy_{kind}", "").strip().rpartition(":")
            schema = f"org.gnome.system.proxy.{kind}"
            ok &= put(schema, "host", f"'{host}'")
            ok &= put(schema, "port", port or "0")
        hosts = [item.strip() for item in config.get("_proxy_no_proxy", "").split(",") if item.strip()]
        ignore = "[" + ", ".join(f"'{item}'" for item in hosts) + "]"
        ok &= put("org.gnome.system.proxy", "ignore-hosts", ignore)
    return ok
