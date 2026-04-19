"""
Package AirCubeTray.app as a distributable .dmg for macOS.

Run on macOS only. Will invoke build_tray.py first if dist/AirCubeTray.app
doesn't exist yet.

The DMG layout is the standard "drag-to-install" pattern:

    AirCubeTray (mounted volume)
      |- AirCubeTray.app
      |- Applications -> /Applications

Output: releases/v<version>/AirCubeTray-<version>-macos.dmg

Usage:
    python build_dmg.py
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
APP_PATH = SCRIPT_DIR / "dist" / "AirCubeTray.app"
ENTRY = SCRIPT_DIR / "aircube_tray.py"
RELEASES_DIR = SCRIPT_DIR / "releases"


def read_version() -> str:
    text = ENTRY.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        print(f"ERROR: could not find __version__ in {ENTRY.name}")
        sys.exit(1)
    return match.group(1)


def ensure_app() -> None:
    if APP_PATH.exists():
        return
    print(f"{APP_PATH} not found; running build_tray.py first...")
    result = subprocess.run([sys.executable, str(SCRIPT_DIR / "build_tray.py")])
    if result.returncode != 0 or not APP_PATH.exists():
        print("ERROR: building the .app failed.")
        sys.exit(1)


def build_dmg(version: str) -> Path:
    out_dir = RELEASES_DIR / f"v{version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dmg_path = out_dir / f"AirCubeTray-{version}-macos.dmg"

    if dmg_path.exists():
        dmg_path.unlink()

    staging = SCRIPT_DIR / "build" / "dmg-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    # Copy the .app into the staging area, preserving symlinks / permissions.
    subprocess.check_call(["cp", "-R", str(APP_PATH), str(staging)])
    # Convenience symlink so the user can drag into /Applications.
    os.symlink("/Applications", staging / "Applications")

    print(f"Creating DMG: {dmg_path}")
    subprocess.check_call([
        "hdiutil", "create",
        "-volname", "AirCubeTray",
        "-srcfolder", str(staging),
        "-ov",
        "-format", "UDZO",
        str(dmg_path),
    ])

    shutil.rmtree(staging, ignore_errors=True)
    return dmg_path


def main() -> None:
    if sys.platform != "darwin":
        print("ERROR: build_dmg.py must be run on macOS (uses hdiutil).")
        sys.exit(1)

    if shutil.which("hdiutil") is None:
        print("ERROR: hdiutil not found. It ships with macOS - check your PATH.")
        sys.exit(1)

    version = read_version()
    print(f"AirCubeTray version: {version}")

    ensure_app()
    dmg = build_dmg(version)

    size_mb = dmg.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 50)
    print("DMG BUILD SUCCESSFUL!")
    print("=" * 50)
    print(f"Location: {dmg}")
    print(f"Size:     {size_mb:.1f} MB")
    print("\nDistribute this .dmg to macOS users.")
    print("Note: it is NOT codesigned/notarized, so first-launch users will")
    print("need to right-click -> Open to bypass Gatekeeper.")


if __name__ == "__main__":
    main()
