"""Spectrum averaging, background/baseline correction and peak finding."""
from __future__ import annotations

import math
import os

import numpy as np

from . import astro
from .paths import user_dir


class Integrator:
    def __init__(self):
        self.reset()
        self.background = None
        self.background_key = None
        self._load_background()

    # ------------------------------------------------------------ averaging
    def reset(self):
        self.avg = None
        self.t_total = 0.0
        self.n = 0

    def add(self, p: np.ndarray, dt: float, tau: float):
        p = np.asarray(p, dtype=np.float64)
        if self.avg is None or self.avg.shape != p.shape:
            self.avg = p.copy()
            self.t_total = dt
            self.n = 1
            return
        self.n += 1
        self.t_total += dt
        if tau and tau > 0:
            a = 1.0 - math.exp(-dt / tau)
            a = max(a, 1.0 / self.n)          # plain mean until we've filled tau
            self.avg += a * (p - self.avg)
        else:
            self.avg += (p - self.avg) / self.n

    def effective_time(self, tau: float) -> float:
        return min(self.t_total, tau) if tau and tau > 0 else self.t_total

    # ----------------------------------------------------------- background
    def _bg_path(self):
        return os.path.join(user_dir(), "background.npz")

    def capture_background(self, key):
        if self.avg is None:
            return False
        self.background = self.avg.copy()
        self.background_key = key
        try:
            np.savez(self._bg_path(), bg=self.background, key=np.array(key, dtype=float))
        except Exception:
            pass
        return True

    def set_background(self, psd, key):
        self.background = np.asarray(psd, dtype=np.float64).copy()
        self.background_key = key
        try:
            np.savez(self._bg_path(), bg=self.background, key=np.array(key, dtype=float))
        except Exception:
            pass

    def clear_background(self):
        self.background = None
        self.background_key = None
        try:
            os.remove(self._bg_path())
        except Exception:
            pass

    def _load_background(self):
        try:
            d = np.load(self._bg_path())
            self.background = d["bg"]
            self.background_key = tuple(float(x) for x in d["key"])
        except Exception:
            pass

    def background_valid(self, key) -> bool:
        return (self.background is not None and self.background_key is not None
                and len(self.background_key) == len(key)
                and all(abs(a - b) < 1e-6 for a, b in zip(self.background_key, key)))


def _smooth(y, n):
    n = int(n)
    if n <= 1:
        return y
    k = np.ones(n) / n
    pad = np.pad(y, (n, n), mode="edge")
    return np.convolve(pad, k, mode="same")[n:-n]


def _rolling_median(y, w):
    w = max(3, int(w) | 1)
    h = w // 2
    pad = np.pad(y, (h, h), mode="reflect")
    win = np.lib.stride_tricks.sliding_window_view(pad, w)
    return np.median(win, axis=1)


def _flank_median(y, gap, width):
    """Local level from the channels on BOTH sides of each point, skipping +-gap.

    Unlike a plain running median this doesn't follow a narrow feature that sits on a
    slope, so the feature's true width can be measured.
    """
    n = len(y)
    pad = np.pad(y, (gap + width, gap + width), mode="reflect")
    win = np.lib.stride_tricks.sliding_window_view(pad, width)
    left = win[0:n]                       # channels i-gap-width .. i-gap-1
    right = win[2 * gap + width + 1: 2 * gap + width + 1 + n]   # i+gap+1 .. i+gap+width
    # mean of the two sides' medians = straight line across the feature, so a narrow
    # line sitting on the slope of a broad one is measured correctly
    return 0.5 * (np.median(left, axis=1) + np.median(right, axis=1))


