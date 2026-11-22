"""pacman helpers for the Install Apps tab and the Advanced uninstall page."""
import re
import shutil
import subprocess

NAME_PATTERN = re.compile(r"^[a-z0-9@._+][a-z0-9@._+-]*$")

# Curated starting point shown before the user searches.
FEATURED_PACKAGES = (
    "firefox", "chromium", "vlc", "mpv", "kodi", "jellyfin-media-player", "plex-desktop",
    "steam", "lutris", "retroarch", "dolphin-emu", "pcsx2", "ppsspp", "duckstation", "mgba-qt",
    "moonlight-qt", "sunshine", "obs-studio", "discord", "telegram-desktop", "signal-desktop",
    "spotify-launcher", "audacious", "strawberry", "qbittorrent", "transmission-gtk",
    "libreoffice-fresh", "gimp", "inkscape", "krita", "blender", "kdenlive", "audacity",
    "handbrake", "kodi-addons", "stremio", "celluloid", "gwenview", "okular", "ark",
    "kate", "kcalc", "spectacle", "kdeconnect", "thunderbird", "filezilla", "remmina",
    "virt-manager", "gparted", "htop", "btop", "neofetch", "fastfetch", "gnome-calculator",
    "yt-dlp", "ffmpeg", "wine", "winetricks", "gamemode", "mangohud", "goverlay", "protonup-qt",
    "emulationstation-de", "pegasus-frontend", "cemu", "rpcs3", "xemu", "flycast", "mednafen",
)

# Packages (and everything they depend on) that keep the OS, boot, network, display
# and this launcher working. They are never offered for removal.
PROTECTED_ROOTS = (
    "base", "pacman", "pacman-contrib", "systemd", "glibc", "bash", "coreutils", "util-linux",
    "filesystem", "sudo", "polkit", "python", "python-pip", "networkmanager",
    "networkmanager-openvpn", "wireguard-tools", "openvpn", "bluez", "bluez-utils",
    "pipewire", "pipewire-pulse", "wireplumber", "wayland", "xorg-server", "xorg-xwayland",
    "plasma-desktop", "plasma-meta", "plasma-workspace", "kwin", "kscreen", "sddm",
    "mesa", "efibootmgr", "mkinitcpio", "dracut", "grub", "refind", "limine", "syslinux",
)
PROTECTED_NAME_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"^linux(-[a-z0-9]+)*$",
    r"^linux-firmware(-.*)?$",
    r".*-ucode$",
    r"^nvidia(-.*)?$",
    r"^vulkan-.*$",
    r"^xf86-.*$",
    r"^(btrfs-progs|e2fsprogs|dosfstools|xfsprogs|lvm2|cryptsetup|mdadm|f2fs-tools|exfatprogs)$",
    r"^(wpa_supplicant|iwd|dhcpcd|systemd-.*)$",
))


def valid_package_name(name):
    return bool(NAME_PATTERN.match(name or ""))


def run_pacman(arguments, timeout=30):
    command = [shutil.which("pacman") or "pacman", *arguments]
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def passwordless_pacman_available(require_check=False):
    sudo = shutil.which("sudo")
    if not sudo or not shutil.which("pacman"):
        return False
    try:
        commands = [["/usr/bin/pacman"]]
        if require_check:
            commands.append(["/usr/bin/env", "LC_ALL=C", "/usr/bin/pacman",
                             "-Qkk", "--color", "never"])
        return all(
            subprocess.run(
                [sudo, "-n", "-l", *command],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False,
            ).returncode == 0
            for command in commands
        )
    except (OSError, subprocess.SubprocessError):
        return False


def elevation_prefix(require_check=False):
    """Command prefix that gains root without a terminal, or None when unavailable."""
    if passwordless_pacman_available(require_check=require_check):
        return ["sudo", "-n"]
    if shutil.which("pkexec"):
        return ["pkexec"]
    if shutil.which("sudo"):
        return ["sudo", "-n"]
    return None


def parse_blocks(output):
    """Parse `pacman -Si/-Qi` output into one dict of field -> text per package."""
    packages, current, last_key = [], {}, None
    for line in output.splitlines():
        if not line.strip():
            if current:
                packages.append(current)
            current, last_key = {}, None
            continue
        if line[0] in " \t":
            if last_key:
                current[last_key] = f"{current[last_key]} {line.strip()}".strip()
            continue
        key, separator, value = line.partition(":")
        if separator:
            last_key = key.strip()
            current[last_key] = value.strip()
    if current:
        packages.append(current)
    return packages


def parse_search(output):
    """Parse `pacman -Ss` into dicts with repo, name, version, description and installed."""
    results, entry = [], None
    for line in output.splitlines():
        if line.startswith((" ", "\t")):
            if entry:
                entry["description"] = f"{entry['description']} {line.strip()}".strip()
            continue
        match = re.match(r"^([^/\s]+)/(\S+)\s+(\S+)(.*)$", line)
        if not match:
            continue
        repo, name, version, rest = match.groups()
        entry = {
            "repo": repo, "name": name, "version": version,
            "description": "", "installed": "[installed" in rest,
        }
        results.append(entry)
    return results


