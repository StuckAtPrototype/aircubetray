"""Alert engine: iOS AlertEngine.swift port over Windows tray notifications.

Dwell, cooldown, 90% hysteresis clear, quiet hours, offline alerts
(max one per device per day), per-device mute, optional all-clear.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer

from .device import Device
from .manager import DeviceManager
from .store import Prefs


@dataclass
class _MetricState:
    above_since: Optional[float] = None
    alerted: bool = False
    last_alert_at: float = 0.0


@dataclass
class _DeviceState:
    co2: _MetricState = field(default_factory=_MetricState)
    voc: _MetricState = field(default_factory=_MetricState)
    was_bad: bool = False
    offline_alert_at: float = 0.0
    offline_alerted: bool = False


class AlertEngine(QObject):
    def __init__(self, manager: DeviceManager, prefs: Prefs,
                 notify: Callable[[str, str, bool], None]):
        """notify(title, body, warning) shows a tray notification."""
        super().__init__()
        self.manager = manager
        self.prefs = prefs
        self.notify = notify
        self._states: dict[str, _DeviceState] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(15_000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _state(self, device_id: str) -> _DeviceState:
        if device_id not in self._states:
            self._states[device_id] = _DeviceState()
        return self._states[device_id]

    def _in_quiet_hours(self) -> bool:
        if not self.prefs.get("notif.quiet_enabled"):
            return False
        start = self.prefs.get("notif.quiet_start_hour")
        end = self.prefs.get("notif.quiet_end_hour")
        hour = datetime.now().hour
        if start == end:
            return True
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end  # overnight wrap

    def _tick(self):
        if not self.prefs.get("notif.enabled"):
            return
        now = time.time()
        for dev in self.manager.devices.values():
            if self.prefs.device_muted(dev.device_id):
                continue
            st = self._state(dev.device_id)
            self._check_offline(dev, st, now)
            reading = dev.last_reading
            if reading is None or not dev.is_online:
                continue
            st.offline_alerted = False

            dwell_s = self.prefs.get("notif.dwell_minutes") * 60
            cooldown_s = self.prefs.get("notif.cooldown_minutes") * 60

            any_bad = False
            # CO2 alerts are Pro-only (true CO2); VOC alerts on all devices
            if dev.is_pro:
                any_bad |= self._check_metric(
                    dev, st.co2, float(reading.co2),
                    float(self.prefs.get("notif.co2_threshold")),
                    dwell_s, cooldown_s, now,
                    lambda v, t: (f"CO2 high on {dev.name}",
                                  f"CO2 has been above {int(t)} ppm for a while "
                                  f"(now {int(v)} ppm). Consider ventilating."))
            any_bad |= self._check_metric(
                dev, st.voc, float(reading.etvoc),
                float(self.prefs.get("notif.voc_threshold")),
                dwell_s, cooldown_s, now,
                lambda v, t: (f"VOC high on {dev.name}",
                              f"VOC has been above {int(t)} ppb for a while "
                              f"(now {int(v)} ppb). Consider ventilating."))

            if st.was_bad and not any_bad:
                if (self.prefs.get("notif.all_clear")
                        and not self._in_quiet_hours()):
                    self.notify(f"Air is good on {dev.name}",
                                "Levels are back in the good range.", False)
                st.was_bad = False
            elif any_bad:
                st.was_bad = True

    def _check_metric(self, dev: Device, ms: _MetricState, value: float,
                      threshold: float, dwell_s: float, cooldown_s: float,
                      now: float, message) -> bool:
        clear_level = threshold * 0.9  # hysteresis
        if ms.alerted:
            if value < clear_level:
                ms.alerted = False
                ms.above_since = None
                return False
            # still bad: re-alert after cooldown
            if now - ms.last_alert_at >= cooldown_s and not self._in_quiet_hours():
                title, body = message(value, threshold)
                self.notify(title, body, True)
                ms.last_alert_at = now
            return True
        if value >= threshold:
            if ms.above_since is None:
                ms.above_since = now
            if now - ms.above_since >= dwell_s:
                if not self._in_quiet_hours():
                    title, body = message(value, threshold)
                    self.notify(title, body, True)
                ms.alerted = True
                ms.last_alert_at = now
            return value >= threshold
        ms.above_since = None
        return False

    def _check_offline(self, dev: Device, st: _DeviceState, now: float):
        if not self.prefs.get("notif.offline_enabled"):
            return
        after_s = self.prefs.get("notif.offline_after_minutes") * 60
        if dev.last_reading_at <= 0:
            return
        offline_for = now - dev.last_reading_at
        if offline_for >= after_s and not st.offline_alerted:
            if now - st.offline_alert_at >= 86_400:  # max 1/device/day
                if not self._in_quiet_hours():
                    self.notify(f"{dev.name} is offline",
                                f"No data received for {int(offline_for // 60)} minutes.",
                                True)
                st.offline_alert_at = now
            st.offline_alerted = True
