"""Safe opt-in copy of legacy observation data into the new Documents location."""
from __future__ import annotations
import hashlib
import os
import shutil
import tempfile
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def _migration_files(source):
    """Observation containers, recovery sidecars and immutable calibration refs."""
    src = Path(source)
    listed = [p for p in src.glob('*.npz') if p.name != 'recovery_checkpoint.npz']
    listed.extend(src.glob('*.recovery.json'))
    catalog = src / 'calibrations'
    if catalog.is_dir():
        listed.extend(catalog.glob('*.npz'))
    return sorted(listed)


def migration_preflight(source, destination):
    """Scan all conflicts before the first file can be published."""
    src, dest = Path(source).resolve(), Path(destination).resolve()
    if not src.is_dir():
        raise FileNotFoundError(src)
    if src == dest or src in dest.parents or dest in src.parents:
        raise ValueError('Migration directories must not overlap')
    copies, identical, conflicts = [], [], []
    for file in _migration_files(src):
        relative = file.relative_to(src)
        target = dest / relative
        if target.exists():
            if target.is_file() and sha256(file) == sha256(target):
                identical.append(str(relative))
            else:
                conflicts.append(str(relative))
        else:
            copies.append(str(relative))
    return {'copy': copies, 'identical': identical, 'conflicts': conflicts,
            'pending_checkpoint': (src / 'recovery_checkpoint.npz').exists()}


def copy_legacy_observations(source, destination):
    """Copy-only migration; preflight all conflicts, include recovery sidecars.

    No file is overwritten or deleted. The CLI independently blocks an active
    checkpoint; direct helper calls exclude it to preserve legacy behavior.
    An interrupted copy can be safely rerun and verified.
    """
    src, dest = Path(source).resolve(), Path(destination).resolve()
    plan = migration_preflight(src, dest)
    if plan['conflicts']:
        raise FileExistsError('Conflicting destination files: ' + ', '.join(plan['conflicts']))
    moved = 0
    for relative in plan['copy']:
        source_file = src / relative
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.hline-migrate-', suffix='.tmp', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as output, open(source_file, 'rb') as inp:
                shutil.copyfileobj(inp, output)
                output.flush()
                os.fsync(output.fileno())
            if sha256(source_file) != sha256(temp):
                raise IOError(f'Migration copy checksum mismatch: {relative}')
            os.link(temp, target)  # exclusive publication, no overwrite
            moved += 1
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return moved
