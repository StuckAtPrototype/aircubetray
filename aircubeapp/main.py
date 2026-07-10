"""App bootstrap: tray + window, theme, alerts."""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

SINGLE_INSTANCE_KEY = "AirCubeTray-single-instance"


def _signal_existing_instance() -> bool:
    """True if another instance is running (and was asked to show itself)."""
    sock = QLocalSocket()
    sock.connectToServer(SINGLE_INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False

from . import theme
from .alerts import AlertEngine
from .manager import DeviceManager
from .store import HistoryStore, Prefs
from .ui.main_window import MainWindow
from .ui.tray import TrayIcon, load_app_icon


def _system_prefers_dark(app: QApplication) -> bool:
    scheme = app.styleHints().colorScheme()
    return scheme != Qt.ColorScheme.Light


def main() -> int:
    # Hide the console window when launched as a script on Windows
    if sys.platform == "win32":
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setApplicationName("AirCube")
    app.setOrganizationName("StuckAtPrototype")

    # Only one instance may own the serial ports: a second launch just tells
    # the running instance to show its window, then exits.
    if _signal_existing_instance():
        return 0
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)  # clear stale socket after crash
    single_server = QLocalServer()
    single_server.listen(SINGLE_INSTANCE_KEY)

    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    prefs = Prefs()
    store = HistoryStore()
    manager = DeviceManager(store, prefs)

    def apply_appearance(mode: str | None = None):
        mode = mode or prefs.get("appearance")
        dark = _system_prefers_dark(app) if mode == "system" else (mode != "light")
        theme.set_mode(dark)

    theme.set_mode(True)
    apply_appearance()

    window = MainWindow(manager, prefs, apply_appearance, icon)

    def _on_second_instance():
        conn = single_server.nextPendingConnection()
        if conn is not None:
            conn.readAll()
            conn.disconnectFromServer()
        window.open_and_raise()

    single_server.newConnection.connect(_on_second_instance)

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = TrayIcon(manager)
        tray.open_app.connect(window.open_and_raise)
        tray.open_device.connect(lambda d: window.open_and_raise(d))

        def quit_app():
            tray.hide()
            manager.shutdown()
            store.close()
            app.quit()

        tray.quit_requested.connect(quit_app)
        tray.show()
        # Windows 11 tucks new tray icons into the overflow; promote ours so
        # the air-score badge is actually visible on the taskbar.
        from PyQt6.QtCore import QTimer
        from .ui.tray import promote_tray_icon
        QTimer.singleShot(2000, promote_tray_icon)

        def notify(title: str, body: str, warning: bool):
            tray.showMessage(
                title, body,
                QSystemTrayIcon.MessageIcon.Warning if warning
                else QSystemTrayIcon.MessageIcon.Information,
                6000)

        engine = AlertEngine(manager, prefs, notify)
        window._alert_engine = engine  # keep alive
        window._tray = tray
    else:
        QMessageBox.warning(None, "AirCube",
                            "System tray unavailable; running window-only.")
        app.setQuitOnLastWindowClosed(True)

    # honor system theme changes while in "system" mode
    app.styleHints().colorSchemeChanged.connect(
        lambda _s: apply_appearance() if prefs.get("appearance") == "system" else None)

    if prefs.get("launch_mode") == "window" or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show()

    _install_dev_hooks(window, prefs)

    return app.exec()


def _install_dev_hooks(window: MainWindow, prefs: Prefs) -> None:
    """Optional dev navigation via AIRCUBE_DEV env var (used for UI checks)."""
    import os
    target = os.environ.get("AIRCUBE_DEV")
    if not target:
        return
    from PyQt6.QtCore import QTimer

    def go():
        if target == "popup":
            tray = getattr(window, "_tray", None)
            if tray is not None:
                tray.popup.show_at_cursor()

                def snap():
                    tray.popup.grab().save("popup_shot.png")
                QTimer.singleShot(1500, snap)
            return
        window.open_and_raise()
        if target.startswith("addble:"):
            window.manager.add_ble_device(target.split(":", 1)[1], "")
        elif target == "light":
            theme.set_mode(False)
        elif target == "detail":
            devs = window.manager.sorted_devices()
            if devs:
                window.show_detail(devs[0].device_id)
        elif target == "detail2":
            devs = window.manager.sorted_devices()
            if len(devs) > 1:
                window.show_detail(devs[1].device_id)
        elif target == "compare":
            window.show_compare()
        elif target == "settings":
            window.show_settings()
        elif target == "notif":
            window.show_notifications()
        elif target == "light-detail":
            theme.set_mode(False)
            devs = window.manager.sorted_devices()
            if devs:
                window.show_detail(devs[0].device_id)

    QTimer.singleShot(6000, go)
