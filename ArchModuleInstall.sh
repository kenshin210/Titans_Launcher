#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mode="${1:-}"
if (( $# > 1 )); then
    printf 'Usage: bash ArchModuleInstall.sh [--gui|--launcher|--autostart|--both]\n' >&2
    exit 1
fi
if [[ -z "$mode" ]]; then
    if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
        mode=--gui
    else
        mode=--launcher
    fi
fi
case "$mode" in
    --gui)
        source "$SCRIPT_DIR/InstallerDialogs.sh"
        titans_gui_init
        if selection="$(zenity --list --radiolist --title="Titans Arch setup" \
            --text="Choose what to set up. Autostart setup also grants account-wide passwordless pacman access; a security confirmation is required." \
            --column="Select" --column="Mode" --column="Setup" --hide-column=2 --print-column=2 \
            --width=750 --height=320 \
            TRUE launcher "Launcher dependencies only" \
            FALSE autostart "Autostart and passwordless pacman only (launcher must be installed)" \
            FALSE both "Both: launcher dependencies, then autostart and passwordless pacman")"; then
            case "$selection" in
                launcher|autostart|both)
                    titans_gui_run "Titans Arch setup" bash "$SCRIPT_DIR/ArchModuleInstall.sh" "--$selection"
                    exit $?
                    ;;
                *)
                    printf 'Invalid setup selection: %s\n' "$selection" >&2
                    exit 1
                    ;;
            esac
        else
            status=$?
            if (( status == 1 )); then
                printf 'Setup cancelled.\n'
                exit 0
            fi
            printf 'Could not open the setup selection dialog (exit %s).\n' "$status" >&2
            exit "$status"
        fi
        ;;
    --autostart)
        bash "$SCRIPT_DIR/SetupAutostart.sh" --cli
        exit $?
        ;;
    --launcher|--both) ;;
    *)
        printf 'Usage: bash ArchModuleInstall.sh [--gui|--launcher|--autostart|--both]\n' >&2
        exit 1
        ;;
esac
if [[ "$mode" == --both && $EUID == 0 ]]; then
    printf 'Run combined setup as the desktop user, not root.\n' >&2
    exit 1
fi

if ! command -v pacman >/dev/null 2>&1; then
    printf 'This installer requires Arch Linux and pacman.\n' >&2
    exit 1
fi

if (( EUID == 0 )); then
    PACMAN=(pacman)
    PRIVILEGED=()
elif command -v sudo >/dev/null 2>&1; then
    PACMAN=(sudo -A pacman)
    PRIVILEGED=(sudo -A)
else
    printf 'Run as root or install sudo to install Arch packages.\n' >&2
    exit 1
fi

PACMAN_PACKAGES=(
    antimicrox
    bluez
    bluez-utils
    brightnessctl
    dbus
    firefox
    gcc
    git
    glib2
    gsettings-system-schemas
    iproute2
    iw
    kwin
    libcec
    libkscreen
    libnotify
    libpulse
    linux
    linux-api-headers
    networkmanager
    networkmanager-openvpn
    openvpn
    pacman-contrib
    pciutils
    polkit
    procps-ng
    python
    python-pip
    qt6-tools
    udisks2
    upower
    v4l-utils
    wireplumber
    wireguard-tools
    wmctrl
    wlr-randr
    xdg-utils
    zenity
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
printf 'SUBSYSTEM=="input", KERNEL=="event*", ENV{ID_INPUT_KEYBOARD}=="1", TAG+="uaccess"\n' |
    "${PRIVILEGED[@]}" tee /etc/udev/rules.d/70-titans-keyboard.rules >/dev/null
if ! "${PRIVILEGED[@]}" modprobe uinput; then
    printf 'Could not load uinput. If the kernel was updated, reboot into the installed kernel and rerun this installer.\n' >&2
    exit 1
fi
"${PRIVILEGED[@]}" udevadm control --reload-rules
"${PRIVILEGED[@]}" udevadm trigger --subsystem-match=misc --sysname-match=uinput
if ! "${PRIVILEGED[@]}" udevadm trigger --subsystem-match=input --property-match=ID_INPUT_KEYBOARD=1; then
    printf 'Could not refresh keyboard device access. Check the udev configuration and rerun this installer.\n' >&2
    exit 1
fi
"${PRIVILEGED[@]}" udevadm settle

printf 'Virtual input and local keyboard access configured. Restart Titans; log out and back in if access is not yet available.\n'
if [[ "$mode" == --both ]]; then
    printf 'Launcher dependencies installed. Starting autostart and privilege setup...\n'
    bash "$SCRIPT_DIR/SetupAutostart.sh" --cli
fi
printf 'Installation complete. Services are not enabled or started by this script.\n'
