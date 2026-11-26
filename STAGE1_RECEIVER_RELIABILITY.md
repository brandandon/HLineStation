# Stage 1 — Receiver reliability follow-up

This working copy extends the initial Stage 1 observation-saving patch. The original ZIP is not modified.

## Changes

- Both receiver threads now report the reason acquisition ended through `acquisitionEnded(reason, unexpected)`.
- An unexpectedly completed receiver thread triggers an automatic attempt to save the accumulated, unprocessed average as an observation with reason `receiver_interrupted`. The saved data is not reset until that write succeeds.
- If the final save fails, the averaged data remains in memory and the recovery checkpoint is not intentionally cleared; the operator receives an error.
- Receiver startup resets stop-request state; RTL-SDR device index validation now rejects negative indices.
- Receiver stop retains the thread reference if the three-second stop wait times out. **A blocked synchronous USB read can still hang**: unplugging the device or forcibly terminating the process is not automated.
- The simulator reports normal stop through the same lifecycle signal, and stops an in-progress simulated background capture without emitting a partial calibration.
- Added storage fault-injection tests for atomic checkpoint replacement, interrupted observation metadata, and distinct final saves.

## Windows verification checklist — NOT YET RUN

1. Extract ZIP into a **new folder**, leaving the original installation untouched. Use a Python environment with dependencies from `requirements.txt`.
2. In a terminal in the `HLineStation` folder, run `python -m unittest discover -s tests -v`. All seven tests should pass.
3. Start `Run-Demo-Simulator.bat`. Confirm the receiver is stopped initially, then click **Start**. Let the spectrum accumulate for 35+ seconds and confirm a checkpoint appears in `%APPDATA%\HLineStation\observations`.
4. Change pointing; confirm a new `observation_*.npz` is written and the average resets. Stop the receiver; confirm another file appears. Repeat using manual averaging reset and application exit.
5. Inspect a saved NPZ using Python `numpy.load(..., allow_pickle=False)`; verify `power` is finite and `metadata` JSON records `reason`, `synthetic`, integration duration, and pointing. Do not use real measurements for destructive tests.
6. With the RTL-SDR connected, start a short observation. Close other SDR applications first. Test stop/restart. For disconnect testing, use a **noncritical short test session** and remove USB only if safe for the hardware. Verify an error is displayed, a saved observation has reason `receiver_interrupted`, and acquisition does not restart automatically.
7. Reconnect the receiver and manually start again. Verify that new data is collected and saved in a separate observation.
8. Test shutdown during a background calibration. Confirm no partially collected calibration is silently accepted.
9. Verify the bias tee is OFF unless deliberately configured for known compatible RF equipment. Existing saved configurations may retain an ON setting.

## Known limitations

- Windows GUI, driver, and real-device tests have **not** been run here. The host environment lacks PySide6 and physical SDR hardware.
- There is no automatic USB reconnect yet; reconnect is operator initiated.
- The synchronous `rtlsdr_read_sync` call cannot be cancelled reliably through the current ctypes wrapper. The application warns and keeps the thread reference on a stop timeout.
- This is a receiver reliability increment, not a full recovery state machine or complete Windows acceptance certification.
- An abnormal process termination may leave only the last 30-second checkpoint; automatic checkpoint restoration is not implemented.
