"""All-sky dome view: stars, constellations, Milky Way, galactic plane, dish beam."""
from __future__ import annotations

import json
import math
import os

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPainterPath,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import astro
from .config import beam_width
from .paths import app_dir

try:
    import ephem
except Exception:  # pragma: no cover
    ephem = None


def bv_color(bv):
    bv = max(-0.4, min(2.0, bv))
    if bv < 0.0:
        return QColor(170, 195, 255)
    if bv < 0.4:
        return QColor(215, 228, 255)
    if bv < 0.8:
        return QColor(255, 250, 235)
    if bv < 1.3:
        return QColor(255, 222, 170)
    return QColor(255, 190, 140)


class SkyDome(QWidget):
    pointRequested = Signal(float, float)  # alt, az (double-click)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setMouseTracking(True)
        with open(os.path.join(app_dir(), "data", "sky.json"), "r", encoding="utf-8") as f:
            sky = json.load(f)
        st = np.array(sky["stars"], dtype=float)
        self.st_ra, self.st_dec, self.st_mag, self.st_bv = st.T
        self.names = sky["names"]
        self.cons = [c for c in sky["constellations"] if c[3] <= 2]
        self.lines = [np.array(seg, dtype=float) for seg in sky["lines"]]
        self.cfg = {}
        self.jd = astro.julian_date(astro.utc_now())
        self.kiosk = False
        self._mw_cache = (None, None)
        self._planets = []
        self._planets_jd = 0
        self._hover = None
        self.peaks_l = None

    # ------------------------------------------------------------------ api
    def update_state(self, jd, cfg):
        self.jd = jd
        self.cfg = cfg
        self.update()

    # ----------------------------------------------------------- projection
    def _geom(self):
        w, h = self.width(), self.height()
        pad = 34 if not self.kiosk else 40
        R = max(10, min(w, h) / 2 - pad)
        return w / 2, h / 2, R

    def _proj(self, alt, az):
        cx, cy, R = self._geom()
        r = (90.0 - np.asarray(alt)) / 90.0 * R
        a = np.asarray(az) * astro.DEG
        return cx - r * np.sin(a), cy - r * np.cos(a)

    def _altaz(self, ra, dec):
        c = self.cfg
        return astro.j2000_to_altaz(ra, dec, self.jd, c.get("lat", 0), c.get("lon", 0))

    # -------------------------------------------------------------- milky way
    def _milky_way_image(self, R):
        key = (round(self.jd * 720), int(R), self.cfg.get("lat"), self.cfg.get("lon"))
        if self._mw_cache[0] == key:
            return self._mw_cache[1]
        n = int(min(2 * R, 420))
        if n < 10:
            return None
        ys, xs = np.mgrid[0:n, 0:n]
        u = (xs + 0.5) / n * 2 - 1
        v = (ys + 0.5) / n * 2 - 1
        r = np.hypot(u, v)
        inside = r <= 1.0
        alt = 90.0 - r * 90.0
        az = np.degrees(np.arctan2(-u, -v)) % 360.0
        c = self.cfg
        ra, dec = astro.altaz_to_j2000(alt[inside], az[inside], self.jd, c["lat"], c["lon"])
        l, b = astro.eq_to_gal(ra, dec)
        lr = np.radians(l)
        width = 3.5 + 4.0 * (0.5 + 0.5 * np.cos(lr))
        core = (0.25 + 0.75 * ((1 + np.cos(lr)) / 2) ** 2)
        inten = core * np.exp(-0.5 * (b / width) ** 2)
        # Great Rift / dark lanes (rough)
        rift = np.exp(-0.5 * ((b - 1.5) / 1.6) ** 2) * np.exp(-0.5 * ((((l + 180) % 360) - 180 - 45) / 30) ** 2)
        inten *= 1 - 0.55 * rift
        inten += 0.25 * np.exp(-0.5 * (b / 18) ** 2) * core
        alpha = np.zeros((n, n), dtype=np.float32)
        alpha[inside] = np.clip(inten, 0, 1)
        img = np.zeros((n, n, 4), dtype=np.uint8)
        img[..., 0] = 255  # B
        img[..., 1] = 225  # G
        img[..., 2] = 200  # R
        img[..., 3] = (alpha * 95).astype(np.uint8)
        q = QImage(img.data, n, n, 4 * n, QImage.Format.Format_ARGB32).copy()
        self._mw_cache = (key, q)
        return q

    def _planet_list(self):
        if ephem is None:
            return []
        if abs(self.jd - self._planets_jd) < 60 / 86400 and self._planets:
            return self._planets
        out = []
        d = ephem.Date(self.jd - 2415020.0)
        for name, body, col, size in [("Sun", ephem.Sun(), QColor(255, 220, 90), 9),
                                      ("Moon", ephem.Moon(), QColor(235, 235, 235), 8),
                                      ("Mercury", ephem.Mercury(), QColor(200, 190, 180), 3),
                                      ("Venus", ephem.Venus(), QColor(255, 250, 220), 4.5),
                                      ("Mars", ephem.Mars(), QColor(255, 140, 100), 3.5),
                                      ("Jupiter", ephem.Jupiter(), QColor(255, 235, 200), 4.5),
                                      ("Saturn", ephem.Saturn(), QColor(240, 220, 160), 4)]:
            body.compute(d, epoch=ephem.J2000)
            out.append((name, math.degrees(body.a_ra), math.degrees(body.a_dec), col, size))
        self._planets = out
        self._planets_jd = self.jd
        return out

    # ------------------------------------------------------------------ paint
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, R = self._geom()
        s = R / 330.0  # size scale
        fs = max(7.0, 9.5 * max(s, 0.8)) * (1.25 if self.kiosk else 1.0)
        p.fillRect(self.rect(), QColor(6, 8, 16))
        if not self.cfg:
            return

        # sky background
        g = QRadialGradient(QPointF(cx, cy), R)
        g.setColorAt(0.0, QColor(10, 16, 38))
        g.setColorAt(0.85, QColor(14, 22, 48))
        g.setColorAt(1.0, QColor(30, 38, 70))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), R, R)

        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), R, R)
        p.save()
        p.setClipPath(clip)

        if self.cfg.get("show_milky_way", True):
            img = self._milky_way_image(R)
            if img is not None:
                p.drawImage(QRectF(cx - R, cy - R, 2 * R, 2 * R), img)

        # alt/az grid
        p.setPen(QPen(QColor(60, 90, 120, 110), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for alt in (30, 60):
            r = (90 - alt) / 90 * R
            p.drawEllipse(QPointF(cx, cy), r, r)
        for az in range(0, 360, 30):
            x, y = self._proj(0, az)
            p.drawLine(QPointF(cx, cy), QPointF(float(x), float(y)))

        # constellation lines
        if self.cfg.get("show_constellations", True):
            p.setPen(QPen(QColor(80, 140, 170, 120), max(0.8, s)))
            for seg in self.lines:
                alt, az = self._altaz(seg[:, 0], seg[:, 1])
                if np.all(alt < -2):
                    continue
                x, y = self._proj(alt, az)
                path = QPainterPath()
                path.moveTo(x[0], y[0])
                for i in range(1, len(x)):
                    path.lineTo(x[i], y[i])
                p.drawPath(path)

        # galactic plane
        ls = np.arange(0, 361, 1.0)
        gra, gdec = astro.gal_to_eq(ls, np.zeros_like(ls))
        galt, gaz = self._altaz(gra, gdec)
        gx, gy = self._proj(galt, gaz)
        pen = QPen(QColor(255, 110, 200, 200), max(1.2, 1.6 * s))
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        path = QPainterPath()
        started = False
        for i in range(len(ls)):
            if galt[i] > -10:
                if not started:
                    path.moveTo(gx[i], gy[i])
                    started = True
                else:
                    path.lineTo(gx[i], gy[i])
            else:
                started = False
        p.drawPath(path)
        f = QFont()
        f.setPointSizeF(fs * 0.95)
        p.setFont(f)
        for lv in range(0, 360, 30):
            i = lv
            if galt[i] > 3:
                p.setPen(QColor(255, 140, 215))
                label = "Galactic Centre" if lv == 0 else f"l={lv}°"
                p.drawText(QPointF(gx[i] + 5, gy[i] - 5), label)
                p.setBrush(QColor(255, 120, 210))
                p.drawEllipse(QPointF(gx[i], gy[i]), 2.5 * max(s, 0.8), 2.5 * max(s, 0.8))
                p.setBrush(Qt.BrushStyle.NoBrush)

        # stars
        alt, az = self._altaz(self.st_ra, self.st_dec)
        vis = alt > -1
        x, y = self._proj(alt[vis], az[vis])
        mags = self.st_mag[vis]
        bvs = self.st_bv[vis]
        p.setPen(Qt.PenStyle.NoPen)
        for xi, yi, m, bv in zip(x, y, mags, bvs):
            rad = max(0.55, (3.4 - 0.55 * m)) * max(s, 0.7)
            col = bv_color(bv)
            if m > 4.0:
                col.setAlpha(170)
            p.setBrush(col)
            p.drawEllipse(QPointF(xi, yi), rad, rad)

        # names
        if self.cfg.get("show_star_names", True):
            p.setPen(QColor(150, 190, 230))
            f.setPointSizeF(fs * 0.9)
            p.setFont(f)
            for ra, dec, nm in self.names:
                a, z = self._altaz(ra, dec)
                if a > 2:
                    xx, yy = self._proj(a, z)
                    p.drawText(QPointF(float(xx) + 5, float(yy) - 3), nm)
        if self.cfg.get("show_constellations", True):
            p.setPen(QColor(90, 150, 180, 170))
            f.setPointSizeF(fs * 0.85)
            f.setCapitalization(QFont.Capitalization.AllUppercase)
            f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 115)
            p.setFont(f)
            for ra, dec, nm, _rk in self.cons:
                a, z = self._altaz(ra, dec)
                if a > 5:
                    xx, yy = self._proj(a, z)
                    w = p.fontMetrics().horizontalAdvance(nm)
                    p.drawText(QPointF(float(xx) - w / 2, float(yy)), nm)
            f.setCapitalization(QFont.Capitalization.MixedCase)
            f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100)

        # sun moon planets
        f.setPointSizeF(fs * 0.95)
        p.setFont(f)
        for name, ra, dec, col, size in self._planet_list():
            a, z = self._altaz(ra, dec)
            if a > -1:
                xx, yy = self._proj(a, z)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                rr = size * max(s, 0.8)
                p.drawEllipse(QPointF(float(xx), float(yy)), rr, rr)
                p.setPen(col)
                p.drawText(QPointF(float(xx) + rr + 3, float(yy) + rr + 6), name)

        # ---- dish beam & drift track
        c = self.cfg
        beam = beam_width(c)
        th = np.linspace(0, 360, 121)
        bl, bb = astro.offset_point(c["dish_az"], c["dish_el"], beam / 2.0, th)
        bx, by = self._proj(bb, bl)
        path = QPainterPath()
        path.moveTo(bx[0], by[0])
        for i in range(1, len(bx)):
            path.lineTo(bx[i], by[i])
        path.closeSubpath()
        p.setBrush(QColor(60, 255, 140, 45))
        p.setPen(QPen(QColor(90, 255, 160), max(1.6, 2.2 * s)))
        p.drawPath(path)
        dx, dy = self._proj(c["dish_el"], c["dish_az"])
        dx, dy = float(dx), float(dy)
        p.setPen(QPen(QColor(90, 255, 160), max(1.4, 1.8 * s)))
        k = 7 * max(s, 0.8)
        p.drawLine(QPointF(dx - k, dy), QPointF(dx + k, dy))
        p.drawLine(QPointF(dx, dy - k), QPointF(dx, dy + k))

        # drift track: sky that will pass through the beam in the next hours
        ra0, dec0 = astro.altaz_to_j2000(c["dish_el"], c["dish_az"], self.jd, c["lat"], c["lon"])
        hours = int(c.get("drift_hours", 4))
        if hours > 0:
            hh = np.linspace(0, hours, hours * 20 + 1)
            tra = (float(ra0) + hh * 15.041) % 360
            talt, taz = self._altaz(tra, np.full_like(hh, float(dec0)))
            tx, ty = self._proj(talt, taz)
            pen = QPen(QColor(120, 255, 180, 170), max(1.0, 1.3 * s))
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            path = QPainterPath()
            path.moveTo(tx[0], ty[0])
            for i in range(1, len(tx)):
                path.lineTo(tx[i], ty[i])
            p.drawPath(path)
            p.setPen(QColor(140, 255, 190))
            f.setPointSizeF(fs * 0.85)
            p.setFont(f)
            for hr in range(1, hours + 1):
                i = hr * 20
                if talt[i] > -5:
                    p.setBrush(QColor(140, 255, 190))
                    p.drawEllipse(QPointF(tx[i], ty[i]), 2.2, 2.2)
                    p.drawText(QPointF(tx[i] + 4, ty[i] + 12), f"+{hr}h")
        p.setPen(QColor(150, 255, 190))
        f.setPointSizeF(fs * 1.05)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QPointF(dx + k + 4, dy - k - 2), "DISH")
        f.setBold(False)

        p.restore()

        # horizon ring + cardinal points
        p.setPen(QPen(QColor(110, 140, 180), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R, R)
        f.setPointSizeF(fs * 1.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 120, 80))
        for lab, az in (("N", 0), ("E", 90), ("S", 180), ("W", 270), ("NE", 45), ("SE", 135), ("SW", 225), ("NW", 315)):
            if len(lab) == 2:
                f.setPointSizeF(fs * 1.0)
            else:
                f.setPointSizeF(fs * 1.5)
            p.setFont(f)
            r = R + 16 * max(s, 0.8)
            a = az * astro.DEG
            x, y = cx - r * math.sin(a), cy - r * math.cos(a)
            w = p.fontMetrics().horizontalAdvance(lab)
            p.drawText(QPointF(x - w / 2, y + fs * 0.6), lab)

        # hover readout
        if self._hover is not None and not self.kiosk:
            alt, az = self._hover
            ra, dec = astro.altaz_to_j2000(alt, az, self.jd, c["lat"], c["lon"])
            l, b = astro.eq_to_gal(ra, dec)
            f.setPointSizeF(fs)
            f.setBold(False)
            p.setFont(f)
            p.setPen(QColor(200, 210, 230))
            p.drawText(QPointF(8, self.height() - 8),
                       f"Az {az:5.1f}°  Alt {alt:4.1f}°   l {float(l):5.1f}°  b {float(b):+5.1f}°   (double-click to aim dish here)")
        p.end()

    # --------------------------------------------------------------- mouse
    def _xy_to_altaz(self, x, y):
        cx, cy, R = self._geom()
        u, v = (x - cx) / R, (y - cy) / R
        r = math.hypot(u, v)
        if r > 1:
            return None
        alt = 90 - r * 90
        az = math.degrees(math.atan2(-u, -v)) % 360
        return alt, az

    def mouseMoveEvent(self, ev):
        self._hover = self._xy_to_altaz(ev.position().x(), ev.position().y())
        self.update()

    def leaveEvent(self, _ev):
        self._hover = None
        self.update()

    def mouseDoubleClickEvent(self, ev):
        aa = self._xy_to_altaz(ev.position().x(), ev.position().y())
        if aa and not self.kiosk:
            self.pointRequested.emit(*aa)
