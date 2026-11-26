# H-Line Station — Development Patch 04

**Branch:** `stage1-consolidated-repairs` only. **Not a release.** Apply on top of the previously validated Patch 03 source (which already includes the Patch 01/02 test fixture corrections). **Do not install over the original observed Windows installation; do not merge to `main`.**

## Implemented in this changeset

1. `hline/processing.py`: Uses iteratively clipped, adaptive-order log-power polynomial fitting, guaranteeing a *positive* trial continuum. Rejects one-sided line-free coverage and unstable continuum ratios; retains raw fallback and peak suppression. Synthetic flat/sloped/curved/line cases covered. This is **not yet astrophysical validation** of baseline placement on a real Discovery Dish spectrum. Archived RTL-SDR failures 0009 and 0010 locally replayed as raw fallbacks with zero candidate peaks.
2. `hline/processing.py`: `raw` now displays all original FFT bins as unmodified averaged-power dB values (no DC notch, interference substitution, median normalization, smoothing, or frequency band crop). The on-disk raw PSD format is unchanged.
3. `hline/processing.py` and `hline/observations.py`: Each captured background spectrum gains an immutable, content-addressed `calibrations/<sha256>.npz` archive. Archive includes full numerical reference and receiver key; a verified copy is retained in `Observations/calibrations` when associated observations are saved. Existing active background files are archived on first load if possible. The original active calibration is preserved if writing a replacement fails; previously archived calibrations are retained on clear. New observation provenance includes calibration ID and relative archive path when a durable archive exists; does **not** claim the calibration was actually applied to this segment.
4. `hline/storage_migration.py` and `hline/migrate_cli.py`: Preflight all filename conflicts before starting a copy; include `.recovery.json` provenance and immutable calibration archives. Checkpoint is never migrated automatically and CLI continues to block `--apply` when one is pending. Uses copy/verify/create-only with hard links to prevent accidental overwrite. A filesystem not supporting exclusive hard links fails safely. Source files are never deleted.
5. `hline/processing.py` and `hline/observations.py`: Adds weight-based effective *independent spectrum block estimate*, explicitly not calibrated integration duration; retains earlier elapsed-time fields. Adds pointing provenance limitations in metadata. Existing observation file schema stays at v1.
6. `hline/app.py` and `hline/receiver_events.py`: Factors the existing receiver generation gate into a pure helper. Adds deterministic generation tests plus a PySide6 queued-signal integration test that runs only in environments with the GUI dependency installed.

## Tests and limitations

- `python -m unittest discover -s tests -q`: **41 tests, 40 passed, 1 skipped locally** (PySide6 test). `python -m compileall -q hline HLineStation.py`: **PASS**.
- The PySide6 queued signal test will run on GitHub CI if its Python requirements are installed; confirm both Windows and Ubuntu jobs.
- Replayed archived hardware observations `b4a7f71d_0009` and `_0010` from private pre-repair backup with the revised baseline algorithm. Both fell back to raw safely; no false peaks; raw file bytes unchanged.
- No physical radio testing, real-line calibration, complete Doppler/time-series pointing validation, full GUI migration workflow, real USB unplug/replug/retry tests, or GUI disk-write failure tests in this patch.
- The original hardware observations and their private metadata are **not** included in the public patch.
- Existing background calibration identity remains source/device index/gain/ppm etc; *serial-number-level physical identity and full RF-chain profile are not implemented*. Users must not assume device indices uniquely identify a physical dongle.
- Calibration history contains full background *shape* and capture timestamp but does not yet record a scientifically independently measured antenna temperature, noise temperature, true receiver effective gain, or whether calibration was applied at every display update.
- The source changes are a development candidate. Review the future GitHub CI and Windows hardware acceptance before calling the consolidated repair package complete.

## File manifest

- Modified: `hline/app.py`, `hline/processing.py`, `hline/observations.py`, `hline/storage_migration.py`, `hline/migrate_cli.py`
- New: `hline/receiver_events.py`, `tests/test_patch04.py`, `tests/test_patch04_qt.py`, `PATCH04_NOTES.md`
