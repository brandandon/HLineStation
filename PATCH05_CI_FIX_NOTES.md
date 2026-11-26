# Patch 05 CI portability correction

This is a targeted correction for the two failed jobs in GitHub Actions following Patch 05.

- `tests/test_patch05.py`: compare already-created directories with `Path.samefile()` to handle Windows short/long (8.3) names.
- `hline/storage_migration.py`: return portable forward-slash relative names in migration previews, conflict reporting, and copy lookup.
- `.github/workflows/tests.yml`: install `libegl1`, `libopengl0`, and `libxkbcommon-x11-0` on the Ubuntu Qt job so PySide6/pyqtgraph can import with the offscreen backend.

Local results: 47 passed, 2 skipped (PySide6 not installed). The mandatory Qt test must run in the updated GitHub workflow.

Copy the three files into the `stage1-consolidated-repairs` repository, maintaining directory structure, then commit and push. Do not merge with `main` or install into the original application.
