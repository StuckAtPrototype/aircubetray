"""BLE transport via bleak, running on a dedicated asyncio thread.

Implements the AirCube GATT protocol: device-info read, live-data notify,
history request/stream, brightness read/write/notify. Auto-reconnects
every 3 seconds while enabled (matches the iOS manager).
"""
from __future__ import annotations

import asyncio
import threading
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from bleak import BleakClient, BleakScanner

from ..models import DeviceInfo, HistorySlot
from .. import protocol as proto


class BleLoop:
    """Singleton asyncio loop on a background thread for all BLE work."""
    _instance: Optional["BleLoop"] = None

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="ble-loop", daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    @classmethod
    def instance(cls) -> "BleLoop":
        if cls._instance is None:
            cls._instance = BleLoop()
        return cls._instance

    def submit(self, coro) -> "asyncio.Future":
        return asyncio.run_coroutine_threadsafe(coro, self.loop)


class BleScanner(QObject):
    """One-shot BLE scan for AirCubes (filtered on the service UUID)."""
    device_found = pyqtSignal(str, str, int)   # address, name, rssi
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def scan(self, timeout: float = 6.0):
        BleLoop.instance().submit(self._scan(timeout))

    async def _scan(self, timeout: float):
        try:
            found = await BleakScanner.discover(
                timeout=timeout, return_adv=True,
                service_uuids=[proto.UUID_SERVICE.lower()])
            for device, adv in found.values():
                name = device.name or adv.local_name or proto.BLE_DEVICE_NAME
                rssi = adv.rssi if adv.rssi is not None else -100
                self.device_found.emit(device.address, name, rssi)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class BleConnection(QObject):
    """Persistent connection to one AirCube over BLE."""
    live_data = pyqtSignal(object)              # LiveReading
    device_info = pyqtSignal(object)            # DeviceInfo
    brightness_changed = pyqtSignal(int)
    history_progress = pyqtSignal(int, int)     # received slots, expected total
    history_complete = pyqtSignal(list, int)    # [HistorySlot], window_s
    history_error = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal(str)
    raw_line = pyqtSignal(str)

    RECONNECT_DELAY_S = 3.0

    def __init__(self, address: str, device_id: str):
        super().__init__()
        self.address = address
        self.device_id = device_id
        self._client: Optional[BleakClient] = None
        self._enabled = False
        self._task: Optional[asyncio.Task] = None
        self._info: Optional[DeviceInfo] = None
        # history stream state (BLE-loop thread only)
        self._hist_slots: list[HistorySlot] = []
        self._hist_active = False
        self._hist_done: Optional[asyncio.Event] = None

    @property
    def info(self) -> Optional[DeviceInfo]:
        return self._info

    # -- public API (GUI thread) ----------------------------------------------

    def start(self):
        self._enabled = True
        BleLoop.instance().submit(self._start_task())

    def stop(self):
        self._enabled = False
        BleLoop.instance().submit(self._stop_task())

    def request_history_sync(self, after_seq: Optional[int] = None):
        BleLoop.instance().submit(self._history_sync(after_seq))

    def set_brightness(self, percent: int):
        BleLoop.instance().submit(self._write_brightness(percent))

    def read_brightness(self):
        BleLoop.instance().submit(self._read_brightness())

    # -- asyncio side -----------------------------------------------------------

    async def _start_task(self):
        if self._task is None or self._task.done():
            self._task = asyncio.get_event_loop().create_task(self._maintain())

    async def _stop_task(self):
        if self._task:
            self._task.cancel()
            self._task = None
        await self._disconnect_client("stopped")

    async def _maintain(self):
        while self._enabled:
            try:
                await self._connect_once()
                # stay until disconnect
                while self._enabled and self._client and self._client.is_connected:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.raw_line.emit(f"BLE: {e}")
                self.disconnected.emit(str(e))
            await self._disconnect_client("")
            if self._enabled:
                await asyncio.sleep(self.RECONNECT_DELAY_S)

    async def _connect_once(self):
        self.raw_line.emit(f"BLE: connecting to {self.address}")
        client = BleakClient(self.address,
                             disconnected_callback=self._on_ble_disconnect)
        await client.connect()
        self._client = client

        raw = await client.read_gatt_char(proto.UUID_DEVICE_INFO)
        info = proto.parse_device_info(bytes(raw))
        if info:
            self._info = info
            self.device_info.emit(info)

        await client.start_notify(proto.UUID_LIVE_DATA, self._on_live)
        try:
            await client.start_notify(proto.UUID_BRIGHTNESS, self._on_brightness)
            bri = await client.read_gatt_char(proto.UUID_BRIGHTNESS)
            if bri:
                self.brightness_changed.emit(int(bri[0]))
        except Exception:
            pass  # older firmware without the brightness characteristic
        await client.start_notify(proto.UUID_HISTORY_DATA, self._on_history)

        self.raw_line.emit("BLE: connected")
        self.connected.emit()

    def _on_ble_disconnect(self, _client):
        if self._hist_active and self._hist_done:
            self._hist_active = False
            self._hist_done.set()
        self.disconnected.emit("connection lost")

    async def _disconnect_client(self, reason: str):
        client, self._client = self._client, None
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
            if reason:
                self.disconnected.emit(reason)

    # -- notifications -----------------------------------------------------------

    def _on_live(self, _char, data: bytearray):
        reading = proto.parse_live_data(bytes(data))
        if reading:
            self.live_data.emit(reading)

    def _on_brightness(self, _char, data: bytearray):
        if data:
            self.brightness_changed.emit(int(data[0]))

    def _on_history(self, _char, data: bytearray):
        frame_type, _count, value, slots = proto.parse_history_frame(bytes(data))
        if frame_type == proto.FRAME_DATA:
            self._hist_slots.extend(slots)
            expected = self._info.history_entry_count if self._info else 0
            self.history_progress.emit(len(self._hist_slots), expected)
        elif frame_type == proto.FRAME_DONE:
            self._hist_active = False
            if self._hist_done:
                self._hist_done.set()
        elif frame_type == proto.FRAME_ERROR:
            self._hist_active = False
            reason = {1: "device busy", 2: "bad request"}.get(value, f"error {value}")
            self.raw_line.emit(f"BLE: history error: {reason}")
            self._hist_slots = []
            if self._hist_done:
                self._hist_done.set()

    # -- operations ---------------------------------------------------------------

    async def _history_sync(self, after_seq: Optional[int]):
        client = self._client
        if not client or not client.is_connected or self._hist_active:
            return
        try:
            # refresh device info so newest_seq / entry count are current
            raw = await client.read_gatt_char(proto.UUID_DEVICE_INFO)
            info = proto.parse_device_info(bytes(raw))
            if info:
                self._info = info
                self.device_info.emit(info)
            if info and info.newest_seq == proto.SEQ_NONE:
                self.history_complete.emit([], info.history_window_s if info else 300)
                return

            self._hist_slots = []
            self._hist_active = True
            self._hist_done = asyncio.Event()
            req = proto.history_start_request(after_seq)
            self.raw_line.emit(f"BLE: history sync after_seq={after_seq}")
            await client.write_gatt_char(proto.UUID_HISTORY_REQUEST, req, response=True)
            try:
                await asyncio.wait_for(self._hist_done.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                self._hist_active = False
                try:
                    await client.write_gatt_char(
                        proto.UUID_HISTORY_REQUEST, proto.history_abort_request(),
                        response=True)
                except Exception:
                    pass
                self.history_error.emit("History sync timed out")
                return
            window_s = self._info.history_window_s if self._info else 300
            self.history_complete.emit(list(self._hist_slots), window_s)
        except Exception as e:
            self._hist_active = False
            self.history_error.emit(str(e))

    async def _write_brightness(self, percent: int):
        client = self._client
        if not client or not client.is_connected:
            return
        try:
            value = max(0, min(100, int(percent)))
            await client.write_gatt_char(proto.UUID_BRIGHTNESS, bytes([value]),
                                         response=True)
        except Exception as e:
            self.raw_line.emit(f"BLE: brightness write failed: {e}")

    async def _read_brightness(self):
        client = self._client
        if not client or not client.is_connected:
            return
        try:
            data = await client.read_gatt_char(proto.UUID_BRIGHTNESS)
            if data:
                self.brightness_changed.emit(int(data[0]))
        except Exception:
            pass
