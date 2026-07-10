# AirCube for Desktop

The desktop companion app for the [AirCube](https://github.com/stuckatprototype/aircube) air quality sensor. Runs as a **system-tray monitor** and a full **windowed app** (styled after the AirCube iOS app), on Windows today with Linux/macOS support in the codebase (Qt + bleak + pyserial are all cross-platform).

## Features

- **Two modes, always in sync** — a tray icon with a color-coded air score badge and quick popup, plus a full window with per-device dashboards. Pick your launch mode in Settings; closing the window minimizes to the tray.
- **iOS-parity UI** — Home device cards, detail view with 270° air gauge and metric tiles, gap-aware history charts with scrubbing (24h / 3d / 7d), multi-device Compare view, dark and light themes.
- **USB + Bluetooth** — cubes plugged in over USB auto-connect (hotplug watched, VID `0x303A` / PID `0x1001`); cubes elsewhere in the house connect over BLE (AirCube GATT service). The same physical cube is recognized on both transports (the USB serial number is the chip MAC) and USB is preferred when available, with automatic BLE fallback on unplug.
- **Multiple cubes** — every connected AirCube gets its own card, history cache (SQLite, keyed by device + sequence), rename/forget, LED brightness control, and CSV export.
- **History sync** — streams the on-device 7-day history (5-minute slots) over either transport, with iOS-style timestamp anchoring and zero/gap cleaning.
- **Alerts** — CO₂ (Pro) and VOC threshold notifications with dwell, cooldown, hysteresis, quiet hours, per-device mute, offline alerts. Same defaults as the iOS app (off by default, CO₂ 1200 ppm, VOC 660 ppb).
- **Firmware flashing** — flash any connected cube over USB straight from the app: pick a release (fetched automatically from [AirCube GitHub Releases](https://github.com/StuckAtPrototype/AirCube/releases)) or a custom `.bin`, watch esptool progress live, auto-reconnect after reboot.

## Quick start

### Install (Windows, recommended)

Build or download the installer and run it:

```
AirCubeTray_Setup_v2.0.0.exe
```

The installer installs to `Program Files\AirCubeTray` (or per-user), adds Start Menu / optional desktop shortcuts, optionally launches at Windows startup, and cleans up on uninstall.

Plug in your AirCube and it connects automatically. To add a cube over Bluetooth, open the app and tap **+**.

### Run from source

Prereqs: Python 3.10+.

```bash
pip install -r requirements.txt
python aircube_tray.py
```

## Building

### Just the `.exe`

```bash
pip install pyinstaller
python build_tray.py
```

Produces `dist/AirCubeTray.exe` (single-file).

### The `.exe` + Windows installer

Prereqs: [Inno Setup 6](https://jrsoftware.org/isdl.php).

```bash
python build_installer.py
```

Produces `installer_output/AirCubeTray_Setup_vX.Y.Z.exe`.

### Regenerating the app icon

```bash
pip install Pillow
python generate_tray_icon.py
```

Overwrites `aircube_tray.ico` as a multi-size Windows ICO.

## Code layout

| Path | What it is |
|------|-----------|
| `aircube_tray.py` | Entry point |
| `aircubeapp/models.py` | Live/history models, quality bands, 0-100 air score (iOS `Theme.swift` logic) |
| `aircubeapp/theme.py` | Light/dark palette + stylesheet (iOS `Theme.swift` colors) |
| `aircubeapp/protocol.py` | BLE GATT binary + USB serial JSON parsers |
| `aircubeapp/store.py` | SQLite history/device cache, preferences |
| `aircubeapp/manager.py` | Multi-device registry, hotplug, sync queue, transport preference |
| `aircubeapp/transports/` | `serial_transport.py` (COM ports), `ble_transport.py` (bleak) |
| `aircubeapp/alerts.py` | Alert engine (dwell/cooldown/quiet hours) |
| `aircubeapp/flash/` | GitHub release fetch + esptool flash worker |
| `aircubeapp/ui/` | Widgets, charts, Home/Detail/Compare/Settings pages, tray, dialogs |
| `AirCubeTray.spec`, `build_tray.py`, `build_installer.py`, `installer.iss` | Packaging |

## Protocol notes

- **Serial**: JSON lines at 115200 baud over the ESP32-H2 USB Serial/JTAG; history via `get_history_info` / paged `get_history`; LED via `set_intensity`.
- **BLE**: AirCube GATT service `A17C0DE0-1D0F-4E7C-8E4B-2A3D5F6B7C80` — device info (14 B), live data notify (20 B), history request/stream, brightness characteristic. See the [protocol spec](https://github.com/StuckAtPrototype/AirCube/blob/main/docs/BLE_GATT_PROTOCOL.md).
- **Flashing**: esptool, chip `esp32h2`, 460800 baud; release images flash at `0x0`, app-only dev builds at `0x10000`.

## License

See [LICENSE](./LICENSE).
