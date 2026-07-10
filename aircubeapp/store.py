"""Persistence: SQLite history cache + known devices, QSettings preferences."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Optional

from PyQt6.QtCore import QSettings, QStandardPaths

from . import ORG_NAME, APP_SETTINGS_NAME
from .models import HistorySlot, seq_distance


def data_dir() -> str:
    path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    os.makedirs(path, exist_ok=True)
    return path


class HistoryStore:
    """History slot cache keyed by (device_id, sequence). Thread-safe."""

    def __init__(self, path: Optional[str] = None):
        self._path = path or os.path.join(data_dir(), "aircube.db")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                device_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                temp_avg REAL, temp_min REAL, temp_max REAL,
                hum_avg REAL, hum_min REAL, hum_max REAL,
                voc_avg INTEGER, voc_min INTEGER, voc_max INTEGER,
                co2_avg INTEGER, co2_min INTEGER, co2_max INTEGER,
                etvoc_avg INTEGER, etvoc_min INTEGER, etvoc_max INTEGER,
                PRIMARY KEY (device_id, sequence)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT,
                is_pro INTEGER DEFAULT 0,
                fw_version TEXT DEFAULT '',
                transport TEXT DEFAULT '',
                address TEXT DEFAULT '',
                ble_address TEXT DEFAULT '',
                last_seen REAL DEFAULT 0,
                last_synced REAL DEFAULT 0,
                last_sequence INTEGER DEFAULT -1
            )
        """)
        # lightweight migration for databases created before ble_address
        try:
            self._conn.execute("ALTER TABLE devices ADD COLUMN ble_address TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        self._migrate_legacy_ids()
        self._conn.commit()

    def _migrate_legacy_ids(self) -> None:
        """Merge legacy 'usb-<mac>' device ids into the unified bare-mac id."""
        cur = self._conn.execute(
            "SELECT device_id FROM devices WHERE device_id LIKE 'usb-%:%'")
        for (old_id,) in cur.fetchall():
            new_id = old_id[4:]
            exists = self._conn.execute(
                "SELECT 1 FROM devices WHERE device_id=?", (new_id,)).fetchone()
            if exists:
                self._conn.execute("DELETE FROM devices WHERE device_id=?", (old_id,))
                self._conn.execute(
                    "DELETE FROM history WHERE device_id=? AND sequence IN "
                    "(SELECT sequence FROM history WHERE device_id=?)",
                    (old_id, new_id))
                self._conn.execute(
                    "UPDATE OR IGNORE history SET device_id=? WHERE device_id=?",
                    (new_id, old_id))
                self._conn.execute("DELETE FROM history WHERE device_id=?", (old_id,))
            else:
                self._conn.execute(
                    "UPDATE devices SET device_id=? WHERE device_id=?",
                    (new_id, old_id))
                self._conn.execute(
                    "UPDATE history SET device_id=? WHERE device_id=?",
                    (new_id, old_id))

    # -- history ------------------------------------------------------------

    def upsert_slots(self, device_id: str, slots: list[HistorySlot]) -> None:
        if not slots:
            return
        rows = [(device_id, s.sequence, s.timestamp,
                 s.temp_avg, s.temp_min, s.temp_max,
                 s.hum_avg, s.hum_min, s.hum_max,
                 s.voc_avg, s.voc_min, s.voc_max,
                 s.co2_avg, s.co2_min, s.co2_max,
                 s.etvoc_avg, s.etvoc_min, s.etvoc_max) for s in slots]
        with self._lock:
            self._conn.executemany("""
                INSERT INTO history VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(device_id, sequence) DO UPDATE SET
                    timestamp=excluded.timestamp,
                    temp_avg=excluded.temp_avg, temp_min=excluded.temp_min, temp_max=excluded.temp_max,
                    hum_avg=excluded.hum_avg, hum_min=excluded.hum_min, hum_max=excluded.hum_max,
                    voc_avg=excluded.voc_avg, voc_min=excluded.voc_min, voc_max=excluded.voc_max,
                    co2_avg=excluded.co2_avg, co2_min=excluded.co2_min, co2_max=excluded.co2_max,
                    etvoc_avg=excluded.etvoc_avg, etvoc_min=excluded.etvoc_min, etvoc_max=excluded.etvoc_max
            """, rows)
            self._conn.commit()

    def slots_since(self, device_id: str, since: float) -> list[HistorySlot]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT sequence, timestamp, temp_avg, temp_min, temp_max,"
                " hum_avg, hum_min, hum_max, voc_avg, voc_min, voc_max,"
                " co2_avg, co2_min, co2_max, etvoc_avg, etvoc_min, etvoc_max"
                " FROM history WHERE device_id=? AND timestamp>=? ORDER BY timestamp",
                (device_id, since))
            rows = cur.fetchall()
        return [HistorySlot(*r) for r in rows]

    def all_slots(self, device_id: str) -> list[HistorySlot]:
        return self.slots_since(device_id, 0)

    def highest_sequence(self, device_id: str) -> Optional[int]:
        """Sequence of the most recent cached slot (by anchored timestamp)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT sequence FROM history WHERE device_id=?"
                " ORDER BY timestamp DESC LIMIT 1", (device_id,))
            row = cur.fetchone()
        return row[0] if row else None

    def clear_history(self, device_id: Optional[str] = None) -> None:
        with self._lock:
            if device_id:
                self._conn.execute("DELETE FROM history WHERE device_id=?", (device_id,))
            else:
                self._conn.execute("DELETE FROM history")
            self._conn.commit()

    # -- known devices --------------------------------------------------------

    def known_devices(self) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT device_id, name, is_pro, fw_version, transport, address,"
                " ble_address, last_seen, last_synced, last_sequence FROM devices")
            rows = cur.fetchall()
        keys = ["device_id", "name", "is_pro", "fw_version", "transport",
                "address", "ble_address", "last_seen", "last_synced", "last_sequence"]
        return [dict(zip(keys, r)) for r in rows]

    def upsert_device(self, device_id: str, **fields) -> None:
        allowed = {"name", "is_pro", "fw_version", "transport", "address",
                   "ble_address", "last_seen", "last_synced", "last_sequence"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        with self._lock:
            self._conn.execute(
                "INSERT INTO devices (device_id) VALUES (?) ON CONFLICT DO NOTHING",
                (device_id,))
            if fields:
                sets = ", ".join(f"{k}=?" for k in fields)
                self._conn.execute(
                    f"UPDATE devices SET {sets} WHERE device_id=?",
                    (*fields.values(), device_id))
            self._conn.commit()

    def forget_device(self, device_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM devices WHERE device_id=?", (device_id,))
            self._conn.execute("DELETE FROM history WHERE device_id=?", (device_id,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def anchor_timestamps(slots: list[HistorySlot], newest_seq: int, window_s: int,
                      now: Optional[float] = None) -> None:
    """Anchor slot timestamps: newest slot = now, older slots step back by
    window_s per sequence step (wrapping u16 math). Mutates in place."""
    if not slots:
        return
    now = now if now is not None else time.time()
    for s in slots:
        s.timestamp = now - seq_distance(newest_seq, s.sequence) * window_s


class Prefs:
    """Typed wrapper over QSettings with iOS-matching defaults."""

    DEFAULTS = {
        "use_fahrenheit": True,
        "appearance": "dark",           # dark | light | system
        "launch_mode": "tray",          # tray | window
        "autostart": False,
        # notifications (iOS NotifPrefs.defaults)
        "notif.enabled": False,
        "notif.co2_threshold": 1200,
        "notif.voc_threshold": 660,
        "notif.dwell_minutes": 5,
        "notif.cooldown_minutes": 60,
        "notif.all_clear": False,
        "notif.offline_enabled": False,
        "notif.offline_after_minutes": 30,
        "notif.quiet_enabled": False,
        "notif.quiet_start_hour": 22,
        "notif.quiet_end_hour": 7,
    }

    def __init__(self):
        self._s = QSettings(ORG_NAME, APP_SETTINGS_NAME)

    def get(self, key: str):
        default = self.DEFAULTS.get(key)
        val = self._s.value(key, default)
        if isinstance(default, bool):
            return val in (True, "true", "True", 1, "1")
        if isinstance(default, int):
            try:
                return int(val)
            except (TypeError, ValueError):
                return default
        return val

    def set(self, key: str, value) -> None:
        if isinstance(value, bool):
            value = "true" if value else "false"
        self._s.setValue(key, value)

    def device_muted(self, device_id: str) -> bool:
        return self._s.value(f"notif.muted.{device_id}", "false") in ("true", True)

    def set_device_muted(self, device_id: str, muted: bool) -> None:
        self._s.setValue(f"notif.muted.{device_id}", "true" if muted else "false")

    def led_last_on_percent(self, device_id: str) -> int:
        try:
            return int(self._s.value(f"led.last_on.{device_id}", 60))
        except (TypeError, ValueError):
            return 60

    def set_led_last_on_percent(self, device_id: str, pct: int) -> None:
        self._s.setValue(f"led.last_on.{device_id}", int(pct))

    def reset_notifications(self) -> None:
        for key in list(self.DEFAULTS):
            if key.startswith("notif."):
                self._s.remove(key)

    def reset_all(self) -> None:
        self._s.clear()
