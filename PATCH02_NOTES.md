# H-Line Station — Development Patch 02 (partial)

**Base:** Patch 01 / corrected CI fixtures. **Status:** Development only; do not install on the observing PC.

## Changes

- Added optional RTL-SDR reconnection after unexpected termination (settings checkbox and maximum attempts). Backoff: 5, 10, 20, 40, then 60 seconds, bounded by configured attempts; does not retry simulator. An operator stop or application close cancels retries. No retry when observation saving failed. Retry counter is reset after 30 seconds of successful acquired sample duration. A recovered receiver starts a new observation segment.
- Added persistent last successful observation save timestamp/path in receiver information. Checkpoint cleanup failures are now reported separately instead of falsely reporting that the durable observation save failed.
- Added detailed observation timing fields, keeping v1 raw spectrum schema and existing fields unchanged. The averaging time constant is explicitly distinguished from accumulated sample duration.
- Added beam width metadata and point-in-time coordinate reference notes to new observations.
- Added configurable observation folder under Settings > Storage with a default in Documents/H-Line Station/Observations. No silent move/deletion of legacy observations. The legacy background and settings remain in application data. An outstanding legacy recovery checkpoint blocks new acquisition until resolved. A separate checksum-verifying, copy-only migration helper is included for later operator-approved migration.
- Added pure Python regression tests for retry backoff, metadata and copy-only migration.

## Limitations / further work

- **Important:** this is a partial implementation, not completion of the approved 20-item program. Physical USB retry timing and Qt signal ordering still need Windows hardware tests.
- Legacy observations remain in the original folder. A safe migration UI/CLI and checkpoint handling must be completed before recommending the Documents switch for existing users.
- Manual stop on some failed-save paths and uncertain interruption timing still need further review.
- Time-zone-aware coordinates are observation start snapshots; full integrated pointing histories/astrophysical corrections are not yet implemented.
- No SDRplay hardware support or Windows installer changes included.
