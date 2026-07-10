"""System tray: worst-score badge icon, quick popup, context menu."""
from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QCursor, QFont, QIcon, QImage,
                         QPainter, QPainterPath, QPixmap)
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMenu,
                             QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget)

from .. import theme
from ..manager import DeviceManager
from ..models import AirQuality, c_to_f
from .home import DeviceCard
from .widgets import make_label


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


def load_app_icon() -> QIcon:
    path = resource_path("aircube_tray.ico")
    if os.path.exists(path):
        return QIcon(path)
    return QIcon()


def promote_tray_icon() -> None:
    """Ask Windows 11 to show our tray icon on the taskbar instead of the
    hidden overflow. Best-effort: flips IsPromoted on our NotifyIconSettings
    entry (HKCU, so no elevation needed)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        exe = os.path.abspath(sys.executable).lower()
        root = r"Control Panel\NotifyIconSettings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root) as base:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(base, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                        f"{root}\\{sub}", 0,
                                        winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                        path, _ = winreg.QueryValueEx(key, "ExecutablePath")
                        if os.path.abspath(path).lower() == exe:
                            winreg.SetValueEx(key, "IsPromoted", 0,
                                              winreg.REG_DWORD, 1)
                except OSError:
                    continue
    except OSError:
        pass


def make_badge_icon(score: int | None, quality: AirQuality | None) -> QIcon:
    """Rounded square badge with the worst air score, iOS quality colors."""
    size = 64
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(2, 2, size - 4, size - 4), 14, 14)
    if score is None or quality is None:
        p.fillPath(path, QColor("#746D82"))
        text = "–"
    else:
        p.fillPath(path, theme.quality_color(quality))
        text = str(score)
    p.setPen(QColor("white"))
    f = QFont(theme.FONT_FAMILY, 26 if len(text) < 3 else 20)
    f.setWeight(QFont.Weight.Bold)
    p.setFont(f)
    p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return QIcon(QPixmap.fromImage(img))


class TrayPopup(QWidget):
    """Frameless popup mirroring the home screen: one DeviceCard per cube."""
    open_app = pyqtSignal()
    open_device = pyqtSignal(str)

    def __init__(self, manager: DeviceManager):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.manager = manager
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame()
        self.frame.setObjectName("popupframe")
        outer.addWidget(self.frame)
        self.lay = QVBoxLayout(self.frame)
        self.lay.setContentsMargins(16, 14, 16, 16)
        self.lay.setSpacing(12)
        self._restyle()
        theme.signals.changed.connect(self._restyle)

    def _restyle(self):
        # the popup is its own top-level window, so the MainWindow stylesheet
        # doesn't reach it — style everything it contains right here.
        # DeviceCards paint themselves; the window bg color goes behind them,
        # same layering as the home screen.
        self.frame.setStyleSheet(f"""
            QFrame#popupframe {{
                background-color: {theme.css('bg')};
                border-radius: 16px;
                border: 1px solid {theme.css('card_border')};
            }}
            QLabel {{ border: none; background: transparent; }}
            QPushButton {{
                background: {theme.css('accent')};
                border: none;
                border-radius: 10px;
                padding: 5px 14px;
                color: white;
                font-weight: 600;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {theme.css('accent_soft')}; }}
            QPushButton:pressed {{ background: {theme.css('accent', 0.8)}; }}
            QProgressBar {{
                background: {theme.css('pill_track')};
                border: none; border-radius: 2px;
            }}
            QProgressBar::chunk {{ background: {theme.css('accent')}; border-radius: 2px; }}
        """)

    def _clear(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    s = sub.takeAt(0)
                    if s.widget():
                        s.widget().deleteLater()

    def refresh(self):
        self._clear()
        title_row = QHBoxLayout()
        title_row.addWidget(make_label("AirCube", 14, QFont.Weight.Bold))
        title_row.addStretch()
        open_btn = QPushButton("Open app")
        open_btn.clicked.connect(lambda: (self.hide(), self.open_app.emit()))
        title_row.addWidget(open_btn)
        self.lay.addLayout(title_row)

        devices = self.manager.sorted_devices()
        if not devices:
            self.lay.addWidget(make_label("No AirCubes detected.", 11,
                                          QFont.Weight.Normal, "muted"))
            return

        for dev in devices:
            card = DeviceCard(dev, self.manager)
            card.clicked.connect(self._open_detail)
            self.lay.addWidget(card)

    def _open_detail(self, device_id: str):
        self.hide()
        self.open_device.emit(device_id)

    def show_at_cursor(self):
        self.refresh()
        # force a synchronous relayout so the size below is the real one
        # (deferred layout gave a stale sizeHint -> popup clipped off screen)
        self.lay.activate()
        self.adjustSize()
        self.resize(self.sizeHint())
        pos = QCursor.pos()
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        avail = screen.availableGeometry()
        w, h = self.width(), self.height()
        x = min(max(pos.x() - w // 2, avail.left() + 10), avail.right() - w - 10)
        y = pos.y() - h - 16
        if y < avail.top() + 10:
            y = pos.y() + 24
        y = min(y, avail.bottom() - h - 10)
        self.move(x, y)
        self.show()


class TrayIcon(QSystemTrayIcon):
    open_app = pyqtSignal()
    open_device = pyqtSignal(str)
    quit_requested = pyqtSignal()

    def __init__(self, manager: DeviceManager):
        super().__init__()
        self.manager = manager
        self.app_icon = load_app_icon()
        if not self.app_icon.isNull():
            self.setIcon(self.app_icon)

        self.popup = TrayPopup(manager)
        self.popup.open_app.connect(self.open_app.emit)
        self.popup.open_device.connect(self.open_device.emit)

        self.menu = QMenu()
        self.open_action = QAction("Open AirCube")
        self.open_action.triggered.connect(self.open_app.emit)
        self.menu.addAction(self.open_action)
        self.menu.addSeparator()
        self.quit_action = QAction("Quit")
        self.quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(self.quit_action)
        self.setContextMenu(self.menu)

        self.activated.connect(self._on_activated)
        manager.device_updated.connect(lambda _id: self._schedule_refresh())
        manager.devices_changed.connect(self._schedule_refresh)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self.refresh_icon)
        self.refresh_icon()

    def _schedule_refresh(self):
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.popup.show_at_cursor()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_app.emit()

    def refresh_icon(self):
        worst_score = None
        worst_quality = None
        lines = []
        use_f = self.manager.prefs.get("use_fahrenheit")
        for dev in self.manager.sorted_devices():
            reading = dev.last_reading
            if reading is not None and dev.is_online:
                score = reading.air_score
                if worst_score is None or score > worst_score:
                    worst_score = score
                    worst_quality = reading.quality
                temp = (f"{c_to_f(reading.temperature_c):.0f}°" if use_f
                        else f"{reading.temperature_c:.0f}°")
                lines.append(f"{dev.name}: {reading.quality.short_label} ({score}) · "
                             f"{reading.etvoc} ppb · {temp}")
            else:
                lines.append(f"{dev.name}: offline")

        if worst_score is None and not self.app_icon.isNull() and not lines:
            self.setIcon(self.app_icon)
        else:
            self.setIcon(make_badge_icon(worst_score, worst_quality))
        tooltip = "AirCube"
        if lines:
            tooltip += "\n" + "\n".join(lines)
        else:
            tooltip += " — no devices"
        self.setToolTip(tooltip)
