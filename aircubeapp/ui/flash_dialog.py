"""Firmware flash dialog: pick a device (USB), pick firmware (GitHub release
or custom .bin), flash via esptool, then reconnect."""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QMessageBox, QProgressBar, QPushButton,
                             QTextEdit, QVBoxLayout, QWidget)

from .. import theme
from ..manager import DeviceManager
from ..flash.flasher import FlashWorker
from ..flash.releases import FirmwareDownloader, FirmwareRelease, ReleaseFetcher
from .widgets import make_label


class FlashDialog(QDialog):
    def __init__(self, manager: DeviceManager, parent=None,
                 preselect_device_id: str | None = None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Flash firmware")
        self.setMinimumSize(560, 520)
        self._releases: list[FirmwareRelease] = []
        self._custom_path: str | None = None
        self._fetcher: ReleaseFetcher | None = None
        self._downloader: FirmwareDownloader | None = None
        self._worker: FlashWorker | None = None
        self._held_device_id: str | None = None
        self._build(preselect_device_id)
        self._fetch_releases()

    def _build(self, preselect: str | None):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        lay.addWidget(make_label("Flash firmware", 15, QFont.Weight.Bold))
        warn = make_label(
            "Flashing works over USB only. Settings on the cube are preserved. "
            "Do not unplug the cube while flashing.", 10, QFont.Weight.Normal, "muted")
        warn.setWordWrap(True)
        lay.addWidget(warn)

        # device picker
        dev_row = QHBoxLayout()
        dev_row.addWidget(make_label("Device", 11))
        self.device_combo = QComboBox()
        self._reload_devices(preselect)
        dev_row.addWidget(self.device_combo, stretch=1)
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(34)
        refresh_btn.clicked.connect(lambda: self._reload_devices(None))
        dev_row.addWidget(refresh_btn)
        lay.addLayout(dev_row)

        # firmware picker
        fw_row = QHBoxLayout()
        fw_row.addWidget(make_label("Firmware", 11))
        self.fw_combo = QComboBox()
        self.fw_combo.addItem("Fetching releases…", None)
        fw_row.addWidget(self.fw_combo, stretch=1)
        browse_btn = QPushButton("Custom .bin…")
        browse_btn.clicked.connect(self._browse)
        fw_row.addWidget(browse_btn)
        lay.addLayout(fw_row)

        self.fw_note = make_label("", 9, QFont.Weight.Normal, "faint")
        self.fw_note.setWordWrap(True)
        lay.addWidget(self.fw_note)

        # offset picker (only meaningful for custom bins)
        off_row = QHBoxLayout()
        off_row.addWidget(make_label("Flash offset", 11))
        self.offset_combo = QComboBox()
        self.offset_combo.addItem("0x0  (merged / release image)", 0x0)
        self.offset_combo.addItem("0x10000  (app-only build)", 0x10000)
        off_row.addWidget(self.offset_combo)
        off_row.addStretch()
        lay.addLayout(off_row)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 8))
        lay.addWidget(self.log, stretch=1)

        btns = QHBoxLayout()
        btns.addStretch()
        self.flash_btn = QPushButton("Flash")
        self.flash_btn.setObjectName("primary")
        self.flash_btn.clicked.connect(self._start)
        btns.addWidget(self.flash_btn)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        btns.addWidget(self.close_btn)
        lay.addLayout(btns)

    # -- device / firmware selection -------------------------------------------

    def _reload_devices(self, preselect: str | None):
        self.device_combo.clear()
        serial_devs = [d for d in self.manager.sorted_devices()
                       if d.transport == "serial"]
        for dev in serial_devs:
            fw = f" · fw {dev.fw_version}" if dev.fw_version else ""
            self.device_combo.addItem(f"{dev.name}  ({dev.address}){fw}",
                                      dev.device_id)
            if preselect and dev.device_id == preselect:
                self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
        if not serial_devs:
            self.device_combo.addItem("No USB AirCubes connected", None)

    def _fetch_releases(self):
        self._fetcher = ReleaseFetcher()
        self._fetcher.releases_ready.connect(self._on_releases)
        self._fetcher.error.connect(self._on_release_error)
        self._fetcher.start()

    def _on_releases(self, releases: list):
        self._releases = releases
        self.fw_combo.clear()
        if self._custom_path:
            self.fw_combo.addItem(f"Custom: {os.path.basename(self._custom_path)}",
                                  "custom")
        for i, rel in enumerate(releases):
            latest = "  (latest)" if i == 0 else ""
            size_mb = rel.size / (1024 * 1024)
            self.fw_combo.addItem(
                f"v{rel.version} — {rel.published_at} · {size_mb:.1f} MB{latest}", rel)
        if not releases and not self._custom_path:
            self.fw_combo.addItem("No releases found — use a custom .bin", None)
        self._on_fw_selected()
        self.fw_combo.currentIndexChanged.connect(self._on_fw_selected)

    def _on_release_error(self, message: str):
        self.fw_combo.clear()
        self.fw_combo.addItem("Could not fetch releases — use a custom .bin", None)
        self._append_log(f"Release fetch failed: {message}")

    def _on_fw_selected(self):
        data = self.fw_combo.currentData()
        if isinstance(data, FirmwareRelease):
            first_line = data.body.strip().splitlines()[0] if data.body.strip() else ""
            self.fw_note.setText(f"{data.name} — {first_line}")
            self.offset_combo.setCurrentIndex(0)
        elif data == "custom":
            self.fw_note.setText(self._custom_path or "")
        else:
            self.fw_note.setText("")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose firmware .bin", "",
                                              "Firmware (*.bin)")
        if not path:
            return
        self._custom_path = path
        if self.fw_combo.itemData(0) == "custom":
            self.fw_combo.setItemText(0, f"Custom: {os.path.basename(path)}")
        else:
            self.fw_combo.insertItem(0, f"Custom: {os.path.basename(path)}", "custom")
        self.fw_combo.setCurrentIndex(0)
        self._on_fw_selected()

    # -- flashing ------------------------------------------------------------------

    def _start(self):
        device_id = self.device_combo.currentData()
        if device_id is None:
            QMessageBox.warning(self, "Flash firmware",
                                "Connect an AirCube over USB first.")
            return
        data = self.fw_combo.currentData()
        if data == "custom":
            if not self._custom_path or not os.path.exists(self._custom_path):
                QMessageBox.warning(self, "Flash firmware", "Pick a valid .bin file.")
                return
            self._flash_file(device_id, self._custom_path)
        elif isinstance(data, FirmwareRelease):
            self._set_busy(True)
            self._append_log(f"Downloading {data.asset_name}…")
            self._downloader = FirmwareDownloader(data)
            self._downloader.progress.connect(self._on_download_progress)
            self._downloader.finished_ok.connect(
                lambda path, d=device_id: self._flash_file(d, path))
            self._downloader.error.connect(self._on_failed)
            self._downloader.start()
        else:
            QMessageBox.warning(self, "Flash firmware", "Pick a firmware first.")

    def _on_download_progress(self, received: int, total: int):
        self.progress.setVisible(True)
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(received)

    def _flash_file(self, device_id: str, path: str):
        self._set_busy(True)
        port = self.manager.hold_for_flash(device_id)
        if port is None:
            self._on_failed("Device is not connected over USB.")
            return
        self._held_device_id = device_id
        self._append_log(f"Flashing {os.path.basename(path)} to {port}…")
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        offset = self.offset_combo.currentData()
        self._worker = FlashWorker(port, path, offset)
        self._worker.log_line.connect(self._append_log)
        self._worker.progress_percent.connect(self.progress.setValue)
        self._worker.finished_ok.connect(self._on_success)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_success(self):
        self._append_log("Flash complete. Rebooting device…")
        self.progress.setValue(100)
        self._release_hold()
        self._set_busy(False)
        QMessageBox.information(self, "Flash firmware",
                                "Firmware flashed successfully. The cube is "
                                "rebooting and will reconnect automatically.")

    def _on_failed(self, message: str):
        self._append_log(f"FAILED: {message}")
        self._release_hold()
        self._set_busy(False)
        QMessageBox.warning(self, "Flash firmware", f"Flashing failed:\n{message}")

    def _release_hold(self):
        if self._held_device_id:
            self.manager.release_flash_hold(self._held_device_id)
            self._held_device_id = None

    def _set_busy(self, busy: bool):
        self.flash_btn.setEnabled(not busy)
        self.close_btn.setEnabled(not busy)
        self.device_combo.setEnabled(not busy)
        self.fw_combo.setEnabled(not busy)

    def _append_log(self, line: str):
        self.log.append(line)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            event.ignore()
            return
        self._release_hold()
        super().closeEvent(event)
