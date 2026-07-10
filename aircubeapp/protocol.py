"""AirCube wire protocols.

BLE GATT (binary, little-endian) per AirCube/docs/BLE_GATT_PROTOCOL.md and
USB serial (JSON lines) per firmware serial_protocol.c. Both normalize into
the models in models.py.
"""
from __future__ import annotations

import json
import re
import struct
from typing import Optional

from .models import DeviceInfo, HistorySlot, LiveReading, SEQ_NONE

# ---------------------------------------------------------------------------
# BLE GATT
# ---------------------------------------------------------------------------

UUID_SERVICE = "A17C0DE0-1D0F-4E7C-8E4B-2A3D5F6B7C80"
UUID_DEVICE_INFO = "A17C0DE1-1D0F-4E7C-8E4B-2A3D5F6B7C80"
UUID_LIVE_DATA = "A17C0DE2-1D0F-4E7C-8E4B-2A3D5F6B7C80"
UUID_HISTORY_REQUEST = "A17C0DE3-1D0F-4E7C-8E4B-2A3D5F6B7C80"
UUID_HISTORY_DATA = "A17C0DE4-1D0F-4E7C-8E4B-2A3D5F6B7C80"
UUID_BRIGHTNESS = "A17C0DE5-1D0F-4E7C-8E4B-2A3D5F6B7C80"

BLE_DEVICE_NAME = "AirCube"

HISTORY_SLOT_SIZE = 32

FRAME_DATA = 0x01
FRAME_DONE = 0x02
FRAME_ERROR = 0x03


def parse_device_info(data: bytes) -> Optional[DeviceInfo]:
    if len(data) < 14:
        return None
    (proto, model, fw_major, fw_minor, fw_patch, _res,
     capacity, entries, window_s, newest_seq) = struct.unpack("<6BHHHH", data[:14])
    return DeviceInfo(
        protocol_version=proto,
        is_pro=(model == 1),
        fw_version=f"{fw_major}.{fw_minor}.{fw_patch}",
        history_capacity=capacity,
        history_entry_count=entries,
        history_window_s=window_s,
        newest_seq=newest_seq,
    )


def parse_live_data(data: bytes) -> Optional[LiveReading]:
    if len(data) < 20:
        return None
    (temp, hum, voc, eco2, etvoc, co2, lux,
     aqi_uba, flags, _uptime) = struct.unpack("<hHHHHHHBBI", data[:20])
    return LiveReading(
        temperature_c=temp / 100.0,
        humidity=hum / 100.0,
        voc_level=voc,
        eco2=eco2,
        etvoc=etvoc,
        co2=co2,
        lux=lux / 10.0,
        aqi_uba=aqi_uba,
        is_pro=bool(flags & 0x01),
    )


def parse_history_slot(data: bytes) -> Optional[HistorySlot]:
    if len(data) < HISTORY_SLOT_SIZE:
        return None
    vals = struct.unpack("<H3h3h3H3H3H", data[:HISTORY_SLOT_SIZE])
    seq = vals[0]
    if seq == SEQ_NONE:
        return None
    return HistorySlot(
        sequence=seq,
        temp_avg=vals[1] / 100.0, temp_min=vals[2] / 100.0, temp_max=vals[3] / 100.0,
        hum_avg=vals[4] / 100.0, hum_min=vals[5] / 100.0, hum_max=vals[6] / 100.0,
        voc_avg=vals[7], voc_min=vals[8], voc_max=vals[9],
        co2_avg=vals[10], co2_min=vals[11], co2_max=vals[12],
        etvoc_avg=vals[13], etvoc_min=vals[14], etvoc_max=vals[15],
    )


def history_start_request(after_seq: Optional[int] = None) -> bytes:
    seq = SEQ_NONE if after_seq is None else after_seq & 0xFFFF
    return struct.pack("<BBH", 0x01, 0x00, seq)


def history_abort_request() -> bytes:
    return struct.pack("<BBH", 0x02, 0x00, SEQ_NONE)


