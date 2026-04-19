"""
Build the standalone AirCubeTray.exe via PyInstaller.

Uses AirCubeTray.spec so the icon is bundled as a runtime data file
(`datas=[('aircube_tray.ico', '.')]`) AND embedded on the exe itself.

Running PyInstaller with CLI args instead would regenerate the .spec on
every run and strip those settings, so always prefer this script.

Usage:
    python build_tray.py
"""
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SPEC_FILE = SCRIPT_DIR / "AirCubeTray.spec"
ICON_PATH = SCRIPT_DIR / "aircube_tray.ico"
EXE_NAME = "AirCubeTray.exe"
EXE_PATH = SCRIPT_DIR / "dist" / EXE_NAME


def kill_running_instances() -> None:
    """Stop any running AirCubeTray.exe so PyInstaller can overwrite the locked binary."""
    if sys.platform != "win32":
        return
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", EXE_NAME],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"Stopped running {EXE_NAME} instance(s) before build.")
    except FileNotFoundError:
        pass


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def main() -> None:
    os.chdir(SCRIPT_DIR)
    print(f"Building AirCubeTray in {SCRIPT_DIR}")

    if not SPEC_FILE.exists():
        print(f"ERROR: {SPEC_FILE.name} not found.")
        sys.exit(1)

    if not ICON_PATH.exists():
        print(f"WARNING: {ICON_PATH.name} not found; regenerating via generate_tray_icon.py...")
        gen = SCRIPT_DIR / "generate_tray_icon.py"
        if gen.exists():
            subprocess.check_call([sys.executable, str(gen)])
        else:
            print("generate_tray_icon.py missing; continuing without a branded icon.")

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

    if not EXE_PATH.exists():
        print(f"\nERROR: Expected output {EXE_PATH} not found.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("BUILD SUCCESSFUL!")
    print("=" * 50)
    print(f"Location: {EXE_PATH}")
    print(f"Size:     {EXE_PATH.stat().st_size / (1024 * 1024):.1f} MB")
    print("\nThis lightweight tray app shows AQI in your taskbar.")
    print("Right-click the tray icon for options.")


if __name__ == "__main__":
    main()
