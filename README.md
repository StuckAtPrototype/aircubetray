# AirCube Tray

A lightweight Windows system-tray app that shows live **AQI** (Air Quality Index) from an [AirCube](https://github.com/stuckatprototype/aircube) sensor directly in your taskbar.

- Color-coded AQI number as the tray icon (updates live).
- Tooltip with temperature, humidity, eCO₂, eTVOC.
- Right-click popup with history charts (AQI, temperature, humidity, eCO₂, eTVOC).
- Configurable AQI threshold alerts.
- Auto-detects the AirCube over USB (VID `0x303A` / PID `0x1001`) with silent auto-connect and hotplug watching.
- Optional "start with Windows" toggle.

> AirCube Tray is an official companion app for the **AirCube** hardware but it lives in its own repo so it can ship and version independently. Firmware and the main GUI app live in the [AirCube repo](https://github.com/stuckatprototype/aircube).

---

## Quick start

### Install (Windows, recommended)

Download the latest installer from [`releases/`](./releases/) and run it:

```
AirCubeTray_Setup_v1.3.0.exe
```

The installer will:

- Install to `Program Files\AirCubeTray` (or per-user `%LocalAppData%` if you pick that option).
- Add a Start Menu shortcut and (optionally) a desktop icon.
- Optionally launch AirCube Tray at Windows startup.
- Clean up registry + shortcuts on uninstall.

Plug in your AirCube and the tray app will auto-connect. No settings required.

### Run from source

Prereqs: Python 3.10+ and an AirCube connected over USB.

```bash
pip install -r requirements.txt
python aircube_tray.py
```

---

## Building

### Just the `.exe`

```bash
pip install pyinstaller
python build_tray.py
```

Produces `dist/AirCubeTray.exe` (~60 MB, single-file).

### The `.exe` + Windows installer

Prereqs: [Inno Setup 6](https://jrsoftware.org/isdl.php) installed at its default path.

```bash
python build_installer.py
```

Produces `installer_output/AirCubeTray_Setup_vX.Y.Z.exe`.

The build script:

1. Kills any running `AirCubeTray.exe` (so PyInstaller can overwrite the locked binary).
2. Runs PyInstaller via `AirCubeTray.spec` (which bundles `aircube_tray.ico` as a runtime resource and sets the `.exe` icon).
3. Invokes Inno Setup on `installer.iss`.

### Regenerating the app icon

The icon is generated from code so it's reproducible:

```bash
pip install Pillow
python generate_tray_icon.py
```

Overwrites `aircube_tray.ico` as a multi-size Windows ICO (16, 24, 32, 48, 64, 128, 256 px).

---

## Files

| File | What it is |
|------|-----------|
| `aircube_tray.py` | The app (PyQt6, tray icon, popup charts, serial I/O) |
| `aircube_tray.ico` | Multi-size app icon (output of `generate_tray_icon.py`) |
| `generate_tray_icon.py` | Pillow-based icon generator |
| `AirCubeTray.spec` | PyInstaller spec (bundles icon, sets exe icon) |
| `build_tray.py` | Builds `dist/AirCubeTray.exe` via PyInstaller |
| `build_installer.py` | One-shot: `.exe` + Inno Setup installer |
| `installer.iss` | Inno Setup script (install/uninstall, shortcuts, Run key cleanup) |
| `requirements.txt` | Runtime deps (PyQt6, pyserial, matplotlib) + optional Pillow for icon gen |
| `releases/` | Versioned release artifacts (gitignored) |

---

## How auto-detect works

- **VID/PID match** — The AirCube is an ESP32-H2 with USB-C wired directly to the chip, so on Windows it enumerates as the built-in USB Serial/JTAG: VID `0x303A`, PID `0x1001`.
- **Description fallback** — If a weird driver is installed, the app also looks for `"USB JTAG/serial debug unit"` or `"Espressif"` in the port description.
- **Startup** — Uses the last saved port if it's still plugged in; otherwise auto-detects silently.
- **Hotplug** — A `QTimer` polls every 2 seconds and connects the moment an AirCube is plugged in.
- **Settings dialog** — AirCube ports are starred (`★`) and sorted to the top so they're obvious if you need to pick manually.

---

## License

See [LICENSE](./LICENSE).
