# Initial GitHub import notes

This package is a **source-only baseline** exported from the tested November 26, 2026 pre-repair backup.
**It does not contain the approved repairs.** The 20-item consolidated repair phase remains pending.

## Important privacy and licensing decisions

- No `UserData/`, personal `settings.json`, background calibration, or recorded observation files are included.
- No recorded spectral regression fixtures are public at this stage. Use synthetic fixtures until reviewed and sanitized.
- The bundled `drivers/rtlsdr.dll` has been **withheld** pending confirmation of its binary redistribution rights and license/attribution requirements. Consequently the source package by itself does **not** include everything needed to run RTL-SDR hardware or build the fully bundled Windows executable. The private pre-repair backup contains the original DLL and must remain private.
- The file `data/LICENSE-d3-celestial.txt` is retained with its accompanying data file, and its conditions should be honored.
- No project-level license has been selected. Public visibility alone does not grant permission to reuse the project's original source. Select an appropriate license after reviewing third-party components.
- The existing `README.md` and `STAGE1_*.md` describe the original experimental application and may describe capabilities that remain unvalidated. The current approved repair plan takes precedence.

## Automated tests

`.github/workflows/tests.yml` runs the existing `unittest` suite and Python compilation on GitHub-hosted Windows and Ubuntu machines. Both are **software-only tests**; no USB/SDR or Discovery Dish is attached. Treat initial CI failures as diagnostic, not as permission to alter original science data.

## Suggested first upload

1. Extract the ZIP locally; **do not upload the ZIP itself as repository source**.
2. Upload the extracted files and folders, including the hidden `.github` folder and `.gitignore`, to the empty `HLineStation` repository.
3. Check the **Actions** tab after the commit to view the first Windows and Ubuntu runs.

For reproducibility, retain the untouched original pre-repair backup in private storage. Do not add personal observations or settings to this public repository.
