"""Device detail page: hero gauge, metric tiles, history, brightness,
advanced drawer, menu (iOS DeviceDetailView)."""
from __future__ import annotations

import csv
import os
import time
from datetime import datetime, timezone

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QInputDialog,
                             QLabel, QMenu, QMessageBox, QProgressBar, QPushButton,
                             QScrollArea, QSlider, QVBoxLayout, QWidget)

from .. import theme
from ..device import Device
from ..manager import DeviceManager
from ..models import (AirQuality, HISTORY_RANGES, HISTORY_METRICS, Metric,
                      c_to_f, co2_tile_status, history_segments, hum_tile_status,
                      temp_tile_status, tile_status_quality, voc_tile_status)
from .charts import HistoryChart
from .widgets import (AirGauge, Card, Pill, PillPicker, Sparkline, StatusDot,
                      centered_column, make_label, retheme_label)


class MetricTile(Card):
    """One 2x2-grid tile: caption, big value, status pill, 2 h sparkline."""
    clicked = pyqtSignal(str)

    def __init__(self, key: str, caption: str, color_key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._color_key = color_key
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.caption = make_label(caption, 9, QFont.Weight.DemiBold, "faint")
        top.addWidget(self.caption)
        top.addStretch()
        self.pill = Pill("--")
        self.pill.set_neutral()
        top.addWidget(self.pill)
        lay.addLayout(top)

        self.value = make_label("--", 22, QFont.Weight.DemiBold)
        lay.addWidget(self.value)
        self.spark = Sparkline(color_key, height=26)
        lay.addWidget(self.spark)
        theme.signals.changed.connect(self._retheme)

    def set_reading(self, value_text: str, status: str, quality: AirQuality):
        self.value.setText(value_text)
        self.pill.setText(status)
        self.pill.set_quality(quality)

    def _retheme(self):
        retheme_label(self.caption)
        retheme_label(self.value)


class DetailPage(QWidget):
    back = pyqtSignal()
    flash_requested = pyqtSignal(str)

    def __init__(self, manager: DeviceManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.device: Device | None = None
        self._range_s = 86_400
        self._metric: Metric = HISTORY_METRICS[0]
        self._build()
        theme.signals.changed.connect(self._retheme)

    # -- layout --------------------------------------------------------------

    LEFT_RAIL_WIDTH = 440

    def _build(self):
        outer = centered_column(self, 1680)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(10)

        header = QHBoxLayout()
        self.back_btn = QPushButton("←")
        self.back_btn.setObjectName("toolbtn")
        self.back_btn.setFixedSize(32, 32)
        self.back_btn.clicked.connect(self.back.emit)
        header.addWidget(self.back_btn)
        self.title = make_label("AirCube", 18, QFont.Weight.Bold)
        header.addWidget(self.title)
        self.type_pill = Pill("AirCube")
        self.type_pill.set_neutral()
        header.addWidget(self.type_pill)
        self.conn_dot = StatusDot()
        header.addWidget(self.conn_dot)
        self.conn_lbl = make_label("", 9, QFont.Weight.Normal, "faint")
        header.addWidget(self.conn_lbl)
        header.addStretch()
        self.menu_btn = QPushButton("⋯")
        self.menu_btn.setObjectName("toolbtn")
        self.menu_btn.setFixedSize(32, 32)
        self.menu_btn.clicked.connect(self._show_menu)
        header.addWidget(self.menu_btn)
        outer.addLayout(header)

        self.sync_bar = QProgressBar()
        self.sync_bar.setTextVisible(False)
        self.sync_bar.setFixedHeight(4)
        self.sync_bar.setVisible(False)
        outer.addWidget(self.sync_bar)

        # two-pane desktop layout: left rail (gauge, tiles, controls),
        # right side is one big history chart that fills the window
        body = QHBoxLayout()
        body.setSpacing(16)
        outer.addLayout(body, stretch=1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setFixedWidth(self.LEFT_RAIL_WIDTH)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 6, 4)
        lay.setSpacing(14)

        # hero card
        self.hero = Card()
        self.hero.setFixedHeight(200)
        hero_lay = QHBoxLayout(self.hero)
        hero_lay.setContentsMargins(18, 18, 18, 18)
        hero_left = QVBoxLayout()
        hero_left.setSpacing(6)
        self.hero_title = make_label("Air is …", 20, QFont.Weight.Bold)
        hero_left.addWidget(self.hero_title)
        self.hero_advice = make_label("", 11, QFont.Weight.Normal, "muted")
        self.hero_advice.setWordWrap(True)
        hero_left.addWidget(self.hero_advice)
        self.hero_pill = Pill("No action needed")
        self.hero_pill.set_neutral()
        hero_left.addWidget(self.hero_pill, alignment=Qt.AlignmentFlag.AlignLeft)
        hero_left.addStretch()
        hero_lay.addLayout(hero_left, stretch=1)
        self.gauge = AirGauge()
        hero_lay.addWidget(self.gauge)
        lay.addWidget(self.hero)

        # metric tiles 2x2
        tiles = QGridLayout()
        tiles.setSpacing(12)
        self.tile_co2 = MetricTile("co2", "CO2", "co2")
        self.tile_voc = MetricTile("voc", "VOC", "voc")
        self.tile_hum = MetricTile("hum", "HUMIDITY", "hum")
        self.tile_temp = MetricTile("temp", "TEMPERATURE", "temp")
        tiles.addWidget(self.tile_co2, 0, 0)
        tiles.addWidget(self.tile_voc, 0, 1)
        tiles.addWidget(self.tile_hum, 1, 0)
        tiles.addWidget(self.tile_temp, 1, 1)
        lay.addLayout(tiles)

        # history card (right pane: pickers in the header row, chart fills)
        self.hist_card = Card()
        hist_lay = QVBoxLayout(self.hist_card)
        hist_lay.setContentsMargins(18, 14, 18, 14)
        hist_lay.setSpacing(10)
        hist_header = QHBoxLayout()
        hist_header.setSpacing(12)
        self.hist_title = make_label("History", 13, QFont.Weight.DemiBold)
        hist_header.addWidget(self.hist_title)
        hist_header.addStretch()
        self.metric_picker = PillPicker([(m, m.label if m.key != "co2" else "CO2")
                                         for m in HISTORY_METRICS])
        self.metric_picker.selection_changed.connect(self._on_metric)
        hist_header.addWidget(self.metric_picker)
        self.range_picker = PillPicker([(s, label) for _, label, s in HISTORY_RANGES])
        self.range_picker.selection_changed.connect(self._on_range)
        hist_header.addWidget(self.range_picker)
        hist_lay.addLayout(hist_header)

        self.chart = HistoryChart(height=260)
        hist_lay.addWidget(self.chart, stretch=1)

        stats = QHBoxLayout()
        stats.setSpacing(24)
        self.stat_labels: list[tuple[QLabel, QLabel, QLabel]] = []
        for name in ("Peak", "Average", "Lowest"):
            box = QVBoxLayout()
            box.setSpacing(0)
            cap = make_label(name.upper(), 8, QFont.Weight.DemiBold, "faint")
            val = make_label("--", 13, QFont.Weight.DemiBold)
            when = make_label("", 8, QFont.Weight.Normal, "faint")
            box.addWidget(cap)
            box.addWidget(val)
            box.addWidget(when)
            stats.addLayout(box)
            self.stat_labels.append((cap, val, when))
        stats.addStretch()
        hist_lay.addLayout(stats)

        sync_row = QHBoxLayout()
        self.sync_status = make_label("", 9, QFont.Weight.Normal, "faint")
        sync_row.addWidget(self.sync_status)
        sync_row.addStretch()
        self.sync_btn = QPushButton("Sync from device")
        self.sync_btn.clicked.connect(self._sync_now)
        sync_row.addWidget(self.sync_btn)
        hist_lay.addLayout(sync_row)

        # brightness card
        self.bri_card = Card()
        bri_lay = QVBoxLayout(self.bri_card)
        bri_lay.setContentsMargins(18, 14, 18, 14)
        bri_lay.setSpacing(8)
        bri_header = QHBoxLayout()
        self.bri_title = make_label("LED brightness", 13, QFont.Weight.DemiBold)
        bri_header.addWidget(self.bri_title)
        bri_header.addStretch()
        self.bri_value = make_label("--%", 11, QFont.Weight.DemiBold, "muted")
        bri_header.addWidget(self.bri_value)
        bri_lay.addLayout(bri_header)
        self.bri_slider = QSlider(Qt.Orientation.Horizontal)
        self.bri_slider.setRange(0, 100)
        self.bri_slider.valueChanged.connect(
            lambda v: self.bri_value.setText(f"{v}%"))
        self.bri_slider.sliderReleased.connect(self._commit_brightness)
        bri_lay.addWidget(self.bri_slider)
        lay.addWidget(self.bri_card)

        # advanced drawer
        adv_card = Card()
        adv_lay = QVBoxLayout(adv_card)
        adv_lay.setContentsMargins(18, 14, 18, 14)
        adv_lay.setSpacing(8)
        self.adv_btn = QPushButton("Advanced data  ▸")
        self.adv_btn.setFlat(True)
        self.adv_btn.setStyleSheet("border: none; text-align: left; padding: 0;")
        self.adv_btn.clicked.connect(self._toggle_advanced)
        adv_lay.addWidget(self.adv_btn)
        self.adv_host = QWidget()
        adv_grid = QGridLayout(self.adv_host)
        adv_grid.setContentsMargins(0, 4, 0, 0)
        adv_grid.setHorizontalSpacing(30)
        adv_grid.setVerticalSpacing(6)
        self.adv_rows: dict[str, QLabel] = {}
        for i, (key, caption) in enumerate([
                ("eco2", "eCO2"), ("voc_level", "VOC Level index"),
                ("aqi_uba", "AQI (UBA)"), ("lux", "Ambient light"),
                ("fw", "Firmware"), ("transport", "Connection")]):
            cap = make_label(caption, 10, QFont.Weight.Normal, "muted")
            val = make_label("--", 10, QFont.Weight.DemiBold)
            adv_grid.addWidget(cap, i, 0)
            adv_grid.addWidget(val, i, 1)
            self.adv_rows[key] = val
        self.adv_host.setVisible(False)
        adv_lay.addWidget(self.adv_host)
        lay.addWidget(adv_card)

        lay.addStretch()
        scroll.setWidget(host)
        body.addWidget(scroll)
        body.addWidget(self.hist_card, stretch=1)

    # -- device wiring --------------------------------------------------------

    def set_device(self, device: Device):
        if self.device is not None:
            try:
                self.device.updated.disconnect(self._refresh_live)
                self.device.history_updated.disconnect(self._refresh_history)
                self.device.sync_state_changed.disconnect(self._refresh_sync)
                self.device.brightness_updated.disconnect(self._on_brightness)
            except TypeError:
                pass
        self.device = device
        device.updated.connect(self._refresh_live)
        device.history_updated.connect(self._refresh_history)
        device.sync_state_changed.connect(self._refresh_sync)
        device.brightness_updated.connect(self._on_brightness)
        self._metric = HISTORY_METRICS[0]
        self.metric_picker.set_selection(self._metric)
        self._refresh_live()
        self._refresh_history()
        self._refresh_sync()
        if device.led_percent is not None:
            self._on_brightness(device.led_percent)

    # -- handlers --------------------------------------------------------------

    def _on_metric(self, metric: Metric):
        self._metric = metric
        self._refresh_history()

    def _on_range(self, seconds: int):
        self._range_s = seconds
        self._refresh_history()

    def _sync_now(self):
        if self.device:
            self.manager.request_sync(self.device.device_id)

    def _commit_brightness(self):
        if self.device:
            self.manager.set_led(self.device, self.bri_slider.value())

    def _on_brightness(self, pct: int):
        if not self.bri_slider.isSliderDown():
            self.bri_slider.blockSignals(True)
            self.bri_slider.setValue(pct)
            self.bri_slider.blockSignals(False)
            self.bri_value.setText(f"{pct}%")

    def _toggle_advanced(self):
        show = not self.adv_host.isVisible()
        self.adv_host.setVisible(show)
        self.adv_btn.setText("Advanced data  ▾" if show else "Advanced data  ▸")

    def _show_menu(self):
        if self.device is None:
            return
        menu = QMenu(self)
        menu.addAction("Sync now", self._sync_now)
        menu.addAction("Export CSV…", self._export_csv)
        menu.addSeparator()
        menu.addAction("Rename…", self._rename)
        if self.device.transport == "serial":
            menu.addSeparator()
            menu.addAction("Flash firmware…",
                           lambda: self.flash_requested.emit(self.device.device_id))
        menu.addSeparator()
        menu.addAction("Forget device", self._forget)
        menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def _rename(self):
        name, ok = QInputDialog.getText(self, "Rename device", "Name:",
                                        text=self.device.name)
        if ok and name.strip():
            self.manager.rename_device(self.device.device_id, name)
            self.title.setText(name.strip())

    def _forget(self):
        ret = QMessageBox.question(
            self, "Forget device",
            f"Forget {self.device.name}? Cached history will be deleted.")
        if ret == QMessageBox.StandardButton.Yes:
            self.manager.forget_device(self.device.device_id)
            self.back.emit()

    def _export_csv(self):
        dev = self.device
        if dev is None:
            return
        default = os.path.join(os.path.expanduser("~/Documents"),
                               f"{dev.name}-history.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export history CSV", default,
                                              "CSV Files (*.csv)")
        if not path:
            return
        slots = sorted(dev.slots, key=lambda s: s.timestamp)
        try:
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp", "sequence",
                            "temp_avg_c", "temp_min_c", "temp_max_c",
                            "hum_avg", "hum_min", "hum_max",
                            "voc_avg", "voc_min", "voc_max",
                            "co2_avg", "co2_min", "co2_max",
                            "etvoc_avg", "etvoc_min", "etvoc_max"])
                for s in slots:
                    iso = datetime.fromtimestamp(s.timestamp).astimezone().isoformat()
                    w.writerow([iso, s.sequence,
                                s.temp_avg, s.temp_min, s.temp_max,
                                s.hum_avg, s.hum_min, s.hum_max,
                                s.voc_avg, s.voc_min, s.voc_max,
                                s.co2_avg, s.co2_min, s.co2_max,
                                s.etvoc_avg, s.etvoc_min, s.etvoc_max])
            QMessageBox.information(self, "Export CSV",
                                    f"Saved {len(slots)} entries to:\n{path}")
        except OSError as e:
            QMessageBox.warning(self, "Export CSV", f"Failed to write CSV: {e}")

    # -- refresh -------------------------------------------------------------------

    def _refresh_live(self):
        dev = self.device
        if dev is None:
            return
        use_f = self.manager.prefs.get("use_fahrenheit")
        self.title.setText(dev.name)
        self.type_pill.setText(dev.model_label)
        reading = dev.last_reading
        online = dev.is_online
        self.conn_dot.set_color(theme.color("good") if online else theme.color("faint"))
        self.conn_lbl.setText(("Connected · " if online else "Offline · ")
                              + dev.display_updated_ago())

        if reading is None:
            self.gauge.clear()
            self.hero_title.setText("Waiting for data…")
            self.hero_advice.setText("")
            self.hero.set_gradient(None)
            return

        q = reading.quality
        score = reading.air_score
        self.gauge.set_score(score, q)
        self.hero_title.setText(q.label)
        advice = {
            AirQuality.GOOD: "Everything looks great. Enjoy the fresh air.",
            AirQuality.FAIR: "Air quality is slightly elevated. A bit of fresh air wouldn't hurt.",
            AirQuality.POOR: "Air quality is poor. Open a window or increase ventilation.",
            AirQuality.BAD: "Air quality is bad. Ventilate this room now.",
        }[q]
        self.hero_advice.setText(advice)
        self.hero_pill.setText("No action needed" if q == AirQuality.GOOD
                               else "Ventilation recommended")
        self.hero_pill.set_quality(q)
        self.hero.set_gradient(theme.quality_color(q))

        # tiles
        if dev.is_pro:
            self.tile_co2.caption.setText("CO2")
            co2_val = reading.co2
        else:
            self.tile_co2.caption.setText("eCO2")
            co2_val = reading.eco2
        self.tile_co2.set_reading(f"{co2_val} ppm", co2_tile_status(co2_val),
                                  tile_status_quality("co2", co2_val))
        self.tile_voc.set_reading(f"{reading.etvoc} ppb", voc_tile_status(reading.etvoc),
                                  tile_status_quality("voc", reading.etvoc))
        self.tile_hum.set_reading(f"{reading.humidity:.0f}%",
                                  hum_tile_status(reading.humidity),
                                  tile_status_quality("hum", reading.humidity))
        temp_txt = (f"{c_to_f(reading.temperature_c):.1f}°F" if use_f
                    else f"{reading.temperature_c:.1f}°C")
        self.tile_temp.set_reading(temp_txt, temp_tile_status(reading.temperature_c),
                                   tile_status_quality("temp", reading.temperature_c))

        # advanced
        self.adv_rows["eco2"].setText(f"{reading.eco2} ppm")
        self.adv_rows["voc_level"].setText(str(reading.voc_level))
        self.adv_rows["aqi_uba"].setText(str(reading.aqi_uba) if reading.aqi_uba else "--")
        self.adv_rows["lux"].setText(f"{reading.lux:.0f} lx" if dev.is_pro else "n/a")
        self.adv_rows["fw"].setText(dev.fw_version or "--")
        self.adv_rows["transport"].setText(
            f"{'USB' if dev.transport == 'serial' else 'Bluetooth'} ({dev.address})")

        self.bri_card.setVisible(dev.connection is not None)

    def _refresh_history(self):
        dev = self.device
        if dev is None:
            return
        use_f = self.manager.prefs.get("use_fahrenheit")
        metric = self._metric
        now = time.time()
        slots = dev.slots_in_range(self._range_s)
        floor = metric.valid_floor()
        valid = [s for s in slots if metric.slot_values(s)[0] > floor]

        def val(s):
            v = metric.slot_values(s)[0]
            if metric.key == "temp" and use_f:
                return c_to_f(v)
            return v

        segments_pts = [[(s.timestamp, val(s)) for s in seg]
                        for seg in history_segments(valid)]
        unit = metric.unit
        if metric.key == "temp":
            unit = "°F" if use_f else "°C"
        fmt = (lambda v: f"{v:.1f}") if metric.key in ("temp", "hum") else (lambda v: f"{v:.0f}")
        self.chart.set_data(segments_pts, theme.color(metric.color_key),
                            f" {unit}" if unit and not unit.startswith("°") else unit,
                            now - self._range_s, now, fmt)

        # sparkline tiles (2h)
        spark = dev.sparkline_slots(24)
        self.tile_co2.spark.set_data([float(s.co2_avg) for s in spark if s.co2_avg > 300])
        self.tile_voc.spark.set_data([float(s.etvoc_avg) for s in spark if s.etvoc_avg > 0])
        self.tile_hum.spark.set_data([s.hum_avg for s in spark if s.hum_avg > 0])
        temps = [s.temp_avg for s in spark if s.temp_avg != 0]
        self.tile_temp.spark.set_data([c_to_f(t) for t in temps] if use_f else temps)

        # stats
        if valid:
            pairs = [(val(s), s.timestamp) for s in valid]
            peak = max(pairs, key=lambda p: p[0])
            low = min(pairs, key=lambda p: p[0])
            avg = sum(p[0] for p in pairs) / len(pairs)
            for (cap, v_lbl, when), (v, t) in zip(
                    self.stat_labels, [peak, (avg, None), low]):
                v_lbl.setText(fmt(v) + (unit if unit.startswith("°") else f" {unit}"))
                when.setText(datetime.fromtimestamp(t).strftime("%a %H:%M") if t else "")
        else:
            for cap, v_lbl, when in self.stat_labels:
                v_lbl.setText("--")
                when.setText("")

        if dev.last_synced_at:
            self.sync_status.setText(
                f"{len(dev.slots)} entries · synced "
                f"{datetime.fromtimestamp(dev.last_synced_at).strftime('%H:%M:%S')}")
        else:
            self.sync_status.setText("No history synced yet")

    def _refresh_sync(self):
        dev = self.device
        if dev is None:
            return
        self.sync_bar.setVisible(dev.is_syncing)
        cur, total = dev.sync_progress
        if total > 0:
            self.sync_bar.setRange(0, total)
            self.sync_bar.setValue(cur)
        else:
            self.sync_bar.setRange(0, 0)
        self.sync_btn.setEnabled(not dev.is_syncing and dev.is_connected)
        if dev.sync_error:
            self.sync_status.setText(f"Sync failed: {dev.sync_error}")

    def _retheme(self):
        for lbl in (self.title, self.conn_lbl, self.hero_title, self.hero_advice,
                    self.hist_title, self.sync_status, self.bri_title, self.bri_value):
            retheme_label(lbl)
        for cap, val, when in self.stat_labels:
            retheme_label(cap)
            retheme_label(val)
            retheme_label(when)
        for lbl in self.adv_rows.values():
            retheme_label(lbl)
        self.type_pill.set_neutral()
        self._refresh_live()
        self._refresh_history()
