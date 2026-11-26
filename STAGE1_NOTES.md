# H-Line Station — Stage 1 working copy (partial implementation)

Original ZIP remains unchanged. This copy introduces an observation archive under `%APPDATA%/HLineStation/observations/` (or `~/.config/HLineStation/observations/` outside Windows).

## Implemented
- Automatic save of unprocessed averaged linear power spectra before pointing changes, manual average reset, receiver stop/restart, settings changes, and application exit.
- Compressed `.npz` records with JSON metadata: UTC timestamps, source/synthetic label, receiver settings, antenna pointing, integration duration, sample count and processing status.
- Atomic write/replace using a temporary file and filesystem sync; failed final save blocks an intentional averaging reset or exit.
- Periodic crash-recovery checkpoint every 30 seconds; previous checkpoint is preserved as a recovered file at startup, not automatically mixed with a new observation.
- Basic receiver thread shutdown timeout handling; the receiver reference is retained if it has not stopped.
- Safer defaults for **new** configurations: receiver autostart off and bias tee off. Existing saved settings are not silently overridden.
- Four standalone observation-storage unit tests.

## Limitations and follow-up before field deployment
- Not yet verified with physical RTL-SDR or SDRplay hardware, or the PySide6 GUI on Windows.
- No user-facing observation browser, restoration of an interrupted average, or session report yet. Recovery checkpoints are preserved for manual loading/analysis.
- Checkpoints capture the current average, not raw IQ, so they cannot recreate every intermediate sample.
- Recording gaps and USB reconnection still require later Stage 1 receiver work.
- Background calibration, SDRplay support and full scientific validation remain outside this initial patch.
- A power loss can lose up to 30 seconds of data, plus any data not yet delivered from the SDR thread.
- Existing installations with bias tee enabled retain that setting; verify hardware before starting.

## Tests
Run `python -m unittest discover -s tests -v` from the `HLineStation` directory.
