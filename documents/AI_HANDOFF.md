# Titans Launcher: implementation handoff

Status at 2026-11-28. This is a work-in-progress handoff, not a release note.
The working tree contains many pre-existing staged and unstaged changes; inspect
it before editing and do not reset or overwrite unrelated work.

## Agreed behavior

- `VERSION` is the authoritative installed launcher version. Home and update
  settings should refresh when it changes, including atomic replacements.
- Home pages are automatic slices within each profile. Paging is on by default,
  is configurable in Settings, and left/right tile edges wrap pages. Controller
  bumpers continue to switch tabs.
- The screensaver runs only while Titans is visible and active. It rotates
  local images or videos, and is configured inside Settings.
- Phone Wi-Fi setup uses a temporary hotspot and two steps: join the hotspot,
  then open the local setup page and enter the target network credentials. A
  browser cannot silently retrieve saved passwords from the phone.
- Users are standard Linux accounts, created with a password and administrator
  authorization. OS updates retain administrator authorization. Do not silently
  weaken sudo or polkit rules; the existing optional passwordless pacman setup
  already carries account-wide root-equivalent risk.
- Cast means a real external Cast-enabled receiver, chosen in Settings; do not
  impersonate a Chromecast or extract device credentials.

## Implemented

- Version synchronization: `Application/core/github_update.py`; Home/profile
  paging: `Application/core/home_profiles.py`,
  `Application/ui/Settings/HomeProfilesWidget.py`, and
  `Application/ui/controller_navigation.py`.
- Screensaver: `Application/ui/widgets/screensaver.py` and
  `Application/ui/Settings/ScreensaverSettings.py`.
- Home shows the current Linux user name; the existing Wi-Fi indicator shows
  the connected SSID. Existing Users settings support session switching.
- Standard account creation: `Application/core/user_manager.py` and
  `Application/ui/Settings/UserNotificationStorageSettings.py`. AccountsService
  authorizes creation and password setting separately. OpenSSL receives the
  password on stdin and sends the resulting SHA-512 crypt hash over D-Bus;
  neither is passed in process arguments. If password setup fails or times out
  after creation, the UI instructs the user to check system account settings;
  it does not delete the account automatically. No real account was created in
  this shared environment: verify authorization, hashing, login, and partial
  failure recovery on a disposable Arch installation before release.
- Cast receiver discovery and status:
  `Application/core/cast_devices.py`,
  `Application/ui/Settings/CastSettings.py`, and `Application/launcher.py`.
  The selected receiver's name and status appear beside the controller battery.
  This does **not** make Titans a receiver or send media to the device.
  The Python dependency is included in `ArchModuleInstall.sh`. Discovery ran
  successfully here but found no receiver; test a real receiver, disconnects,
  changing selections during scans, and mDNS/firewall behavior.

## Phone-assisted Wi-Fi setup

Implemented in `Application/core/phone_wifi.py` and
`Application/ui/Settings/PhoneWifiSetup.py`, exposed from `WifiSettings.py`.
It creates a random WPA2 hotspot via NetworkManager's volatile connection
bound to the D-Bus client; a timed checkpoint restores the adapter on failure,
cancel, timeout, or process death. It serves a one-use, origin-checked setup
page only on the hotspot address and subnet. A second checkpoint restores the
previous network if the subsequent `nmcli --ask` connection fails. Secrets are
sent through D-Bus or stdin, not command arguments or logs.

The local page is HTTP, not TLS; anyone with hotspot and page access may be
able to observe credentials. The consent dialog explains this and that
NetworkManager may share other internet connections with hotspot clients.
Only open and WPA personal networks are supported. The installer declares
`dnsmasq`, `dbus-next` and `qrcode`.

**Still required before release:** test on a disposable Arch installation with
NetworkManager, an AP-capable Wi-Fi adapter and a real phone. Verify D-Bus
authorization, hotspot activation and expiry, password prompting via
`nmcli --ask` on stdin, each QR on actual phones, successful target connection,
failed-password restoration, cancel and launcher termination. This shared
environment has no `nmcli` or Wi-Fi hardware, so these integration paths were
not exercised; mocks and local HTTP tests do not prove hardware compatibility.

## Verification and release

Focused tests run successfully for Cast, account behavior, installer, controller
regressions, Home paging, version watching, and screensaver. For example:

```sh
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_cast_devices.py' -q
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_system_behaviors.py' -q
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_screensaver.py' -q
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_arch_module_install.py' -q
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_phone_wifi.py' -q
```

`launcher-files.sha256.json` tracks distributed files; update hashes for the
files actually changed and include any new runtime modules. Avoid blindly
regenerating unrelated hashes in the dirty tree. `Titans_Launcher.zip` is a
static snapshot: rebuild it after changes; editing `VERSION` cannot update an
already-built archive.
