#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    exec zenity --password --title="Titans administrator authentication" --text="${1:-Enter your password:}"
fi

titans_gui_init() {
    if ! command -v zenity >/dev/null 2>&1; then
        printf 'The GUI requires Zenity. Install it with: sudo -A pacman -S --needed zenity\n' >&2
        return 1
    fi
    if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
        printf 'The GUI requires an active desktop session. Use a command-line option instead.\n' >&2
        return 1
    fi
    SUDO_ASKPASS="$(mktemp)"
    export SUDO_ASKPASS
    trap 'rm -f -- "$SUDO_ASKPASS"' EXIT
    printf '#!/usr/bin/env bash\nexec bash %q "$@"\n' "$SCRIPT_DIR/InstallerDialogs.sh" > "$SUDO_ASKPASS"
    chmod 700 "$SUDO_ASKPASS"
    export TITANS_SETUP_GUI=1
}

titans_gui_run() {
    local title="$1"
    shift
    local log
    log="$(mktemp)"
    local -a statuses
    if "$@" 2>&1 | tee "$log" | sed -u 's/^/# /' |
        zenity --progress --pulsate --auto-close --no-cancel \
            --title="$title" --text="Please wait. Do not close this window or power off the device."; then
        statuses=("${PIPESTATUS[@]}")
    else
        statuses=("${PIPESTATUS[@]}")
    fi
    if [[ "${statuses[*]}" != "0 0 0 0" ]]; then
        printf '%s failed. Output:\n' "$title" >&2
        cat "$log" >&2
        if zenity --text-info --title="$title failed" --filename="$log" --width=700 --height=450; then
            :
        else
            printf 'The failure details dialog was closed or could not be displayed.\n' >&2
        fi
        rm -f -- "$log"
        return 1
    fi
    rm -f -- "$log"
    zenity --info --title="$title complete" --text="Setup completed successfully."
}
