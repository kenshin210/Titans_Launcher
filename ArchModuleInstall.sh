#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v pacman >/dev/null 2>&1; then
    printf 'This installer requires Arch Linux and pacman.\n' >&2
    exit 1
fi

if (( EUID == 0 )); then
    PACMAN=(pacman)
    PRIVILEGED=()
elif command -v sudo >/dev/null 2>&1; then
    PACMAN=(sudo pacman)
    PRIVILEGED=(sudo)
else
    printf 'Run as root or install sudo to install Arch packages.\n' >&2
    exit 1
fi

PACMAN_PACKAGES=(
    bluez
    bluez-utils
    dbus
    iw
    kwin
    libcec
    libkscreen
    libpulse
    linux
    networkmanager
    networkmanager-openvpn
    openvpn
    pacman-contrib
    pciutils
    polkit
    python
    python-pip
    qt6-tools
    udisks2
    upower
    wireplumber
    wireguard-tools
    wmctrl
    wlr-randr
    xdg-utils
)

printf 'Installing Arch system dependencies...\n'
"${PACMAN[@]}" -S --needed --noconfirm -- "${PACMAN_PACKAGES[@]}"

VENV_DIR="$SCRIPT_DIR/.venv"
printf 'Creating or reusing virtual environment at %s\n' "$VENV_DIR"
python -m venv "$VENV_DIR"

PYTHON_PACKAGES=(
    evdev
    opencv-python
    pygame-ce
    psutil
    PyQt6
)

printf 'Installing Python dependencies into the virtual environment...\n'
"$VENV_DIR/bin/python" -m pip install "${PYTHON_PACKAGES[@]}"

printf 'Configuring virtual input access for the active local desktop user...\n'
printf 'uinput\n' | "${PRIVILEGED[@]}" tee /etc/modules-load.d/titans-uinput.conf >/dev/null
printf 'SUBSYSTEM=="misc", KERNEL=="uinput", MODE="0660", TAG+="uaccess"\n' |
    "${PRIVILEGED[@]}" tee /etc/udev/rules.d/70-titans-uinput.rules >/dev/null
if ! "${PRIVILEGED[@]}" modprobe uinput; then
    printf 'Could not load uinput. If the kernel was updated, reboot into the installed kernel and rerun this installer.\n' >&2
    exit 1
fi
"${PRIVILEGED[@]}" udevadm control --reload-rules
"${PRIVILEGED[@]}" udevadm trigger --subsystem-match=misc --sysname-match=uinput
"${PRIVILEGED[@]}" udevadm settle

printf 'Virtual input access configured. Restart Titans; log out and back in if access is not yet available.\n'
printf 'Installation complete. Services are not enabled or started by this script.\n'
