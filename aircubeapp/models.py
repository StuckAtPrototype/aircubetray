"""Data models shared by the serial and BLE transports and the UI.

Mirrors the iOS app (AirCubeProtocol.swift / Theme.swift): live readings,
history slots, device info, and the quality verdict / 0-100 air score.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

SEQ_NONE = 0xFFFF


class AirQuality(IntEnum):
    GOOD = 0
    FAIR = 1
    POOR = 2
    BAD = 3

    @property
    def label(self) -> str:
        return {
            AirQuality.GOOD: "Air is good",
            AirQuality.FAIR: "Air is OK",
            AirQuality.POOR: "Air is poor",
            AirQuality.BAD: "Air is bad",
        }[self]

    @property
    def short_label(self) -> str:
        return {
            AirQuality.GOOD: "Good",
            AirQuality.FAIR: "OK",
            AirQuality.POOR: "Poor",
            AirQuality.BAD: "Bad",
        }[self]

    @property
    def status_pill(self) -> str:
        """Home-card status pill wording (iOS: Good / Elevated / Ventilate)."""
        return {
            AirQuality.GOOD: "Good",
            AirQuality.FAIR: "Elevated",
            AirQuality.POOR: "Ventilate",
            AirQuality.BAD: "Ventilate",
        }[self]


def voc_quality(ppb: float) -> AirQuality:
    if ppb <= 220:
        return AirQuality.GOOD
    if ppb <= 660:
        return AirQuality.FAIR
    if ppb <= 2200:
        return AirQuality.POOR
    return AirQuality.BAD


def co2_quality(ppm: float) -> AirQuality:
    if ppm < 800:
        return AirQuality.GOOD
    if ppm < 1200:
        return AirQuality.FAIR
    if ppm < 2000:
        return AirQuality.POOR
    return AirQuality.BAD


def _band_score(value: float, thresholds: list[float]) -> float:
    """Map a value onto 0-100 given the 5 band-threshold edges."""
    if value <= thresholds[0]:
        return 0.0
    for i in range(1, len(thresholds)):
        if value <= thresholds[i]:
            lo, hi = thresholds[i - 1], thresholds[i]
            return (i - 1) * 25 + 25 * (value - lo) / (hi - lo)
    return 100.0


VOC_SCORE_THRESHOLDS = [0, 220, 660, 2200, 5500]
CO2_SCORE_THRESHOLDS = [400, 800, 1200, 2000, 3000]


@dataclass
class LiveReading:
    """Normalized live sensor reading (from either transport)."""
    temperature_c: float = 0.0
    humidity: float = 0.0
    voc_level: int = 0          # 0-500 VOC index (serial "aqi" since fw 1.5)
    eco2: int = 0               # ppm, ENS16X estimate
    etvoc: int = 0              # ppb
    co2: int = 0                # ppm, SCD41 NDIR; 0 on Base
    lux: float = 0.0            # VCNL4040; 0 on Base
    aqi_uba: int = 0            # 1-5
    is_pro: bool = False
    timestamp: float = field(default_factory=time.time)

    @property
    def quality(self) -> AirQuality:
        """Overall verdict: worst of VOC (and true CO2 on Pro)."""
        q = voc_quality(self.etvoc)
        if self.is_pro:
            q = max(q, co2_quality(self.co2))
        return q

    @property
    def air_score(self) -> int:
        """0-100 score, lower is better (iOS Theme.airScore)."""
        score = _band_score(float(self.etvoc), VOC_SCORE_THRESHOLDS)
        if self.is_pro:
            score = max(score, _band_score(float(self.co2), CO2_SCORE_THRESHOLDS))
        return round(score)


@dataclass
class HistorySlot:
    """One aggregated history window (5 min on real hardware).

    On Base the co2_* fields hold eCO2; on Pro they hold true CO2 (matches
    the firmware history buffer and BLE wire format).
    """
    sequence: int
    timestamp: float = 0.0      # anchored unix seconds (device has no RTC)
    temp_avg: float = 0.0
    temp_min: float = 0.0
    temp_max: float = 0.0
    hum_avg: float = 0.0
    hum_min: float = 0.0
    hum_max: float = 0.0
    voc_avg: int = 0
    voc_min: int = 0
    voc_max: int = 0
    co2_avg: int = 0
    co2_min: int = 0
    co2_max: int = 0
    etvoc_avg: int = 0
    etvoc_min: int = 0
    etvoc_max: int = 0


@dataclass
class DeviceInfo:
    protocol_version: int = 1
    is_pro: bool = False
    fw_version: str = ""
    history_capacity: int = 0
    history_entry_count: int = 0
    history_window_s: int = 300
    newest_seq: int = SEQ_NONE


def seq_distance(newer: int, older: int) -> int:
    """Wrapping u16 sequence distance (monotonic, wraps at 0xFFFE)."""
    return (newer - older) & 0xFFFF


# ---------------------------------------------------------------------------
# History cleaning (iOS HistoryProcessing.swift)
# ---------------------------------------------------------------------------

CO2_VALID_FLOOR = 300  # ppm; readings at/below this are treated as missing
SEGMENT_MAX_SEQ_GAP = 3
SEGMENT_MAX_TIME_GAP_S = 1200  # 20 minutes


def history_value_is_valid(value: float, floor: float = 0.0) -> bool:
    return value > floor


def clean_slots(slots: list[HistorySlot], value_of, floor: float = 0.0) -> list[HistorySlot]:
    """Drop slots whose average for the selected metric is missing/invalid."""
    return [s for s in slots if history_value_is_valid(value_of(s), floor)]


def history_segments(slots: list[HistorySlot]) -> list[list[HistorySlot]]:
    """Split slots into contiguous segments for gap-aware charts."""
    segments: list[list[HistorySlot]] = []
    current: list[HistorySlot] = []
    for slot in sorted(slots, key=lambda s: s.sequence):
        if current:
            prev = current[-1]
            seq_gap = seq_distance(slot.sequence, prev.sequence)
            time_gap = abs(slot.timestamp - prev.timestamp)
            if seq_gap > SEGMENT_MAX_SEQ_GAP or time_gap > SEGMENT_MAX_TIME_GAP_S:
                segments.append(current)
                current = []
        current.append(slot)
    if current:
        segments.append(current)
    return segments


# ---------------------------------------------------------------------------
# Metric descriptors used across charts / tiles / compare
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    color_key: str  # Theme color name

    def slot_values(self, s: HistorySlot) -> tuple[float, float, float]:
        return {
            "co2": (s.co2_avg, s.co2_min, s.co2_max),
            "voc": (s.etvoc_avg, s.etvoc_min, s.etvoc_max),
            "temp": (s.temp_avg, s.temp_min, s.temp_max),
            "hum": (s.hum_avg, s.hum_min, s.hum_max),
        }[self.key]

    def valid_floor(self) -> float:
        return CO2_VALID_FLOOR if self.key == "co2" else 0.0


METRIC_CO2 = Metric("co2", "CO2", "ppm", "co2")
METRIC_VOC = Metric("voc", "VOC", "ppb", "voc")
METRIC_TEMP = Metric("temp", "Temperature", "°", "temp")
METRIC_HUM = Metric("hum", "Humidity", "%", "hum")

HISTORY_METRICS = [METRIC_CO2, METRIC_VOC, METRIC_TEMP, METRIC_HUM]

HISTORY_RANGES = [("24h", "Past 24h", 86_400), ("3d", "Past 3d", 259_200), ("7d", "Past 7d", 604_800)]


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def format_temp(c: float, fahrenheit: bool, decimals: int = 1) -> str:
    v = c_to_f(c) if fahrenheit else c
    return f"{v:.{decimals}f}°{'F' if fahrenheit else 'C'}"


# Detail-tile status pills (iOS DeviceDetailView thresholds)

def co2_tile_status(ppm: float) -> str:
    if ppm < 800:
        return "Fresh"
    if ppm < 1200:
        return "Elevated"
    if ppm < 2000:
        return "High"
    return "Very high"


def voc_tile_status(ppb: float) -> str:
    if ppb <= 220:
        return "Low"
    if ppb <= 660:
        return "Moderate"
    if ppb <= 2200:
        return "Elevated"
    return "High"


def hum_tile_status(pct: float) -> str:
    if pct < 30:
        return "Dry"
    if pct <= 60:
        return "Ideal"
    return "Humid"


def temp_tile_status(c: float) -> str:
    if c < 18:
        return "Cool"
    if c < 26:
        return "Ideal"
    if c < 30:
        return "Warm"
    return "Hot"


def tile_status_quality(key: str, value: float) -> AirQuality:
    """Quality color for a tile status pill."""
    if key == "co2":
        return co2_quality(value)
    if key == "voc":
        return voc_quality(value)
    if key == "hum":
        if value < 30 or value > 60:
            return AirQuality.FAIR
        return AirQuality.GOOD
    if key == "temp":
        if 18 <= value < 26:
            return AirQuality.GOOD
        if value < 18 or value < 30:
            return AirQuality.FAIR
        return AirQuality.POOR
    return AirQuality.GOOD
