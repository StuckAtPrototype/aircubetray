"""
Build script that creates both the AirCubeTray.exe and the Windows installer.

Windows-only. For the macOS .dmg run build_dmg.py; for the Linux AppImage
run build_appimage.py.

Steps:
  1. Build AirCubeTray.exe via PyInstaller using AirCubeTray.spec
     (the spec bundles aircube_tray.ico as a runtime data file and sets
      the exe icon, which the plain `build_tray.py` does not do).
  2. Compile installer.iss into AirCubeTray_Setup_vX.Y.Z.exe via Inno Setup.

Requirements:
  - pip install pyinstaller
  - Inno Setup 6 from https://jrsoftware.org/isdl.php

Usage:
    python build_installer.py
"""
import os
import sys
import subprocess
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SPEC_FILE = SCRIPT_DIR / "AirCubeTray.spec"
ISS_FILE = SCRIPT_DIR / "installer.iss"
EXE_NAME = "AirCubeTray.exe"
EXE_PATH = SCRIPT_DIR / "dist" / EXE_NAME
LICENSE_PATH = SCRIPT_DIR / "LICENSE"
ICON_PATH = SCRIPT_DIR / "aircube_tray.ico"
INSTALLER_OUTPUT = SCRIPT_DIR / "installer_output"


def find_inno_setup() -> str | None:
    """Locate the Inno Setup compiler (ISCC.exe)."""
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def kill_running_instances() -> None:
    """Kill any running AirCubeTray.exe so PyInstaller can overwrite dist\\AirCubeTray.exe.

    A running tray instance holds an exclusive lock on the .exe and will cause
    PyInstaller's EXE-assembly step to fail with `PermissionError: [WinError 5]`.
    """
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


def build_exe() -> None:
    print("=" * 60)
    print("STEP 1: Building AirCubeTray.exe with PyInstaller")
    print("=" * 60)

    os.chdir(SCRIPT_DIR)
    ensure_pyinstaller()
    kill_running_instances()

    if not SPEC_FILE.exists():
        print(f"\nERROR: Spec file not found: {SPEC_FILE}")
        sys.exit(1)
    if not ICON_PATH.exists():
        print(f"\nWARNING: {ICON_PATH.name} not found; regenerating via generate_tray_icon.py...")
        gen = SCRIPT_DIR / "generate_tray_icon.py"
        if gen.exists():
            subprocess.check_call([sys.executable, str(gen)])
        else:
            print("generate_tray_icon.py not found; the exe will build without a branded icon.")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC_FILE),
    ]
    print(f"\nCommand: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nERROR: PyInstaller build failed.")
        sys.exit(1)

    if not EXE_PATH.exists():
        print(f"\nERROR: {EXE_PATH} was not created.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Executable built successfully!")
    print(f"  Location: {EXE_PATH}")
    print(f"  Size:     {EXE_PATH.stat().st_size / (1024 * 1024):.1f} MB")
    print("=" * 60)


def build_installer() -> None:
    print("\n" + "=" * 60)
    print("STEP 2: Building installer with Inno Setup")
    print("=" * 60)

    iscc = find_inno_setup()
    if not iscc:
        print("\nERROR: Inno Setup not found!")
        print("Install Inno Setup 6 from https://jrsoftware.org/isdl.php and retry.")
        sys.exit(1)
    print(f"Found Inno Setup: {iscc}")

    if not ISS_FILE.exists():
        print(f"\nERROR: Inno Setup script not found: {ISS_FILE}")
        sys.exit(1)
    if not EXE_PATH.exists():
        print(f"\nERROR: {EXE_PATH} not found. Run the build step first.")
        sys.exit(1)
    if not LICENSE_PATH.exists():
        print(f"\nERROR: LICENSE file not found at {LICENSE_PATH}")
        sys.exit(1)

    cmd = [iscc, str(ISS_FILE)]
    print(f"\nCommand: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        print("\nERROR: Installer build failed.")
        sys.exit(1)

    installers = sorted(INSTALLER_OUTPUT.glob("AirCubeTray_Setup_*.exe"))
    if not installers:
        print(f"\nWARNING: No installer found in {INSTALLER_OUTPUT}")
        return

    installer_path = installers[-1]
    print("\n" + "=" * 60)
    print("INSTALLER BUILD SUCCESSFUL!")
    print("=" * 60)
    print(f"  Location: {installer_path}")
    print(f"  Size:     {installer_path.stat().st_size / (1024 * 1024):.1f} MB")
    print("=" * 60)


def main() -> None:
    if sys.platform != "win32":
        print("ERROR: build_installer.py only runs on Windows (it drives Inno Setup).")
        if sys.platform == "darwin":
            print("       Use `python build_dmg.py` for a macOS distributable.")
        else:
            print("       Use `python build_appimage.py` for a Linux distributable.")
        sys.exit(1)

    print("=" * 60)
    print("AirCube Tray Installer Builder")
    print("=" * 60)
    print("This script will:")
    print("  1. Build AirCubeTray.exe via PyInstaller (using AirCubeTray.spec)")
    print("  2. Compile a Windows installer via Inno Setup")
    print("=" * 60 + "\n")

    build_exe()
    build_installer()

    print("\nAll builds completed successfully.")


if __name__ == "__main__":
    main()
