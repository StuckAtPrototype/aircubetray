"""USB serial transport: one reader thread per COM port, JSON line protocol."""
from __future__ import annotations

import json
import time
from typing import Optional

import serial
from serial.tools import list_ports
from PyQt6.QtCore import QThread, pyqtSignal

from ..models import DeviceInfo, HistorySlot, LiveReading
from .. import protocol as proto


def is_aircube_port(p) -> bool:
    if p.vid == proto.AIRCUBE_VID and p.pid == proto.AIRCUBE_PID:
        return True
    desc = (p.description or "") + " " + (getattr(p, "manufacturer", "") or "")
    return any(h in desc for h in proto.AIRCUBE_DESC_HINTS)


def detect_aircube_ports() -> list:
    """ListPortInfo entries that look like AirCubes (VID/PID matches first)."""
    vid_pid, desc = [], []
    for p in list_ports.comports():
        if p.vid == proto.AIRCUBE_VID and p.pid == proto.AIRCUBE_PID:
            vid_pid.append(p)
        elif is_aircube_port(p):
            desc.append(p)
    return vid_pid + desc


def port_device_id(p) -> str:
    """Stable device id for a serial AirCube.

    The ESP32-H2 USB-JTAG serial number is the chip's base MAC — the same
    address the cube advertises over BLE — so the same physical cube gets
    the same id on both transports.
    """
    sn = getattr(p, "serial_number", None)
    if sn:
        return sn.lower()
    return f"usb-{p.device.lower()}"


class SerialConnection(QThread):
    """Reader/writer thread for one AirCube on a COM port.

    Emits normalized models. History sync runs over the same line protocol
    (get_history_info + paged get_history) with timestamps anchored on
    completion by the caller.
    """
    live_data = pyqtSignal(object)          # LiveReading
    device_info = pyqtSignal(object)        # DeviceInfo
    config_received = pyqtSignal(dict)      # {"intensity": 0.6, "readout_period": 1000}
    history_progress = pyqtSignal(int, int)  # fetched, total
    history_complete = pyqtSignal(list, int)  # [HistorySlot], window_s
    history_error = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal(str)          # reason
    raw_line = pyqtSignal(str)

    PAGE_SIZE = 48
    HISTORY_TIMEOUT_S = 8.0

    def __init__(self, port: str, device_id: str):
        super().__init__()
        self.port = port
        self.device_id = device_id
        self._running = False
        self._serial: Optional[serial.Serial] = None
        # history fetch state (worker-thread only)
        self._fetch_active = False
        self._fetch_slots: list[HistorySlot] = []
        self._fetch_total = 0
        self._fetch_start = 0
        self._fetch_window_s = 300
        self._fetch_deadline = 0.0
        self._fetch_requested = False
        self._pending_writes: list[str] = []

    # -- public API (any thread) --------------------------------------------

    def stop(self):
        self._running = False
        self.wait(3000)

    def request_history_sync(self):
        self._fetch_requested = True

    def send_command(self, cmd_json: str):
        self._pending_writes.append(cmd_json)

    def set_brightness(self, percent: int):
        """LED brightness 0-100 via set_intensity (0..1 fraction)."""
        self.send_command(proto.cmd_set_intensity(max(0, min(100, percent)) / 100.0))

    # -- worker thread --------------------------------------------------------

    def run(self):
        try:
            self._serial = serial.Serial(self.port, proto.SERIAL_BAUD, timeout=0.2)
        except (serial.SerialException, OSError) as e:
            self.disconnected.emit(str(e))
            return

        self._running = True
        self.connected.emit()
        try:
            while self._running:
                self._flush_writes()
                self._check_fetch_state()
                try:
                    line = self._serial.readline()
                except (serial.SerialException, OSError) as e:
                    if self._running:
                        self.disconnected.emit(str(e))
                    return
                if not line:
                    continue
                decoded = line.decode(errors="ignore").strip()
                if not decoded:
                    continue
                self.raw_line.emit(f"RX: {decoded}")
                data = proto.extract_json(decoded)
                if data is None:
                    continue
                if "ens210" in data:
                    reading = proto.parse_serial_live(data)
                    if reading:
                        self.live_data.emit(reading)
                        # Synthesize DeviceInfo-ish fields from live data once
                elif "history_info" in data:
                    self._on_history_info(data["history_info"])
                elif "history" in data:
                    self._on_history_page(data)
                elif "config" in data:
                    self.config_received.emit(data["config"])
        finally:
            self._running = False
            if self._serial and self._serial.is_open:
                self._serial.close()

    def _flush_writes(self):
        while self._pending_writes:
            cmd = self._pending_writes.pop(0)
            try:
                self.raw_line.emit(f"TX: {cmd}")
                self._serial.write((cmd + "\n").encode())
                self._serial.flush()
            except (serial.SerialException, OSError) as e:
                self.raw_line.emit(f"TX ERROR: {e}")

    def _check_fetch_state(self):
        if self._fetch_requested and not self._fetch_active:
            self._fetch_requested = False
            self._fetch_active = True
            self._fetch_slots = []
            self._fetch_total = 0
            self._fetch_start = 0
            self._fetch_deadline = time.monotonic() + self.HISTORY_TIMEOUT_S
            self._pending_writes.append(proto.cmd_get_history_info())
        elif self._fetch_active and time.monotonic() > self._fetch_deadline:
            self._fetch_active = False
            self.history_error.emit("Timeout: device did not respond")

    def _on_history_info(self, info: dict):
        if not self._fetch_active:
            return
        self._fetch_deadline = time.monotonic() + self.HISTORY_TIMEOUT_S
        if self._fetch_total:
            # Duplicate info (e.g. a reply left in the stream by a previous
            # client) while this fetch is already paging: restarting the pages
            # would desynchronize the cursor from the device's replies.
            return
        self._fetch_total = int(info.get("entries", 0))
        window_us = int(info.get("window_us", 300_000_000))
        self._fetch_window_s = max(1, window_us // 1_000_000)
        if self._fetch_total == 0:
            self._fetch_active = False
            self.history_complete.emit([], self._fetch_window_s)
            return
        self._request_next_page()

    def _on_history_page(self, data: dict):
        if not self._fetch_active:
            return
        self._fetch_deadline = time.monotonic() + self.HISTORY_TIMEOUT_S
        if self._fetch_total <= 0:
            return  # page belongs to an earlier fetch; this one has no info yet
        resp_start = data.get("start")
        if resp_start is not None and int(resp_start) != self._fetch_start:
            # Duplicate or stale page: advancing the cursor here would append
            # the same slots twice and end the sync before the newest page.
            return
        raw = [s for s in data.get("history", []) if s is not None]
        for s in raw:
            slot = proto.parse_serial_history_slot(s)
            if slot is not None:
                self._fetch_slots.append(slot)
        self._fetch_start += int(data.get("count", len(raw)))
        self.history_progress.emit(self._fetch_start, self._fetch_total)
        if self._fetch_start >= self._fetch_total:
            self._fetch_active = False
            self.history_complete.emit(self._fetch_slots, self._fetch_window_s)
        else:
            self._request_next_page()

    def _request_next_page(self):
        count = min(self.PAGE_SIZE, self._fetch_total - self._fetch_start)
        self._pending_writes.append(proto.cmd_get_history(self._fetch_start, count))
