"""Compare page: multi-device overlay chart (iOS CompareView)."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QHBoxLayout, QPushButton, QVBoxLayout, QWidget)

from .. import theme
from ..manager import DeviceManager
from ..models import (HISTORY_METRICS, HISTORY_RANGES, Metric, c_to_f,
                      history_segments)
from .charts import CompareChart
from .widgets import Card, PillPicker, centered_column, make_label, retheme_label

# per-device palette order (iOS: temp, hum, voc, co2, eco2, lux)
PALETTE_KEYS = ["temp", "hum", "voc", "co2", "eco2", "lux"]


class ComparePage(QWidget):
    back = pyqtSignal()

    def __init__(self, manager: DeviceManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._metric: Metric = HISTORY_METRICS[1]  # VOC default
        self._range_s = 86_400
        self._build()
        manager.device_updated.connect(lambda _id: None)
        theme.signals.changed.connect(self._retheme)

    def _build(self):
        outer = centered_column(self, 1680)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        back_btn = QPushButton("←")
        back_btn.setObjectName("toolbtn")
        back_btn.setFixedSize(32, 32)
        back_btn.clicked.connect(self.back.emit)
        header.addWidget(back_btn)
        self.title = make_label("Compare", 20, QFont.Weight.Bold)
        header.addWidget(self.title)
        header.addStretch()
        self.metric_picker = PillPicker(
            [(m, "VOC" if m.key == "voc" else "CO2" if m.key == "co2" else m.label)
             for m in [HISTORY_METRICS[1], HISTORY_METRICS[0],
                       HISTORY_METRICS[2], HISTORY_METRICS[3]]])
        self.metric_picker.selection_changed.connect(self._on_metric)
        header.addWidget(self.metric_picker)
        self.range_picker = PillPicker([(s, label) for _, label, s in HISTORY_RANGES])
        self.range_picker.selection_changed.connect(self._on_range)
        header.addWidget(self.range_picker)
        outer.addLayout(header)

        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        self.chart = CompareChart(height=320)
        lay.addWidget(self.chart, stretch=1)

        self.legend = QHBoxLayout()
        self.legend.setSpacing(16)
        self.legend_host = QWidget()
        self.legend_host.setLayout(self.legend)
        lay.addWidget(self.legend_host)

        outer.addWidget(card, stretch=1)

    def _on_metric(self, metric: Metric):
        self._metric = metric
        self.refresh()

    def _on_range(self, seconds: int):
        self._range_s = seconds
        self.refresh()

    def refresh(self):
        use_f = self.manager.prefs.get("use_fahrenheit")
        metric = self._metric
        now = time.time()
        floor = metric.valid_floor()

        def val(s):
            v = metric.slot_values(s)[0]
            if metric.key == "temp" and use_f:
                return c_to_f(v)
            return v

        series = []
        # rebuild legend
        while self.legend.count():
            item = self.legend.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, dev in enumerate(self.manager.sorted_devices()):
            color = theme.color(PALETTE_KEYS[i % len(PALETTE_KEYS)])
            slots = dev.slots_in_range(self._range_s)
            valid = [s for s in slots if metric.slot_values(s)[0] > floor]
            segments = [[(s.timestamp, val(s)) for s in seg]
                        for seg in history_segments(valid)]
            series.append((dev.name, color, segments))
            dot = make_label("●  " + dev.name, 10, QFont.Weight.DemiBold)
            dot.setStyleSheet(f"color: {color.name()}; background: transparent;")
            self.legend.addWidget(dot)
        self.legend.addStretch()

        unit = metric.unit
        if metric.key == "temp":
            unit = "°F" if use_f else "°C"
        fmt = (lambda v: f"{v:.1f}") if metric.key in ("temp", "hum") else (lambda v: f"{v:.0f}")
        self.chart.set_data(series, f" {unit}" if not unit.startswith("°") else unit,
                            now - self._range_s, now, fmt)

    def _retheme(self):
        retheme_label(self.title)
        self.refresh()
