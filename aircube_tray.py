"""
AirCube for Windows
Entry point: iOS-parity desktop app with tray + windowed modes,
serial + BLE transports, multi-cube support, and firmware flashing.
"""
import sys

from aircubeapp import __version__, __app_name__  # noqa: F401
from aircubeapp.main import main

if __name__ == "__main__":
    sys.exit(main())
