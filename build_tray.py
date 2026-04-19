"""
Build the standalone AirCubeTray binary via PyInstaller.

Cross-platform: detects the host OS and produces the right artifact.

  Windows : dist/AirCubeTray.exe       (single-file)
  macOS   : dist/AirCubeTray.app/...   (menu-bar bundle)
  Linux   : dist/AirCubeTray           (single-file ELF)

Always invokes PyInstaller with the .spec file. Passing CLI flags would cause
PyInstaller to overwrite the .spec and strip our datas / icon settings.

Usage:
    python build_tray.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SPEC_FILE = SCRIPT_DIR / "AirCubeTray.spec"
DIST_DIR = SCRIPT_DIR / "dist"

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

if IS_WIN:
    REQUIRED_ICON = SCRIPT_DIR / "aircube_tray.ico"
    OUTPUT_PATH = DIST_DIR / "AirCubeTray.exe"
    PROCESS_NAME = "AirCubeTray.exe"
elif IS_MAC:
    REQUIRED_ICON = SCRIPT_DIR / "aircube_tray.icns"
    OUTPUT_PATH = DIST_DIR / "AirCubeTray.app"
    PROCESS_NAME = "AirCubeTray"
else:
    REQUIRED_ICON = SCRIPT_DIR / "aircube_tray.png"
    OUTPUT_PATH = DIST_DIR / "AirCubeTray"
    PROCESS_NAME = "AirCubeTray"


def kill_running_instances() -> None:
    """Stop any running AirCubeTray so PyInstaller can overwrite the locked binary."""
    if IS_WIN:
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", PROCESS_NAME],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                print(f"Stopped running {PROCESS_NAME} instance(s) before build.")
        except FileNotFoundError:
            pass
        return

    # macOS / Linux: pkill is part of procps and is present on essentially every
    # mainstream distro and modern macOS. Silently no-op if missing.
    if shutil.which("pkill") is None:
        return
    try:
        result = subprocess.run(
            ["pkill", "-f", PROCESS_NAME],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"Stopped running {PROCESS_NAME} instance(s) before build.")
    except FileNotFoundError:
        pass


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def regenerate_icons_if_missing() -> None:
    if REQUIRED_ICON.exists():
        return
    print(f"WARNING: {REQUIRED_ICON.name} not found; regenerating via generate_tray_icon.py...")
    gen = SCRIPT_DIR / "generate_tray_icon.py"
    if gen.exists():
        subprocess.check_call([sys.executable, str(gen)])
    else:
        print("generate_tray_icon.py missing; continuing without a branded icon.")


def main() -> None:
    os.chdir(SCRIPT_DIR)
    plat = "Windows" if IS_WIN else ("macOS" if IS_MAC else "Linux")
    print(f"Building AirCubeTray for {plat} in {SCRIPT_DIR}")

    if not SPEC_FILE.exists():
        print(f"ERROR: {SPEC_FILE.name} not found.")
        sys.exit(1)

    regenerate_icons_if_missing()
    ensure_pyinstaller()
    kill_running_instances()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC_FILE),
    ]
    print(f"\nCommand: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nBUILD FAILED!")
        sys.exit(1)

    if not OUTPUT_PATH.exists():
        print(f"\nERROR: Expected output {OUTPUT_PATH} not found.")
        sys.exit(1)

    if OUTPUT_PATH.is_file():
        size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
        size_str = f"{size_mb:.1f} MB"
    else:
        # .app bundle - sum the contents
        total = sum(p.stat().st_size for p in OUTPUT_PATH.rglob("*") if p.is_file())
        size_str = f"{total / (1024 * 1024):.1f} MB (bundle)"

    print("\n" + "=" * 50)
    print("BUILD SUCCESSFUL!")
    print("=" * 50)
    print(f"Location: {OUTPUT_PATH}")
    print(f"Size:     {size_str}")

    if IS_WIN:
        print("\nNext: build the installer with `python build_installer.py`.")
    elif IS_MAC:
        print("\nNext: package as a .dmg with `python build_dmg.py`.")
    else:
        print("\nNext: package as an AppImage with `python build_appimage.py`.")


if __name__ == "__main__":
    main()
