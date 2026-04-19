# -*- mode: python ; coding: utf-8 -*-
"""
Platform-aware PyInstaller spec for AirCubeTray.

  Windows : single-file AirCubeTray.exe with embedded .ico
  macOS   : AirCubeTray.app menu-bar bundle (LSUIElement) with .icns
  Linux   : single-file AirCubeTray binary; .png ships next to the binary
            (used by the AppImage / .desktop file)
"""
import os
import re
import sys

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

APP_NAME = "AirCubeTray"
ENTRY = "aircube_tray.py"


def _read_version() -> str:
    here = os.path.dirname(os.path.abspath(SPEC))
    with open(os.path.join(here, ENTRY), "r", encoding="utf-8") as fh:
        match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', fh.read(), re.MULTILINE)
    return match.group(1) if match else "0.0.0"


VERSION = _read_version()

if IS_WIN:
    icon_file = "aircube_tray.ico"
elif IS_MAC:
    icon_file = "aircube_tray.icns"
else:
    icon_file = "aircube_tray.png"

# Bundle every icon flavor we have so the running app can find one regardless
# of the host OS layout (helps when running the source script on a non-native
# platform, and lets the .app fall back to the .ico if Qt prefers it).
extra_icons = []
for candidate in ("aircube_tray.ico", "aircube_tray.icns", "aircube_tray.png"):
    if os.path.exists(candidate):
        extra_icons.append((candidate, "."))

a = Analysis(
    [ENTRY],
    pathex=[],
    binaries=[],
    datas=extra_icons,
    hiddenimports=[
        "PyQt6.QtWidgets",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "matplotlib.backends.backend_qtagg",
        "serial.tools.list_ports",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

if IS_MAC:
    # Wrap the executable in a proper .app bundle. LSUIElement hides the dock
    # icon so the app behaves as a menu-bar-only utility, matching its tray
    # behavior on Windows / Linux.
    app = BUNDLE(
        exe,
        name=f"{APP_NAME}.app",
        icon=icon_file,
        bundle_identifier="com.stuckatprototype.aircubetray",
        version=VERSION,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": "AirCube Tray",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "© stuckatprototype",
        },
    )
