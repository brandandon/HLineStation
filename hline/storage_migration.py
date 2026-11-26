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


def _migration_files(source, calibration_source=None):
    """Yield (source_file, destination-relative filename) pairs.

    calibration_source may be the legacy application-data calibrations folder,
    which lives beside observations rather than underneath it.
    """
    src = Path(source)
    listed = [(p, p.relative_to(src)) for p in src.glob('*.npz')
              if p.name != 'recovery_checkpoint.npz']
    listed.extend((p, p.relative_to(src)) for p in src.glob('*.recovery.json'))
    catalog = src / 'calibrations'
    if catalog.is_dir():
        listed.extend((p, p.relative_to(src)) for p in catalog.glob('*.npz'))
    if calibration_source is not None:
        external = Path(calibration_source).resolve()
        if external.is_dir() and external != catalog.resolve():
            for p in external.glob('*.npz'):
                rel = Path('calibrations') / p.name
                listed.append((p, rel))
    seen = {}
    for file, relative in listed:
        if relative in seen and seen[relative] != file:
            raise ValueError(f'Conflicting calibration sources: {relative}')
        seen[relative] = file
    return sorted(((path, rel) for rel, path in seen.items()), key=lambda pair: str(pair[1]))


def migration_preflight(source, destination, *, calibration_source=None):
    """Scan all conflicts before the first file can be published."""
    src, dest = Path(source).resolve(), Path(destination).resolve()
    if not src.is_dir():
        raise FileNotFoundError(src)
    if src == dest or src in dest.parents or dest in src.parents:
        raise ValueError('Migration directories must not overlap')
    copies, identical, conflicts = [], [], []
    for file, relative in _migration_files(src, calibration_source):
        target = dest / relative
        if target.exists():
            if target.is_file() and sha256(file) == sha256(target):
                identical.append(relative.as_posix())
            else:
                conflicts.append(relative.as_posix())
        else:
            copies.append(relative.as_posix())
    return {'copy': copies, 'identical': identical, 'conflicts': conflicts,
            'pending_checkpoint': (src / 'recovery_checkpoint.npz').exists()}


def copy_legacy_observations(source, destination, *, calibration_source=None):
    """Copy-only migration; preflight all conflicts, include recovery sidecars.

    No file is overwritten or deleted. The CLI independently blocks an active
    checkpoint; direct helper calls omit it to preserve legacy compatibility.
    An interrupted copy can be safely rerun and verified.
    """
    src, dest = Path(source).resolve(), Path(destination).resolve()
    plan = migration_preflight(src, dest, calibration_source=calibration_source)
    if plan['conflicts']:
        raise FileExistsError('Conflicting destination files: ' + ', '.join(plan['conflicts']))
    moved = 0
    sources = {rel.as_posix(): file for file, rel in _migration_files(src, calibration_source)}
    for relative in plan['copy']:
        source_file = sources[relative]
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
