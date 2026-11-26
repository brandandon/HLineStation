"""Settings, stored as JSON in %APPDATA%\\HLineStation\\settings.json."""
from __future__ import annotations

import copy
import json
import os

from .paths import user_dir

DEFAULTS = {
    # Observing site (defaults: Alton / Riverbend area, Illinois — change in Settings)
    "site_name": "Riverbend Astronomy Club",
    "lat": 38.89,
    "lon": -90.18,
    "elev_m": 180.0,

    # Dish pointing (fixed / drift scan)
    "dish_az": 180.0,
    "dish_el": 60.0,
    "dish_diameter_m": 0.7,
    "beam_deg": 0.0,              # 0 = compute from diameter
    "reset_on_repoint": True,
    "observation_dir": "",  # blank = Documents/H-Line Station/Observations

    # Receiver
    "source": "rtlsdr",           # "rtlsdr" or "simulator"
    "device_index": 0,
    "center_mhz": 1420.40575,
    "sample_rate": 2.4e6,
    "gain": 40.2,                 # dB or "auto"
    "ppm": 0,
    "bias_tee": False,            # OFF until the operator confirms compatible powered equipment
    "nfft": 2048,
    "ffts_per_block": 128,
    "autostart": False,
    "auto_reconnect": True,      # only for an unexpectedly stopped physical receiver
    "reconnect_max_attempts": 5, # bounded; operator Stop cancels pending retries

    # Processing
    "integration_s": 60.0,        # running average time constant; 0 = average forever
    "mode": "baseline",           # raw | background | baseline | background+baseline
    "baseline_order": 2,
    "line_window_kms": 150.0,     # |v| inside this is NOT used for the baseline fit
    "band_use_fraction": 0.76,    # trim rolled-off band edges
    "dc_notch": True,
    "smooth_kms": 4.0,
    "remove_spikes": True,        # remove narrow radio-interference spikes
    "spike_max_kms": 5.0,         # anything narrower than this (FWHM) counts as interference
    "show_spikes": True,          # shade where interference was removed
    "show_peaks": True,
    "peak_sigma": 5.0,
    "auto_bg_offset_mhz": 2.5,    # tune this far either side of the line for Auto background
    "auto_bg_seconds": 60.0,

    # Display
    "y_fixed": False,             # lock the vertical scale instead of auto-zooming
    "y_pct_min": -5.0,            # fixed scale for the % views
    "y_pct_max": 40.0,
    "y_db_span": 4.0,             # fixed scale height for the dB views (auto-centred)
    "kiosk_fixed_scale": True,    # outreach mode always uses the fixed scale
    "v_min": -200.0,
    "v_max": 200.0,
    "show_constellations": True,
    "show_star_names": True,
    "show_milky_way": True,
    "drift_hours": 4,
    "kiosk_font_scale": 1.0,
    "kiosk_captions": True,
}

MODES = [
    ("baseline", "Auto baseline (no background needed)"),
    ("background", "Divide by captured background"),
    ("background+baseline", "Background + baseline"),
    ("raw", "Raw power (dB)"),
    ("sdr", "SDR#-style (raw dB, whole band)"),
]


def beam_width(cfg) -> float:
    if float(cfg.get("beam_deg", 0) or 0) > 0:
        return float(cfg["beam_deg"])
    lam = 299.792458 / 1420.405751768
    return 70.0 * lam / max(float(cfg.get("dish_diameter_m", 0.7)), 0.1)


def _path():
    return os.path.join(user_dir(), "settings.json")


def load() -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save(cfg: dict):
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:  # pragma: no cover
        print("Could not save settings:", e)