def search_regex_terms(query):
    """Split a user query into pacman search terms with regex characters escaped."""
    terms = re.split(r"\s+", query.strip())[:6]
    return [re.sub(r"([\\.^$*+?()\[\]{}|])", r"\\\1", term) for term in terms if term]


def search_packages(query, limit=48):
    terms = search_regex_terms(query)
    if not terms:
        return []
    result = run_pacman(["-Ss", "--", *terms], timeout=30)
    if result.returncode not in (0, 1) or (result.returncode == 1 and result.stderr.strip()):
        raise RuntimeError((result.stderr or "pacman search failed").strip())
    return parse_search(result.stdout)[:limit]


def featured_packages():
    listing = run_pacman(["-Sl"], timeout=30)
    if listing.returncode != 0:
        raise RuntimeError((listing.stderr or "could not read repository packages").strip())
    available = {
        fields[1] for line in listing.stdout.splitlines()
        if len(fields := line.split()) >= 3
    }
    names = [name for name in FEATURED_PACKAGES if name in available]
    if not names:
        return []
    result = run_pacman(["-Si", "--", *names], timeout=30)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "could not read suggested package details").strip())
    found = []
    for block in parse_blocks(result.stdout):
        if block.get("Name"):
            found.append({
                "repo": block.get("Repository", ""),
                "name": block["Name"],
                "version": block.get("Version", ""),
                "description": block.get("Description", ""),
                "installed": False,
            })
    return found


def installed_names():
    result = run_pacman(["-Qq"], timeout=15)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "could not read installed package names").strip())
    return set(result.stdout.split())


def _dependency_name(entry):
    return re.split(r"[<>=:]", entry, maxsplit=1)[0]


def read_installed():
    """Every installed package with version, size, dependencies and reverse dependencies."""
    result = run_pacman(["-Qi"], timeout=60)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "could not read the package database").strip())
    packages = {}
    for block in parse_blocks(result.stdout):
        name = block.get("Name")
        if not name:
            continue
        depends = block.get("Depends On", "None")
        required_by = block.get("Required By", "None")
        provides = block.get("Provides", "None")
        packages[name] = {
            "name": name,
            "version": block.get("Version", ""),
            "description": block.get("Description", ""),
            "size": block.get("Installed Size", ""),
            "groups": [] if block.get("Groups", "None") == "None" else block["Groups"].split(),
            "explicit": block.get("Install Reason", "").startswith("Explicitly"),
            "depends": [] if depends == "None" else [_dependency_name(item) for item in depends.split()],
            "provides": [] if provides == "None" else [_dependency_name(item) for item in provides.split()],
            "required_by": [] if required_by == "None" else required_by.split(),
        }
    return packages


def protected_packages(packages):
    """Names of installed packages that must never be removed."""
    providers = {}
    for name, info in packages.items():
        for provided in info["provides"]:
            providers.setdefault(provided, name)

    roots = {name for name in packages if name in PROTECTED_ROOTS}
    roots |= {name for name in packages if any(p.match(name) for p in PROTECTED_NAME_PATTERNS)}
    roots |= {name for name, info in packages.items() if "base" in info["groups"]}

    protected, queue = set(), list(roots)
    while queue:
        name = queue.pop()
        if name in protected:
            continue
        protected.add(name)
        for dependency in packages[name]["depends"]:
            target = dependency if dependency in packages else providers.get(dependency)
            if target and target not in protected:
                queue.append(target)
    return protected


def removable_packages(packages=None):
    """Explicitly installed packages that nothing else needs and that are not protected."""
    packages = packages if packages is not None else read_installed()
    protected = protected_packages(packages)
    hidden = sum(1 for info in packages.values() if info["explicit"] and info["name"] in protected)
    apps = [
        info for info in packages.values()
        if info["explicit"] and info["name"] not in protected and not info["required_by"]
    ]
    apps.sort(key=lambda info: info["name"])
    return apps, hidden


def plan_removal(name):
    """Return (packages_to_remove, error) without changing anything.

    Re-checks protection against what pacman itself would remove, so unneeded
    dependencies pulled in by `-Rs` cannot include a protected package.
    """
    if not valid_package_name(name):
        return [], "Invalid package name."
    packages = read_installed()
    if name not in packages:
        return [], f"{name} is not installed."
    if name in protected_packages(packages):
        return [], f"{name} is part of the system and cannot be removed."
    dry_run = run_pacman(["-Rsp", "--print-format", "%n", "--", name], timeout=30)
    if dry_run.returncode != 0:
        return [], (dry_run.stderr or "pacman cannot remove this package.").strip()
    planned = dry_run.stdout.split()
    blocked = sorted(set(planned) & protected_packages(packages))
    if not planned or name not in planned:
        return [], "pacman did not plan to remove this package."
    if blocked:
        return [], "Removal would also remove system packages: " + ", ".join(blocked)
    return planned, ""


def install_command(name):
    prefix = elevation_prefix()
    if prefix is None or not valid_package_name(name):
        return None
    return [*prefix, "pacman", "-S", "--needed", "--noconfirm", "--", name]


def remove_command(planned):
    prefix = elevation_prefix()
    if prefix is None or not planned or not all(valid_package_name(name) for name in planned):
        return None
    # Explicit names (no -s) so exactly the checked set is removed.
    return [*prefix, "pacman", "-R", "--noconfirm", "--", *planned]
