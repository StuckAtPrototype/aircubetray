"""iOS-style custom widgets: cards, pills, gauge, sparkline, toggles."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, QSize, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath,
                         QPen, QBrush, QFontMetrics)
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QVBoxLayout, QWidget)

from .. import theme
from ..models import AirQuality


class Card(QFrame):
    """Flat surface, radius 24, low-opacity hairline border (CardBackground)."""

    def __init__(self, parent=None, gradient_color: QColor | None = None):
        super().__init__(parent)
        self._gradient_color = gradient_color
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_gradient(self, color: QColor | None):
        self._gradient_color = color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, theme.CARD_RADIUS, theme.CARD_RADIUS)
        if self._gradient_color is not None:
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            tint = QColor(self._gradient_color)
            tint.setAlphaF(0.16)
            grad.setColorAt(0.0, tint)
            grad.setColorAt(1.0, theme.color("card_bottom"))
            p.fillPath(path, QBrush(grad))
        else:
            p.fillPath(path, theme.color("card"))
        border = theme.color("card_border")
        border.setAlphaF(0.6)
        p.setPen(QPen(border, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


class Pill(QLabel):
    """Small rounded status pill with tinted background."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._fg = theme.color("muted")
        self._bg = theme.color("pill_track")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(theme.FONT_FAMILY, 8)
        f.setWeight(QFont.Weight.DemiBold)
        self.setFont(f)
        self.setContentsMargins(10, 3, 10, 3)

    def set_colors(self, fg: QColor, bg: QColor):
        self._fg = fg
        self._bg = bg
        self.update()

    def set_quality(self, q: AirQuality):
        c = theme.quality_color(q)
        bg = QColor(c)
        bg.setAlphaF(0.16)
        self.set_colors(c, bg)

    def set_neutral(self):
        self.set_colors(theme.color("muted"), theme.color("pill_track"))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.fillPath(path, self._bg)
        p.setPen(self._fg)
        p.setFont(self.font())
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class StatusDot(QWidget):
    """7px colored dot showing online status / quality."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = theme.color("faint")
        self.setFixedSize(10, 10)

    def set_color(self, color: QColor):
        self._color = color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(1.5, 1.5, 7, 7))


class PillPicker(QWidget):
    """Segmented capsule control (iOS PillPicker): inset track, raised pill."""
    selection_changed = pyqtSignal(object)

    def __init__(self, options: list[tuple[object, str]], parent=None, fill=False):
        super().__init__(parent)
        self._options = options
        self._selection = options[0][0] if options else None
        self._fill = fill
        self._buttons: list[QPushButton] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(4)
        for value, label in options:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
            btn.clicked.connect(lambda _, v=value: self.set_selection(v, emit=True))
            if fill:
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            lay.addWidget(btn)
            self._buttons.append(btn)
        self._restyle()
        theme.signals.changed.connect(self._restyle)

    def selection(self):
        return self._selection

    def set_selection(self, value, emit=False):
        if value == self._selection:
            if emit:
                self.selection_changed.emit(value)
            return
        self._selection = value
        self._restyle()
        if emit:
            self.selection_changed.emit(value)

    def _restyle(self):
        for (value, _), btn in zip(self._options, self._buttons):
            selected = value == self._selection
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {theme.css('pill_selected') if selected else 'transparent'};
                    color: {theme.css('text') if selected else theme.css('muted')};
                    border: none;
                    border-radius: 12px;
                    padding: 5px 12px;
                    font-size: 12px;
                    font-weight: 500;
                }}
            """)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.fillPath(path, theme.color("pill_track"))


