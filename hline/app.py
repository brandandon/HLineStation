"""H-Line Station – main window."""
from __future__ import annotations

import math
import html as html_utils
import os
import sys
from datetime import datetime

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox,
                               QLabel, QMainWindow, QMessageBox, QSizePolicy,
                               QSplitter, QToolBar, QVBoxLayout, QWidget)

from . import astro, config
from .config import MODES, beam_width
from .galaxymap import GalaxyMap
from .paths import app_dir, snapshot_dir, observation_dir, user_dir
from .observations import ObservationStore, utc_stamp
from .recovery import preserve_checkpoint
from .receiver_events import is_current_event
from .reconnect import retry_delay
from .processing import Integrator, describe_peaks, process
from .sdr import RtlSdrThread, SimulatorThread
from .settings_dialog import SettingsDialog
from .skydome import SkyDome
from .spectrum import SpectrumWidget

try:
    import ephem
except Exception:  # pragma: no cover
    ephem = None

APP_NAME = "H-Line Station"
VERSION = "1.0"

DARK_QSS = """
QMainWindow, QWidget { background: #070a12; color: #d8e0ee; }
QToolBar { background: #0d1220; border: 0; spacing: 6px; padding: 4px; }
QToolBar QToolButton { padding: 4px 8px; border-radius: 4px; }
QToolBar QToolButton:hover { background: #1b2540; }
QToolBar QToolButton:checked { background: #1d3b2c; color: #9dffc4; }
QStatusBar { background: #0d1220; color: #9aa8c0; }
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit { background: #121a2e; border: 1px solid #263252; padding: 2px 4px; border-radius: 3px; }
QSplitter::handle { background: #141c30; }
QTabWidget::pane { border: 1px solid #263252; }
QTabBar::tab { background: #121a2e; padding: 6px 12px; }
QTabBar::tab:selected { background: #1d2a48; }
QPushButton { background: #1b2540; border: 1px solid #2c3a60; padding: 4px 12px; border-radius: 3px; }
"""

FACTS = [
    "Hydrogen is the most common element in the universe. A cold hydrogen atom very occasionally "
    "flips its electron's spin and gives off a radio wave at exactly 1420.406 MHz – a wavelength of 21 cm.",
    "Visible light is blocked by interstellar dust, but 21 cm radio waves pass straight through. "
    "That's how astronomers first mapped the spiral arms of our Milky Way in the 1950s.",
    "Gas moving toward us is squeezed to a slightly higher frequency; gas moving away is stretched lower "
    "(the Doppler effect). The bumps in the graph are clouds moving at different speeds.",
    "Because the Milky Way rotates, each spiral arm along our line of sight moves at its own speed – "
    "so each bump in the spectrum is a different arm, sometimes tens of thousands of light-years away.",
    "This dish does not move. The Earth's rotation sweeps the sky through the beam – a 'drift scan'. "
    "Watch the green circle on the sky map as different parts of the Milky Way drift into view.",
    "The signal is incredibly faint – only a few percent above the noise of the receiver itself. "
    "We average thousands of measurements every minute to make it stand out.",
]


class InfoPanel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setWordWrap(True)
        self.setMargin(10)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(240)


