"""Averaged hydrogen-line spectrum: LSR velocity (bottom) and frequency (top)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QFont

from . import astro


class FreqAxis(pg.AxisItem):
    """Top axis that labels the velocity axis in observed MHz."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.corr = 0.0  # vLSR correction (km/s)

    def _v2f(self, v):
        return astro.vtopo_to_freq(np.asarray(v) - self.corr)

    def _f2v(self, f):
        return astro.freq_to_vtopo(np.asarray(f)) + self.corr

    def tickValues(self, minVal, maxVal, size):
        f1, f2 = sorted((float(self._v2f(minVal)), float(self._v2f(maxVal))))
        levels = super().tickValues(f1, f2, size)
        out = []
        for spacing, vals in levels:
            vv = [float(self._f2v(x)) for x in vals]
            out.append((spacing, vv))
        return out

    def tickStrings(self, values, scale, spacing):
        fs = self._v2f(values)
        dec = 3 if spacing >= 0.001 else 4
        return [f"{x:.{dec}f}" for x in fs]


class SpectrumWidget(pg.GraphicsLayoutWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground((8, 10, 18))
        self.top_axis = FreqAxis("top")
        self.plot = self.addPlot(axisItems={"top": self.top_axis})
        self.plot.showAxis("top")
        self.plot.showGrid(x=True, y=True, alpha=0.18)
        self.plot.setLabel("bottom", "Velocity relative to the Sun's neighbourhood (LSR), km/s")
        self.plot.setLabel("top", "Observed frequency, MHz")
        self.plot.setMenuEnabled(False)
        self.plot.hideButtons()
        self.curve = self.plot.plot([], [], pen=pg.mkPen((120, 180, 255), width=2),
                                    fillLevel=0, brush=(70, 110, 220, 90))
        self.zero = pg.InfiniteLine(0, angle=90, pen=pg.mkPen((200, 200, 200, 90), style=pg.QtCore.Qt.PenStyle.DashLine))
        self.plot.addItem(self.zero)
        self.base = pg.InfiniteLine(0, angle=0, pen=pg.mkPen((200, 200, 200, 60)))
        self.plot.addItem(self.base)
        self.title = pg.TextItem("", color=(220, 230, 245), anchor=(0, 0))
        self.title.setParentItem(self.plot.vb)
        self.title.setPos(8, 4)
        self.peak_items = []
        self._vrange = None
        self._font_scale = 1.0
        self.set_font_scale(1.0)

    def set_font_scale(self, s):
        self._font_scale = s
        f = QFont()
        f.setPointSizeF(9.5 * s)
        for ax in ("bottom", "top", "left"):
            a = self.plot.getAxis(ax)
            a.setTickFont(f)
            a.label.setFont(f)
            a.setTextPen((190, 200, 220))
        tf = QFont()
        tf.setPointSizeF(11 * s)
        tf.setBold(True)
        self.title.setFont(tf)

    def y_view(self):
        return tuple(self.plot.vb.viewRange()[1])

    def set_view(self, vmin, vmax):
        if self._vrange != (vmin, vmax):
            self._vrange = (vmin, vmax)
            self.plot.setXRange(vmin, vmax, padding=0)

    def display(self, res, corr, title="", show_spikes=True, yrange=None):
        self.top_axis.corr = corr
        self.top_axis.picture = None
        self.top_axis.update()
        if res is None:
            self.curve.setData([], [])
            self.title.setText(title)
            return
        v, y = res["v"], res["y"]
        self.curve.setData(v, y)
        db = res["mode"] in ("raw", "sdr")
        self.base.setVisible(not db)
        self.curve.setFillLevel(-1000 if res["mode"] == "sdr" else (None if db else 0))
        self.plot.setLabel("left", res["ylabel"])
        vmin, vmax = self._vrange or (v.min(), v.max())
        m = (v >= vmin) & (v <= vmax)
        if yrange is not None:
            self.plot.setYRange(yrange[0], yrange[1], padding=0)
        elif m.any():
            lo, hi = float(np.min(y[m])), float(np.max(y[m]))
            pad = 0.12 * (hi - lo + 1e-9)
            self.plot.setYRange(lo - pad, hi + pad * 2.2, padding=0)
        for it in self.peak_items:
            self.plot.removeItem(it)
        self.peak_items = []
        f = QFont()
        f.setPointSizeF(9.5 * self._font_scale)
        f.setBold(True)
        for amp, vel in res.get("peaks", []):
            t = pg.TextItem(f"{round(vel) + 0:+d} km/s", color=(255, 240, 120), anchor=(0.5, 1.2))
            t.setFont(f)
            t.setPos(vel, amp)
            ln = pg.ScatterPlotItem([vel], [amp], symbol="t", size=10 * self._font_scale,
                                    brush=(255, 240, 120), pen=None)
            self.plot.addItem(t)
            self.plot.addItem(ln)
            self.peak_items += [t, ln]
        if show_spikes:
            for a, b in res.get("spikes", []):
                reg = pg.LinearRegionItem((a, b), movable=False, brush=(255, 120, 80, 45),
                                          pen=pg.mkPen((255, 120, 80, 0)))
                reg.setZValue(-10)
                self.plot.addItem(reg)
                self.peak_items.append(reg)
        self.title.setText(title)
