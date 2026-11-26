"""Stage 1: durable, lossless averaged-spectrum records and crash checkpoints.

All files are local NPZ containers with JSON metadata and unprocessed linear PSD.
Synthetic data is explicitly labelled; no background/RFI processing is applied here.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .paths import user_dir

SCHEMA_VERSION = 1


def utc_stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ObservationStore:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else Path(user_dir()) / "observations"
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
    def read(path):
        with np.load(path, allow_pickle=False) as archive:
            power = archive["power"].copy()
            metadata = json.loads(str(archive["metadata"].item()))
        if power.ndim != 1 or not np.all(np.isfinite(power)):
            raise ValueError("Invalid observation power spectrum")
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported observation schema")
        return power, metadata

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
        }

    def save(self, cfg, integ, pointing, reason, started_utc, *, checkpoint=False):
        if integ.avg is None or integ.n <= 0:
            return None
        metadata = self._metadata(cfg, integ, pointing, reason, started_utc)
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
