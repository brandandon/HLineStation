# H-Line Station — Patch 05 (development, not an installer)

Based on the user-uploaded HLS.zip at the Patch 04 audit checkpoint, with no edits to main or archived observations.

## Fixes

- **Live observation-directory setting:** On a Settings change, preflight the destination, finish the active segment in the original folder, block if a recovery checkpoint remains, persist new settings, then change the active ObservationStore. A new store gets a fresh session ID. Old files never move automatically. Folder-transition errors are shown to the operator.
- **Settings durability:** settings.json is written into a temporary file in the same folder, flushed and fsynced, then atomically replaced. Errors propagate to a GUI warning; a failed save during settings-dialog application restores the previous configuration.
- **Migration:** An optional `--calibration-source` accepts the separately stored app-data `calibrations` catalog. The tool previews it, checks destination conflicts before copying, uses exclusive publication and checksum verification, and leaves originals unchanged. A pending recovery checkpoint blocks CLI `--apply`; direct compatibility helper still skips checkpoints.
- **CI:** A dedicated mandatory Windows/Ubuntu Qt job installs requirements, imports the GUI, then runs queued-event and MainWindow smoke tests with QT_QPA_PLATFORM=offscreen. The existing queued event test now uses QApplication (not QCoreApplication) so the GUI smoke test can run in the same process.
- **Tests:** added regression cases for atomic settings, error preservation, store transitions, external calibration catalogs, and offscreen GUI smoke/failure presentation.

## Verification in this environment

`python -m pytest -q`: **47 passed, 2 skipped**. The two Qt files skip locally because PySide6 is unavailable. The CI job independently installs PySide6 and verifies GUI imports; those two files should be exercised on GitHub Windows and Ubuntu. Python compile checks passed. This does **not** establish actual hardware correctness.

## Limitations and next acceptance steps

- The actual GUI folder-change flow and reconnect events still require testing on Windows; CI Qt smoke is not equivalent to an RTL-SDR disconnect/reconnect.
- Settings persistence reports failures but still needs an end-to-end disk-full GUI exercise.
- Migration CLI is preview-first; guided in-app migration remains future work. To include externally archived calibration spectra use `--calibration-source <app-data-calibrations-folder>`.
- Stable SDR hardware serial number and antenna/RF-chain profile are not yet captured automatically. These remain scientific provenance gaps.
- Do not merge with main or deploy this patch over the original H-Line Station installation until hardware acceptance.
