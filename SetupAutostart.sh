#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

mode="${1:-}"
if (( $# > 1 )); then
    printf 'Usage: bash SetupAutostart.sh [--gui|--cli]\n' >&2
    exit 1
fi
if [[ -z "$mode" ]]; then
    if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
        mode=--gui
    else
        mode=--cli
    fi
fi
case "$mode" in
    --gui)
        source "$SCRIPT_DIR/InstallerDialogs.sh"
        titans_gui_init
        titans_gui_run "Titans autostart setup" bash "$SCRIPT_DIR/SetupAutostart.sh" --cli
        exit $?
        ;;
    --cli) ;;
    *)
        printf 'Usage: bash SetupAutostart.sh [--gui|--cli]\n' >&2
        exit 1
        ;;
esac

if (( EUID == 0 )); then
    printf 'Run this script as the desktop user, not root.\n' >&2
    exit 1
fi
if [[ ! -x "$SCRIPT_DIR/.venv/bin/python" ]] || [[ ! -f "$SCRIPT_DIR/launcher.py" ]]; then
    printf 'Install Titans with ArchModuleInstall.sh before configuring startup.\n' >&2
    exit 1
fi
if [[ "$SCRIPT_DIR" == *[$'\\\n\r\t"$`%']* ]]; then
    printf 'The launcher path contains characters unsupported by this setup script.\n' >&2
    exit 1
fi
for command in sudo visudo pacman; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "$command" >&2
        exit 1
    fi
done
if [[ ! -x /usr/bin/pacman ]]; then
    printf 'Expected pacman at /usr/bin/pacman.\n' >&2
    exit 1
fi
username="$(id -un)"
if [[ ! "$username" =~ ^[a-z_][a-z0-9_-]*\$?$ ]]; then
    printf 'Unsupported username for sudoers: %s\n' "$username" >&2
    exit 1
fi
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
if [[ "$config_home" != /* ]]; then
    printf 'XDG_CONFIG_HOME must be an absolute path.\n' >&2
    exit 1
fi

printf '%s\n' \
    'WARNING: This grants your entire account passwordless root access through pacman.' \
    'Other apps can use it too, and pacman can be used to obtain full root access.' \
    'Only continue if you trust every program running as this user.'
if [[ "${TITANS_SETUP_GUI:-}" == 1 ]]; then
    if ! zenity --question --title="Security warning: passwordless root access" \
        --text="Autostart setup grants EVERY app running as your user passwordless pacman access, not just Titans. Pacman can be used to obtain FULL ROOT ACCESS.\n\nOther sudo commands keep their existing policy, but this does not protect the system from untrusted apps using pacman.\n\nOnly enable this if you trust every program running as your user." \
        --ok-label="Accept risk and enable" --cancel-label="Cancel" \
        --default-cancel --width=650; then
        printf 'Autostart setup cancelled or the security dialog could not be displayed. No changes were made by autostart setup.\n' >&2
        exit 1
    fi
else
    read -r -p 'Type YES to continue: ' confirmation
    if [[ "$confirmation" != YES ]]; then
        printf 'Setup cancelled.\n' >&2
        exit 1
    fi
fi

rule="$(mktemp)"
trap 'rm -f -- "$rule"' EXIT
printf '%s ALL=(root) NOPASSWD: /usr/bin/pacman, /usr/bin/env LC_ALL=C /usr/bin/pacman -Qkk --color never\n' "$username" > "$rule"
sudo -A visudo -c -f "$rule"
sudo -A install -o root -g root -m 0440 -- "$rule" "/etc/sudoers.d/titans-pacman-$username"

mkdir -p -- "$config_home/autostart"
desktop="$config_home/autostart/titans-launcher.desktop"
printf '[Desktop Entry]\nType=Application\nName=Titans Launcher\nExec="%s/.venv/bin/python" "%s/launcher.py"\nTerminal=false\n' \
    "$SCRIPT_DIR" "$SCRIPT_DIR" > "$desktop"
printf 'Desktop autostart installed at %s\n' "$desktop"
printf 'Passwordless pacman configured for %s.\n' "$username"
