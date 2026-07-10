"""Main window: stacked Home / Detail / Compare / Settings pages."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent, QIcon
from PyQt6.QtWidgets import QMainWindow, QStackedWidget

from .. import theme
from ..manager import DeviceManager
from ..store import Prefs
from .add_device import AddDeviceDialog
from .compare import ComparePage
from .detail import DetailPage
from .flash_dialog import FlashDialog
from .home import HomePage
from .settings import NotificationSettingsPage, SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, manager: DeviceManager, prefs: Prefs,
                 apply_appearance, icon: QIcon):
        super().__init__()
        self.manager = manager
        self.prefs = prefs
        self._apply_appearance = apply_appearance
        self.setWindowTitle("AirCube")
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.resize(1200, 800)
        self.setMinimumSize(900, 620)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.home = HomePage(manager)
        self.detail = DetailPage(manager)
        self.compare = ComparePage(manager)
        self.settings = SettingsPage(manager, prefs)
        self.notif = NotificationSettingsPage(manager, prefs)
        for page in (self.home, self.detail, self.compare, self.settings, self.notif):
            self.stack.addWidget(page)

        self.home.open_detail.connect(self.show_detail)
        self.home.open_compare.connect(self.show_compare)
        self.home.open_settings.connect(self.show_settings)
        self.home.open_add.connect(self.show_add_device)

        self.detail.back.connect(self.show_home)
        self.detail.flash_requested.connect(self.show_flash)
        self.compare.back.connect(self.show_home)
        self.settings.back.connect(self.show_home)
        self.settings.open_notifications.connect(self.show_notifications)
        self.settings.open_flash.connect(lambda: self.show_flash(None))
        self.settings.appearance_changed.connect(self._apply_appearance)
        self.settings.units_changed.connect(self._refresh_all)
        self.notif.back.connect(self.show_settings_refresh)

        self._retheme()
        theme.signals.changed.connect(self._retheme)

    # -- navigation ------------------------------------------------------------

    def show_home(self):
        self.stack.setCurrentWidget(self.home)

    def show_detail(self, device_id: str):
        dev = self.manager.devices.get(device_id)
        if dev is None:
            return
        self.detail.set_device(dev)
        self.stack.setCurrentWidget(self.detail)
        self.manager.request_sync(device_id)

    def show_compare(self):
        self.compare.refresh()
        self.stack.setCurrentWidget(self.compare)

    def show_settings(self):
        self.settings.refresh()
        self.stack.setCurrentWidget(self.settings)

    def show_settings_refresh(self):
        self.settings.refresh()
        self.stack.setCurrentWidget(self.settings)

    def show_notifications(self):
        self.notif.refresh()
        self.stack.setCurrentWidget(self.notif)

    def show_add_device(self):
        dlg = AddDeviceDialog(self.manager, self)
        dlg.exec()

    def show_flash(self, device_id: str | None = None):
        dlg = FlashDialog(self.manager, self, preselect_device_id=device_id)
        dlg.exec()

    def open_and_raise(self, device_id: str | None = None):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        if device_id:
            self.show_detail(device_id)
        self.manager.request_sync_all()

    # -- theme ----------------------------------------------------------------

    def _retheme(self):
        self.setStyleSheet(theme.app_stylesheet())

    def _refresh_all(self):
        for card in self.home._cards.values():
            card.refresh()
            card.refresh_sparkline()
        if self.detail.device is not None:
            self.detail._refresh_live()
            self.detail._refresh_history()
        self.compare.refresh()

    # -- close = minimize to tray -----------------------------------------------

    def closeEvent(self, event: QCloseEvent):
        event.ignore()
        self.hide()