def remove_spikes(v, y, max_fwhm_kms=5.0, k=5.0, win_kms=60.0):
    """Remove narrow radio-interference spikes.

    Real hydrogen features are many km/s wide; interference from computers, USB, chargers
    etc. is only a few channels wide. A spike is anything that rises more than k x noise
    above a running median AND whose full width at half maximum is <= max_fwhm_kms.
    It is replaced by the running median. Returns (cleaned y, list of (v_lo, v_hi)).
    """
    n = len(y)
    if n < 20:
        return y, []
    dv = abs(v[1] - v[0])
    # With coarse FFTs (few channels) a narrow hydrogen line is only a few channels wide,
    # so judge interference by channel count there: a carrier is ~1-2 channels after the FFT.
    max_fwhm_eff = max_fwhm_kms if dv < 0.9 else min(max_fwhm_kms, 2.2 * dv)
    med = _flank_median(y, max(2, round(6.0 / dv)), max(4, round(15.0 / dv)))
    r = y - med
    sig = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-30
    rs = _smooth(r, max(1, round(1.0 / dv)))
    out = y.copy()
    regions = []
    done = np.zeros(n, bool)
    for i in np.argsort(-rs):
        if rs[i] < k * sig:
            break
        if done[i]:
            continue
        half = rs[i] / 2.0
        lo = i
        while lo > 0 and rs[lo - 1] > half:
            lo -= 1
        hi = i
        while hi < n - 1 and rs[hi + 1] > half:
            hi += 1
        # interpolate the half-maximum crossings for an accurate width even with coarse bins
        left = lo - (rs[lo] - half) / (rs[lo] - rs[lo - 1]) if lo > 0 and rs[lo] != rs[lo - 1] else lo - 0.5
        right = hi + (rs[hi] - half) / (rs[hi] - rs[hi + 1]) if hi < n - 1 and rs[hi] != rs[hi + 1] else hi + 0.5
        fwhm = (right - left) * dv
        # extent to replace: the spike plus its skirts, but never more than ~1 FWHM
        # either side, so a spike sitting on top of real hydrogen doesn't eat the line
        reach = max(1, hi - lo + 1) + max(1, round(1.0 / dv))
        a = lo
        while a > max(0, lo - reach) and rs[a - 1] > 1.5 * sig:
            a -= 1
        b = hi
        while b < min(n - 1, hi + reach) and rs[b + 1] > 1.5 * sig:
            b += 1
        done[a:b + 1] = True
        if fwhm <= max_fwhm_eff:
            out[a:b + 1] = med[a:b + 1]
            regions.append((float(min(v[a], v[b])), float(max(v[a], v[b]))))
    return out, regions


