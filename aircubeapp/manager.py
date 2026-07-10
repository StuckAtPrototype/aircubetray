"""DeviceManager: multi-device registry across serial + BLE transports.

- Serial: hotplug watcher auto-connects every matching COM port.
- BLE: known devices persist and auto-reconnect; new ones added via scan.
- History syncs run one device at a time (matches the iOS sync queue).
"""
from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .device import Device
from .models import HistorySlot, LiveReading, SEQ_NONE
from .store import HistoryStore, Prefs, anchor_timestamps
from .transports.serial_transport import (
    SerialConnection, detect_aircube_ports, port_device_id)

AUTO_SYNC_INTERVAL_S = 600  # periodic re-sync while connected


class DeviceManager(QObject):
    devices_changed = pyqtSignal()          # add / remove / rename
    device_updated = pyqtSignal(str)        # live data or connection state
    bluetooth_error = pyqtSignal(str)

    def __init__(self, store: HistoryStore, prefs: Prefs):
        super().__init__()
        self.store = store
        self.prefs = prefs
        self.devices: dict[str, Device] = {}
        self._sync_queue: list[str] = []
        self._sync_active: Optional[str] = None
        self._flash_holds: set[str] = set()   # serial device_ids paused for flashing
        self._serial_fail_at: dict[str, float] = {}  # open-failure backoff

        self._load_known_devices()

        self._hotplug = QTimer(self)
        self._hotplug.setInterval(2000)
        self._hotplug.timeout.connect(self._hotplug_tick)
        self._hotplug.start()

        self._autosync = QTimer(self)
        self._autosync.setInterval(30_000)
        self._autosync.timeout.connect(self._autosync_tick)
        self._autosync.start()

        QTimer.singleShot(300, self._startup_connect)

    # -- known devices --------------------------------------------------------

    def _load_known_devices(self):
        for row in self.store.known_devices():
            dev = Device(row["device_id"], row["name"] or "AirCube",
                         row["transport"], row["address"])
            dev.is_pro = bool(row["is_pro"])
            dev.fw_version = row["fw_version"] or ""
            dev.ble_address = row.get("ble_address") or ""
            dev.last_synced_at = row["last_synced"] or 0.0
            dev.slots = self.store.all_slots(dev.device_id)
            self.devices[dev.device_id] = dev

    def _startup_connect(self):
        self._hotplug_tick()
        for dev in list(self.devices.values()):
            if dev.ble_address and dev.connection is None:
                self._start_ble(dev)

    def sorted_devices(self) -> list[Device]:
        return sorted(self.devices.values(), key=lambda d: d.name.lower())

    def connected_devices(self) -> list[Device]:
        return [d for d in self.devices.values() if d.is_connected]

    # -- serial hotplug ---------------------------------------------------------

    def _hotplug_tick(self):
        from .transports.ble_transport import BleConnection
        open_ports = {d.address for d in self.devices.values()
                      if d.transport == "serial" and d.connection is not None}
        for p in detect_aircube_ports():
            if p.device in open_ports:
                continue
            device_id = port_device_id(p)
            if device_id in self._flash_holds:
                continue
            dev = self.devices.get(device_id)
            if dev is None:
                dev = Device(device_id, self._default_name(), "serial", p.device)
                self.devices[device_id] = dev
                self.store.upsert_device(device_id, name=dev.name,
                                         transport="serial", address=p.device)
                dev.slots = []
                self.devices_changed.emit()
            elif dev.connection is not None:
                # prefer USB over BLE for the same cube (flashing, console),
                # but not if the port recently refused to open (busy port)
                if isinstance(dev.connection, BleConnection):
                    if time.time() - self._serial_fail_at.get(device_id, 0) < 60:
                        continue
                    dev.connection.stop()
                    dev.connection = None
                    dev.is_connected = False
                else:
                    continue
            dev.transport = "serial"
            dev.address = p.device
            self.store.upsert_device(device_id, transport="serial", address=p.device)
            self._start_serial(dev)

    def _default_name(self) -> str:
        base = "AirCube"
        names = {d.name for d in self.devices.values()}
        if base not in names:
            return base
        i = 2
        while f"{base} {i}" in names:
            i += 1
        return f"{base} {i}"

    def _start_serial(self, dev: Device):
        # BLE device_info (incl. newest_seq) must not leak into USB history anchoring.
        dev.info = None
        conn = SerialConnection(dev.address, dev.device_id)
        dev.connection = conn
        conn.live_data.connect(lambda r, d=dev: self._on_live(d, r))
        conn.connected.connect(lambda d=dev: self._on_connected(d))
        conn.disconnected.connect(lambda reason, d=dev: self._on_disconnected(d, reason))
        conn.history_progress.connect(lambda cur, tot, d=dev: self._on_sync_progress(d, cur, tot))
        conn.history_complete.connect(lambda slots, win, d=dev: self._on_serial_history(d, slots, win))
        conn.history_error.connect(lambda msg, d=dev: self._on_sync_error(d, msg))
        conn.config_received.connect(lambda cfg, d=dev: self._on_serial_config(d, cfg))
        conn.raw_line.connect(lambda line, d=dev: self._on_raw_line(d, line))
        conn.start()

    def _on_serial_config(self, dev: Device, cfg: dict):
        try:
            dev.led_percent = round(float(cfg.get("intensity", 0)) * 100)
            dev.brightness_updated.emit(dev.led_percent)
        except (TypeError, ValueError):
            pass

    # -- BLE ------------------------------------------------------------------

    def _start_ble(self, dev: Device):
        from .transports.ble_transport import BleConnection
        dev.transport = "ble"
        conn = BleConnection(dev.ble_address or dev.address, dev.device_id)
        dev.connection = conn
        conn.live_data.connect(lambda r, d=dev: self._on_live(d, r))
        conn.device_info.connect(lambda info, d=dev: self._on_device_info(d, info))
        conn.connected.connect(lambda d=dev: self._on_connected(d))
        conn.disconnected.connect(lambda reason, d=dev: self._on_disconnected(d, reason))
        conn.history_progress.connect(lambda cur, tot, d=dev: self._on_sync_progress(d, cur, tot))
        conn.history_complete.connect(lambda slots, win, d=dev: self._on_ble_history(d, slots, win))
        conn.history_error.connect(lambda msg, d=dev: self._on_sync_error(d, msg))
        conn.brightness_changed.connect(lambda pct, d=dev: self._on_brightness(d, pct))
        conn.raw_line.connect(lambda line, d=dev: self._on_raw_line(d, line))
        conn.start()

    def add_ble_device(self, address: str, name: str):
        # BLE MAC == USB serial number on the ESP32-H2, so a cube already
        # known over USB is the same device.
        device_id = address.lower()
        dev = self.devices.get(device_id)
        if dev is not None:
            dev.ble_address = address
            self.store.upsert_device(device_id, ble_address=address)
            if dev.connection is None:
                self._start_ble(dev)
            return dev
        dev = Device(device_id, name or self._default_name(), "ble", address)
        dev.ble_address = address
        self.devices[device_id] = dev
        self.store.upsert_device(device_id, name=dev.name, transport="ble",
                                 address=address, ble_address=address)
        self.devices_changed.emit()
        self._start_ble(dev)
        return dev

    # -- shared handlers ----------------------------------------------------------

    def _on_connected(self, dev: Device):
        dev.is_connected = True
        dev.sync_error = ""
        self.store.upsert_device(dev.device_id, last_seen=time.time())
        self.device_updated.emit(dev.device_id)
        dev.updated.emit()
        if dev.transport == "serial" and dev.connection:
            from . import protocol as proto
            dev.connection.send_command(proto.cmd_get_config())
        elif dev.transport == "ble" and dev.connection:
            dev.connection.read_brightness()
        self.request_sync(dev.device_id)

    def _on_disconnected(self, dev: Device, reason: str):
        was_connected = dev.is_connected
        dev.is_connected = False
        if dev.transport == "serial":
            if not was_connected:
                # port exists but would not open (busy/permission)
                self._serial_fail_at[dev.device_id] = time.time()
            # thread ends on error; drop it so hotplug can reconnect
            dev.connection = None
            # fall back to BLE if we know this cube's radio
            if (dev.ble_address and dev.device_id not in self._flash_holds):
                QTimer.singleShot(5000, lambda d=dev: self._ble_fallback(d))
        if dev.is_syncing:
            self._finish_sync(dev)
        if was_connected:
            self.device_updated.emit(dev.device_id)
            dev.updated.emit()

    def _ble_fallback(self, dev: Device):
        if (dev.connection is None and dev.ble_address
                and dev.device_id in self.devices
                and dev.device_id not in self._flash_holds):
            self._start_ble(dev)

    def _on_live(self, dev: Device, reading: LiveReading):
        dev.last_reading = reading
        dev.last_reading_at = time.time()
        if reading.is_pro != dev.is_pro:
            dev.is_pro = reading.is_pro
            self.store.upsert_device(dev.device_id, is_pro=int(dev.is_pro))
        self.device_updated.emit(dev.device_id)
        dev.updated.emit()

    def _on_device_info(self, dev: Device, info):
        dev.info = info
        dev.is_pro = info.is_pro
        dev.fw_version = info.fw_version
        dev.history_window_s = info.history_window_s or 300
        self.store.upsert_device(dev.device_id, is_pro=int(info.is_pro),
                                 fw_version=info.fw_version)

    def _on_brightness(self, dev: Device, pct: int):
        dev.led_percent = pct
        if pct > 0:
            self.prefs.set_led_last_on_percent(dev.device_id, pct)
        dev.brightness_updated.emit(pct)

    def _on_raw_line(self, dev: Device, line: str):
        dev.append_log(line)

    # -- LED ----------------------------------------------------------------------

    def set_led(self, dev: Device, percent: int):
        if dev.connection is None:
            return
        percent = max(0, min(100, percent))
        dev.connection.set_brightness(percent)
        dev.led_percent = percent
        if percent > 0:
            self.prefs.set_led_last_on_percent(dev.device_id, percent)
        dev.brightness_updated.emit(percent)

    def toggle_led(self, dev: Device):
        current = dev.led_percent or 0
        if current > 0:
            self.set_led(dev, 0)
        else:
            self.set_led(dev, self.prefs.led_last_on_percent(dev.device_id))

    # -- history sync queue ---------------------------------------------------------

    def request_sync(self, device_id: str):
        dev = self.devices.get(device_id)
        if dev is None or not dev.is_connected:
            return
        if device_id in self._sync_queue or self._sync_active == device_id:
            return
        self._sync_queue.append(device_id)
        self._pump_sync()

    def request_sync_all(self):
        for dev in self.connected_devices():
            self.request_sync(dev.device_id)

    def _pump_sync(self):
        if self._sync_active is not None:
            return
        while self._sync_queue:
            device_id = self._sync_queue.pop(0)
            dev = self.devices.get(device_id)
            if dev is None or not dev.is_connected or dev.connection is None:
                continue
            self._sync_active = device_id
            dev.is_syncing = True
            dev.sync_progress = (0, 0)
            dev.sync_error = ""
            dev.sync_state_changed.emit()
            if dev.transport == "ble":
                after = None
                # incremental: only fetch newer than what we have (if any)
                newest_cached = self.store.highest_sequence(device_id)
                if newest_cached is not None and dev.slots:
                    after = newest_cached
                dev.connection.request_history_sync(after)
            else:
                dev.connection.request_history_sync()
            return

    def _autosync_tick(self):
        now = time.time()
        for dev in self.connected_devices():
            if now - dev.last_synced_at > AUTO_SYNC_INTERVAL_S and not dev.is_syncing:
                self.request_sync(dev.device_id)

    def _on_sync_progress(self, dev: Device, current: int, total: int):
        dev.sync_progress = (current, total)
        dev.sync_state_changed.emit()

    def _on_serial_history(self, dev: Device, slots: list[HistorySlot], window_s: int):
        self._store_history(dev, slots, window_s)

    def _on_ble_history(self, dev: Device, slots: list[HistorySlot], window_s: int):
        self._store_history(dev, slots, window_s)

    def _history_newest_seq(self, dev: Device, slots: list[HistorySlot]) -> int:
        """Sequence number of the device's newest history slot for timestamp anchoring."""
        valid = [s for s in slots if s.sequence != SEQ_NONE]
        if not valid:
            return SEQ_NONE
        if dev.transport == "ble" and dev.info is not None and dev.info.newest_seq != SEQ_NONE:
            # BLE incremental sync may not include the newest slot in this batch.
            return dev.info.newest_seq
        # Serial returns oldest-first; the last emitted slot is the newest entry.
        return valid[-1].sequence

    def _store_history(self, dev: Device, slots: list[HistorySlot], window_s: int):
        if slots:
            newest_seq = self._history_newest_seq(dev, slots)
            anchor_timestamps(slots, newest_seq, window_s or 300)
            self.store.upsert_slots(dev.device_id, slots)
        dev.history_window_s = window_s or 300
        dev.slots = self.store.all_slots(dev.device_id)
        dev.last_synced_at = time.time()
        self.store.upsert_device(dev.device_id, last_synced=dev.last_synced_at)
        self._finish_sync(dev)
        dev.history_updated.emit()
        self.device_updated.emit(dev.device_id)

    def _on_sync_error(self, dev: Device, message: str):
        dev.sync_error = message
        self._finish_sync(dev)

    def _finish_sync(self, dev: Device):
        dev.is_syncing = False
        dev.sync_state_changed.emit()
        if self._sync_active == dev.device_id:
            self._sync_active = None
            self._pump_sync()

    # -- rename / forget --------------------------------------------------------------

    def rename_device(self, device_id: str, name: str):
        dev = self.devices.get(device_id)
        if dev is None or not name.strip():
            return
        dev.name = name.strip()
        self.store.upsert_device(device_id, name=dev.name)
        self.devices_changed.emit()

    def forget_device(self, device_id: str):
        dev = self.devices.pop(device_id, None)
        if dev is None:
            return
        if dev.connection is not None:
            dev.connection.stop()
            dev.connection = None
        self.store.forget_device(device_id)
        self.prefs.set_device_muted(device_id, False)
        self.devices_changed.emit()

    # -- flashing support ---------------------------------------------------------------

    def hold_for_flash(self, device_id: str) -> Optional[str]:
        """Disconnect a serial device and stop hotplug so esptool owns the port.
        Returns the COM port, or None if not a connected serial device."""
        dev = self.devices.get(device_id)
        if dev is None or dev.transport != "serial":
            return None
        port = dev.address
        self._flash_holds.add(device_id)
        if dev.connection is not None:
            dev.connection.stop()
            dev.connection = None
        dev.is_connected = False
        self.device_updated.emit(device_id)
        dev.updated.emit()
        return port

    def release_flash_hold(self, device_id: str):
        self._flash_holds.discard(device_id)
        # hotplug watcher reconnects on the next tick

    def shutdown(self):
        self._hotplug.stop()
        self._autosync.stop()
        for dev in self.devices.values():
            if dev.connection is not None:
                try:
                    dev.connection.stop()
                except Exception:
                    pass
                dev.connection = None