class MainWindow(QMainWindow):
    def __init__(self, demo=False, kiosk=False):
        super().__init__()
        self.cfg = config.load()
        self._saved_source = self.cfg["source"]
        self.demo = demo
        if demo:
            self.cfg["source"] = "simulator"
        self.setWindowTitle(f"{APP_NAME} – {self.cfg['site_name']}")
        self.resize(1500, 900)
        self.integ = Integrator()
        self.observations = ObservationStore(root=observation_dir(self.cfg.get("observation_dir")))
        self.segment_started_utc = utc_stamp()
        self.segment_pointing = {}
        self._last_checkpoint_count = 0
        self.rx = None
        self._rx_generation = 0  # Invalidates queued signals from retired receivers.
        self._rx_ended_reason = None
        self._rx_end_unexpected = False
        self._receiver_stop_in_progress = False
        self._reconnect_attempts = 0
        self._retry_active = False
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._run_reconnect)
        self.last_save = None
        self.last_save_error = None
        self.dirty = False
        self.last_res = None
        self.state = {}
        self.device_desc = ""
        self.rx_error = ""
        self.bg_progress = None
        self.fact_i = 0
        self.kiosk = False

        # ---- widgets
        self.sky = SkyDome()
        self.sky.pointRequested.connect(self.aim_dish)
        self.galaxy = GalaxyMap()
        self.info = InfoPanel()
        self.spec = SpectrumWidget()
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        self.caption.setTextFormat(Qt.TextFormat.RichText)
        self.caption.setMargin(12)
        self.caption.setStyleSheet("background:#0c1426; border-top:1px solid #23304f;")
        self.caption.hide()

        top = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(self.info)
        top.addWidget(self.galaxy)
        top.setSizes([330, 420])
        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(top)
        right.addWidget(self.spec)
        right.setSizes([380, 520])
        rwrap = QWidget()
        rl = QVBoxLayout(rwrap)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(right, 1)
        rl.addWidget(self.caption)
        main = QSplitter(Qt.Orientation.Horizontal)
        main.addWidget(self.sky)
        main.addWidget(rwrap)
        main.setSizes([720, 780])
        self.setCentralWidget(main)

        self._build_toolbar()
        self.statusBar().showMessage("Ready")

        # ---- timers
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.tick)
        self.clock.start(1000)
        self.redraw = QTimer(self)
        self.redraw.timeout.connect(self.refresh_spectrum)
        self.redraw.start(400)
        self.recovery_timer = QTimer(self)
        self.recovery_timer.timeout.connect(self._checkpoint)
        self.recovery_timer.start(30000)
        self.facts = QTimer(self)
        self.facts.timeout.connect(self._next_fact)
        self.facts.start(20000)

        for key, fn in (("F11", self.toggle_kiosk), ("Escape", self.exit_kiosk),
                        ("R", self.reset_average), ("B", self.capture_background), ("A", self.auto_background), ("L", lambda: self.act_lock.toggle()),
                        ("Space", self.toggle_rx), ("F12", self.snapshot), ("S", self.snapshot)):
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(fn)

        self.tick()
        self.segment_pointing = self._observation_pointing()
        self._check_recovery()
        legacy_checkpoint = os.path.join(user_dir(), "observations", "recovery_checkpoint.npz")
        if os.path.isfile(legacy_checkpoint) and os.path.abspath(legacy_checkpoint) != os.path.abspath(str(self.observations.checkpoint)):
            QMessageBox.warning(self, APP_NAME, "An earlier recovery checkpoint still exists at:\n"
                                + legacy_checkpoint + "\n\nIt has NOT been migrated or modified. "
                                "New acquisition is disabled until the checkpoint is recovered safely.")
            self._recovery_blocked = True
        if self.cfg.get("autostart", True):
            QTimer.singleShot(300, self.start_rx)
        if kiosk:
            QTimer.singleShot(400, self.toggle_kiosk)

    # ------------------------------------------------------------------ UI
    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)
        self.tb = tb
        self.act_rx = QAction("▶ Start", self)
        self.act_rx.setCheckable(True)
        self.act_rx.triggered.connect(self.toggle_rx)
        tb.addAction(self.act_rx)
        tb.addSeparator()
        tb.addWidget(QLabel(" Dish  Az "))
        self.az_spin = QDoubleSpinBox()
        self.az_spin.setRange(0, 360)
        self.az_spin.setDecimals(1)
        self.az_spin.setSuffix("°")
        self.az_spin.setValue(self.cfg["dish_az"])
        self.az_spin.setKeyboardTracking(False)
        self.az_spin.valueChanged.connect(lambda _v: self.aim_dish(self.el_spin.value(), self.az_spin.value()))
        tb.addWidget(self.az_spin)
        tb.addWidget(QLabel(" El "))
        self.el_spin = QDoubleSpinBox()
        self.el_spin.setRange(0, 90)
        self.el_spin.setDecimals(1)
        self.el_spin.setSuffix("°")
        self.el_spin.setValue(self.cfg["dish_el"])
        self.el_spin.setKeyboardTracking(False)
        self.el_spin.valueChanged.connect(lambda _v: self.aim_dish(self.el_spin.value(), self.az_spin.value()))
        tb.addWidget(self.el_spin)
        tb.addSeparator()
        tb.addWidget(QLabel(" Processing "))
        self.mode_combo = QComboBox()
        for k, lab in MODES:
            self.mode_combo.addItem(lab, k)
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(self.cfg["mode"])))
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        tb.addWidget(self.mode_combo)
        self.act_lock = QAction("🔒 Lock scale", self)
        self.act_lock.setCheckable(True)
        self.act_lock.setChecked(bool(self.cfg.get("y_fixed", False)))
        self.act_lock.setToolTip("Freeze the graph's vertical scale at what you see now (L).\n"
                                 "The graph stops auto-zooming, so noise looks small and you can\n"
                                 "watch the hydrogen bump rise and fall as the sky drifts by.")
        self.act_lock.toggled.connect(self.toggle_lock)
        tb.addAction(self.act_lock)
        tb.addSeparator()
        self.act_autobg = QAction("★ Auto background", self)
        self.act_autobg.setToolTip(
            "Measure the receiver's own frequency response without moving the dish (A).\n"
            "The receiver briefly tunes a few MHz away from the hydrogen line, records the\n"
            "shape of the empty band, then tunes back. Takes about a minute.")
        self.act_autobg.triggered.connect(self.auto_background)
        for text, fn, tip in (("⟲ Reset average", self.reset_average, "Start averaging again (R)"),
                              (None, None, None),
                              ("Capture background", self.capture_background,
                               "Save the current average as the 'empty sky' reference (B).\n"
                               "Do this with the dish pointed well away from the Milky Way."),
                              ("Clear background", self.clear_background, "Forget the saved background"),
                              ("⚙ Settings", self.open_settings, "Site, dish, receiver and display settings"),
                              ("⛶ Outreach mode", self.toggle_kiosk, "Full-screen display for the public (F11, Esc to leave)"),
                              ("📷 Snapshot", self.snapshot, "Save a picture and the spectrum data (S)")):
            if text is None:
                tb.addAction(self.act_autobg)
                continue
            a = QAction(text, self)
            a.setToolTip(tip)
            a.triggered.connect(fn)
            tb.addAction(a)

    def _mode_changed(self, _i):
        self.cfg["mode"] = self.mode_combo.currentData()
        self._db_center = None
        self._save()
        self.dirty = True
        self.refresh_spectrum()

    def _save(self):
        c = dict(self.cfg)
        if self.demo and c["source"] == "simulator":
            c["source"] = self._saved_source  # --demo is for this session only
        try:
            config.save(c)
            return True
        except (OSError, TypeError, ValueError) as exc:
            self.last_save_error = f"Settings could not be saved: {exc}"
            QMessageBox.warning(self, APP_NAME, self.last_save_error)
            return False

    # ------------------------------------------------------ observation safety
    def _observation_pointing(self):
        return {"dish_az_deg": float(self.cfg["dish_az"]),
                "dish_el_deg": float(self.cfg["dish_el"]),
                "ra_j2000_deg": self.state.get("ra"),
                "dec_j2000_deg": self.state.get("dec"),
                "galactic_l_deg": self.state.get("l"),
                "galactic_b_deg": self.state.get("b")}

    def _check_recovery(self):
        path = self.observations.checkpoint
        if not path.exists():
            return
        try:
            _power, metadata = self.observations.read(path)
            detail = f"Saved {metadata.get('saved_utc', 'unknown time')}\n" \
                     f"{metadata.get('spectrum_count', 0)} spectra; " \
                     f"{metadata.get('elapsed_integration_s', 0):.1f} s integration."
        except Exception as exc:
            # Never start a new acquisition while an unreadable checkpoint
            # could be overwritten by a fresh periodic checkpoint.
            self._recovery_blocked = True
            QMessageBox.warning(self, APP_NAME, f"A recovery file exists but could not be read:\n{exc}\n{path}\n\n"
                                "Acquisition is blocked to protect the checkpoint. Back it up and resolve the problem first.")
            return
        QMessageBox.information(self, APP_NAME, "A previous observation checkpoint was found.\n"
                                + detail + "\n\nThe checkpoint has been preserved at:\n" + str(path)
                                + "\nIt will not be deleted or overwritten during this session.")
        # Preserve the original bytes and record recovery provenance separately.
        try:
            recovered, warning = preserve_checkpoint(path, metadata)
            self.statusBar().showMessage(f"Recovered checkpoint preserved: {recovered}", 12000)
            if warning:
                QMessageBox.warning(self, APP_NAME, warning)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Cannot protect the recovery checkpoint: {exc}\n"
                                "New acquisition is disabled until this is resolved.")
            self._recovery_blocked = True

    def _save_segment(self, reason):
        if self.integ.avg is None:
            return True
        try:
            path = self.observations.save(self.cfg, self.integ, self.segment_pointing,
                                          reason, self.segment_started_utc)
            self.last_save = (utc_stamp(), str(path))
            self.last_save_error = None
            try:
                self.observations.clear_checkpoint()
            except OSError as exc:
                # The observation is already durable; warn separately about the checkpoint.
                self.last_save_error = f"Checkpoint cleanup failed: {exc}"
                self.statusBar().showMessage(f"Observation saved at {path}; {self.last_save_error}", 15000)
                return True
            self.statusBar().showMessage(f"Observation saved: {path}", 7000)
            return True
        except Exception as exc:
            self.last_save_error = str(exc)
            QMessageBox.critical(self, APP_NAME, "Could not save the observation. Averaging will NOT be reset.\n"
                                 f"{type(exc).__name__}: {exc}")
            return False

    def _reset_segment(self, reason):
        if not self._save_segment(reason):
            return False
        self.integ.reset()
        self.segment_started_utc = utc_stamp()
        self.segment_pointing = self._observation_pointing()
        self._last_checkpoint_count = 0
        self.dirty = True
        return True

    def _checkpoint(self):
        if self.integ.avg is None or self.integ.n == self._last_checkpoint_count:
            return
        try:
            self.observations.save(self.cfg, self.integ, self.segment_pointing,
                                   "periodic_checkpoint", self.segment_started_utc, checkpoint=True)
            self._last_checkpoint_count = self.integ.n
        except Exception as exc:
            self.statusBar().showMessage(f"WARNING: Recovery checkpoint failed: {exc}", 12000)

    # ------------------------------------------------------------- receiver
    def _rx_cfg(self):
        return {k: self.cfg[k] for k in ("device_index", "center_mhz", "sample_rate", "gain", "ppm",
                                         "bias_tee", "nfft", "ffts_per_block")}

    def _pointing(self):
        s = self.state
        return s.get("ra", 0.0), s.get("dec", 0.0), s.get("corr", 0.0)

    def _receiver_event(self, generation, method, *args):
        """Ignore queued Qt signals from a superseded or stopped receiver."""
        if not is_current_event(generation, self._rx_generation, self.rx is not None):
            return
        return method(*args)

    def _cancel_reconnect(self):
        self._reconnect_timer.stop()
        self._retry_active = False
        self._reconnect_attempts = 0

    def _schedule_reconnect(self):
        if self.cfg.get("source") != "rtlsdr" or not self.cfg.get("auto_reconnect", True):
            return False
        attempt = self._reconnect_attempts + 1
        delay = retry_delay(attempt, maximum=int(self.cfg.get("reconnect_max_attempts", 5)))
        if delay is None:
            self.statusBar().showMessage("RTL-SDR reconnect attempts exhausted; start manually", 0)
            return False
        self._reconnect_attempts = attempt
        self._retry_active = True
        self.statusBar().showMessage(
            f"RTL-SDR interrupted; attempt {attempt} in {delay}s. Stop cancels retry.", 0)
        self._reconnect_timer.start(delay * 1000)
        return True

    def _run_reconnect(self):
        if not self._retry_active:
            return
        if self.rx is not None or getattr(self, "_recovery_blocked", False):
            self._cancel_reconnect()
            return
        # Do not reset the retry count. A subsequent early failure consumes
        # another attempt. Only sustained acquisition resets this counter.
        self._retry_active = False
        self.start_rx(retry=True)

    def start_rx(self, retry=False):
        if not retry:
            self._cancel_reconnect()
        if getattr(self, "_recovery_blocked", False):
            return False
        if self.rx is not None:
            if not self.stop_rx():
                return False
        if not self._reset_segment("receiver_restart"):
            return False
        self.rx_error = ""
        self._rx_ended_reason = None
        self._rx_end_unexpected = False
        self._rx_generation += 1
        generation = self._rx_generation
        if self.cfg["source"] == "simulator":
            self.rx = SimulatorThread(self._rx_cfg(), self._pointing, self)
        else:
            self.rx = RtlSdrThread(self._rx_cfg(), self)
        # Queued signals already in Qt's event loop may fire after stop/wait.
        # Each callback must verify the worker's generation before mutating state.
        for signal, handler in (
            (self.rx.spectrum, self.on_spectrum),
            (self.rx.status, self.on_status),
            (self.rx.opened, self.on_opened),
            (self.rx.acquisitionEnded, self.on_acquisition_ended),
            (self.rx.bgProgress, self.on_bg_progress),
            (self.rx.bgDone, self.on_bg_done),
            (self.rx.finished, self.on_rx_finished),
        ):
            signal.connect(lambda *args, _generation=generation, _handler=handler:
                           self._receiver_event(_generation, _handler, *args))
        self.bg_progress = None
        self.act_autobg.setEnabled(True)
        self.rx.start()
        self.act_rx.setChecked(True)
        self.act_rx.setText("■ Stop")
        return True

    def stop_rx(self):
        # An operator stop or settings change must cancel all queued retries.
        self._cancel_reconnect()
        if self.rx is not None:
            self._receiver_stop_in_progress = True
            self.rx.stop()
            if not self.rx.wait(3000):
                QMessageBox.warning(self, APP_NAME, "Receiver has not stopped. Its thread is still active; "
                                    "do not disconnect the SDR. Try stopping again.")
                self._receiver_stop_in_progress = False
                return False
            # Advance generation before retiring the receiver: queued signals
            # must never append data to the next empty observation segment.
            self._rx_generation += 1
            self.rx = None
            self._receiver_stop_in_progress = False
            self._rx_ended_reason = None
            self._rx_end_unexpected = False
        self.act_rx.setChecked(False)
        self.act_rx.setText("▶ Start")
        if not self._save_segment("receiver_stop"):
            return False
        self.integ.reset()
        self.segment_started_utc = utc_stamp()
        self.segment_pointing = self._observation_pointing()
        self._last_checkpoint_count = 0
        self.dirty = True
        return True

    def toggle_rx(self):
        if self._reconnect_timer.isActive():
            self._cancel_reconnect()
            self.statusBar().showMessage("Automatic reconnection canceled by operator", 10000)
            self.act_rx.setChecked(False)
            self.act_rx.setText("▶ Start")
            return
        if self.rx is not None and self.rx.isRunning():
            # Do not conceal a failed save with a false "Stopped" message.
            self.stop_rx()  # _save_segment owns success/failure messaging.
        else:
            self.start_rx()

    def on_acquisition_ended(self, reason, unexpected):
        self._rx_ended_reason = str(reason)
        self._rx_end_unexpected = bool(unexpected)

    def on_rx_finished(self):
        if self._receiver_stop_in_progress:
            return
        if self.rx is None or self.rx.isRunning():
            return
        self.act_rx.setChecked(False)
        self.act_rx.setText("▶ Start")
        reason = self._rx_ended_reason or "receiver_ended"
        unexpected = self._rx_end_unexpected or reason != "operator_stop"
        self._rx_ended_reason = None
        self._rx_end_unexpected = False
        has_observation = self.integ.avg is not None
        if not self._save_segment("receiver_interrupted" if unexpected else "receiver_finished"):
            self.statusBar().showMessage("Receiver stopped; unsaved observation retained for recovery; retry disabled", 0)
            return
        self.integ.reset()
        self.segment_started_utc = utc_stamp()
        self.segment_pointing = self._observation_pointing()
        self._last_checkpoint_count = 0
        self.dirty = True
        # Invalidate callbacks still queued from this completed worker.
        self._rx_generation += 1
        self.rx = None
        if unexpected:
            if not self._schedule_reconnect():
                self.statusBar().showMessage(
                    "Receiver interrupted; " + ("observation saved; " if has_observation else "no observation acquired; ")
                    + "restart manually or check reconnect settings", 0)

    def on_spectrum(self, p, dt):
        # Never average a spectrum against different FFT metadata.  Refuse
        # malformed blocks rather than creating another one-block segment.
        p = np.asarray(p)
        expected = int(self.cfg["nfft"])
        if p.ndim != 1 or p.size != expected or not np.all(np.isfinite(p)) or np.any(p < 0):
            self.statusBar().showMessage("Rejected invalid receiver spectrum (FFT/data mismatch)", 12000)
            return
        if not np.isfinite(dt) or dt <= 0:
            self.statusBar().showMessage("Rejected receiver spectrum with invalid duration", 12000)
            return
        if self.integ.avg is not None and self.integ.avg.shape != p.shape:
            self.statusBar().showMessage("Rejected spectrum: observation FFT shape changed unexpectedly", 12000)
            return
        self.integ.add(p, dt, float(self.cfg["integration_s"]))
        # A continuously acquiring receiver is considered recovered. An early
        # disconnect still counts towards the bounded retry limit.
        if self._reconnect_attempts and self.integ.t_total >= 30.0:
            self._reconnect_attempts = 0
        self.dirty = True

    def on_status(self, msg, err):
        if err:
            self.rx_error = msg
            self.statusBar().showMessage(msg)
            if not self.kiosk and (self.cfg.get("source") != "rtlsdr" or not self.cfg.get("auto_reconnect", True)):
                QMessageBox.warning(self, APP_NAME, msg + "\n\nCheck the USB connection and receiver driver. "
                                    "Restart manually when the device is ready.")
        else:
            self.rx_error = ""
            self.statusBar().showMessage(msg)

    def on_opened(self, desc):
        self.device_desc = desc

    # --------------------------------------------------------------- actions
    def aim_dish(self, el, az):
        el = max(0.0, min(90.0, float(el)))
        az = float(az) % 360.0
        if abs(el - self.cfg["dish_el"]) < 1e-6 and abs(az - self.cfg["dish_az"]) < 1e-6:
            return
        if self.cfg.get("reset_on_repoint", True) and not self._reset_segment("new_pointing"):
            return
        self.cfg["dish_el"], self.cfg["dish_az"] = round(el, 1), round(az, 1)
        for sp, val in ((self.el_spin, self.cfg["dish_el"]), (self.az_spin, self.cfg["dish_az"])):
            sp.blockSignals(True)
            sp.setValue(val)
            sp.blockSignals(False)
        self._save()
        self.tick()
        self.segment_pointing = self._observation_pointing()

    def reset_average(self):
        if self._reset_segment("manual_average_reset"):
            self.statusBar().showMessage("Previous average saved; new average started", 4000)

    def _bg_key(self):
        return (str(self.cfg["source"]), int(self.cfg.get("device_index", 0)),
                float(self.cfg["center_mhz"]), int(self.cfg["nfft"]),
                float(self.cfg["sample_rate"]), str(self.cfg.get("gain", "auto")),
                int(self.cfg.get("ppm", 0)), bool(self.cfg.get("bias_tee", False)))

    def capture_background(self):
        try:
            captured = self.integ.capture_background(self._bg_key())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, APP_NAME, f"Background calibration was not saved: {exc}")
            return
        if captured:
            self.statusBar().showMessage(
                f"Background captured from {self.integ.effective_time(self.cfg['integration_s']):.0f} s of data", 5000)
            if self.mode_combo.currentData() in ("baseline", "raw"):
                self.mode_combo.setCurrentIndex(self.mode_combo.findData("background+baseline"))
        else:
            self.statusBar().showMessage("No data yet – start the receiver first", 4000)
        self.dirty = True

    def _units(self, mode):
        return "db" if mode in ("raw", "sdr") else "pct"

    def toggle_lock(self, on):
        self.cfg["y_fixed"] = bool(on)
        if on and self.last_res is not None:
            lo, hi = self.spec.y_view()
            if self._units(self.last_res["mode"]) == "pct":
                self.cfg["y_pct_min"], self.cfg["y_pct_max"] = round(lo, 1), round(hi, 1)
            else:
                self.cfg["y_db_span"] = round(hi - lo, 2)
                self._db_center = (lo + hi) / 2
        self._save()
        self.dirty = True
        self.statusBar().showMessage("Vertical scale locked" if on else "Vertical scale: auto-zoom", 3000)

    def _yrange(self, res):
        c = self.cfg
        locked = c.get("y_fixed", False) or (self.kiosk and c.get("kiosk_fixed_scale", True))
        mode = res["mode"]
        if self._units(mode) == "pct":
            if not locked:
                return None
            return (float(c["y_pct_min"]), float(c["y_pct_max"]))
        # dB views: fixed height, centred on the data, re-centred only if it drifts away
        if not locked and mode != "sdr":
            return None
        span = float(c.get("y_db_span", 4.0))
        y = res["y"]
        mid = float(np.median(y))
        top = float(np.percentile(y, 99))
        cen = getattr(self, "_db_center", None)
        if cen is None or getattr(self, "_db_center_mode", None) != mode or \
                top > cen + 0.42 * span or mid < cen - 0.42 * span:
            # like IF Average: curve sits in the lower-middle with room above for the line
            cen = mid + 0.2 * span if mode == "sdr" else mid + 0.15 * span
            self._db_center = cen
            self._db_center_mode = mode
        return (cen - span / 2, cen + span / 2)

    def auto_background(self):
        if self.rx is None or not self.rx.isRunning():
            self.statusBar().showMessage("Start the receiver first", 4000)
            return
        if self.bg_progress is not None:
            return
        self.bg_progress = 0.0
        self.act_autobg.setEnabled(False)
        self.rx.request_background(float(self.cfg.get("auto_bg_offset_mhz", 2.5)),
                                   float(self.cfg.get("auto_bg_seconds", 60.0)))
        self.statusBar().showMessage("Auto background: measuring the receiver's shape away from the hydrogen line…")
        self.dirty = True

    def on_bg_progress(self, frac):
        self.bg_progress = frac
        self.dirty = True

    def on_bg_done(self, psd):
        self.bg_progress = None
        self.act_autobg.setEnabled(True)
        if psd is None:
            self.statusBar().showMessage("Auto background failed – no data", 6000)
        else:
            try:
                self.integ.set_background(psd, self._bg_key())
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, APP_NAME, f"Automatic background calibration was not saved: {exc}")
                return
            if self.mode_combo.currentData() != "background+baseline":
                self.mode_combo.setCurrentIndex(self.mode_combo.findData("background+baseline"))
            self.statusBar().showMessage("Auto background done – the receiver's shape is now divided out", 8000)
        self.dirty = True

    def clear_background(self):
        try:
            self.integ.clear_background()
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not remove background calibration: {exc}")
            return
        self.statusBar().showMessage("Background cleared", 3000)
        self.dirty = True

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec():
            old = dict(self.cfg)
            new_cfg = dlg.values()
            acquisition_changed = any(old.get(k) != new_cfg.get(k) for k in
                                      ("source", "device_index", "center_mhz", "sample_rate", "gain", "ppm", "nfft",
                                       "dish_az", "dish_el", "integration_s"))
            rx_keys = ("source", "device_index", "center_mhz", "sample_rate", "gain", "ppm", "bias_tee", "nfft", "ffts_per_block")
            restart_receiver = self.rx is not None and any(old.get(k) != new_cfg.get(k) for k in rx_keys)
            storage_changed = observation_dir(old.get('observation_dir')) != observation_dir(new_cfg.get('observation_dir'))
            candidate_store = self.observations
            if storage_changed:
                # Preflight before stopping the SDR or changing any saved setting.
                try:
                    candidate_store = ObservationStore.prepare_directory_change(
                        self.observations, observation_dir(new_cfg.get('observation_dir')),
                        active_segment=self.integ.avg is not None)
                except (OSError, RuntimeError, ValueError) as exc:
                    QMessageBox.warning(self, APP_NAME, f"Cannot change observation folder: {exc}")
                    return
                # An active segment must finish in its original directory.
                restart_receiver = self.rx is not None
            if restart_receiver:
                # Stop and invalidate old queued signals before applying new settings.
                if not self.stop_rx():
                    return
            elif (acquisition_changed or storage_changed) and not self._reset_segment("settings_change"):
                return
            if storage_changed and self.observations.checkpoint.exists():
                QMessageBox.warning(self, APP_NAME,
                                    "The old observation folder still has a recovery checkpoint. "
                                    "Resolve it before changing folders.")
                return
            # Settings must be persisted BEFORE changing the active store.
            # If writing fails, the original configuration and storage stay in use.
            self.cfg = new_cfg
            if not self._save():
                self.cfg = old
                return
            self.observations = candidate_store
            if storage_changed:
                self.statusBar().showMessage(
                    f"New observations will be saved to {self.observations.root}; existing files were not moved", 15000)
            self.setWindowTitle(f"{APP_NAME} – {self.cfg['site_name']}")
            for sp, k in ((self.el_spin, "dish_el"), (self.az_spin, "dish_az")):
                sp.blockSignals(True)
                sp.setValue(self.cfg[k])
                sp.blockSignals(False)
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(self.cfg["mode"])))
            self.mode_combo.blockSignals(False)
            self.act_lock.blockSignals(True)
            self.act_lock.setChecked(bool(self.cfg.get("y_fixed", False)))
            self.act_lock.blockSignals(False)
            self._db_center = None
            if restart_receiver:
                self.start_rx()
            if (old["dish_az"], old["dish_el"]) != (self.cfg["dish_az"], self.cfg["dish_el"]) and self.cfg["reset_on_repoint"]:
                self._reset_segment("settings_pointing_change")
            self.segment_pointing = self._observation_pointing()
            self.dirty = True
            self.tick()

    def toggle_kiosk(self):
        self.kiosk = not self.kiosk
        s = float(self.cfg.get("kiosk_font_scale", 1.0))
        for wdg in (self.sky, self.galaxy):
            wdg.kiosk = self.kiosk
        if self.kiosk:
            self.tb.hide()
            self.statusBar().hide()
            self.caption.setVisible(bool(self.cfg.get("kiosk_captions", True)))
            self.spec.set_font_scale(1.35 * s)
            self.showFullScreen()
        else:
            self.tb.show()
            self.statusBar().show()
            self.caption.hide()
            self.spec.set_font_scale(1.0)
            self.showNormal()
        self.tick()
        self.dirty = True

    def exit_kiosk(self):
        if self.kiosk:
            self.toggle_kiosk()

    def snapshot(self):
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        d = snapshot_dir()
        png = os.path.join(d, f"hline_{stamp}.png")
        self.grab().save(png)
        res = self.last_res
        if res is not None:
            s = self.state
            with open(os.path.join(d, f"hline_{stamp}.csv"), "w", encoding="utf-8") as f:
                f.write(f"# {APP_NAME} {VERSION} | {self.cfg['site_name']} | UTC {s.get('utc','')}\n")
                f.write(f"# dish az={self.cfg['dish_az']} el={self.cfg['dish_el']} beam={beam_width(self.cfg):.1f}deg\n")
                f.write(f"# RA={s.get('ra',0):.3f} Dec={s.get('dec',0):.3f} (J2000 deg) l={s.get('l',0):.2f} b={s.get('b',0):.2f}\n")
                f.write(f"# vLSR correction={s.get('corr',0):.3f} km/s  mode={res['mode']}  integration={self.integ.effective_time(self.cfg['integration_s']):.0f}s\n")
                f.write("v_lsr_kms,freq_mhz,value\n")
                for v, y in zip(res["v"], res["y"]):
                    fr = float(astro.vtopo_to_freq(v - s.get("corr", 0)))
                    f.write(f"{v:.3f},{fr:.6f},{y:.5f}\n")
        self.statusBar().showMessage(f"Saved snapshot to {d}", 6000)

    # ------------------------------------------------------------- updating
    def tick(self):
        c = self.cfg
        now = astro.utc_now()
        jd = astro.julian_date(now)
        ra, dec = astro.altaz_to_j2000(c["dish_el"], c["dish_az"], jd, c["lat"], c["lon"])
        ra, dec = float(ra), float(dec)
        l, b = astro.eq_to_gal(ra, dec)
        l, b = float(l), float(b)
        corr = astro.vlsr_correction(ra, dec, jd, c["lat"], c["lon"])
        cons = ""
        if ephem is not None:
            try:
                cons = ephem.constellation((math.radians(ra), math.radians(dec)), epoch=ephem.J2000)[1]
            except Exception:
                cons = ""
        hours = int(c.get("drift_hours", 4))
        future = []
        for h in range(1, hours + 1):
            fl, _fb = astro.eq_to_gal((ra + h * 15.041) % 360, dec)
            future.append((h, float(fl)))
        lst = astro.lst_deg(jd, c["lon"])
        self.state = dict(jd=jd, ra=ra, dec=dec, l=l, b=b, corr=corr, cons=cons, future=future,
                          utc=now.strftime("%Y-%m-%d %H:%M:%S"), lst=lst)
        self.sky.update_state(jd, c)
        clouds = []
        if self.last_res is not None and abs(b) <= 15:
            clouds = describe_peaks(l, b, self.last_res.get("peaks", []))
        self.galaxy.set_state(l, b, beam_width(c), clouds, future[:3])
        self._update_info()

    def _axes(self):
        c = self.cfg
        nfft = len(self.integ.avg) if self.integ.avg is not None else int(c["nfft"])
        f = float(c["center_mhz"]) + (np.arange(nfft) - nfft / 2) * float(c["sample_rate"]) / nfft / 1e6
        v = astro.freq_to_vtopo(f) + self.state.get("corr", 0.0)
        return f, v

    def refresh_spectrum(self):
        if not self.dirty:
            return
        self.dirty = False
        c = self.cfg
        self.spec.set_view(float(c["v_min"]), float(c["v_max"]))
        title = ""
        if c["source"] == "simulator":
            title = "⚠ SIMULATED DATA – demo mode"
        if self.integ.avg is None:
            self.last_res = None
            self.spec.display(None, self.state.get("corr", 0.0), title or "Waiting for data…")
            return
        f, v = self._axes()
        res = process(c, self.integ, f, v, self.integ.background_valid(self._bg_key()), self.state.get("corr", 0.0))
        if res and res["mode"] == "sdr":
            self.spec.set_view(float(res["v"].min()), float(res["v"].max()))  # whole band, like IF Average
        self.last_res = res
        t = self.integ.effective_time(float(c["integration_s"]))
        if not title:
            title = f"Hydrogen 21 cm – averaged {t:.0f} s"
        else:
            title += f"  (averaged {t:.0f} s)"
        if self.bg_progress is not None:
            title += f"   [measuring background… {self.bg_progress*100:.0f}%]"
        elif res and res.get("baseline_failed"):
            title += "   [baseline invalid – displaying raw spectrum; peaks disabled]"
        elif res and res.get("fallback"):
            title += "   [no background yet – press ★ Auto background]"
        if res and res.get("spikes"):
            title += f"   ({len(res['spikes'])} interference spike{'s' if len(res['spikes']) != 1 else ''} removed)"
        self.spec.display(res, self.state.get("corr", 0.0), title,
                          show_spikes=bool(c.get("show_spikes", True)) and not self.kiosk,
                          yrange=self._yrange(res) if res else None)

    def _update_info(self):
        s, c = self.state, self.cfg
        if not s:
            return
        local = datetime.now().strftime("%a %d %b %Y  %I:%M:%S %p")
        t_int = self.integ.effective_time(float(c["integration_s"]))
        rx = self.rx is not None and self.rx.isRunning()
        if c["source"] == "simulator":
            rx_txt = "<span style='color:#ffb070'>SIMULATOR (demo)</span>"
        elif self.rx_error:
            rx_txt = f"<span style='color:#ff7070'>{self.rx_error[:140]}</span>"
        elif rx:
            rx_txt = f"<span style='color:#90ffb0'>● receiving</span> {self.device_desc}"
        else:
            rx_txt = "<span style='color:#a0a8b8'>stopped</span>"
        plane = abs(s["b"])
        where = ("in the plane of the Milky Way" if plane < 5 else
                 "near the Milky Way" if plane < 15 else "away from the Milky Way")
        fut = " · ".join(f"+{h}h: l={fl:.0f}°" for h, fl in s["future"][:4])
        scale = float(c.get("kiosk_font_scale", 1.0)) if self.kiosk else 1.0
        base = 10.5 * scale * (1.35 if self.kiosk else 1.0)
        big = base * 1.9
        lab = "color:#8b98b4"
        html = f"""
<div style='font-size:{base}pt'>
<div style='font-size:{base*1.25}pt; font-weight:bold; color:#e6eefc'>{c['site_name']}</div>
<div style='{lab}'>{local} &nbsp;·&nbsp; UTC {s['utc'][11:]} &nbsp;·&nbsp; LST {astro.fmt_hms(s['lst'])[:7]}</div>
<br>
<div style='{lab}'>DISH IS LOOKING AT</div>
<div style='font-size:{big}pt; font-weight:bold; color:#9dffc4'>{s['cons'] or '—'}</div>
<div>{where}</div>
<table cellspacing=0 cellpadding=2 style='margin-top:6px'>
<tr><td style='{lab}'>Galactic&nbsp;longitude&nbsp;</td><td><b>l = {s['l']:.1f}°</b></td></tr>
<tr><td style='{lab}'>Galactic latitude</td><td><b>b = {s['b']:+.1f}°</b></td></tr>
<tr><td style='{lab}'>RA / Dec (J2000)</td><td>{astro.fmt_hms(s['ra'])[:7]} &nbsp; {s['dec']:+.1f}°</td></tr>
<tr><td style='{lab}'>Az / El</td><td>{c['dish_az']:.1f}° / {c['dish_el']:.1f}° &nbsp;(beam {beam_width(c):.0f}°)</td></tr>
<tr><td style='{lab}'>LSR correction</td><td>{s['corr']:+.2f} km/s</td></tr>
<tr><td style='{lab}'>Coming up</td><td>{fut}</td></tr>
</table>
<br>
<div style='{lab}'>RECEIVER</div>
<div>{rx_txt}</div>
<div>{float(c['center_mhz']):.4f} MHz · {float(c['sample_rate'])/1e6:.2f} MS/s · gain {c['gain']}{' · bias-tee' if c['bias_tee'] and c['source']=='rtlsdr' else ''}</div>
<div>Averaged: <b>{t_int:.0f} s</b> ({self.integ.n} blocks){' · background ✓' if self.integ.background_valid(self._bg_key()) else ''}</div>
<div style='{lab}'>Acquired samples: {self.integ.t_total:.1f} s · averaging constant: {float(c['integration_s']):.0f} s</div>
<div style='{lab}'>Last saved: {html_utils.escape(self.last_save[0] + ' · ' + self.last_save[1]) if self.last_save else 'not yet'}
{' · WARNING: ' + html_utils.escape(self.last_save_error) if self.last_save_error else ''}</div>
</div>"""
        if self.kiosk:
            html = f"""
<div style='font-size:{base}pt'>
<div style='font-size:{base*1.3}pt; font-weight:bold; color:#e6eefc'>{c['site_name']} radio telescope</div>
<div style='{lab}'>{local}</div><br>
<div style='{lab}'>THE DISH IS LISTENING TO</div>
<div style='font-size:{big*1.15}pt; font-weight:bold; color:#9dffc4'>{s['cons'] or '—'}</div>
<div style='font-size:{base*1.1}pt'>{where}</div><br>
<div>Galactic longitude <b>{s['l']:.0f}°</b> · latitude <b>{s['b']:+.0f}°</b></div>
<div>Listening for <b>{t_int/60:.1f} minutes</b></div>
<div style='{lab}'>{'SIMULATED DATA' if c['source']=='simulator' else ''}</div>
</div>"""
        self.info.setText(html)
        self._update_caption()

    def _next_fact(self):
        self.fact_i = (self.fact_i + 1) % len(FACTS)
        self._update_caption()

    def _update_caption(self):
        if not self.kiosk:
            return
        s = self.state
        scale = float(self.cfg.get("kiosk_font_scale", 1.0))
        res = self.last_res
        lines = []
        if res and res.get("peaks"):
            parts = []
            for cl in describe_peaks(s["l"], s["b"], res["peaks"]):
                v = cl["v"]
                mv = "toward us" if v < 0 else "away from us"
                txt = f"<b>{abs(v):.0f} km/s {mv}</b>" if not cl.get("local") else "<b>hydrogen all around us</b>"
                if cl.get("local"):
                    txt += " (gas near the Sun, in our own spiral arm)"
                elif cl["d"] and not cl["ambiguous"]:
                    ly = cl["d"][0] * 3262
                    txt += f" (about {ly/1000:,.0f},000 light-years away)" if ly > 1500 else " (nearby, in our own spiral arm)"
                elif cl["d"]:
                    txt += f" ({cl['d'][0]*3.262:,.0f} or {cl['d'][1]*3.262:,.0f} thousand light-years away – we can't tell which)"
                parts.append(txt)
            n = len(parts)
            lines.append(f"We are detecting {'a cloud' if n == 1 else f'{n} clouds'} of hydrogen gas: " + "; ".join(parts) + ".")
        else:
            lines.append("Collecting signal… the hydrogen bump grows out of the noise as we keep averaging.")
        lines.append(f"<span style='color:#9aa8c0'>{FACTS[self.fact_i]}</span>")
        self.caption.setText(f"<div style='font-size:{14*scale}pt'>" + "<br>".join(lines) + "</div>")

    def closeEvent(self, ev):
        self._cancel_reconnect()
        if not self.stop_rx():
            ev.ignore()
            return
        self._save()
        super().closeEvent(ev)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--demo", action="store_true", help="use the built-in simulator")
    ap.add_argument("--kiosk", action="store_true", help="start in full-screen outreach mode")
    args, _ = ap.parse_known_args()
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RiverbendAstro.HLineStation")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(DARK_QSS)
    ico = os.path.join(app_dir(), "assets", "hline_icon.png")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    f = QFont("Segoe UI", 9)
    app.setFont(f)
    w = MainWindow(demo=args.demo, kiosk=args.kiosk)
    w.show()
    sys.exit(app.exec())