def process(cfg, integ: Integrator, f_mhz: np.ndarray, v_lsr: np.ndarray, bg_ok: bool, corr: float = 0.0):
    """Return dict(v, y, ylabel, noise, peaks) ready for plotting."""
    p = integ.avg
    if p is None:
        return None
    p = p.copy()
    nfft = len(p)
    mode = cfg.get("mode", "baseline")
    if mode.startswith("background") and not bg_ok:
        mode = "baseline" if mode == "background+baseline" else "baseline"
        fallback = True
    else:
        fallback = False

    # DC spike notch
    bin_hz = float(cfg.get("sample_rate", 2.4e6)) / nfft
    w_dc = max(1, int(round(3500.0 / bin_hz)))   # ~ +-3.5 kHz around the centre
    if cfg.get("dc_notch", True):
        c = nfft // 2
        w = w_dc
        lo, hi = c - w - 1, c + w + 1
        p[lo + 1:hi] = np.linspace(p[lo], p[hi], hi - lo + 1)[1:-1]

    # usable part of the band
    frac = float(cfg.get("band_use_fraction", 0.84)) if mode != "sdr" else 0.98
    keep = int(nfft * frac / 2)
    sl = slice(nfft // 2 - keep, nfft // 2 + keep)
    v = v_lsr[sl]
    y = p[sl]
    # The baseline region is fixed in *receiver* frequency (topocentric velocity), so
    # re-aiming the dish only relabels the axis and never changes the hump height.
    v_rx = v - corr

    if mode.startswith("background"):
        bg = integ.background.copy()
        if cfg.get("dc_notch", True):
            c = nfft // 2
            lo, hi = c - w_dc - 1, c + w_dc + 1
            bg[lo + 1:hi] = np.linspace(bg[lo], bg[hi], hi - lo + 1)[1:-1]
        y = y / np.maximum(bg[sl], 1e-30)

    spikes = []
    if cfg.get("remove_spikes", True):
        y, spikes = remove_spikes(v, y, float(cfg.get("spike_max_kms", 5.0)))

    ylabel = ""
    if mode == "raw":
        y = 10 * np.log10(np.maximum(y, 1e-30))
        y = y - np.median(y)
        ylabel = "Power (dB, relative)"
    elif mode == "sdr":
        # like SDR#'s IF Average: absolute dB with the receiver's shape left in
        # normalised so the level doesn't change with FFT size (Hann window: sum(w^2) = 0.375 N)
        y = 10 * np.log10(np.maximum(y, 1e-30) / (0.375 * nfft))
        ylabel = "Power (dB)"
    else:
        if mode in ("baseline", "background+baseline"):
            win = float(cfg.get("line_window_kms", 160))
            mask = np.abs(v_rx) > win
            if mask.sum() < 20:  # not enough baseline; use the outer 20% of band
                q = len(v) // 10
                mask = np.zeros(len(v), bool)
                mask[:q] = True
                mask[-q:] = True
            order = int(cfg.get("baseline_order", 3))
            x = np.linspace(-1, 1, len(v))
            base = _robust_baseline(x, y, mask, order)
            y = y / np.maximum(base, 1e-30)
        else:
            y = y / np.median(y)
        y = (y - 1.0) * 100.0
        ylabel = "Signal above background (%)"

    # smoothing
    dv = abs(v[1] - v[0]) if len(v) > 1 else 1.0
    y = _smooth(y, max(1, round(float(cfg.get("smooth_kms", 3)) / dv)))

    # noise estimate from line-free region
    win = float(cfg.get("line_window_kms", 160))
    off = np.abs(v_rx) > win
    if off.sum() > 10:
        r = y[off] - np.median(y[off])
        noise = float(1.4826 * np.median(np.abs(r)))  # robust: ignores interference spikes
    else:
        noise = float(np.std(np.diff(y)) / math.sqrt(2))
    peaks = find_peaks(v, y, noise, cfg) if cfg.get("show_peaks", True) and mode not in ("raw", "sdr") else []

    # sort ascending velocity for plotting
    order = np.argsort(v)
    return dict(v=v[order], y=y[order], ylabel=ylabel, noise=noise, peaks=peaks,
                mode=mode, fallback=fallback, spikes=spikes)


def _robust_baseline(x, y, mask, order):
    """Polynomial fit that rejects interference spikes (iterative sigma clipping)."""
    m = mask.copy()
    base = np.full_like(y, np.median(y[mask]))
    for _ in range(6):
        if m.sum() <= order + 3:
            break
        try:
            coef = np.polyfit(x[m], y[m], order)
        except Exception:
            break
        base = np.polyval(coef, x)
        r = y - base
        sig = 1.4826 * np.median(np.abs(r[m] - np.median(r[m]))) + 1e-12
        new = mask & (np.abs(r) < 3.0 * sig)
        if np.array_equal(new, m):
            break
        m = new
    return base


def _width_kms(v, ys, i):
    """Full width at half maximum of the feature at index i."""
    half = ys[i] / 2.0
    lo = i
    while lo > 0 and ys[lo] > half:
        lo -= 1
    hi = i
    while hi < len(ys) - 1 and ys[hi] > half:
        hi += 1
    return abs(v[hi] - v[lo])


def find_peaks(v, y, noise, cfg, max_peaks=4, min_sep=18.0, min_width=8.0):
    if noise <= 0 or len(y) < 10:
        return []
    thr = float(cfg.get("peak_sigma", 5.0)) * noise
    win = float(cfg.get("line_window_kms", 160))
    dv = abs(v[1] - v[0])
    ys = _smooth(y, max(1, round(6.0 / dv)))
    cand = []
    for i in range(2, len(ys) - 2):
        if ys[i] > thr and ys[i] >= ys[i - 1] and ys[i] >= ys[i + 1] and ys[i] >= ys[i - 2] and ys[i] >= ys[i + 2]:
            # hydrogen lines are broad; narrow spikes are radio interference
            if abs(v[i]) < win + 20 and _width_kms(v, y, i) >= min_width:
                cand.append((ys[i], v[i]))
    cand.sort(reverse=True)
    out = []
    for amp, vel in cand:
        if all(abs(vel - o[1]) > min_sep for o in out):
            # require a dip between this and existing peaks (real separate component)
            ok = True
            for _a, ov in out:
                lo, hi = sorted((ov, vel))
                seg = ys[(v >= lo) & (v <= hi)]
                if len(seg) and seg.min() > 0.8 * min(amp, _a):
                    ok = False
            if ok:
                out.append((float(amp), float(vel)))
        if len(out) >= max_peaks:
            break
    return sorted(out, key=lambda t: t[1])


def describe_peaks(l_deg, b_deg, peaks):
    """Plain-language list of (velocity, distances, ambiguous)."""
    res = []
    for amp, vel in peaks:
        if abs(vel) < 12:
            # local gas: velocities this small can't be turned into a distance
            res.append(dict(v=vel, amp=amp, d=[0.6], ambiguous=False, local=True))
            continue
        ds, amb = astro.distances_for_velocity(l_deg, vel) if abs(b_deg) < 15 else ([], False)
        res.append(dict(v=vel, amp=amp, d=ds, ambiguous=amb, local=False))
    return res
