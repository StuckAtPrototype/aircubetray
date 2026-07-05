"""
Package AirCubeTray as a portable AppImage for Linux.

Run on Linux only. Produces a single self-contained file users can chmod +x
and run on essentially any glibc-based distro.

Steps:
    1. Build dist/AirCubeTray with build_tray.py (if needed).
    2. Assemble an AppDir:
         AppDir/
           AppRun                          (launcher script)
           AirCubeTray.desktop             (.desktop entry)
           aircube_tray.png                (top-level icon, AppImage convention)
           usr/bin/AirCubeTray             (the binary)
           usr/share/applications/AirCubeTray.desktop
           usr/share/icons/hicolor/256x256/apps/aircube_tray.png
    3. Run appimagetool against the AppDir.

If appimagetool is not on PATH, this script downloads the official static
build (x86_64) into ./build/ and uses it from there.

Output: releases/v<version>/AirCubeTray-<version>-x86_64.AppImage

Usage:
    python build_appimage.py
"""
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BIN_PATH = SCRIPT_DIR / "dist" / "AirCubeTray"
ICON_PATH = SCRIPT_DIR / "aircube_tray.png"
ENTRY = SCRIPT_DIR / "aircube_tray.py"
RELEASES_DIR = SCRIPT_DIR / "releases"
BUILD_DIR = SCRIPT_DIR / "build"

APPIMAGETOOL_URL_X86_64 = (
    "https://github.com/AppImage/AppImageKit/releases/"
    "download/continuous/appimagetool-x86_64.AppImage"
)
APPIMAGETOOL_URL_AARCH64 = (
    "https://github.com/AppImage/AppImageKit/releases/"
    "download/continuous/appimagetool-aarch64.AppImage"
)


def read_version() -> str:
    text = ENTRY.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        print(f"ERROR: could not find __version__ in {ENTRY.name}")
        sys.exit(1)
    return match.group(1)


def ensure_binary() -> None:
    if BIN_PATH.exists():
        return
    print(f"{BIN_PATH} not found; running build_tray.py first...")
    result = subprocess.run([sys.executable, str(SCRIPT_DIR / "build_tray.py")])
    if result.returncode != 0 or not BIN_PATH.exists():
        print("ERROR: building the Linux binary failed.")
        sys.exit(1)


def detect_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    print(f"ERROR: unsupported architecture {machine!r} for AppImage packaging.")
    sys.exit(1)


def get_appimagetool(arch: str) -> Path:
    on_path = shutil.which("appimagetool")
    if on_path:
        return Path(on_path)

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    cached = BUILD_DIR / f"appimagetool-{arch}.AppImage"
    if cached.exists():
        return cached

    url = APPIMAGETOOL_URL_X86_64 if arch == "x86_64" else APPIMAGETOOL_URL_AARCH64
    print(f"Downloading appimagetool from {url}")
    urllib.request.urlretrieve(url, cached)
    cached.chmod(cached.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return cached


def write_desktop_file(target: Path) -> None:
    target.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=AirCube Tray\n"
        "GenericName=VOC Level Monitor\n"
        "Comment=Lightweight tray app showing VOC Level from an AirCube sensor\n"
        "Exec=AirCubeTray\n"
        "Icon=aircube_tray\n"
        "Categories=Utility;Monitor;\n"
        "Terminal=false\n"
        "StartupNotify=false\n"
        "X-GNOME-UsesNotifications=true\n",
        encoding="utf-8",
    )


def build_appdir() -> Path:
    appdir = BUILD_DIR / "AirCubeTray.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)

    bin_dir = appdir / "usr" / "bin"
    apps_dir = appdir / "usr" / "share" / "applications"
    icon_dir = appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    bin_dir.mkdir(parents=True)
    apps_dir.mkdir(parents=True)
    icon_dir.mkdir(parents=True)

    shutil.copy2(BIN_PATH, bin_dir / "AirCubeTray")
    (bin_dir / "AirCubeTray").chmod(0o755)

    if not ICON_PATH.exists():
        print(f"ERROR: {ICON_PATH} missing. Run generate_tray_icon.py first.")
        sys.exit(1)
    shutil.copy2(ICON_PATH, appdir / "aircube_tray.png")
    shutil.copy2(ICON_PATH, icon_dir / "aircube_tray.png")
    # Some AppImage tooling looks for .DirIcon explicitly.
    shutil.copy2(ICON_PATH, appdir / ".DirIcon")

    write_desktop_file(appdir / "AirCubeTray.desktop")
    shutil.copy2(appdir / "AirCubeTray.desktop", apps_dir / "AirCubeTray.desktop")

    apprun = appdir / "AppRun"
    apprun.write_text(
        "#!/bin/sh\n"
        'HERE="$(dirname "$(readlink -f "${0}")")"\n'
        'export PATH="${HERE}/usr/bin:${PATH}"\n'
        'exec "${HERE}/usr/bin/AirCubeTray" "$@"\n',
        encoding="utf-8",
    )
    apprun.chmod(0o755)

    return appdir


def main() -> None:
    if not sys.platform.startswith("linux"):
        print("ERROR: build_appimage.py must be run on Linux.")
        sys.exit(1)

    arch = detect_arch()
    version = read_version()
    print(f"AirCubeTray version: {version}  (arch={arch})")

    ensure_binary()
    appdir = build_appdir()
    tool = get_appimagetool(arch)

    out_dir = RELEASES_DIR / f"v{version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"AirCubeTray-{version}-{arch}.AppImage"
    if out_file.exists():
        out_file.unlink()

    print(f"Running appimagetool: {tool}")
    env = os.environ.copy()
    env["ARCH"] = arch
    result = subprocess.run([str(tool), str(appdir), str(out_file)], env=env)
    if result.returncode != 0:
        print("ERROR: appimagetool failed.")
        sys.exit(1)

    out_file.chmod(out_file.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    size_mb = out_file.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 50)
    print("APPIMAGE BUILD SUCCESSFUL!")
    print("=" * 50)
    print(f"Location: {out_file}")
    print(f"Size:     {size_mb:.1f} MB")
    print("\nUsers can run it directly:")
    print(f"  chmod +x {out_file.name}")
    print(f"  ./{out_file.name}")
    print("\nTip: integrate into the app menu with `appimaged` or by copying")
    print("the .desktop entry into ~/.local/share/applications/.")


if __name__ == "__main__":
    main()
