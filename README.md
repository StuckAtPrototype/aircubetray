# AirCube Tray

A lightweight cross-platform system-tray app that shows live **VOC Level** from an [AirCube](https://github.com/stuckatprototype/aircube) sensor directly in your taskbar / menu bar / panel.

- Color-coded VOC Level number as the tray icon (updates live).
- Tooltip with temperature, humidity, eCO₂, eTVOC.
- Right-click popup with history charts (VOC Level, temperature, humidity, eCO₂, eTVOC).
- Configurable VOC Level threshold alerts.
- Auto-detects the AirCube over USB (VID `0x303A` / PID `0x1001`) with silent auto-connect and hotplug watching.
- Optional "start at login" toggle (Windows today; macOS / Linux planned — see [Limitations](#limitations)).

> AirCube Tray is an official companion app for the **AirCube** hardware but it lives in its own repo so it can ship and version independently. Firmware and the main GUI app live in the [AirCube repo](https://github.com/stuckatprototype/aircube).

---

## Quick start

### Install (Windows)

Download the latest installer from [`releases/`](./releases/) and run it:

```
AirCubeTray_Setup_v1.3.0.exe
```

The installer will:

- Install to `Program Files\AirCubeTray` (or per-user `%LocalAppData%` if you pick that option).
- Add a Start Menu shortcut and (optionally) a desktop icon.
- Optionally launch AirCube Tray at Windows startup.
- Clean up registry + shortcuts on uninstall.

Plug in your AirCube and the tray app will auto-connect.

### Install (macOS)

Download `AirCubeTray-<version>-macos.dmg` from [`releases/`](./releases/), open it, and drag **AirCubeTray** into your Applications folder.

The app shows up as a menu-bar icon (no Dock entry — it's an `LSUIElement`). On first launch you may need to right-click → **Open** to bypass Gatekeeper, since the build is not codesigned/notarized.

To grant USB serial access, ensure the AirCube enumerates as `/dev/cu.usbmodem*`. macOS doesn't require a driver for the ESP32-H2's built-in USB serial.

### Install (Linux, AppImage)

Download `AirCubeTray-<version>-x86_64.AppImage` (or `aarch64`) from [`releases/`](./releases/), then:

```bash
chmod +x AirCubeTray-1.3.0-x86_64.AppImage
./AirCubeTray-1.3.0-x86_64.AppImage
```

Notes:

- Add yourself to the `dialout` group so non-root processes can open the serial port: `sudo usermod -aG dialout $USER` (re-login required).
- On modern GNOME you'll need an extension that exposes a system tray (e.g. **AppIndicator and KStatusNotifierItem Support**), or run KDE / XFCE / Cinnamon / MATE / Budgie etc., where tray support is built in.
- For the app to appear in your launcher, copy `AirCubeTray.desktop` from the AppImage (right-click → Show Contents) into `~/.local/share/applications/`, or use the `appimaged` daemon.

### Run from source (any platform)

Prereqs: Python 3.10+ and an AirCube connected over USB.

```bash
pip install -r requirements.txt
python aircube_tray.py
```

---

## Building

PyInstaller can only build for the OS you run it on, so each target needs to be built natively.

### Windows: `.exe` + installer

Prereqs: [Inno Setup 6](https://jrsoftware.org/isdl.php) installed at its default path.

```bash
pip install pyinstaller
python build_installer.py     # builds AirCubeTray.exe AND the installer
# or, just the executable:
python build_tray.py
```

Outputs:

- `dist/AirCubeTray.exe` — single-file executable (~60 MB).
- `installer_output/AirCubeTray_Setup_vX.Y.Z.exe` — Inno Setup installer.

### macOS: `.app` + `.dmg`

Prereqs: macOS, Python 3.10+, `pip install pyinstaller`. (`hdiutil` ships with macOS.)

```bash
python build_dmg.py           # builds AirCubeTray.app AND the .dmg
# or, just the bundle:
python build_tray.py
```

Outputs:

- `dist/AirCubeTray.app` — menu-bar app bundle (`LSUIElement = true`).
- `releases/v<version>/AirCubeTray-<version>-macos.dmg` — drag-to-Applications DMG.

The build is **not** codesigned or notarized. To distribute outside your machine you'll want to add `codesign` + `xcrun notarytool` steps; AirCubeTray.spec already exposes `codesign_identity` and `entitlements_file` slots.

### Linux: AppImage

Prereqs: Linux x86_64 or aarch64, Python 3.10+, `pip install pyinstaller`. `appimagetool` will be auto-downloaded if not on `PATH`.

```bash
python build_appimage.py      # builds binary AND the .AppImage
# or, just the binary:
python build_tray.py
```

Outputs:

- `dist/AirCubeTray` — single-file binary.
- `releases/v<version>/AirCubeTray-<version>-x86_64.AppImage` — portable AppImage.

System libs needed at runtime on the user's machine: `libxcb`, `libfontconfig`, `libxkbcommon` and friends — present on essentially every desktop distro.

### Regenerating the app icons

Icons are generated from code so they're reproducible across all three platforms:

```bash
pip install Pillow>=10.0
python generate_tray_icon.py
```

Produces:

- `aircube_tray.ico` — Windows multi-resolution.
- `aircube_tray.icns` — macOS multi-resolution (used in the `.app` bundle).
- `aircube_tray.png` — 1024×1024 master PNG (used by the AppImage / `.desktop`).

---

## Files

| File | What it is |
|------|-----------|
| `aircube_tray.py` | The app (PyQt6, tray icon, popup charts, serial I/O) |
| `aircube_tray.ico` / `.icns` / `.png` | Per-platform app icons (output of `generate_tray_icon.py`) |
| `generate_tray_icon.py` | Pillow-based icon generator (writes all three formats) |
| `AirCubeTray.spec` | Platform-aware PyInstaller spec (Windows EXE / macOS BUNDLE / Linux ELF) |
| `build_tray.py` | Cross-platform: builds the right artifact for the host OS |
| `build_installer.py` | Windows-only: `.exe` + Inno Setup installer |
| `build_dmg.py` | macOS-only: `.app` + drag-to-Applications `.dmg` |
| `build_appimage.py` | Linux-only: binary + portable `.AppImage` |
| `installer.iss` | Inno Setup script (install/uninstall, shortcuts, Run key cleanup) |
| `requirements.txt` | Runtime deps (PyQt6, pyserial, matplotlib) + optional Pillow for icon gen |
| `releases/` | Versioned release artifacts (gitignored except for what you choose to commit) |

---

## How auto-detect works

- **VID/PID match** — The AirCube is an ESP32-H2 with USB-C wired directly to the chip, so it enumerates as the built-in USB Serial/JTAG: VID `0x303A`, PID `0x1001`. Detection uses `pyserial`'s `list_ports`, which works on Windows, macOS, and Linux.
- **Description fallback** — If a weird driver is installed, the app also looks for `"USB JTAG/serial debug unit"` or `"Espressif"` in the port description.
- **Startup** — Uses the last saved port if it's still plugged in; otherwise auto-detects silently.
- **Hotplug** — A `QTimer` polls every 2 seconds and connects the moment an AirCube is plugged in.
- **Settings dialog** — AirCube ports are starred (`★`) and sorted to the top so they're obvious if you need to pick manually.

---

## Limitations

- **Start at login** is currently Windows-only. The macOS path (LaunchAgent plist in `~/Library/LaunchAgents/`) and the Linux path (`.desktop` file in `~/.config/autostart/`) are tracked as a follow-up; the toggle in Settings is a no-op on those platforms today.
- **Code signing / notarization** is not performed for any platform. macOS users will see a Gatekeeper warning on first launch; right-click → Open to bypass. Windows builds are unsigned and will trigger SmartScreen.
- **GNOME tray support** requires the AppIndicator extension on modern GNOME (3.26+).

---

## License

See [LICENSE](./LICENSE).
