# H-Line Station — Development Patch 03

**Base:** Patch 02 plus the cross-platform path-test correction; apply only to branch `stage1-consolidated-repairs`.

**Development only. Do not replace the original tested Windows installation or merge to `main`.**

## Changed files

- `hline/app.py`: protect unreadable recovery checkpoints by blocking acquisition; safely archive valid crash checkpoints using dedicated recovery helper.
- `hline/recovery.py` (new): unique, non-overwriting recovered file names, unmodified NPZ bytes, separate `.recovery.json` provenance including original checkpoint UTC time, recovered UTC time and explicitly unknown termination cause. Failures preserving the checkpoint block acquisition. Sidecar failure warns without disguising successful observation preservation.
- `hline/observations.py`: add processing-settings snapshot and background-calibration fingerprint/identity to new observation metadata; label pointing-reference timestamp as segment start, rather than the later save time. Preserve file schema version 1 and raw spectrum unchanged.
- `hline/migrate_cli.py` (new): explicitly approved, preview-first copy-only migration command using checksum-verifying migration helper from Patch 02. Refuses active checkpoint or conflicting files, and never removes originals.
- `tests/test_patch03.py` (new): seven new regression cases for recovery, metadata and migration.

## Tests

- `python -m pytest -q`: **30 passed** in the local Linux Python environment (Patch 02's corrected path test included).
- `python -m compileall -q hline HLineStation.py`: **passed**.
- **Not yet verified**: GitHub Actions Windows/Ubuntu results, actual PySide6 GUI recovery dialog, RTL-SDR hardware or real USB reconnect. Local environment does not have PySide6.

## Migrating existing observations — operator approval required

Only after the current application has exited and any active recovery checkpoint has been safely resolved:

```powershell
python -m hline.migrate_cli --source "OLD_OBSERVATIONS_FOLDER" --destination "NEW_OBSERVATIONS_FOLDER"
python -m hline.migrate_cli --source "OLD_OBSERVATIONS_FOLDER" --destination "NEW_OBSERVATIONS_FOLDER" --apply
```

The first command is **preview only**. The second copies files without deleting originals. **Do not run this against your real observations yet**: the full Windows migration/restore workflow remains to be tested and reviewed.

## Remaining work from approved repair specification

The scientific baseline remains a safety fallback, not a validated positive-constrained scientific fit. Complete calibration reproducibility still requires retaining calibration spectra, not only fingerprint metadata. A full history of time-varying pointing and proper Doppler/velocity frame conventions remain outstanding. Qt receiver lifecycle and live save-failure edge cases require Windows tests. Source-only CI cannot validate the SDR hardware. This patch does not complete the consolidated repair program.
