# Titans Launcher

**Current version:** see [`VERSION`](../VERSION).

Titans Launcher is a console-style Linux launcher built with PyQt6. Its main
window is borderless and maximized rather than using true fullscreen mode.
It gives games, desktop apps, streaming services, and website shortcuts
a shared home screen that is comfortable to use from a couch with a gamepad.

It is still alpha software. The automated setup and package-management features
target **Arch Linux with pacman**. Other Linux distributions need manual setup,
and Windows and macOS are not supported.

## What Titans can do

- Launch desktop programs and website shortcuts from a customizable Home screen.
- Organize Home shortcuts into profiles and change their order or visibility.
- Automatically split Home shortcuts into pages. Configure the page size,
  animation and duration under **Settings > Home Screen**; disable paging there
  to keep all shortcuts on one screen. Moving past the first or last tile
  switches pages and wraps around.
- Track launched applications from the **Running Apps** view.
- Navigate the launcher with an SDL-compatible controller.
- Control Firefox website shortcuts with a built-in controller bridge.
- Open an on-screen keyboard for use inside and outside Titans.
- Show weather, Wi-Fi status, and a selected Bluetooth controller or device
  battery on the Home screen.
- Show the installed launcher version below the Home screen date and time.
- Show the signed-in Linux account name at the top of the Home screen.
- Configure an optional idle screensaver under **Settings > General > Screensaver**.
  Add local images, GIFs or videos and choose the idle and rotation intervals.
  Keyboard, mouse or controller input dismisses it; it runs only while Titans is active.
- Under **Settings > General > Cast**, select an external Cast-enabled receiver.
  Its name and receiver status appear next to the controller battery. Titans
  does not itself act as a Chromecast or stream media to the receiver.
- **Advanced Settings > Users** can create a standard Linux user through
  AccountsService. Administrator authorization and a password are required.
  If password setup fails after creation, use system account settings to finish
  or remove the account.
- **Settings > Network > Wi-Fi > Set Up with Phone** starts a temporary WPA2
  hotspot after confirmation. Scan the first QR to join it, then scan the
  second to open the setup page and enter the target Wi-Fi details. Setup
  expires after five minutes and may interrupt the selected adapter's current
  connection. The page uses HTTP over the hotspot: only share its hotspot and
  page codes with trusted people. Other internet connections may be shared with
  hotspot clients. NetworkManager, `dnsmasq`, and a WPA2 access-point-capable
  Wi-Fi adapter are required.
- Open a Control Centre for quick Wi-Fi, Bluetooth, volume, and brightness
  controls.
- Manage Wi-Fi, Bluetooth, sound, displays, VPN connections, and proxy settings.
- Use basic or advanced settings, including themes, backgrounds, button styles,
  startup screens, navigation sounds, display profiles, accessibility options,
  notifications, users and sessions, storage, and logging.
- Show CPU, memory, network, and available temperature information in Task
  Manager.
- Check for system and launcher updates, verify launcher files, and inspect
  package integrity.

The optional **Applications** module uses pacman to search for, install, and
remove applications from the Arch repositories. It is disabled by default.

## Requirements

The supported automated installation is for:

- Arch Linux with `pacman`
- A normal desktop user with sudo access
- An active graphical desktop session
- Network access
- Enough disk space for system packages and a local Python environment

The installer does not install a desktop environment or display manager, and it
does not enable NetworkManager, Bluetooth, or display-manager services.

Controller input, brightness, audio, networking, global shortcuts, and window
switching depend on the user's hardware, desktop session, available services,
and device permissions. Some features may show as unavailable when the required
tool or service is not present.

## Install on Arch Linux

### Recommended: graphical setup

Clone the project into a folder owned by your desktop user:

```sh
git clone https://github.com/kenshin210/Titans_Launcher.git
cd Titans_Launcher
```

The setup interface needs Zenity. Install it if it is not already available:

```sh
sudo pacman -S --needed zenity
```

Run the installer:

```sh
bash ArchModuleInstall.sh --gui
```

For a normal first install, choose **Launcher dependencies only**. That installs
the system tools and Python packages without adding desktop autostart or
passwordless pacman access.

The installer also:

- Creates `.venv` in the project folder.
- Verifies the launcher's Python modules can be imported after installation.
- Installs Firefox, AntiMicroX, NetworkManager tools, audio/display helpers, and
  other runtime dependencies.
- Loads the Linux `uinput` module.
- Gives the active local desktop user controlled access to `uinput` and keyboard
  event devices so the launcher can provide controller-based and virtual input.

