"""Minimal ctypes wrapper around librtlsdr (only what H-Line Station needs).

Loads drivers/rtlsdr.dll (RTL-SDR Blog build: supports V3 and V4 dongles and the
bias-tee) on Windows; falls back to a system librtlsdr elsewhere.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys

import numpy as np

from .paths import app_dir

_lib = None


def _load():
    global _lib
    if _lib is not None:
        return _lib
    cands = []
    drv = os.path.join(app_dir(), "drivers")
    if sys.platform.startswith("win"):
        cands.append(os.path.join(drv, "rtlsdr.dll"))
        cands.append("rtlsdr.dll")
        try:
            os.add_dll_directory(drv)
        except Exception:
            pass
    else:
        cands += [os.path.join(drv, "librtlsdr.so"), "librtlsdr.so.0", "librtlsdr.so",
                  "librtlsdr.dylib", ctypes.util.find_library("rtlsdr")]
    err = None
    for c in cands:
        if not c:
            continue
        try:
            _lib = ctypes.CDLL(c)
            break
        except OSError as e:
            err = e
    if _lib is None:
        raise OSError("Could not load the RTL-SDR driver (rtlsdr.dll): %s" % err)
    L = _lib
    p = ctypes.c_void_p
    L.rtlsdr_get_device_count.restype = ctypes.c_uint32
    L.rtlsdr_get_device_name.restype = ctypes.c_char_p
    L.rtlsdr_get_device_name.argtypes = [ctypes.c_uint32]
    L.rtlsdr_open.argtypes = [ctypes.POINTER(p), ctypes.c_uint32]
    L.rtlsdr_close.argtypes = [p]
    L.rtlsdr_set_sample_rate.argtypes = [p, ctypes.c_uint32]
    L.rtlsdr_set_center_freq.argtypes = [p, ctypes.c_uint32]
    L.rtlsdr_get_center_freq.restype = ctypes.c_uint32
    L.rtlsdr_get_center_freq.argtypes = [p]
    L.rtlsdr_set_freq_correction.argtypes = [p, ctypes.c_int]
    L.rtlsdr_set_tuner_gain_mode.argtypes = [p, ctypes.c_int]
    L.rtlsdr_set_tuner_gain.argtypes = [p, ctypes.c_int]
    L.rtlsdr_get_tuner_gain.argtypes = [p]
    L.rtlsdr_get_tuner_gains.argtypes = [p, ctypes.POINTER(ctypes.c_int)]
    L.rtlsdr_set_agc_mode.argtypes = [p, ctypes.c_int]
    L.rtlsdr_reset_buffer.argtypes = [p]
    L.rtlsdr_read_sync.argtypes = [p, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    L.rtlsdr_get_tuner_type.argtypes = [p]
    if hasattr(L, "rtlsdr_set_bias_tee"):
        L.rtlsdr_set_bias_tee.argtypes = [p, ctypes.c_int]
    return L


TUNERS = {0: "unknown", 1: "E4000", 2: "FC0012", 3: "FC0013", 4: "FC2580", 5: "R820T", 6: "R828D"}


def device_count() -> int:
    return int(_load().rtlsdr_get_device_count())


class RtlSdr:
    def __init__(self, index=0):
        L = _load()
        self.L = L
        n = L.rtlsdr_get_device_count()
        if n == 0:
            raise IOError("No RTL-SDR dongle found")
        self.name = (L.rtlsdr_get_device_name(index) or b"RTL-SDR").decode(errors="ignore")
        self.dev = ctypes.c_void_p()
        r = L.rtlsdr_open(ctypes.byref(self.dev), index)
        if r < 0:
            raise IOError("Could not open RTL-SDR #%d (error %d)" % (index, r))
        self.tuner = TUNERS.get(L.rtlsdr_get_tuner_type(self.dev), "?")

    def _chk(self, r, what):
        if r < 0:
            raise IOError("%s failed (error %d)" % (what, r))

    def set_sample_rate(self, hz):
        self._chk(self.L.rtlsdr_set_sample_rate(self.dev, int(hz)), "Set sample rate")

    def set_center_freq(self, hz):
        self._chk(self.L.rtlsdr_set_center_freq(self.dev, int(round(hz))), "Set frequency")

    def set_ppm(self, ppm):
        if ppm:
            r = self.L.rtlsdr_set_freq_correction(self.dev, int(ppm))
            if r < 0 and r != -2:
                self._chk(r, "Set ppm")

    def gains(self):
        n = self.L.rtlsdr_get_tuner_gains(self.dev, None)
        if n <= 0:
            return []
        arr = (ctypes.c_int * n)()
        self.L.rtlsdr_get_tuner_gains(self.dev, arr)
        return [g / 10.0 for g in arr]

    def set_gain(self, gain):
        if str(gain).lower() == "auto":
            self.L.rtlsdr_set_tuner_gain_mode(self.dev, 0)
            return "auto"
        self.L.rtlsdr_set_tuner_gain_mode(self.dev, 1)
        g = float(gain)
        gs = self.gains()
        if gs:
            g = min(gs, key=lambda x: abs(x - g))
        self._chk(self.L.rtlsdr_set_tuner_gain(self.dev, int(round(g * 10))), "Set gain")
        self.L.rtlsdr_set_agc_mode(self.dev, 0)
        return g

    def set_bias_tee(self, on):
        if not hasattr(self.L, "rtlsdr_set_bias_tee"):
            raise IOError("this driver has no bias-tee support")
        self._chk(self.L.rtlsdr_set_bias_tee(self.dev, 1 if on else 0), "Bias-tee")

    def reset_buffer(self):
        self.L.rtlsdr_reset_buffer(self.dev)

    def read_samples(self, n):
        nbytes = int(n) * 2
        buf = (ctypes.c_ubyte * nbytes)()
        got = ctypes.c_int(0)
        self._chk(self.L.rtlsdr_read_sync(self.dev, buf, nbytes, ctypes.byref(got)), "Read samples")
        a = np.frombuffer(buf, dtype=np.uint8, count=got.value).astype(np.float32)
        a = (a - 127.4) / 128.0
        return a[0::2] + 1j * a[1::2]

    def close(self):
        if self.dev:
            self.L.rtlsdr_close(self.dev)
            self.dev = ctypes.c_void_p()
