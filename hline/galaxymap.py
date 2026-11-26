"""Top-down Milky Way map showing where the dish is looking and where the
detected hydrogen clouds sit (kinematic distances)."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient, QBrush
from PySide6.QtWidgets import QWidget

from . import astro


class GalaxyMap(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.l = None
        self.b = 0.0
        self.beam = 20.0
        self.clouds = []      # list of dict(v, d=[...], ambiguous)
        self.future_l = []    # [(hours, l)]
        self.kiosk = False
        self._arms = [(name, astro.arm_polyline(r, pch), col) for name, r, pch, col in astro.ARMS]
        la = astro.LOCAL_ARM
        self._local = (la[0], astro.arm_polyline(la[1], la[2], la[4]), la[3])

    def set_state(self, l, b, beam, clouds, future_l):
        self.l, self.b, self.beam, self.clouds, self.future_l = l, b, beam, clouds, future_l
        self.update()

    def _map(self):
        w, h = self.width(), self.height()
        top = 26 if not self.kiosk else 34
        span = 30.0  # kpc shown
        scale = min(w, h - top - 14) / span
        cx = w / 2
        cy = top + (h - top - 14) / 2 - 3.0 * scale  # centre the view between GC and Sun
        # view from the North Galactic Pole: +X (toward l=90) is to the LEFT
        return (lambda x, y: QPointF(cx - x * scale, cy + y * scale)), scale

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(6, 8, 16))
        to, scale = self._map()
        fs = max(7.5, min(self.width(), self.height()) / 42) * (1.2 if self.kiosk else 1.0)
        f = QFont()

        # disc glow
        gc = to(0, 0)
        g = QRadialGradient(gc, 16 * scale)
        g.setColorAt(0, QColor(255, 230, 180, 120))
        g.setColorAt(0.25, QColor(160, 140, 200, 50))
        g.setColorAt(1, QColor(20, 20, 40, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(gc, 16 * scale, 16 * scale)

        # bar
        p.save()
        p.translate(gc)
        p.rotate(117)  # bar ~27 deg from the Sun-GC line, near end toward l>0
        p.setBrush(QColor(255, 220, 160, 140))
        p.drawEllipse(QPointF(0, 0), 4.4 * scale, 1.3 * scale)
        p.restore()

        # arms
        for name, (x, y), col in self._arms + [self._local]:
            c = QColor(*col)
            c.setAlpha(150)
            pen = QPen(c, max(2.0, 0.55 * scale))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            path = QPainterPath()
            path.moveTo(to(x[0], y[0]))
            for i in range(1, len(x), 3):
                path.lineTo(to(x[i], y[i]))
            p.drawPath(path)
        # arm labels
        f.setPointSizeF(fs * 0.8)
        p.setFont(f)
        labels = [(a[0], a[1] * math.exp(0.95 * math.tan(a[2] * math.pi / 180)), -0.95, a[3]) for a in astro.ARMS]
        la = astro.LOCAL_ARM
        labels.append((la[0], la[1] * math.exp(-0.45 * math.tan(la[2] * math.pi / 180)), 0.45, la[3]))
        for name, R, beta, col in labels:
            p.setPen(QColor(*col))
            pt = to(R * math.sin(beta), R * math.cos(beta))
            short = name.split("–")[0].split(" (")[0]
            p.drawText(QPointF(pt.x() + 5, pt.y() + 4), short if self.width() < 460 else name)

        sun = to(0, astro.R0_KPC)
        # beam wedge + line of sight
        if self.l is not None:
            L = 25.0
            def dirpt(lv, d):
                x, y = astro.galactic_to_xy(lv, d)
                return to(float(x), float(y))
            poly = QPolygonF([sun] + [dirpt(self.l + a, L) for a in np.linspace(-self.beam / 2, self.beam / 2, 12)])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(80, 255, 150, 40))
            p.drawPolygon(poly)
            pen = QPen(QColor(110, 255, 170), max(1.5, 0.12 * scale))
            p.setPen(pen)
            p.drawLine(sun, dirpt(self.l, L))
            # future longitudes (drift)
            pen = QPen(QColor(110, 255, 170, 90), 1)
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            f.setPointSizeF(fs * 0.75)
            p.setFont(f)
            for hrs, lv in self.future_l:
                end = dirpt(lv, 7.0)
                p.drawLine(sun, end)

            # clouds
            for cl in self.clouds:
                for d in cl["d"]:
                    pt = dirpt(self.l, d)
                    r = max(4.0, 0.42 * scale)
                    if cl["ambiguous"]:
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.setPen(QPen(QColor(255, 240, 120), 2))
                    else:
                        p.setBrush(QColor(255, 240, 120))
                        p.setPen(QPen(QColor(40, 30, 0), 1))
                    p.drawEllipse(pt, r, r)

        # Sun & GC markers
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 225, 90))
        p.drawEllipse(sun, max(3.5, 0.3 * scale), max(3.5, 0.3 * scale))
        f.setPointSizeF(fs * 0.9)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 225, 90))
        p.drawText(QPointF(sun.x() + 7, sun.y() + 14), "You are here")
        p.setPen(QColor(255, 235, 200))
        p.drawText(QPointF(gc.x() + 6, gc.y() - 6), "Galactic Centre")
        f.setBold(False)

        # longitude ticks around the Sun
        f.setPointSizeF(fs * 0.8)
        p.setFont(f)
        p.setPen(QColor(140, 160, 190))
        for lv in (0, 90, 180, 270):
            x, y = astro.galactic_to_xy(lv, 4.6)
            pt = to(float(x), float(y))
            t = f"{lv}°"
            w = p.fontMetrics().horizontalAdvance(t)
            p.drawText(QPointF(pt.x() - w / 2, pt.y() + fs / 2), t)

        # title
        f.setPointSizeF(fs * 1.1)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(220, 230, 245))
        p.drawText(QPointF(8, fs * 1.6), "Our Milky Way – seen from above")
        f.setBold(False)
        f.setPointSizeF(fs * 0.8)
        p.setFont(f)
        p.setPen(QColor(150, 160, 180))
        foot = "● hydrogen cloud   ○ two possible distances   (flat rotation curve, b≈0)"
        p.drawText(QPointF(8, self.height() - 6), foot)
        if self.l is not None and abs(self.b) > 15:
            p.setPen(QColor(255, 190, 120))
            p.drawText(QPointF(8, fs * 3.0), f"Beam is {abs(self.b):.0f}° off the plane – distances not shown")
        p.end()