Restart Titans after installation. You may need to sign out and back in before
new input-device permissions take effect.

Do not run Titans itself as root.

### Command-line setup

```sh
bash ArchModuleInstall.sh --launcher
```

This installs launcher dependencies only. The default mode also does the same
thing when no graphical session is detected.

After installation, start Titans with:

```sh
.venv/bin/python launcher.py
```

If the kernel was updated while `uinput` was unavailable, reboot into the new
kernel and rerun the installer.

### Manual setup on other Linux distributions

There is no supported installer for Debian, Ubuntu, Fedora, or another
distribution. A manual installation needs these Python packages in an isolated
environment:

```text
PyQt6
opencv-python
pygame-ce
psutil
evdev
PyChromecast
dbus-next
qrcode
```

Equivalent system packages from
[`ArchModuleInstall.sh`](../ArchModuleInstall.sh) must be installed and
configured separately. Pacman-based app installation, removal, system updates,
and package repair are Arch-specific and will not work without a suitable Arch
setup.

## Optional autostart

If Titans should start when the desktop user signs in, run:

```sh
bash SetupAutostart.sh --gui
```

This creates an XDG autostart entry for the current checkout. It does not enable
automatic login. Move the checkout? Rerun the script so the entry points to the
new location.

### Important security warning

Autostart setup also offers to install a sudoers rule that allows the user's
entire account to run pacman as root without a password. That permission applies
to **every process running as that user**, not only Titans. Pacman can be used to
obtain unrestricted root access, so only enable this if every application using
the account is trusted.

Using **Launcher dependencies only** avoids granting this permission.

To remove the setup:

1. Delete `~/.config/autostart/titans-launcher.desktop`.
2. Remove `/etc/sudoers.d/titans-pacman-USERNAME` with administrator access.
3. Replace `USERNAME` with the affected login name.

## Everyday controls

The controller bindings can be changed under **Settings > Controller**. The
default Xbox-style layout uses:

| Input | Action |
| --- | --- |
| D-pad or left stick | Move between controls |
| A | Select |
| B | Back or cancel |
| LB / RB | Previous / next tab |

The Home screen, settings menus, dialogs, task manager, app views, and Control
Centre are designed around that navigation.

### Firefox shortcuts

To add uBlock Origin on Arch Linux, open **Settings > General > Browser** and
select **Install uBlock Origin**. After confirmation and administrator
authentication, Titans installs the `firefox-ublock-origin` package for the
system Firefox installation, including use outside Titans. Restart Firefox and
approve or enable the add-on if prompted. The package can be removed with
pacman; Firefox policies or other Firefox installations may affect availability.
No extension is installed automatically at launcher startup.

For Firefox website shortcuts using Titans' built-in controller bridge:

| Input | Action |
| --- | --- |
| D-pad / left stick | Navigate the page |
| A | Select the focused item |
| B | Browser Back |
| Left / right shoulders | Change focus direction |
| Right stick | Move the pointer |
| Right trigger | Hold left click |
| Left trigger | Hold right click |

This mode requires an SDL-recognized controller, `pygame-ce`, `evdev`, and
`uinput` access. A configured AntiMicroX profile is used for non-Firefox
shortcuts. Stop an independently running AntiMicroX instance when using the
built-in Firefox bridge to avoid conflicting input.

Holding the controller Back button for 1.2 seconds can close an active
application and return to Titans when that option is enabled for the shortcut.

### On-screen keyboard

- Press the controller Guide/Xbox button and B (or X) to open or close the
  keyboard.
- Press **Ctrl+Alt+K** for the keyboard shortcut while Titans is running.
- D-pad or left stick moves between keys.
- A selects, X or LB deletes, and RB inserts a space.
- B cancels or closes the keyboard.

External typing requires `evdev`, access to keyboard event devices, and write
access to `uinput`. The installer configures these permissions for a local
desktop session. A US keyboard layout is expected.

### Control Centre

The default **Ctrl+Shift+Space** shortcut opens the Control Centre, including
while another application is active. Its shortcut can be changed in Settings.
When input-device access is unavailable, it remains usable from the Titans
window but cannot be captured globally.

The Control Centre exposes only controls detected on the current system. Wi-Fi,
Bluetooth, volume, and brightness can appear as unavailable if the required
backend is missing.

## Applications and Home profiles

In **Settings > Applications**, switch to the Advanced Menu to edit a shortcut.
For a **Website**, the **Display mode** dropdown saves a choice for that site:

