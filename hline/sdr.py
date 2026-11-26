"""Receiver back-ends: RTL-SDR (direct librtlsdr) and a built-in simulator.

Both run in a QThread and emit averaged power spectra (linear, fftshifted).
"""
from __future__ import annotations

import time
import traceback

import numpy as np
from PySide6.QtCore import QThread, Signal

from . import astro


class ReceiverThread(QThread):
    spectrum = Signal(object, float)      # (power array, seconds of data)
    status = Signal(str, bool)            # (message, is_error)
    opened = Signal(str)                  # description of device
    bgProgress = Signal(float)            # 0..1 while an auto-background is running
    bgDone = Signal(object)               # averaged off-frequency spectrum (or None on failure)
    acquisitionEnded = Signal(str, bool)  # reason, unexpected (device error or unrequested exit)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self._running = False
        self._bg_req = None
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True
        self._running = False

    def request_background(self, offset_mhz: float, seconds: float):
        """Measure the receiver's own bandpass by tuning away from the hydrogen line.

        Half the time is spent at centre+offset and half at centre-offset; averaging the
        two cancels any slow slope of the feed's RF filter. The hydrogen line is outside
        the band at both settings, so what remains is purely the receiver's shape.
        """
        self._bg_req = (float(offset_mhz), float(seconds))

    # ---------------------------------------------------------------- helpers
    def _psd(self, samples: np.ndarray, nfft: int, window: np.ndarray) -> np.ndarray:
        n = (len(samples) // nfft) * nfft
        x = samples[:n].reshape(-1, nfft)
        spec = np.fft.fft(x * window, axis=1)
        p = (spec.real ** 2 + spec.imag ** 2).mean(axis=0)
        return np.fft.fftshift(p)


class RtlSdrThread(ReceiverThread):
    def run(self):
        self._running = True
        self._stop_requested = False
        failure = None
        c = self.cfg
        nfft = int(c["nfft"])
        rate = float(c["sample_rate"])
        sdr = None
        try:
            from . import rtlsdr_lite
            n = rtlsdr_lite.device_count()
            if n == 0:
                raise IOError("No RTL-SDR dongle found. Check the USB cable, and close SDR# "
                              "(only one program can use the dongle at a time).")
            idx = int(c.get("device_index", 0))
            if idx < 0 or idx >= n:
                raise IOError("Device index %d requested but only %d dongle(s) found" % (idx, n))
            sdr = rtlsdr_lite.RtlSdr(idx)
            sdr.set_sample_rate(rate)
            sdr.set_center_freq(float(c["center_mhz"]) * 1e6)
            sdr.set_ppm(int(c.get("ppm", 0)))
            g = sdr.set_gain(c.get("gain", "auto"))
            bias = ""
            if c.get("bias_tee", False):
                try:
                    sdr.set_bias_tee(True)
                    bias = " · bias-tee on"
                except Exception as e:
                    self.status.emit("Could not switch on the bias-tee (%s). The Discovery Dish feed "
                                     "needs power from the bias-tee or an external injector." % e, True)
            gtxt = "auto" if g == "auto" else "%.1f dB" % g
            self.opened.emit("%s (%s tuner) – gain %s%s" % (sdr.name, sdr.tuner, gtxt, bias))
            self.status.emit("Receiving", False)
            window = np.hanning(nfft).astype(np.float32)
            # ~0.1 s of data per block whatever the FFT size (2^18 samples at 2.4 MS/s)
            block = max(nfft * max(16, int(c.get("ffts_per_block", 128))), 262144 // nfft * nfft)
            sdr.reset_buffer()
            sdr.read_samples(block)  # discard settling data
            if not self._running:
                return
            center_hz = float(c["center_mhz"]) * 1e6
            while self._running:
                if self._bg_req is not None:
                    offset, secs = self._bg_req
                    self._bg_req = None
                    acc, n_acc = None, 0
                    per_side = max(2, int(round(secs / 2 / (block / rate))))
                    try:
                        for side_i, sign in enumerate((+1, -1)):
                            sdr.set_center_freq(center_hz + sign * offset * 1e6)
                            sdr.reset_buffer()
                            sdr.read_samples(block)  # settle after retune
                            for k in range(per_side):
                                if not self._running:
                                    break
                                x = sdr.read_samples(block)
                                if len(x) < nfft:
                                    continue
                                p = self._psd(x.astype(np.complex64), nfft, window)
                                acc = p if acc is None else acc + p
                                n_acc += 1
                                self.bgProgress.emit((side_i * per_side + k + 1) / (2 * per_side))
                    finally:
                        sdr.set_center_freq(center_hz)
                        sdr.reset_buffer()
                        if self._running:
                            sdr.read_samples(block)
                    self.bgDone.emit(acc / n_acc if n_acc else None)
                    continue
                x = sdr.read_samples(block)
                if len(x) < nfft:
                    continue
                p = self._psd(x.astype(np.complex64), nfft, window)
                self.spectrum.emit(p, len(x) / rate)
        except Exception as e:
            msg = str(e) or e.__class__.__name__
            failure = msg
            if "open" in msg.lower():
                msg += (" — Is SDR# (or another SDR program) still running? Only one program can use "
                        "the RTL-SDR at a time. If the dongle has never been used on this PC, install "
                        "the WinUSB driver with Zadig (same as for SDR#).")
            self.status.emit("RTL-SDR: " + msg, True)
            traceback.print_exc()
        finally:
            if sdr is not None:
                try:
                    if c.get("bias_tee", False):
                        sdr.set_bias_tee(False)
                except Exception:
                    pass
                try:
                    sdr.close()
                except Exception:
                    pass
            self._running = False
            self.acquisitionEnded.emit(failure or ("operator_stop" if self._stop_requested else "receiver_ended"),
                                       failure is not None or not self._stop_requested)


class SimulatorThread(ReceiverThread):
    """Generates realistic-looking spectra for demos and testing.

    pointing_fn() -> (ra_j2000, dec_j2000, vlsr_correction)
    """

    def __init__(self, cfg, pointing_fn, parent=None):
        super().__init__(cfg, parent)
        self.pointing_fn = pointing_fn
        self.model = astro.HISimulator()

    def run(self):
        self._running = True
        self._stop_requested = False
        c = self.cfg
        nfft = int(c["nfft"])
        rate = float(c["sample_rate"])
        center = float(c["center_mhz"])
        f = center + (np.arange(nfft) - nfft / 2) * rate / nfft / 1e6
        v_topo = astro.freq_to_vtopo(f)
        x = np.linspace(-1, 1, nfft)
        # RTL-SDR-like bandpass: rolled-off edges, gentle ripple and tilt
        bandpass = (1.0 / (1.0 + (np.abs(x) / 0.94) ** 26)) * (1 + 0.05 * x + 0.006 * np.cos(9 * x))
        bandpass = np.maximum(bandpass, 0.02)
        bandpass[nfft // 2] *= 2.5  # DC spike
        navg = max(16, int(c.get("ffts_per_block", 128)), 262144 // nfft)
        dt = nfft * navg / rate
        self.opened.emit("Simulator (no hardware)")
        self.status.emit("Simulating", False)
        prof = np.zeros(nfft)
        last = 0.0
        while self._running:
            if self._bg_req is not None:
                _offset, secs = self._bg_req
                self._bg_req = None
                steps = max(4, int(secs / dt))
                acc = np.zeros(nfft)
                for k in range(steps):
                    if not self._running:
                        break
                    noise = np.random.chisquare(2 * navg, nfft) / (2 * navg)
                    acc += bandpass * noise * 1e4
                    self.bgProgress.emit((k + 1) / steps)
                    self.msleep(int(dt * 1000))
                self.bgDone.emit(acc / max(1, k + 1) if self._running else None)
                continue
            now = time.time()
            if now - last > 2.0:
                try:
                    ra, dec, corr = self.pointing_fn()
                    l, b = astro.eq_to_gal(ra, dec)
                    prof = self.model.profile(float(l), float(b), v_topo + corr)
                except Exception:
                    traceback.print_exc()
                last = now
            tsys = 1.0 + 0.035 * prof
            noise = np.random.chisquare(2 * navg, nfft) / (2 * navg)
            self.spectrum.emit(bandpass * tsys * noise * 1e4, dt)
            self.msleep(int(dt * 1000))
        self._running = False
        self.acquisitionEnded.emit("operator_stop" if self._stop_requested else "simulator_ended",
                                   not self._stop_requested)
