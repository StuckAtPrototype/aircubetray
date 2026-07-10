"""iOS Theme.swift port: adaptive light/dark palette + app stylesheet.

Color is reserved for communicating air quality; everything else stays
neutral. The active mode is a module-level switch; widgets repaint after
`set_mode` via the ThemeSignals.changed signal.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor

from .models import AirQuality

# (light, dark) hex pairs, verbatim from Theme.swift
_PALETTE = {
    "bg":           (0xF4F2F8, 0x09080D),
    "card":         (0xFFFFFF, 0x15121C),
    "card_top":     (0xFFFFFF, 0x181420),
    "card_bottom":  (0xFAF8FD, 0x120F19),
    "card_border":  (0xE4E0EC, 0x24202D),
    "text":         (0x1B1626, 0xF5F2FA),
    "muted":        (0x6E6680, 0x9A93A8),
    "faint":        (0x9A93A8, 0x746D82),
    "accent":       (0x8B5CF6, 0x8B5CF6),
    "accent_soft":  (0xC084FC, 0xC084FC),
    "pill_track":   (0xE9E5F1, 0x0F0D15),
    "pill_selected": (0xFFFFFF, 0x2B2635),

    "temp":   (0xD1568F, 0xE887B8),
    "hum":    (0x2493D6, 0x5BB8F0),
    "voc":    (0x11A874, 0x3DE0A0),
    "eco2":   (0x8163E8, 0xA78BFA),
    "etvoc":  (0x0FA08B, 0x2DD4BF),
    "co2":    (0xE87420, 0xFF9445),
    "lux":    (0xD9A800, 0xFFD23F),

    "good": (0x11A874, 0x3DE0A0),
    "warn": (0xD79A17, 0xFFC94D),
    "bad":  (0xE87420, 0xFF9445),
    "crit": (0xE04F4F, 0xFF6B6B),
}


class ThemeSignals(QObject):
    changed = pyqtSignal()


signals = ThemeSignals()

_dark = True


def set_mode(dark: bool) -> None:
    global _dark
    if dark != _dark:
        _dark = dark
        signals.changed.emit()


def is_dark() -> bool:
    return _dark


def _hex(name: str) -> int:
    light, dark = _PALETTE[name]
    return dark if _dark else light


def color(name: str) -> QColor:
    v = _hex(name)
    return QColor((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


def css(name: str, alpha: float = 1.0) -> str:
    c = color(name)
    if alpha >= 1.0:
        return c.name()
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha:.2f})"


_QUALITY_KEY = {
    AirQuality.GOOD: "good",
    AirQuality.FAIR: "warn",
    AirQuality.POOR: "bad",
    AirQuality.BAD: "crit",
}


def quality_color(q: AirQuality) -> QColor:
    return color(_QUALITY_KEY[q])


def quality_css(q: AirQuality, alpha: float = 1.0) -> str:
    return css(_QUALITY_KEY[q], alpha)


FONT_FAMILY = "Segoe UI"
CARD_RADIUS = 24


def app_stylesheet() -> str:
    """Global stylesheet for standard Qt widgets (custom widgets self-paint)."""
    return f"""
    QMainWindow, QDialog {{ background: {css('bg')}; }}
    QWidget {{
        color: {css('text')};
        font-family: '{FONT_FAMILY}';
        font-size: 13px;
    }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{
        background: transparent; width: 8px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {css('card_border')}; border-radius: 4px; min-height: 30px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; }}
    QScrollBar::handle:horizontal {{
        background: {css('card_border')}; border-radius: 4px; min-width: 30px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    QLabel {{ background: transparent; }}

    QPushButton {{
        background: {css('card')};
        border: 1px solid {css('card_border', 0.8)};
        border-radius: 10px;
        padding: 7px 14px;
        color: {css('text')};
    }}
    QPushButton:hover {{ border-color: {css('accent')}; }}
    QPushButton:pressed {{ background: {css('pill_track')}; }}
    QPushButton:disabled {{ color: {css('faint')}; }}

    QPushButton#primary {{
        background: {css('accent')};
        border: none;
        color: white;
        font-weight: 600;
    }}
    QPushButton#primary:hover {{ background: {css('accent_soft')}; }}
    QPushButton#primary:disabled {{ background: {css('pill_track')}; color: {css('faint')}; }}

    QPushButton#toolbtn {{
        background: {css('card')};
        border: 1px solid {css('card_border', 0.6)};
        border-radius: 16px;
        padding: 0px;
        font-size: 15px;
    }}
    QPushButton#toolbtn:hover {{ border-color: {css('accent')}; }}

    QLineEdit, QComboBox, QSpinBox {{
        background: {css('card')};
        border: 1px solid {css('card_border')};
        border-radius: 10px;
        padding: 6px 10px;
        color: {css('text')};
        selection-background-color: {css('accent')};
    }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {css('card')};
        color: {css('text')};
        border: 1px solid {css('card_border')};
        selection-background-color: {css('pill_track')};
        selection-color: {css('text')};
    }}

    QMenu {{
        background: {css('card')};
        color: {css('text')};
        border: 1px solid {css('card_border')};
        border-radius: 10px;
        padding: 6px;
    }}
    QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {css('pill_track')}; }}
    QMenu::separator {{ height: 1px; background: {css('card_border')}; margin: 4px 8px; }}

    QSlider::groove:horizontal {{
        height: 4px; background: {css('pill_track')}; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{ background: {css('accent')}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        width: 18px; height: 18px; margin: -7px 0;
        background: white; border: 1px solid {css('card_border')};
        border-radius: 9px;
    }}

    QProgressBar {{
        background: {css('pill_track')};
        border: none; border-radius: 3px; height: 6px;
    }}
    QProgressBar::chunk {{ background: {css('accent')}; border-radius: 3px; }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px;
        border: 1px solid {css('card_border')};
        border-radius: 5px;
        background: {css('card')};
    }}
    QCheckBox::indicator:checked {{
        background: {css('accent')};
        border-color: {css('accent')};
    }}

    QTextEdit {{
        background: {css('card')};
        border: 1px solid {css('card_border')};
        border-radius: 10px;
        color: {css('text')};
    }}

    QToolTip {{
        background: {css('card')};
        color: {css('text')};
        border: 1px solid {css('card_border')};
        padding: 4px;
    }}
    """
