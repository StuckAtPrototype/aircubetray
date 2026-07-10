"""Settings + notification settings pages (iOS SettingsView port)."""
from __future__ import annotations

import sys
import webbrowser

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
                             QWidget)

from .. import __version__, theme
from ..manager import DeviceManager
from ..store import Prefs
from .widgets import (Card, PillPicker, ToggleSwitch, centered_column,
                      make_label, retheme_label)

SITE_URL = "https://stuckatprototype.com"


def _row(label_text: str, control: QWidget, sub: str = "") -> QWidget:
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 4, 0, 4)
    box = QVBoxLayout()
    box.setSpacing(0)
    lbl = make_label(label_text, 12)
    box.addWidget(lbl)
    if sub:
        box.addWidget(make_label(sub, 9, QFont.Weight.Normal, "faint"))
    lay.addLayout(box)
    lay.addStretch()
    lay.addWidget(control)
    return host


class SettingsPage(QWidget):
    back = pyqtSignal()
    open_notifications = pyqtSignal()
    open_flash = pyqtSignal()
    appearance_changed = pyqtSignal(str)
    units_changed = pyqtSignal()

    def __init__(self, manager: DeviceManager, prefs: Prefs, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.prefs = prefs
        self._build()
        theme.signals.changed.connect(self._retheme)

    def _card(self, title: str) -> tuple[Card, QVBoxLayout]:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)
        lbl = make_label(title.upper(), 9, QFont.Weight.DemiBold, "faint")
        lay.addWidget(lbl)
        self._section_labels.append(lbl)
        return card, lay

    def _build(self):
        self._section_labels: list[QLabel] = []
        outer = centered_column(self)
        outer.setContentsMargins(20, 16, 20, 0)
        outer.setSpacing(12)

        header = QHBoxLayout()
        back_btn = QPushButton("←")
        back_btn.setObjectName("toolbtn")
        back_btn.setFixedSize(32, 32)
        back_btn.clicked.connect(self.back.emit)
        header.addWidget(back_btn)
        self.title = make_label("Settings", 20, QFont.Weight.Bold)
        header.addWidget(self.title)
        header.addStretch()
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 6, 16)
        lay.setSpacing(14)

        # notifications
        card, clay = self._card("Notifications")
        notif_btn = QPushButton(
            "Alerts: " + ("On" if self.prefs.get("notif.enabled") else "Off") + "  ›")
        notif_btn.setFlat(True)
        notif_btn.setStyleSheet("border:none; text-align:left; padding: 4px 0;")
        notif_btn.clicked.connect(self.open_notifications.emit)
        self.notif_btn = notif_btn
        clay.addWidget(notif_btn)
        lay.addWidget(card)

        # display
        card, clay = self._card("Display")
        self.unit_picker = PillPicker([(True, "Fahrenheit"), (False, "Celsius")], fill=True)
        self.unit_picker.set_selection(self.prefs.get("use_fahrenheit"))
        self.unit_picker.selection_changed.connect(self._on_units)
        clay.addWidget(_row("Temperature unit", self.unit_picker))

        self.appearance_picker = PillPicker(
            [("dark", "Dark"), ("light", "Light"), ("system", "System")], fill=True)
        self.appearance_picker.set_selection(self.prefs.get("appearance"))
        self.appearance_picker.selection_changed.connect(self._on_appearance)
        clay.addWidget(_row("Appearance", self.appearance_picker))
        lay.addWidget(card)

        # app behavior
        card, clay = self._card("App")
        self.launch_picker = PillPicker([("tray", "Tray"), ("window", "Window")],
                                        fill=True)
        self.launch_picker.set_selection(self.prefs.get("launch_mode"))
        self.launch_picker.selection_changed.connect(
            lambda v: self.prefs.set("launch_mode", v))
        clay.addWidget(_row("Launch mode", self.launch_picker,
                            "Tray starts in the system tray; open the window "
                            "from the tray icon anytime"))

        self.autostart_toggle = ToggleSwitch()
        self.autostart_toggle.setChecked(self.prefs.get("autostart"))
        self.autostart_toggle.toggled.connect(self._on_autostart)
        clay.addWidget(_row("Start with Windows", self.autostart_toggle))
        lay.addWidget(card)

        # firmware
        card, clay = self._card("Firmware")
        flash_btn = QPushButton("Flash firmware…")
        flash_btn.clicked.connect(self.open_flash.emit)
        clay.addWidget(_row("Update or flash a connected cube (USB)", flash_btn))
        lay.addWidget(card)

        # reset
        card, clay = self._card("Reset options")
        clear_btn = QPushButton("Clear cached history")
        clear_btn.clicked.connect(self._clear_history)
        clay.addWidget(_row("Delete synced history for all devices", clear_btn))
        reset_btn = QPushButton("Reset app")
        reset_btn.clicked.connect(self._reset_app)
        clay.addWidget(_row("Forget all devices and restore defaults", reset_btn))
        lay.addWidget(card)

        # about
        card, clay = self._card("About")
        about_lbl = make_label("Made by StuckAtPrototype", 12)
        clay.addWidget(about_lbl)
        self.about_lbl = about_lbl
        site_btn = QPushButton("Visit website")
        site_btn.clicked.connect(lambda: webbrowser.open(SITE_URL))
        clay.addWidget(_row("stuckatprototype.com", site_btn))
        version_lbl = make_label(f"AirCube for Windows · v{__version__}", 9,
                                 QFont.Weight.Normal, "faint")
        clay.addWidget(version_lbl)
        self.version_lbl = version_lbl
        lay.addWidget(card)

        lay.addStretch()
        scroll.setWidget(host)
        outer.addWidget(scroll, stretch=1)

    def refresh(self):
        self.notif_btn.setText(
            "Alerts: " + ("On" if self.prefs.get("notif.enabled") else "Off") + "  ›")

    def _on_units(self, use_f: bool):
        self.prefs.set("use_fahrenheit", use_f)
        self.units_changed.emit()

    def _on_appearance(self, mode: str):
        self.prefs.set("appearance", mode)
        self.appearance_changed.emit(mode)

    def _on_autostart(self, enabled: bool):
        self.prefs.set("autostart", enabled)
        if sys.platform != "win32":
            return
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            if enabled:
                winreg.SetValueEx(key, "AirCubeTray", 0, winreg.REG_SZ, sys.executable)
            else:
                try:
                    winreg.DeleteValue(key, "AirCubeTray")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except OSError:
            pass

    def _clear_history(self):
        ret = QMessageBox.question(self, "Clear cached history",
                                   "Delete synced history for all devices?")
        if ret == QMessageBox.StandardButton.Yes:
            self.manager.store.clear_history()
            for dev in self.manager.devices.values():
                dev.slots = []
                dev.history_updated.emit()

    def _reset_app(self):
        ret = QMessageBox.question(
            self, "Reset app",
            "Forget all devices, delete history, and restore defaults?")
        if ret == QMessageBox.StandardButton.Yes:
            for device_id in list(self.manager.devices):
                self.manager.forget_device(device_id)
            self.prefs.reset_all()
            QMessageBox.information(self, "Reset app",
                                    "App reset. Devices will reappear when detected.")

    def _retheme(self):
        retheme_label(self.title)
        retheme_label(self.about_lbl)
        retheme_label(self.version_lbl)
        for lbl in self._section_labels:
            retheme_label(lbl)