- **Normal window**: launch without kiosk or maximized startup flags.
- **Maximized window**: use Firefox's maximized startup option.
- **Fullscreen (KDE Wayland)**: ask KWin to fullscreen the launched Firefox
  window without enabling kiosk restrictions.
- **Kiosk**: use Firefox's kiosk mode.

Existing website shortcuts keep kiosk mode unless changed. Maximized and
Fullscreen modes require Firefox; automatic Fullscreen also requires a KDE
Wayland session with working KWin scripting and `qdbus`. If the fullscreen
request fails, Titans reports the error instead of treating it as successful.
Changing a website's mode takes effect the next time it is launched. These
choices do not change Titans' own borderless maximized window or guarantee that
an external keyboard overlay will retain focus.

Titans keeps a single lifecycle manager for Home shortcuts and the Running Apps
view. A command is split into an executable and arguments, not passed through a
shell. Shell operators, substitutions, and pipelines are therefore not
interpreted.

The manager tracks the child process Titans started. It does not track detached
processes or apps that hand their work to an existing process. Successful exits
are shown as stopped; unexpected non-zero exits and signals are shown as crashes.
Titans does not automatically restart crashed apps.

Application shortcuts, running state, and crash information are stored under
`~/.local/share/titans/`.

## Appearance, accessibility, and profiles

Settings lets you change the:

- Background video and startup screen.
- Theme, accent color, corner style, and button treatment.
- Navigation sound and volume.
- Animation and motion-reduction preferences.
- Text size, high contrast, and focus indicators.
- Keyboard colors, background image, and opacity.
- Home shortcut profiles.
- Display profiles and audio preferences.

Startup images can be local images or GIFs. Changes to the startup screen take
effect the next time Titans starts. With animations disabled or Reduce Motion
enabled, animated images remain on their first frame.

Weather requires a city and country to be configured under
**Settings > General > Weather**.

## System and launcher updates

Open **Settings > About Device > System Update** to manage both Arch system
updates and launcher updates.

System updates remain active while Titans is open, even if you navigate away or
launch another application. The launcher stays locked open until the operation
finishes. Check the update status before powering off the device, and back up
important files before major package work.

Launcher updates:

- Check the public **Stable** or **Beta** branch.
- Support a trusted public **Custom** repository and branch.
- Run an initial background check after startup and then every six hours.
- Require confirmation before downloading or installing an update.
- Refuse dirty Git checkouts rather than overwriting local changes.
- Ask for a restart when changed code requires it.

Installing a custom launcher version runs code from that source as your user, so
only use repositories and branches you trust. Private repositories are not
supported.

The installed version is read from the root
[`VERSION`](../VERSION) file. For a release, change that file and regenerate the
file manifest:

```sh
.venv/bin/python generate_launcher_manifest.py
```

## File checks and package repair

**Settings > About Device > File Check** can:

- Compare launcher files with the bundled SHA-256 manifest.
- Check the bundled Python files for syntax errors.
- Use `pacman -Qkk` to inspect installed packages.

The result depends on installed package metadata and can report expected
configuration changes as differences. Unmanaged files are not checked, and the
bundled manifest is not independently authenticated.

After a package check, **Repair All Packages** can reinstall installed Arch
packages with a full upgrade. This is a significant system operation: it may
download a large amount of data, replace system files, and run package scripts.
Review the report, resolve package configuration prompts, and back up important
data first.

## Where Titans stores data

User settings:

```text
~/.config/Titans-launcher/profiles.json
```

Application state and crash details:

```text
~/.local/share/titans/apps
~/.local/share/titans/logs
```

Settings are written beside the existing file to a temporary file, synced, and
atomically replaced. If writing fails, the error is logged and the previous
settings file is retained.

Titans does not include usage telemetry. Internet-enabled features can still
contact external services for weather, time, and GitHub update metadata. See the
[privacy audit](PRIVACY_AUDIT.md) for the current network and permission
behavior.

## Known platform boundaries

- Window activation uses `wmctrl` for X11/XWayland. KWin Wayland is also
  supported through its scripting interface; other Wayland compositors do not
  provide a generic equivalent.
- Hardware readings depend on what the Linux system exposes.
- Bluetooth battery information depends on Linux or BlueZ reporting it.
- Session switching depends on logind and a supported display-manager greeter.
- Titans does not install services, change global display-manager files, or
  configure a desktop session automatically. Creating a standard user requires
  administrator authorization.
- System power actions are explicit and require confirmation. Titans does not
  change power profiles, suspend automatically, or hibernate automatically.
- There is no achievement system, screenshot library, voice assistant, activity
  feed, or automated recommendation system.
