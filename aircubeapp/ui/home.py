"""Home page: 'AirCube Home' title, device cards, toolbar (iOS HomeView)."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                             QWidget)

from .. import theme
from ..device import Device
from ..manager import DeviceManager
from ..models import AirQuality, c_to_f
from .widgets import (AirGauge, Card, Pill, Sparkline, StatusDot, ToggleSwitch,
                      centered_column, make_label, retheme_label)


class DeviceCard(Card):
    clicked = pyqtSignal(str)

    def __init__(self, device: Device, manager: DeviceManager, parent=None):
        super().__init__(parent)
        self.device = device
        self.manager = manager
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(560)
        self._build()
        device.updated.connect(self.refresh)
        device.history_updated.connect(self.refresh_sparkline)
        device.sync_state_changed.connect(self.refresh_sync)
        device.brightness_updated.connect(self._on_brightness)
        theme.signals.changed.connect(self._retheme)
        self.refresh()
        self.refresh_sparkline()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(12)

        # header
        header = QHBoxLayout()
        header.setSpacing(8)
        self.dot = StatusDot()
        header.addWidget(self.dot)
        self.name_lbl = make_label(self.device.name, 16, QFont.Weight.DemiBold)
        header.addWidget(self.name_lbl)
        self.type_pill = Pill(self.device.model_label)
        self.type_pill.set_neutral()
        header.addWidget(self.type_pill)
        header.addStretch()
        self.status_pill = Pill("Waiting…")
        self.status_pill.set_neutral()
        header.addWidget(self.status_pill)
        lay.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(10)
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # main readings
        main = QHBoxLayout()
        main.setSpacing(28)
        self.voc_value = make_label("--", 34, QFont.Weight.DemiBold)
        self.voc_caption = make_label("VOC ppb", 9, QFont.Weight.Normal, "faint")
        voc_box = QVBoxLayout()
        voc_box.setSpacing(0)
        voc_box.addWidget(self.voc_value)
        voc_box.addWidget(self.voc_caption)
        main.addLayout(voc_box)

        self.co2_value = make_label("--", 34, QFont.Weight.DemiBold)
        self.co2_caption = make_label("CO2 ppm", 9, QFont.Weight.Normal, "faint")
        self.co2_box_widget = QWidget()
        co2_box = QVBoxLayout(self.co2_box_widget)
        co2_box.setContentsMargins(0, 0, 0, 0)
        co2_box.setSpacing(0)
        co2_box.addWidget(self.co2_value)
        co2_box.addWidget(self.co2_caption)
        main.addWidget(self.co2_box_widget)
        main.addStretch()
        left_col.addLayout(main)

        # sparkline
        self.spark = Sparkline("voc", height=48)
        left_col.addWidget(self.spark)
        self.spark_caption = make_label("VOC · last 2 hours", 8, QFont.Weight.Normal, "faint")
        left_col.addWidget(self.spark_caption)

        # secondary row
        sec = QHBoxLayout()
        sec.setSpacing(22)
        self.sec_labels: list[tuple[QLabel, QLabel]] = []
        for _ in range(4):
            box = QVBoxLayout()
            box.setSpacing(0)
            value = make_label("--", 12, QFont.Weight.DemiBold)
            caption = make_label("", 8, QFont.Weight.Normal, "faint")
            box.addWidget(value)
            box.addWidget(caption)
            sec.addLayout(box)
            self.sec_labels.append((value, caption))
        sec.addStretch()
        left_col.addLayout(sec)

        body.addLayout(left_col, stretch=1)
        self.gauge = AirGauge()
        body.addWidget(self.gauge, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(body)

        # sync progress
        self.sync_bar = QProgressBar()
        self.sync_bar.setTextVisible(False)
        self.sync_bar.setFixedHeight(5)
        self.sync_bar.setVisible(False)
        lay.addWidget(self.sync_bar)

        # footer
        footer = QHBoxLayout()
        self.updated_lbl = make_label("Never updated", 9, QFont.Weight.Normal, "faint")
        footer.addWidget(self.updated_lbl)
        footer.addStretch()
        footer.addWidget(make_label("LED", 9, QFont.Weight.Normal, "faint"))
        self.led_toggle = ToggleSwitch()
        self.led_toggle.toggled.connect(self._on_led_toggled)
        footer.addWidget(self.led_toggle)
        lay.addLayout(footer)

    def mouseReleaseEvent(self, event):
        # The LED toggle grabs its own clicks, so any release reaching the
        # card body means "open detail".
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.device.device_id)
        super().mouseReleaseEvent(event)

    def _on_led_toggled(self, on: bool):
        if on:
            self.manager.set_led(self.device,
                                 self.manager.prefs.led_last_on_percent(self.device.device_id))
        else:
            self.manager.set_led(self.device, 0)

    def _on_brightness(self, pct: int):
        self.led_toggle.setChecked(pct > 0)

    def refresh(self):
        dev = self.device
        self.name_lbl.setText(dev.name)
        self.type_pill.setText(dev.model_label)
        use_f = self.manager.prefs.get("use_fahrenheit")

        reading = dev.last_reading
        online = dev.is_online
        if online and reading is not None:
            q = reading.quality
            self.dot.set_color(theme.quality_color(q))
            self.status_pill.setText(q.status_pill)
            self.status_pill.set_quality(q)
            self.gauge.set_score(reading.air_score, q)
        else:
            self.dot.set_color(theme.color("faint"))
            self.status_pill.setText("Offline" if reading is None or not dev.is_connected
                                     else "Waiting…")
            self.status_pill.set_neutral()
            self.gauge.clear()

        if reading is not None:
            self.voc_value.setText(str(reading.etvoc))
            self.co2_value.setText(str(reading.co2) if dev.is_pro else "--")

            temp_txt = (f"{c_to_f(reading.temperature_c):.0f}°" if use_f
                        else f"{reading.temperature_c:.0f}°")
            last_cell = ((f"{reading.lux:.0f} lx", "LIGHT") if dev.is_pro
                         else (str(reading.eco2), "eCO2 ppm"))
            values = [
                (temp_txt, "TEMP"),
                (f"{reading.humidity:.0f}%", "HUMIDITY"),
                (str(reading.aqi_uba) if reading.aqi_uba else "--", "AQI (UBA)"),
                last_cell,
            ]
            for (value_lbl, caption_lbl), (v, c) in zip(self.sec_labels, values):
                value_lbl.setText(v)
                caption_lbl.setText(c)
        self.co2_box_widget.setVisible(dev.is_pro)
        self.spark_caption.setText(("CO2" if dev.is_pro else "VOC") + " · last 2 hours")
        self.updated_lbl.setText(dev.display_updated_ago())
        if dev.led_percent is not None:
            self.led_toggle.setChecked(dev.led_percent > 0)
        self.update()

    def refresh_sparkline(self):
        dev = self.device
        slots = dev.sparkline_slots(24)
        if dev.is_pro:
            self.spark.set_data([float(s.co2_avg) for s in slots if s.co2_avg > 300], "co2")
        else:
            self.spark.set_data([float(s.etvoc_avg) for s in slots if s.etvoc_avg > 0], "voc")

    def refresh_sync(self):
        dev = self.device
        self.sync_bar.setVisible(dev.is_syncing)
        cur, total = dev.sync_progress
        if total > 0:
            self.sync_bar.setRange(0, total)
            self.sync_bar.setValue(cur)
        else:
            self.sync_bar.setRange(0, 0)  # indeterminate

    def _retheme(self):
        for lbl in (self.name_lbl, self.voc_value, self.voc_caption, self.co2_value,
                    self.co2_caption, self.spark_caption, self.updated_lbl):
            retheme_label(lbl)
        for v, c in self.sec_labels:
            retheme_label(v)
            retheme_label(c)
        self.type_pill.set_neutral()
        self.refresh()


class HomePage(QWidget):
    open_detail = pyqtSignal(str)
    open_compare = pyqtSignal()
    open_settings = pyqtSignal()
    open_add = pyqtSignal()

    def __init__(self, manager: DeviceManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._cards: dict[str, DeviceCard] = {}
        self._build()
        manager.devices_changed.connect(self.rebuild_cards)
        theme.signals.changed.connect(self._retheme)
        self.rebuild_cards()

    def _build(self):
        outer = centered_column(self, 1760)
        outer.setContentsMargins(24, 16, 24, 0)
        outer.setSpacing(12)

        header = QHBoxLayout()
        self.title = make_label("AirCube Home", 24, QFont.Weight.Bold)
        header.addWidget(self.title)
        header.addStretch()

        self.compare_btn = QPushButton("⇄")
        self.compare_btn.setObjectName("toolbtn")
        self.compare_btn.setFixedSize(32, 32)
        self.compare_btn.setToolTip("Compare devices")
        self.compare_btn.clicked.connect(self.open_compare.emit)
        header.addWidget(self.compare_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("toolbtn")
        self.settings_btn.setFixedSize(32, 32)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self.open_settings.emit)
        header.addWidget(self.settings_btn)

        self.add_btn = QPushButton("+")
        self.add_btn.setObjectName("toolbtn")
        self.add_btn.setFixedSize(32, 32)
        self.add_btn.setToolTip("Add device")
        self.add_btn.clicked.connect(self.open_add.emit)
        header.addWidget(self.add_btn)
        outer.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.cards_host = QWidget()
        host_row = QHBoxLayout(self.cards_host)
        host_row.setContentsMargins(0, 0, 6, 16)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        host_row.addStretch(1)
        host_row.addWidget(self.grid_host, 0,
                           alignment=Qt.AlignmentFlag.AlignTop)
        host_row.addStretch(1)
        self.scroll.setWidget(self.cards_host)
        outer.addWidget(self.scroll, stretch=1)
        self._cols = 1

        self.empty_lbl = make_label(
            "No AirCubes yet.\nPlug one in over USB or tap + to add one over Bluetooth.",
            12, QFont.Weight.Normal, "muted")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.empty_lbl)

    def rebuild_cards(self):
        devices = self.manager.sorted_devices()
        ids = {d.device_id for d in devices}
        for device_id in list(self._cards):
            if device_id not in ids:
                card = self._cards.pop(device_id)
                self.grid.removeWidget(card)
                card.deleteLater()
        for dev in devices:
            if dev.device_id not in self._cards:
                card = DeviceCard(dev, self.manager)
                card.clicked.connect(self.open_detail.emit)
                self._cards[dev.device_id] = card
            else:
                self._cards[dev.device_id].name_lbl.setText(dev.name)
        self._relayout_grid()
        self.empty_lbl.setVisible(not devices)
        self.compare_btn.setEnabled(len(devices) >= 2)

    def _relayout_grid(self):
        cards = [self._cards[d.device_id] for d in self.manager.sorted_devices()
                 if d.device_id in self._cards]
        for card in cards:
            self.grid.removeWidget(card)
        for i, card in enumerate(cards):
            self.grid.addWidget(card, i // self._cols, i % self._cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 1-3 columns depending on how much room the window gives us
        cols = max(1, min(3, (self.width() - 48) // 580))
        cols = min(cols, max(1, len(self._cards)))
        if cols != self._cols:
            self._cols = cols
            self._relayout_grid()

    def _retheme(self):
        retheme_label(self.title)
        retheme_label(self.empty_lbl)
