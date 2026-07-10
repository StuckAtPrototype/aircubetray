"""Add-device dialog: BLE scan (filtered on the AirCube service) + serial info."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel,
                             QListWidget, QListWidgetItem, QPushButton,
                             QVBoxLayout)

from .. import theme
from ..manager import DeviceManager
from ..transports.ble_transport import BleScanner
from .widgets import make_label


class AddDeviceDialog(QDialog):
    def __init__(self, manager: DeviceManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Add AirCube")
        self.setMinimumSize(400, 420)
        self._scanner: BleScanner | None = None
        self._found: dict[str, tuple[str, int]] = {}
        self._build()
        self._start_scan()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        lay.addWidget(make_label("Add over Bluetooth", 15, QFont.Weight.Bold))
        hint = make_label(
            "USB cubes connect automatically when plugged in — no setup needed.\n"
            "Scanning for nearby AirCubes over Bluetooth…", 10,
            QFont.Weight.Normal, "muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.hint = hint

        self.list = QListWidget()
        self.list.setStyleSheet(f"""
            QListWidget {{
                background: {theme.css('card')};
                border: 1px solid {theme.css('card_border')};
                border-radius: 12px;
                padding: 6px;
            }}
            QListWidget::item {{ padding: 10px; border-radius: 8px; }}
            QListWidget::item:selected {{ background: {theme.css('pill_track')};
                                          color: {theme.css('text')}; }}
        """)
        self.list.itemDoubleClicked.connect(lambda _: self._add_selected())
        lay.addWidget(self.list, stretch=1)

        self.status = make_label("Scanning…", 10, QFont.Weight.Normal, "faint")
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        self.rescan_btn = QPushButton("Scan again")
        self.rescan_btn.setEnabled(False)
        self.rescan_btn.clicked.connect(self._start_scan)
        btns.addWidget(self.rescan_btn)
        btns.addStretch()
        add_btn = QPushButton("Add")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_selected)
        btns.addWidget(add_btn)
        close_btn = QPushButton("Done")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

    def _start_scan(self):
        self.rescan_btn.setEnabled(False)
        self.status.setText("Scanning…")
        self._scanner = BleScanner()
        self._scanner.device_found.connect(self._on_found)
        self._scanner.finished.connect(self._on_finished)
        self._scanner.error.connect(self._on_error)
        self._scanner.scan(6.0)

    def _on_found(self, address: str, name: str, rssi: int):
        self._found[address] = (name, rssi)
        # refresh list
        self.list.clear()
        for addr, (nm, rs) in sorted(self._found.items(),
                                     key=lambda kv: -kv[1][1]):
            dev = self.manager.devices.get(addr.lower())
            if dev is not None:
                suffix = f"  (known as {dev.name})"
                nm = dev.name
            else:
                suffix = ""
            item = QListWidgetItem(f"{nm}   {addr}   {rs} dBm{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, addr)
            self.list.addItem(item)

    def _on_finished(self):
        self.rescan_btn.setEnabled(True)
        n = len(self._found)
        self.status.setText(f"Found {n} AirCube{'s' if n != 1 else ''}"
                            if n else "No AirCubes found. Is the cube powered and "
                                      "not commissioned to Zigbee?")

    def _on_error(self, message: str):
        self.rescan_btn.setEnabled(True)
        self.status.setText(f"Bluetooth error: {message}")

    def _add_selected(self):
        item = self.list.currentItem()
        if item is None:
            return
        address = item.data(Qt.ItemDataRole.UserRole)
        default_name = self._found.get(address, ("AirCube", 0))[0]
        name, ok = QInputDialog.getText(self, "Name this AirCube",
                                        "Name:", text=default_name)
        if not ok:
            return
        self.manager.add_ble_device(address, name.strip() or default_name)
        self.status.setText(f"Added {name.strip() or default_name}. Connecting…")
