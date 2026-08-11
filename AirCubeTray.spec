# -*- mode: python ; coding: utf-8 -*-
# AirCube for Windows: tray + windowed app, serial + BLE, firmware flashing.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# esptool loads its flasher stubs from JSON files on disk
# (esptool/targets/stub_flasher/<version>/<chip>.json), resolved relative to the
# esptool package directory. There is no PyInstaller hook for esptool, so
# declaring the modules as hidden imports is not enough: without these data
# files a frozen build fails with "Flasher stub data is missing for ESP32-H2".
esptool_datas = collect_data_files('esptool')
esptool_hiddenimports = collect_submodules('esptool')

a = Analysis(
    ['aircube_tray.py'],
    pathex=[],
    binaries=[],
    datas=[('aircube_tray.ico', '.')] + esptool_datas,
    hiddenimports=[
        'PyQt6.QtWidgets', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtNetwork',
        'serial.tools.list_ports',
        'bleak',
        'winrt.windows.devices.bluetooth',
        'winrt.windows.devices.bluetooth.advertisement',
        'winrt.windows.devices.bluetooth.genericattributeprofile',
        'winrt.windows.devices.enumeration',
        'winrt.windows.devices.radios',
        'winrt.windows.foundation',
        'winrt.windows.foundation.collections',
        'winrt.windows.storage.streams',
        'requests',
    ] + esptool_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'tkinter'],
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
    name='AirCubeTray',
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
    icon='aircube_tray.ico',
)
