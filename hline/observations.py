"""Stage 1: durable, lossless averaged-spectrum records and crash checkpoints.

All files are local NPZ containers with JSON metadata and unprocessed linear PSD.
Synthetic data is explicitly labelled; no background/RFI processing is applied here.
"""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .paths import observation_dir
from .config import beam_width

SCHEMA_VERSION = 1


def utc_stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ObservationStore:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else Path(observation_dir())
        self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoint = self.root / "recovery_checkpoint.npz"
        self.session_id = uuid.uuid4().hex
        self.sequence = 0

    @staticmethod
    def _atomic_npz(destination, spectrum, metadata):
        """Write, sync, then replace. Never delete an older good file on failure."""
        destination = Path(destination)
        fd, tmp = tempfile.mkstemp(prefix=".hline-", suffix=".npz", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                np.savez_compressed(f, power=np.asarray(spectrum, dtype=np.float64),
                                    metadata=np.array(json.dumps(metadata, allow_nan=False)))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, destination)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _validate(power, metadata):
        """Validate persisted observations without altering legacy v1 contents."""
        if not isinstance(metadata, dict):
            raise ValueError("Observation metadata must be a JSON object")
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported observation schema")
        power = np.asarray(power)
        if power.ndim != 1 or power.size == 0 or not np.issubdtype(power.dtype, np.number):
            raise ValueError("Invalid observation power spectrum dimensions or type")
        if not np.all(np.isfinite(power)) or np.any(power < 0):
            raise ValueError("Observation spectrum contains nonfinite or negative power")
        required = ("session_id", "reason", "synthetic", "settings", "pointing",
                    "saved_utc", "started_utc", "spectrum_count",
                    "elapsed_integration_s", "effective_integration_s")
        missing = [key for key in required if key not in metadata]
        if missing:
            raise ValueError("Missing observation metadata: " + ", ".join(missing))
        settings = metadata["settings"]
        if not isinstance(settings, dict):
            raise ValueError("Observation settings must be a JSON object")
        for key in ("source", "center_mhz", "sample_rate", "nfft", "gain"):
            if key not in settings or settings[key] is None:
                raise ValueError(f"Missing receiver setting: {key}")
        nfft = settings["nfft"]
        if isinstance(nfft, bool) or not isinstance(nfft, int) or nfft <= 0:
            raise ValueError("Invalid FFT size in observation metadata")
        if power.size != nfft:
            raise ValueError(f"FFT mismatch: {power.size} spectrum bins, metadata nfft={nfft}")
        for key in ("center_mhz", "sample_rate"):
            value = settings[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid receiver setting: {key}")
        if not isinstance(metadata["pointing"], dict):
            raise ValueError("Invalid observation pointing metadata")
        if not isinstance(metadata["synthetic"], bool):
            raise ValueError("Invalid synthetic-data indicator")
        count = metadata["spectrum_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("Invalid observation spectrum count")
        for key in ("elapsed_integration_s", "effective_integration_s"):
            value = metadata[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0:
                raise ValueError(f"Invalid observation timing: {key}")
        for key in ("started_utc", "saved_utc"):
            try:
                stamp = datetime.fromisoformat(metadata[key])
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError("missing timezone")
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid UTC timestamp: {key}") from exc
        return power, metadata

    @staticmethod
    def read(path):
        with np.load(path, allow_pickle=False) as archive:
            power = archive["power"].copy()
            metadata = json.loads(str(archive["metadata"].item()))
        return ObservationStore._validate(power, metadata)

    @staticmethod
    def _background_provenance(integ):
        """Describe the calibration available at save time; do not claim it was applied."""
        bg = getattr(integ, "background", None)
        key = getattr(integ, "background_key", None)
        if bg is None or key is None:
            return {"available": False}
        arr = np.asarray(bg, dtype="<f8")
        if arr.ndim != 1 or not np.all(np.isfinite(arr)):
            return {"available": False, "warning": "invalid background array"}
        return {
            "available": True,
            "identity": list(key),
            "spectrum_sha256": hashlib.sha256(arr.tobytes()).hexdigest(),
            "spectrum_bins": int(arr.size),
            "note": "Calibration fingerprint only; original background file must be retained for full reprocessing",
        }

    def _metadata(self, cfg, integ, pointing, reason, started_utc):
        keys = ("source", "device_index", "center_mhz", "sample_rate", "gain", "ppm",
                "bias_tee", "nfft", "ffts_per_block", "integration_s", "mode",
                "site_name", "lat", "lon", "elev_m", "dish_az", "dish_el",
                "dish_diameter_m", "beam_deg")
        return {
            "schema_version": SCHEMA_VERSION, "session_id": self.session_id,
            "saved_utc": utc_stamp(), "started_utc": started_utc,
            "reason": reason, "synthetic": cfg.get("source") == "simulator",
            "settings": {k: cfg.get(k) for k in keys},
            "pointing": dict(pointing), "spectrum_count": int(integ.n),
            "elapsed_integration_s": float(integ.t_total),
            "effective_integration_s": float(integ.effective_time(float(cfg["integration_s"]))),
            "power_units": "linear relative power spectral density (uncalibrated)",
            "processing": "unprocessed averaged PSD; no background, baseline, RFI replacement or smoothing",
            "frequency_axis": "center_mhz + (bin - nfft/2) * sample_rate_hz / nfft / 1e6",
            "acquisition_timing": {
                "acquired_sample_duration_s": float(integ.t_total),
                "wall_clock_duration_s": max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(started_utc)).total_seconds()),
                "averaging_time_constant_s": float(cfg.get("integration_s", 0)),
                "effective_integration_is_estimate": True,
            },
            "beam_metadata": {
                "beam_width_deg": beam_width(cfg),
                "beam_width_method": "configured" if float(cfg.get("beam_deg") or 0) > 0 else "approx_70_lambda_over_D",
                "beam_width_configured_deg": float(cfg.get("beam_deg") or 0),
            },
            "pointing_reference_utc": started_utc,
            "pointing_reference_frame": "ICRS/J2000 approximate; az/el input",
            "pointing_reference_note": "Snapshot at segment start, not time-averaged beam track",
            "processing_provenance": {
                "raw_saved_spectrum": "unprocessed averaged linear PSD",
                "view_mode_at_save": cfg.get("mode"),
                "processing_settings": {k: cfg.get(k) for k in (
                    "baseline_order", "line_window_kms", "band_use_fraction",
                    "dc_notch", "smooth_kms", "remove_spikes", "spike_max_kms",
                    "peak_sigma", "show_peaks", "auto_bg_offset_mhz",
                    "auto_bg_seconds")},
                "background_calibration": self._background_provenance(integ),
            },
            "velocity_reference_frame": "receiver topocentric (processing may apply optional LSR correction)",
        }

    def save(self, cfg, integ, pointing, reason, started_utc, *, checkpoint=False):
        if integ.avg is None or integ.n <= 0:
            return None
        metadata = self._metadata(cfg, integ, pointing, reason, started_utc)
        self._validate(integ.avg, metadata)
        if checkpoint:
            target = self.checkpoint
        else:
            self.sequence += 1
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
            target = self.root / f"observation_{timestamp}_{self.session_id[:8]}_{self.sequence:04d}.npz"
        self._atomic_npz(target, integ.avg, metadata)
        return target

    def clear_checkpoint(self):
        self.checkpoint.unlink(missing_ok=True)
