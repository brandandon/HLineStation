from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .config import MODES, beam_width


def _dspin(lo, hi, val, dec=2, step=1.0, suffix=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(float(val))
    if suffix:
        s.setSuffix(suffix)
    return s


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("H-Line Station – Settings")
        self.cfg = dict(cfg)
        tabs = QTabWidget()
        w = {}

        # site
        t = QWidget(); fl = QFormLayout(t)
        w["site_name"] = QLineEdit(cfg["site_name"])
        w["lat"] = _dspin(-90, 90, cfg["lat"], 4, 0.01, "°")
        w["lon"] = _dspin(-180, 180, cfg["lon"], 4, 0.01, "°  (west is negative)")
        w["elev_m"] = _dspin(-100, 6000, cfg["elev_m"], 0, 10, " m")
        fl.addRow("Site name", w["site_name"])
        fl.addRow("Latitude", w["lat"])
        fl.addRow("Longitude", w["lon"])
        fl.addRow("Elevation", w["elev_m"])
        tabs.addTab(t, "Site")

        # dish
        t = QWidget(); fl = QFormLayout(t)
        w["dish_az"] = _dspin(0, 360, cfg["dish_az"], 1, 1, "°")
        w["dish_el"] = _dspin(0, 90, cfg["dish_el"], 1, 1, "°")
        w["dish_diameter_m"] = _dspin(0.1, 30, cfg["dish_diameter_m"], 2, 0.05, " m")
        w["beam_deg"] = _dspin(0, 90, cfg["beam_deg"], 1, 0.5, "°")
        w["beam_deg"].setSpecialValueText("auto (from diameter)")
        w["reset_on_repoint"] = QCheckBox("Restart the average when the dish is re-aimed")
        w["reset_on_repoint"].setChecked(cfg["reset_on_repoint"])
        w["drift_hours"] = QSpinBox(); w["drift_hours"].setRange(0, 12); w["drift_hours"].setValue(int(cfg["drift_hours"]))
        fl.addRow("Azimuth (N=0, E=90)", w["dish_az"])
        fl.addRow("Elevation", w["dish_el"])
        fl.addRow("Dish diameter", w["dish_diameter_m"])
        fl.addRow("Beam width override", w["beam_deg"])
        fl.addRow("", QLabel(f"Current beam width ≈ {beam_width(cfg):.1f}° (70·λ/D)"))
        fl.addRow("Drift track length", w["drift_hours"])
        fl.addRow("", w["reset_on_repoint"])
        tabs.addTab(t, "Dish")

        # receiver
        t = QWidget(); fl = QFormLayout(t)
        w["source"] = QComboBox()
        w["source"].addItem("RTL-SDR dongle", "rtlsdr")
        w["source"].addItem("Simulator (demo, no hardware)", "simulator")
        w["source"].setCurrentIndex(0 if cfg["source"] == "rtlsdr" else 1)
        w["device_index"] = QSpinBox(); w["device_index"].setRange(0, 9); w["device_index"].setValue(int(cfg["device_index"]))
        w["center_mhz"] = _dspin(24, 1766, cfg["center_mhz"], 5, 0.1, " MHz")
        w["sample_rate"] = QComboBox()
        for r in (1.024e6, 1.4e6, 1.8e6, 2.048e6, 2.4e6, 2.56e6, 2.88e6, 3.2e6):
            w["sample_rate"].addItem(f"{r/1e6:.3f} MS/s", r)
        idx = w["sample_rate"].findData(float(cfg["sample_rate"]))
        w["sample_rate"].setCurrentIndex(idx if idx >= 0 else 4)
        w["gain"] = QComboBox()
        w["gain"].addItem("auto", "auto")
        for g in (0.0, 0.9, 1.4, 2.7, 3.7, 7.7, 8.7, 12.5, 14.4, 15.7, 16.6, 19.7, 20.7, 22.9, 25.4,
                  28.0, 29.7, 32.8, 33.8, 36.4, 37.2, 38.6, 40.2, 42.1, 43.4, 43.9, 44.5, 48.0, 49.6):
            w["gain"].addItem(f"{g:.1f} dB", g)
        idx = w["gain"].findData(cfg["gain"] if cfg["gain"] == "auto" else float(cfg["gain"]))
        w["gain"].setCurrentIndex(idx if idx >= 0 else 0)
        w["ppm"] = QSpinBox(); w["ppm"].setRange(-200, 200); w["ppm"].setValue(int(cfg["ppm"]))
        w["bias_tee"] = QCheckBox("Bias-tee ON (powers the Discovery Dish feed/LNA)")
        w["bias_tee"].setChecked(cfg["bias_tee"])
        w["nfft"] = QComboBox()
        for n in (256, 512, 1024, 2048, 4096, 8192):
            w["nfft"].addItem(str(n), n)
        w["nfft"].setCurrentIndex(max(0, w["nfft"].findData(int(cfg["nfft"]))))
        w["autostart"] = QCheckBox("Start receiving when the program opens")
        w["autostart"].setChecked(cfg["autostart"])
        fl.addRow("Source", w["source"])
        fl.addRow("Device index", w["device_index"])
        fl.addRow("Centre frequency", w["center_mhz"])
        fl.addRow("Sample rate", w["sample_rate"])
        fl.addRow("Tuner gain", w["gain"])
        fl.addRow("Frequency correction (ppm)", w["ppm"])
        fl.addRow("FFT size", w["nfft"])
        fl.addRow("", w["bias_tee"])
        fl.addRow("", w["autostart"])
        w["auto_reconnect"] = QCheckBox("Reconnect automatically after unexpected RTL-SDR interruption")
        w["auto_reconnect"].setChecked(cfg.get("auto_reconnect", True))
        w["reconnect_max_attempts"] = QSpinBox()
        w["reconnect_max_attempts"].setRange(1, 20)
        w["reconnect_max_attempts"].setValue(int(cfg.get("reconnect_max_attempts", 5)))
        fl.addRow("", w["auto_reconnect"])
        fl.addRow("Maximum reconnect attempts", w["reconnect_max_attempts"])
        tabs.addTab(t, "Receiver")

        # storage: changes take effect after restarting the application.
        t = QWidget(); fl = QFormLayout(t)
        w["observation_dir"] = QLineEdit(str(cfg.get("observation_dir", "")))
        w["observation_dir"].setPlaceholderText("Default: Documents/H-Line Station/Observations")
        fl.addRow("Observation folder", w["observation_dir"])
        fl.addRow("", QLabel("Existing observations are not moved automatically.\nRestart after changing this folder."))
        tabs.addTab(t, "Storage")

        # processing
        t = QWidget(); fl = QFormLayout(t)
        w["mode"] = QComboBox()
        for k, lab in MODES:
            w["mode"].addItem(lab, k)
        w["mode"].setCurrentIndex(max(0, w["mode"].findData(cfg["mode"])))
        w["integration_s"] = _dspin(0, 3600, cfg["integration_s"], 0, 10, " s")
        w["integration_s"].setSpecialValueText("forever (until reset)")
        w["baseline_order"] = QSpinBox(); w["baseline_order"].setRange(0, 7); w["baseline_order"].setValue(int(cfg["baseline_order"]))
        w["line_window_kms"] = _dspin(20, 400, cfg["line_window_kms"], 0, 10, " km/s")
        w["band_use_fraction"] = _dspin(0.3, 1.0, cfg["band_use_fraction"], 2, 0.02)
        w["smooth_kms"] = _dspin(0, 30, cfg["smooth_kms"], 1, 0.5, " km/s")
        w["dc_notch"] = QCheckBox("Remove the RTL-SDR centre (DC) spike"); w["dc_notch"].setChecked(cfg["dc_notch"])
        w["show_peaks"] = QCheckBox("Mark hydrogen peaks"); w["show_peaks"].setChecked(cfg["show_peaks"])
        w["remove_spikes"] = QCheckBox("Remove narrow interference spikes"); w["remove_spikes"].setChecked(cfg.get("remove_spikes", True))
        w["show_spikes"] = QCheckBox("Shade where spikes were removed (hidden in outreach mode)"); w["show_spikes"].setChecked(cfg.get("show_spikes", True))
        w["spike_max_kms"] = _dspin(1, 15, cfg.get("spike_max_kms", 5.0), 1, 0.5, " km/s")
        w["peak_sigma"] = _dspin(2, 30, cfg["peak_sigma"], 1, 0.5, " × noise")
        w["auto_bg_offset_mhz"] = _dspin(1.0, 10.0, cfg.get("auto_bg_offset_mhz", 2.5), 2, 0.1, " MHz")
        w["auto_bg_seconds"] = _dspin(10, 600, cfg.get("auto_bg_seconds", 60), 0, 10, " s")
        fl.addRow("Processing", w["mode"])
        fl.addRow("Averaging time", w["integration_s"])
        fl.addRow("Baseline polynomial order", w["baseline_order"])
        fl.addRow("Line window (±, excluded from baseline)", w["line_window_kms"])
        fl.addRow("Fraction of band to use", w["band_use_fraction"])
        fl.addRow("Smoothing", w["smooth_kms"])
        fl.addRow("Peak threshold", w["peak_sigma"])
        fl.addRow("Auto background offset (±)", w["auto_bg_offset_mhz"])
        fl.addRow("Auto background duration", w["auto_bg_seconds"])
        fl.addRow("", w["dc_notch"])
        fl.addRow("", w["show_peaks"])
        fl.addRow("Spikes narrower than", w["spike_max_kms"])
        fl.addRow("", w["remove_spikes"])
        fl.addRow("", w["show_spikes"])
        tabs.addTab(t, "Processing")

        # display
        t = QWidget(); fl = QFormLayout(t)
        w["v_min"] = _dspin(-500, 0, cfg["v_min"], 0, 10, " km/s")
        w["v_max"] = _dspin(0, 500, cfg["v_max"], 0, 10, " km/s")
        w["show_constellations"] = QCheckBox("Constellations"); w["show_constellations"].setChecked(cfg["show_constellations"])
        w["show_star_names"] = QCheckBox("Bright star names"); w["show_star_names"].setChecked(cfg["show_star_names"])
        w["show_milky_way"] = QCheckBox("Milky Way glow"); w["show_milky_way"].setChecked(cfg["show_milky_way"])
        w["kiosk_captions"] = QCheckBox("Plain-language captions in outreach mode"); w["kiosk_captions"].setChecked(cfg["kiosk_captions"])
        w["kiosk_font_scale"] = _dspin(0.6, 3.0, cfg["kiosk_font_scale"], 2, 0.1, " ×")
        w["y_fixed"] = QCheckBox("Lock the vertical scale (no auto-zoom)"); w["y_fixed"].setChecked(cfg.get("y_fixed", False))
        w["kiosk_fixed_scale"] = QCheckBox("Always lock the scale in outreach mode"); w["kiosk_fixed_scale"].setChecked(cfg.get("kiosk_fixed_scale", True))
        w["y_pct_min"] = _dspin(-100, 100, cfg.get("y_pct_min", -5), 1, 1, " %")
        w["y_pct_max"] = _dspin(-50, 1000, cfg.get("y_pct_max", 40), 1, 5, " %")
        w["y_db_span"] = _dspin(0.2, 40, cfg.get("y_db_span", 4), 1, 0.5, " dB")
        fl.addRow("", w["y_fixed"])
        fl.addRow("", w["kiosk_fixed_scale"])
        fl.addRow("Locked scale bottom (% views)", w["y_pct_min"])
        fl.addRow("Locked scale top (% views)", w["y_pct_max"])
        fl.addRow("Locked scale height (dB views)", w["y_db_span"])
        fl.addRow("Spectrum from", w["v_min"])
        fl.addRow("Spectrum to", w["v_max"])
        fl.addRow("Outreach text size", w["kiosk_font_scale"])
        for k in ("show_constellations", "show_star_names", "show_milky_way", "kiosk_captions"):
            fl.addRow("", w[k])
        tabs.addTab(t, "Display")

        self.w = w
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)

    def values(self):
        out = dict(self.cfg)
        for k, wid in self.w.items():
            if isinstance(wid, QCheckBox):
                out[k] = wid.isChecked()
            elif isinstance(wid, QComboBox):
                out[k] = wid.currentData()
            elif isinstance(wid, QLineEdit):
                out[k] = wid.text()
            else:
                out[k] = wid.value()
        return out