class AirGauge(QWidget):
    """270-degree arc gauge: 0-100 score, gap at the bottom (iOS AirGauge)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._score = 0
        self._quality = AirQuality.GOOD
        self._has_data = False
        self.setFixedSize(150, 150)

    def set_score(self, score: int, quality: AirQuality):
        self._score = max(0, min(100, score))
        self._quality = quality
        self._has_data = True
        self.update()

    def clear(self):
        self._has_data = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = 124.0
        stroke = 9.0
        x = (self.width() - size) / 2
        y = (self.height() - size) / 2 - 4
        arc_rect = QRectF(x + stroke / 2, y + stroke / 2, size - stroke, size - stroke)

        # Qt angles: 0 = 3 o'clock, CCW positive, in 1/16 deg.
        # iOS: trim 0..0.75 rotated 135deg -> arc from 225deg sweeping -270.
        start_angle = int(225 * 16)
        full_span = int(-270 * 16)

        track = theme.color("card_border")
        track.setAlphaF(0.7)
        pen = QPen(track, stroke)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(arc_rect, start_angle, full_span)

        if self._has_data:
            frac = max(self._score, 3) / 100.0
            qcolor = theme.quality_color(self._quality)
            pen = QPen(qcolor, stroke)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(arc_rect, start_angle, int(full_span * frac))

        # center text: caption / score / verdict stacked
        p.setPen(theme.color("faint"))
        p.setFont(QFont(theme.FONT_FAMILY, 7))
        p.drawText(QRectF(x, y + 26, size, 12),
                   Qt.AlignmentFlag.AlignCenter, "AIR QUALITY")

        p.setPen(theme.color("text"))
        f = QFont(theme.FONT_FAMILY, 26)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        score_text = str(self._score) if self._has_data else "--"
        p.drawText(QRectF(x, y + 38, size, 44),
                   Qt.AlignmentFlag.AlignCenter, score_text)

        if self._has_data:
            p.setPen(theme.quality_color(self._quality))
            f = QFont(theme.FONT_FAMILY, 10)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            p.drawText(QRectF(x, y + 84, size, 16),
                       Qt.AlignmentFlag.AlignCenter, self._quality.short_label)

        # scale labels 0 / 100 near the bottom gap
        p.setPen(theme.color("faint"))
        p.setFont(QFont(theme.FONT_FAMILY, 7))
        p.drawText(QRectF(x + 8, y + size - 14, 30, 12),
                   Qt.AlignmentFlag.AlignLeft, "0")
        p.drawText(QRectF(x + size - 38, y + size - 14, 30, 12),
                   Qt.AlignmentFlag.AlignRight, "100")


class Sparkline(QWidget):
    """Tiny area+line chart for the last ~2 h of one metric."""

    def __init__(self, color_key: str = "voc", parent=None, height: int = 34):
        super().__init__(parent)
        self._color_key = color_key
        self._values: list[float] = []
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, values: list[float], color_key: str | None = None):
        self._values = [v for v in values if v == v]  # drop NaN
        if color_key:
            self._color_key = color_key
        self.update()

    def paintEvent(self, event):
        if len(self._values) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad = 2.0
        vmin, vmax = min(self._values), max(self._values)
        span = (vmax - vmin) or 1.0
        n = len(self._values)
        pts = []
        for i, v in enumerate(self._values):
            px = pad + (w - 2 * pad) * i / (n - 1)
            py = pad + (h - 2 * pad) * (1 - (v - vmin) / span)
            pts.append((px, py))

        color = theme.color(self._color_key)
        line = QPainterPath()
        line.moveTo(*pts[0])
        for pt in pts[1:]:
            line.lineTo(*pt)

        area = QPainterPath(line)
        area.lineTo(pts[-1][0], h - pad)
        area.lineTo(pts[0][0], h - pad)
        area.closeSubpath()
        fill = QColor(color)
        fill.setAlphaF(0.18)
        p.fillPath(area, fill)

        p.setPen(QPen(color, 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)


class ToggleSwitch(QWidget):
    """iOS-style toggle switch."""
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(44, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if checked != self._checked:
            self._checked = checked
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.fillPath(path, theme.color("accent") if self._checked else theme.color("pill_track"))
        knob_d = rect.height() - 4
        kx = rect.right() - knob_d - 2 if self._checked else rect.left() + 2
        p.setBrush(QColor("white"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(kx, rect.top() + 2, knob_d, knob_d))


MAX_CONTENT_WIDTH = 860


def centered_column(page: QWidget, max_width: int = MAX_CONTENT_WIDTH) -> QVBoxLayout:
    """Constrain a page's content to a centered column so cards keep an
    iOS-like width instead of stretching across wide/maximized windows.
    Returns the layout to build the page into."""
    row = QHBoxLayout(page)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    column = QWidget()
    column.setMaximumWidth(max_width)
    column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    row.addStretch(1)
    row.addWidget(column, 100)
    row.addStretch(1)
    return QVBoxLayout(column)


def make_label(text: str, size: int = 13, weight: QFont.Weight = QFont.Weight.Normal,
               color_key: str = "text") -> QLabel:
    lbl = QLabel(text)
    f = QFont(theme.FONT_FAMILY, size)
    f.setWeight(weight)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {theme.css(color_key)}; background: transparent;")
    lbl.setProperty("theme_color_key", color_key)
    return lbl


def retheme_label(lbl: QLabel):
    key = lbl.property("theme_color_key") or "text"
    lbl.setStyleSheet(f"color: {theme.css(key)}; background: transparent;")


class ValueLabel(QLabel):
    """Big monospaced-digit metric value."""

    def __init__(self, size: int = 26, color_key: str = "text", parent=None):
        super().__init__("--", parent)
        f = QFont(theme.FONT_FAMILY, size)
        f.setWeight(QFont.Weight.DemiBold)
        self.setFont(f)
        self._color_key = color_key
        self.retheme()

    def retheme(self):
        self.setStyleSheet(f"color: {theme.css(self._color_key)}; background: transparent;")
