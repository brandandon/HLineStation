# AT-01 — Information panel refresh correction

## Cause
`hline/app.py` imports the stdlib `html` module, but `_update_info()` also assigns a local string named `html`. The local binding shadows the module, so `html.escape(...)` throws `UnboundLocalError` when `last_save` or `last_save_error` is present.

## Changes
- `hline/app.py`: alias the stdlib module as `html_utils`, using `html_utils.escape()` for saved-path and error text while retaining the local `html` markup string.
- `tests/test_patch05_qt.py`: add an AT-01 regression for no prior save, a populated `last_save`, escaped path text, warning text, and warning without a prior save.

## Local validation
`python -m compileall -q hline tests`: PASS.
`python -m pytest -q`: 47 passed, 2 skipped (Qt unavailable in this local environment).
The new AT-01 regression must run in the GitHub Actions mandatory Qt jobs; do not claim it has passed until CI verifies it.

## Installation
On `stage1-consolidated-repairs`, copy the two Python files into the corresponding folders of your GitHub Desktop repository. Commit, push, and verify Windows and Ubuntu mandatory Qt jobs.
Only after CI passes, close the acceptance-test application, back up or preserve the existing isolated test observation, then copy only `hline/app.py` into `C:\Users\Dan\Downloads\HLineStation_Acceptance_Test\hline\app.py`. Do not overwrite the original installation, `Observations`, or `PrivateData`.

## Remaining
Repeat the stopped/saved info-panel refresh in the isolated Windows acceptance test. This package does not modify SDR acquisition or observation storage.