class NotificationSettingsPage(QWidget):
    back = pyqtSignal()

    def __init__(self, manager: DeviceManager, prefs: Prefs, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.prefs = prefs
        self._build()
        theme.signals.changed.connect(self._retheme)

    def _build(self):
        self._labels: list[QLabel] = []
        outer = centered_column(self)
        outer.setContentsMargins(20, 16, 20, 0)
        outer.setSpacing(12)

        header = QHBoxLayout()
        back_btn = QPushButton("←")
        back_btn.setObjectName("toolbtn")
        back_btn.setFixedSize(32, 32)
        back_btn.clicked.connect(self.back.emit)
        header.addWidget(back_btn)
        self.title = make_label("Notifications", 20, QFont.Weight.Bold)
        header.addWidget(self.title)
        header.addStretch()
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 6, 16)
        lay.setSpacing(14)

        def card(title: str):
            c = Card()
            cl = QVBoxLayout(c)
            cl.setContentsMargins(18, 14, 18, 14)
            cl.setSpacing(4)
            lbl = make_label(title.upper(), 9, QFont.Weight.DemiBold, "faint")
            self._labels.append(lbl)
            cl.addWidget(lbl)
            lay.addWidget(c)
            return cl

        # master
        clay = card("Alerts")
        self.enabled = ToggleSwitch()
        self.enabled.setChecked(self.prefs.get("notif.enabled"))
        self.enabled.toggled.connect(lambda v: self.prefs.set("notif.enabled", v))
        clay.addWidget(_row("Air quality alerts", self.enabled,
                            "Notify when CO2 or VOC stays above your thresholds"))

        # thresholds
        clay = card("Thresholds")
        self.co2_spin = QSpinBox()
        self.co2_spin.setRange(600, 5000)
        self.co2_spin.setSingleStep(100)
        self.co2_spin.setSuffix(" ppm")
        self.co2_spin.setValue(self.prefs.get("notif.co2_threshold"))
        self.co2_spin.valueChanged.connect(lambda v: self.prefs.set("notif.co2_threshold", v))
        clay.addWidget(_row("CO2 threshold (Pro)", self.co2_spin))

        self.voc_spin = QSpinBox()
        self.voc_spin.setRange(100, 5000)
        self.voc_spin.setSingleStep(50)
        self.voc_spin.setSuffix(" ppb")
        self.voc_spin.setValue(self.prefs.get("notif.voc_threshold"))
        self.voc_spin.valueChanged.connect(lambda v: self.prefs.set("notif.voc_threshold", v))
        clay.addWidget(_row("VOC threshold", self.voc_spin))

        self.dwell_spin = QSpinBox()
        self.dwell_spin.setRange(1, 60)
        self.dwell_spin.setSuffix(" min")
        self.dwell_spin.setValue(self.prefs.get("notif.dwell_minutes"))
        self.dwell_spin.valueChanged.connect(lambda v: self.prefs.set("notif.dwell_minutes", v))
        clay.addWidget(_row("Dwell", self.dwell_spin,
                            "How long a level must stay high before alerting"))

        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(5, 720)
        self.cooldown_spin.setSingleStep(5)
        self.cooldown_spin.setSuffix(" min")
        self.cooldown_spin.setValue(self.prefs.get("notif.cooldown_minutes"))
        self.cooldown_spin.valueChanged.connect(
            lambda v: self.prefs.set("notif.cooldown_minutes", v))
        clay.addWidget(_row("Cooldown", self.cooldown_spin,
                            "Minimum time between repeat alerts"))

        self.all_clear = ToggleSwitch()
        self.all_clear.setChecked(self.prefs.get("notif.all_clear"))
        self.all_clear.toggled.connect(lambda v: self.prefs.set("notif.all_clear", v))
        clay.addWidget(_row("All-clear notification", self.all_clear,
                            "Notify when levels return to good"))

        # connection alerts
        clay = card("Connection")
        self.offline = ToggleSwitch()
        self.offline.setChecked(self.prefs.get("notif.offline_enabled"))
        self.offline.toggled.connect(lambda v: self.prefs.set("notif.offline_enabled", v))
        clay.addWidget(_row("Offline alerts", self.offline))

        self.offline_spin = QSpinBox()
        self.offline_spin.setRange(5, 720)
        self.offline_spin.setSingleStep(5)
        self.offline_spin.setSuffix(" min")
        self.offline_spin.setValue(self.prefs.get("notif.offline_after_minutes"))
        self.offline_spin.valueChanged.connect(
            lambda v: self.prefs.set("notif.offline_after_minutes", v))
        clay.addWidget(_row("Alert after offline for", self.offline_spin))

        # quiet hours
        clay = card("Quiet hours")
        self.quiet = ToggleSwitch()
        self.quiet.setChecked(self.prefs.get("notif.quiet_enabled"))
        self.quiet.toggled.connect(lambda v: self.prefs.set("notif.quiet_enabled", v))
        clay.addWidget(_row("Quiet hours", self.quiet))

        self.quiet_start = QComboBox()
        self.quiet_end = QComboBox()
        for h in range(24):
            label = f"{h:02d}:00"
            self.quiet_start.addItem(label, h)
            self.quiet_end.addItem(label, h)
        self.quiet_start.setCurrentIndex(self.prefs.get("notif.quiet_start_hour"))
        self.quiet_end.setCurrentIndex(self.prefs.get("notif.quiet_end_hour"))
        self.quiet_start.currentIndexChanged.connect(
            lambda i: self.prefs.set("notif.quiet_start_hour", i))
        self.quiet_end.currentIndexChanged.connect(
            lambda i: self.prefs.set("notif.quiet_end_hour", i))
        clay.addWidget(_row("From", self.quiet_start))
        clay.addWidget(_row("Until", self.quiet_end))

        # per-device mute
        clay = card("Per-device mute")
        self._mute_layout = clay

        # reset
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        lay.addWidget(reset_btn)

        lay.addStretch()
        scroll.setWidget(host)
        outer.addWidget(scroll, stretch=1)

    def refresh(self):
        # rebuild per-device mute rows
        while self._mute_layout.count() > 1:
            item = self._mute_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        for dev in self.manager.sorted_devices():
            toggle = ToggleSwitch()
            toggle.setChecked(self.prefs.device_muted(dev.device_id))
            toggle.toggled.connect(
                lambda v, d=dev.device_id: self.prefs.set_device_muted(d, v))
            self._mute_layout.addWidget(_row(f"Mute {dev.name}", toggle))

    def _reset_defaults(self):
        self.prefs.reset_notifications()
        self.enabled.setChecked(self.prefs.get("notif.enabled"))
        self.co2_spin.setValue(self.prefs.get("notif.co2_threshold"))
        self.voc_spin.setValue(self.prefs.get("notif.voc_threshold"))
        self.dwell_spin.setValue(self.prefs.get("notif.dwell_minutes"))
        self.cooldown_spin.setValue(self.prefs.get("notif.cooldown_minutes"))
        self.all_clear.setChecked(self.prefs.get("notif.all_clear"))
        self.offline.setChecked(self.prefs.get("notif.offline_enabled"))
        self.offline_spin.setValue(self.prefs.get("notif.offline_after_minutes"))
        self.quiet.setChecked(self.prefs.get("notif.quiet_enabled"))
        self.quiet_start.setCurrentIndex(self.prefs.get("notif.quiet_start_hour"))
        self.quiet_end.setCurrentIndex(self.prefs.get("notif.quiet_end_hour"))

    def _retheme(self):
        retheme_label(self.title)
        for lbl in self._labels:
            retheme_label(lbl)
