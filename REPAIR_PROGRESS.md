# H-Line Station — Consolidated repairs (development branch)

**Status:** Partial, unreleased work in progress. Not a complete repair release. Do not replace the tested Windows application with these files yet.

This changeset was developed against the sanitized initial GitHub source and the privately retained pre-repair archive. Existing observations and user settings are not included.

## Implemented or improved in this changeset

- **R01 (partial):** Receiver lifecycle signals are guarded by an acquisition generation. Manual stop invalidates queued old-generation signals before saving. Spectrum blocks are validated against current FFT size, finiteness and duration. Settings changes requiring a new receiver stop the old worker before updating acquisition settings. Still requires real Qt / Windows timing tests and reconnect work.
- **R02 (partial):** ObservationStore validates FFT dimensions, finite/nonnegative raw PSD, required metadata, timestamps and basic settings before saving and after reading. Historical observation whose FFT header disagreed with the spectrum is correctly rejected; no files were changed.
- **R03 / R04 (partial):** One-sided/invalid baseline fits fall back to relative raw-power dB and disable automatic hydrogen peak detection. The display labels the failure. Both original problematic RTL-SDR observation spectra were privately replayed with no huge spurious peaks. A revised baseline fitting *strategy* and full scientific validation remain outstanding.
- **R05 / R06 / R14 (partial):** Background calibration identity includes receiver type, device index, gain, center frequency, FFT size, sample rate, PPM and bias-tee setting; legacy three-number calibration is retained but never silently reused. Background saves now use atomic write/fsync/replace, and save errors are surfaced. No multi-calibration catalog yet; the active file can be replaced after explicit new capture.
- **R07 (partial):** No invented 0.6 kpc distance for low-velocity gas.
- **R09 / R18 (partial):** Stop no longer replaces the observation save result with a generic status message. Persistent save history remains outstanding.

## Verification performed in this environment

- 19 Python unit tests passed locally (`python -m pytest -q`).
- `python -m compileall -q hline HLineStation.py` passed.
- Privately replayed original observation 0009 and 0010 with corrected processing: both safely fell back to relative raw power, without detected peaks. These observations were **not** added to the public patch.
- **Not verified yet:** Windows GUI/PySide6 execution, live RTL-SDR, reconnect flows, simultaneous delivery/race conditions, hardware integration timings.

## Remaining approved scope

R01 receiver lifecycle/reconnect validation and retry design; R02 remaining metadata validation; R03 adaptive robust baseline validation; R04 broader peak quality flags; R05 calibration catalog / RF-chain identity; R06 calibration handling edge cases; R07 astrophysical distance caveats beyond local-velocity case; R08 full reproducibility; R09 persistent status; R10–R12 reconnection and timing; R13 Documents data location and safe migration; R15 raw display transparency; R16–R17 scientific pointing/beam metadata; R19–R20 recovery and messages; more tests and Windows packaging remain.

**Important:** A green CI result indicates only that the tests run and pass, not that all repairs or scientific validation are complete.