def parse_history_frame(data: bytes) -> tuple[int, int, int, list[HistorySlot]]:
    """Return (frame_type, count_or_reason_field, value, slots)."""
    if len(data) < 4:
        return (0, 0, 0, [])
    frame_type, slot_count, value = struct.unpack("<BBH", data[:4])
    slots: list[HistorySlot] = []
    if frame_type == FRAME_DATA:
        payload = data[4:]
        for i in range(slot_count):
            chunk = payload[i * HISTORY_SLOT_SIZE:(i + 1) * HISTORY_SLOT_SIZE]
            slot = parse_history_slot(chunk)
            if slot is not None:
                slots.append(slot)
    return (frame_type, slot_count, value, slots)


# ---------------------------------------------------------------------------
# USB serial (JSON lines)
# ---------------------------------------------------------------------------

JSON_PATTERN = re.compile(r"\{.*\}")

# ESP32-H2 built-in USB Serial/JTAG
AIRCUBE_VID = 0x303A
AIRCUBE_PID = 0x1001
AIRCUBE_DESC_HINTS = ("USB JTAG/serial debug unit", "Espressif")
SERIAL_BAUD = 115200


def parse_serial_live(data: dict) -> Optional[LiveReading]:
    """Parse the periodic sensor JSON object into a LiveReading.

    Note: since firmware 1.5.0 the `aqi` field is the canonical VOC Level
    (0-500). Pro units add scd41.co2 and vcnl4040.lux; `model` is
    "base"/"pro" (older firmware omits it).
    """
    try:
        ens210 = data.get("ens210", {})
        ens16x = data.get("ens16x", {})
        scd41 = data.get("scd41", {}) or {}
        vcnl = data.get("vcnl4040", {}) or {}
        model = data.get("model")
        co2 = int(scd41.get("co2") or 0)
        lux = float(vcnl.get("lux") or 0.0)
        if model is not None:
            is_pro = (model == "pro")
        else:
            is_pro = co2 > 0
        return LiveReading(
            temperature_c=float(ens210.get("temperature_c") or 0.0),
            humidity=float(ens210.get("humidity") or 0.0),
            voc_level=int(ens16x.get("aqi") or 0),
            eco2=int(ens16x.get("eco2") or 0),
            etvoc=int(ens16x.get("etvoc") or 0),
            co2=co2,
            lux=lux,
            aqi_uba=int(ens16x.get("aqi_uba") or 0),
            is_pro=is_pro,
        )
    except (TypeError, ValueError):
        return None


def parse_serial_history_slot(s: dict) -> Optional[HistorySlot]:
    """Parse one slot from a get_history response page.

    Serial field names: t_*=temp x100, h_*=humidity x100, q_*=VOC level,
    c_*=eCO2 (true CO2 source on Pro history), v_*=eTVOC.
    """
    try:
        seq = int(s.get("seq", SEQ_NONE))
        if seq == SEQ_NONE:
            return None
        return HistorySlot(
            sequence=seq,
            temp_avg=s.get("t_a", 0) / 100.0,
            temp_min=s.get("t_n", 0) / 100.0,
            temp_max=s.get("t_x", 0) / 100.0,
            hum_avg=s.get("h_a", 0) / 100.0,
            hum_min=s.get("h_n", 0) / 100.0,
            hum_max=s.get("h_x", 0) / 100.0,
            voc_avg=int(s.get("q_a", 0)), voc_min=int(s.get("q_n", 0)), voc_max=int(s.get("q_x", 0)),
            co2_avg=int(s.get("c_a", 0)), co2_min=int(s.get("c_n", 0)), co2_max=int(s.get("c_x", 0)),
            etvoc_avg=int(s.get("v_a", 0)), etvoc_min=int(s.get("v_n", 0)), etvoc_max=int(s.get("v_x", 0)),
        )
    except (TypeError, ValueError):
        return None


def extract_json(line: str) -> Optional[dict]:
    match = JSON_PATTERN.search(line)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def cmd_get_config() -> str:
    return '{"cmd":"get_config"}'


def cmd_set_intensity(fraction: float) -> str:
    return json.dumps({"cmd": "set_intensity", "value": round(fraction, 2)}, separators=(",", ":"))


def cmd_get_history_info() -> str:
    return '{"cmd":"get_history_info"}'


def cmd_get_history(start: int, count: int) -> str:
    return json.dumps({"cmd": "get_history", "start": start, "count": count}, separators=(",", ":"))
