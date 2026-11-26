"""Crash checkpoint archival, preserving the original scientific NPZ unchanged."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def preserve_checkpoint(checkpoint, metadata, *, now=None):
    """Move a validated checkpoint to an unoccupied recovered name.

    Returns (recovered_path, sidecar_warning).  A sidecar failure never hides
    the fact that the checkpoint itself was successfully protected. The caller
    must validate the file *before* invoking this helper.
    """
    source = Path(checkpoint)
    if not source.is_file():
        raise FileNotFoundError(source)
    now = now or datetime.now(timezone.utc)
    session = str(metadata.get('session_id', 'unknown'))
    safe_session = ''.join(c for c in session if c.isalnum())[:12] or 'unknown'
    timestamp = now.strftime('%Y%m%dT%H%M%S_%fZ')
    for number in range(1000):
        name = f'recovered_{safe_session}_{timestamp}_{number:03d}.npz'
        target = source.parent / name
        # Atomic exclusive reservation: never clobber a previous recovery.
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            break
        except FileExistsError:
            continue
    else:
        raise FileExistsError('Cannot reserve a unique recovery filename')
    try:
        os.replace(source, target)
    except BaseException:
        target.unlink(missing_ok=True)
        raise

    details = {
        'recovery_status': 'recovered_from_checkpoint',
        'original_checkpoint_saved_utc': metadata.get('saved_utc'),
        'original_observation_started_utc': metadata.get('started_utc'),
        'recovered_utc': now.isoformat(timespec='milliseconds'),
        'termination_reason': 'unknown_unexpected_exit',
        'original_session_id': metadata.get('session_id'),
        'original_spectrum_count': metadata.get('spectrum_count'),
        'original_acquired_sample_duration_s': metadata.get('elapsed_integration_s'),
        'original_npz_unchanged': True,
    }
    sidecar = target.with_suffix('.recovery.json')
    temp = None
    try:
        fd, temp = tempfile.mkstemp(prefix='.hline-recovery-', suffix='.tmp', dir=target.parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(details, output, indent=2, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, sidecar)
        return target, None
    except (OSError, TypeError, ValueError) as exc:
        return target, f'Recovery saved at {target}, but metadata sidecar failed: {exc}'
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
