"""QPainter charts: gap-aware area+line history chart with scrubbing,
and a multi-device compare chart."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .. import theme

Point = tuple[float, float]  # (unix ts, value)


class _BaseChart(QWidget):
    PAD_LEFT = 8
    PAD_RIGHT = 44
    PAD_TOP = 10
    PAD_BOTTOM = 22

    def __init__(self, parent=None, height: int = 220):
        super().__init__(parent)
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._t0 = 0.0
        self._t1 = 1.0
        self._v0 = 0.0
        self._v1 = 1.0
        self._scrub_x: Optional[float] = None
        self._empty_text = "No history yet"

    def _plot_rect(self) -> QRectF:
        return QRectF(self.PAD_LEFT, self.PAD_TOP,
                      self.width() - self.PAD_LEFT - self.PAD_RIGHT,
                      self.height() - self.PAD_TOP - self.PAD_BOTTOM)

    def _x(self, t: float, r: QRectF) -> float:
        span = (self._t1 - self._t0) or 1.0
        return r.left() + r.width() * (t - self._t0) / span

    def _y(self, v: float, r: QRectF) -> float:
        span = (self._v1 - self._v0) or 1.0
        return r.bottom() - r.height() * (v - self._v0) / span

    def _set_domain(self, all_points: list[Point], t_start: float, t_end: float):
        self._t0, self._t1 = t_start, t_end
        if all_points:
            vals = [v for _, v in all_points]
            vmin, vmax = min(vals), max(vals)
            pad = (vmax - vmin) * 0.15 or max(abs(vmax) * 0.1, 1.0)
            self._v0, self._v1 = vmin - pad, vmax + pad
        else:
            self._v0, self._v1 = 0.0, 1.0

    def _draw_grid(self, p: QPainter, r: QRectF):
        grid = theme.color("card_border")
        grid.setAlphaF(0.45)
        p.setPen(QPen(grid, 1, Qt.PenStyle.DashLine))
        for i in range(1, 4):
            y = r.top() + r.height() * i / 4
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        # y labels
        p.setPen(theme.color("faint"))
        p.setFont(QFont(theme.FONT_FAMILY, 7))
        for i in range(5):
            v = self._v1 - (self._v1 - self._v0) * i / 4
            y = r.top() + r.height() * i / 4
            p.drawText(QRectF(r.right() + 4, y - 7, self.PAD_RIGHT - 6, 14),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self._fmt_axis(v))

    def _fmt_axis(self, v: float) -> str:
        if abs(v) >= 1000:
            return f"{v / 1000:.1f}k"
        if abs(v) >= 100:
            return f"{v:.0f}"
        return f"{v:.1f}"

    def _draw_time_axis(self, p: QPainter, r: QRectF):
        p.setPen(theme.color("faint"))
        p.setFont(QFont(theme.FONT_FAMILY, 7))
        span = self._t1 - self._t0
        n_ticks = 5
        for i in range(n_ticks):
            t = self._t0 + span * i / (n_ticks - 1)
            dt = datetime.fromtimestamp(t)
            label = dt.strftime("%H:%M") if span <= 86_400 * 1.5 else dt.strftime("%a %H:%M")
            align = (Qt.AlignmentFlag.AlignLeft if i == 0 else
                     Qt.AlignmentFlag.AlignRight if i == n_ticks - 1 else
                     Qt.AlignmentFlag.AlignHCenter)
            x = self._x(t, r)
            p.drawText(QRectF(x - 44, r.bottom() + 4, 88, 14), align, label)

    def _draw_series(self, p: QPainter, r: QRectF, segments: list[list[Point]],
                     color: QColor, area: bool = True):
        for seg in segments:
            if len(seg) < 2:
                if len(seg) == 1:
                    p.setBrush(color)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawEllipse(QPointF(self._x(seg[0][0], r), self._y(seg[0][1], r)), 2, 2)
                continue
            path = QPainterPath()
            path.moveTo(self._x(seg[0][0], r), self._y(seg[0][1], r))
            for t, v in seg[1:]:
                path.lineTo(self._x(t, r), self._y(v, r))
            if area:
                fill_path = QPainterPath(path)
                fill_path.lineTo(self._x(seg[-1][0], r), r.bottom())
                fill_path.lineTo(self._x(seg[0][0], r), r.bottom())
                fill_path.closeSubpath()
                fill = QColor(color)
                fill.setAlphaF(0.14)
                p.fillPath(fill_path, fill)
            p.setPen(QPen(color, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

    def mouseMoveEvent(self, event):
        self._scrub_x = event.position().x()
        self.update()

    def leaveEvent(self, event):
        self._scrub_x = None
        self.update()

    def _draw_empty(self, p: QPainter):
        p.setPen(theme.color("faint"))
        p.setFont(QFont(theme.FONT_FAMILY, 10))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._empty_text)


class HistoryChart(_BaseChart):
    """Single-metric area+line chart with gap-aware segments and scrubbing."""

    def __init__(self, parent=None, height: int = 220):
        super().__init__(parent, height)
        self._segments: list[list[Point]] = []
        self._color = theme.color("voc")
        self._unit = ""
        self._fmt: Callable[[float], str] = lambda v: f"{v:.0f}"

    def set_data(self, segments: list[list[Point]], color: QColor, unit: str,
                 t_start: float, t_end: float,
                 fmt: Optional[Callable[[float], str]] = None):
        self._segments = segments
        self._color = color
        self._unit = unit
        if fmt:
            self._fmt = fmt
        all_points = [pt for seg in segments for pt in seg]
        self._set_domain(all_points, t_start, t_end)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._segments:
            self._draw_empty(p)
            return
        r = self._plot_rect()
        self._draw_grid(p, r)
        self._draw_time_axis(p, r)
        self._draw_series(p, r, self._segments, self._color)
        self._draw_scrub(p, r)

    def _nearest_point(self, t: float) -> Optional[Point]:
        best, best_d = None, float("inf")
        for seg in self._segments:
            for pt in seg:
                d = abs(pt[0] - t)
                if d < best_d:
                    best, best_d = pt, d
        return best

    def _draw_scrub(self, p: QPainter, r: QRectF):
        if self._scrub_x is None or not r.contains(QPointF(self._scrub_x, r.center().y())):
            return
        span = (self._t1 - self._t0) or 1.0
        t = self._t0 + (self._scrub_x - r.left()) / r.width() * span
        pt = self._nearest_point(t)
        if pt is None:
            return
        x, y = self._x(pt[0], r), self._y(pt[1], r)
        guide = theme.color("faint")
        guide.setAlphaF(0.5)
        p.setPen(QPen(guide, 1))
        p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        p.setBrush(self._color)
        p.setPen(QPen(theme.color("card"), 2))
        p.drawEllipse(QPointF(x, y), 5, 5)

        label = f"{self._fmt(pt[1])}{self._unit}   {datetime.fromtimestamp(pt[0]).strftime('%a %H:%M')}"
        p.setFont(QFont(theme.FONT_FAMILY, 8))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(label) + 16
        bx = min(max(x - tw / 2, r.left()), r.right() - tw)
        box = QRectF(bx, r.top() - 2, tw, 18)
        path = QPainterPath()
        path.addRoundedRect(box, 9, 9)
        p.fillPath(path, theme.color("card_top"))
        p.setPen(theme.color("text"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)


class CompareChart(_BaseChart):
    """Multi-device overlay chart with all-device scrub readout."""

    def __init__(self, parent=None, height: int = 300):
        super().__init__(parent, height)
        self._series: list[tuple[str, QColor, list[list[Point]]]] = []
        self._unit = ""
        self._fmt: Callable[[float], str] = lambda v: f"{v:.0f}"
        self._empty_text = "No data for this range"

    def set_data(self, series: list[tuple[str, QColor, list[list[Point]]]],
                 unit: str, t_start: float, t_end: float,
                 fmt: Optional[Callable[[float], str]] = None):
        self._series = series
        self._unit = unit
        if fmt:
            self._fmt = fmt
        all_points = [pt for _, _, segs in series for seg in segs for pt in seg]
        self._set_domain(all_points, t_start, t_end)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not any(segs for _, _, segs in self._series):
            self._draw_empty(p)
            return
        r = self._plot_rect()
        self._draw_grid(p, r)
        self._draw_time_axis(p, r)
        for _, color, segments in self._series:
            self._draw_series(p, r, segments, color, area=False)
        self._draw_scrub(p, r)

    def _draw_scrub(self, p: QPainter, r: QRectF):
        if self._scrub_x is None or not r.contains(QPointF(self._scrub_x, r.center().y())):
            return
        span = (self._t1 - self._t0) or 1.0
        t = self._t0 + (self._scrub_x - r.left()) / r.width() * span

        guide = theme.color("faint")
        guide.setAlphaF(0.5)
        p.setPen(QPen(guide, 1))
        x_guide = self._x(t, r)
        p.drawLine(QPointF(x_guide, r.top()), QPointF(x_guide, r.bottom()))

        rows: list[tuple[str, QColor, float]] = []
        for name, color, segments in self._series:
            best, best_d = None, float("inf")
            for seg in segments:
                for pt in seg:
                    d = abs(pt[0] - t)
                    if d < best_d:
                        best, best_d = pt, d
            if best is not None and best_d <= 1800:
                rows.append((name, color, best[1]))
                p.setBrush(color)
                p.setPen(QPen(theme.color("card"), 2))
                p.drawEllipse(QPointF(self._x(best[0], r), self._y(best[1], r)), 4, 4)
        if not rows:
            return

        p.setFont(QFont(theme.FONT_FAMILY, 8))
        fm = p.fontMetrics()
        lines = [f"{name}: {self._fmt(v)}{self._unit}" for name, _, v in rows]
        header = datetime.fromtimestamp(t).strftime("%a %H:%M")
        w = max(fm.horizontalAdvance(s) for s in lines + [header]) + 24
        h = 18 + len(lines) * 15 + 6
        bx = min(max(x_guide + 8, r.left()), r.right() - w)
        by = r.top() + 4
        box = QRectF(bx, by, w, h)
        path = QPainterPath()
        path.addRoundedRect(box, 8, 8)
        p.fillPath(path, theme.color("card_top"))
        p.setPen(QPen(theme.color("card_border"), 1))
        p.drawPath(path)
        p.setPen(theme.color("faint"))
        p.drawText(QRectF(bx + 12, by + 4, w - 16, 14),
                   Qt.AlignmentFlag.AlignLeft, header)
        for i, (name, color, v) in enumerate(rows):
            y = by + 18 + i * 15
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(bx + 10, y + 4, 7, 7))
            p.setPen(theme.color("text"))
            p.drawText(QRectF(bx + 22, y, w - 26, 14), Qt.AlignmentFlag.AlignLeft,
                       f"{name}: {self._fmt(v)}{self._unit}")
