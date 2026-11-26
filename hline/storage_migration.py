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


def copy_legacy_observations(source, destination):
    """Copy-only migration. No deletion, overwriting or checkpoint auto-resume.

    Existing destination entries must match byte-for-byte, otherwise abort.
    Call only from an explicit operator-approved migration action.
    """
    src = Path(source).resolve()
    dest = Path(destination).resolve()
    if not src.is_dir():
        raise FileNotFoundError(src)
    if dest == src or src in dest.parents or dest in src.parents:
        raise ValueError("Migration directories must not overlap")
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for source_file in sorted(src.glob("*.npz")):
        # A recovery checkpoint is active data, not merely an archived observation.
        # Do not copy it into the new active checkpoint location.
        if source_file.name == "recovery_checkpoint.npz":
            continue
        target = dest / source_file.name
        if target.exists():
            if sha256(source_file) != sha256(target):
                raise FileExistsError(f"Conflicting destination observation: {target}")
            continue
        fd, temp = tempfile.mkstemp(prefix=".hline-migrate-", suffix=".tmp", dir=dest)
        try:
            with os.fdopen(fd, "wb") as output, open(source_file, "rb") as inp:
                shutil.copyfileobj(inp, output)
                output.flush()
                os.fsync(output.fileno())
            if sha256(source_file) != sha256(temp):
                raise IOError(f"Migration copy checksum mismatch: {source_file.name}")
            # Atomic publish, never overwrite an existing file.
            try:
                os.link(temp, target)
            except FileExistsError:
                raise
            except OSError:
                # Hard links may be unavailable; refuse rather than risk overwrite.
                raise RuntimeError("Filesystem cannot safely publish a non-overwriting migration file")
            moved += 1
        finally:
            if os.path.exists(temp): os.unlink(temp)
    return moved
