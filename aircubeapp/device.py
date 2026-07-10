"""Device: one AirCube, regardless of transport (serial or BLE)."""
from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from .models import DeviceInfo, HistorySlot, LiveReading

ONLINE_WINDOW_S = 15  # readings arrive at ~1 Hz on both transports


class Device(QObject):
    """UI-facing state for one known AirCube."""
    updated = pyqtSignal()            # live reading / connection state change
    history_updated = pyqtSignal()    # cached history slots changed
    sync_state_changed = pyqtSignal()
    brightness_updated = pyqtSignal(int)

    def __init__(self, device_id: str, name: str, transport: str, address: str):
        super().__init__()
        self.device_id = device_id
        self.name = name
        self.transport = transport          # "serial" | "ble"
        self.address = address              # COM port or BLE address
        self.ble_address = ""               # known BLE address, if any
        self.is_pro = False
        self.fw_version = ""

        self.connection = None              # SerialConnection | BleConnection
        self.is_connected = False
        self.last_reading: Optional[LiveReading] = None
        self.last_reading_at: float = 0.0
        self.info: Optional[DeviceInfo] = None

        self.slots: list[HistorySlot] = []  # cached history, sorted by timestamp
        self.history_window_s = 300
        self.last_synced_at: float = 0.0

        self.is_syncing = False
        self.sync_progress: tuple[int, int] = (0, 0)
        self.sync_error: str = ""

        self.led_percent: Optional[int] = None
        self.serial_log: list[str] = []

    @property
    def is_online(self) -> bool:
        return (self.is_connected and self.last_reading is not None
                and time.time() - self.last_reading_at < ONLINE_WINDOW_S)

    @property
    def model_label(self) -> str:
        return "AirCube Pro" if self.is_pro else "AirCube Base"

    def display_updated_ago(self) -> str:
        if self.last_reading_at <= 0:
            return "Never updated"
        delta = time.time() - self.last_reading_at
        if delta < 90:
            return "Updated just now"
        if delta < 3600:
            return f"Updated {int(delta // 60)} min ago"
        if delta < 86_400:
            return f"Updated {int(delta // 3600)} hr ago"
        return f"Updated {int(delta // 86_400)} d ago"

    def slots_in_range(self, seconds: int) -> list[HistorySlot]:
        cutoff = time.time() - seconds
        return [s for s in self.slots if s.timestamp >= cutoff]

    def sparkline_slots(self, count: int = 24) -> list[HistorySlot]:
        """Last `count` slots (~2 h at 5-min windows), matching iOS cards."""
        return self.slots[-count:] if self.slots else []

    def append_log(self, line: str):
        self.serial_log.append(line)
        if len(self.serial_log) > 500:
            del self.serial_log[:100]
