"""Explicit, preview-first, copy-only observation migration.

Run from the project root:
    python -m hline.migrate_cli --source OLD --destination NEW
    python -m hline.migrate_cli --source OLD --destination NEW --apply

Existing observations are never removed or overwritten. Pending recovery
checkpoints are not migrated automatically.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .storage_migration import copy_legacy_observations, sha256


def migration_preview(source, destination):
    src, dest = Path(source).expanduser().resolve(), Path(destination).expanduser().resolve()
    if not src.is_dir():
        raise FileNotFoundError(src)
    if src == dest or src in dest.parents or dest in src.parents:
        raise ValueError('Source and destination directories must not overlap')
    files = sorted(src.glob('*.npz'))
    checkpoint = src / 'recovery_checkpoint.npz'
    copies, identical, conflicts = [], [], []
    for path in files:
        if path.name == checkpoint.name:
            continue
        target = dest / path.name
        if target.exists():
            (identical if target.is_file() and sha256(path) == sha256(target) else conflicts).append(path.name)
        else:
            copies.append(path.name)
    return {'source': str(src), 'destination': str(dest),
            'copy': copies, 'identical': identical, 'conflicts': conflicts,
            'pending_checkpoint': checkpoint.exists(),
            'total_source_observations': len(files) - int(checkpoint.exists())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', required=True, help='Original observations folder')
    parser.add_argument('--destination', required=True, help='New observations folder')
    parser.add_argument('--apply', action='store_true', help='Explicitly approve copying after preview')
    args = parser.parse_args(argv)
    try:
        plan = migration_preview(args.source, args.destination)
        print('Source:', plan['source'])
        print('Destination:', plan['destination'])
        print('Copy candidates:', len(plan['copy']))
        print('Already identical:', len(plan['identical']))
        print('Conflicting filenames:', len(plan['conflicts']))
        print('Pending recovery checkpoint:', plan['pending_checkpoint'])
        if plan['conflicts']:
            print('ERROR: Conflicts must be resolved before migration:', ', '.join(plan['conflicts']))
            return 2
        if plan['pending_checkpoint']:
            print('ERROR: Preserve/recover the active checkpoint in the original application before migration.')
            return 2
        if not args.apply:
            print('PREVIEW ONLY: Nothing changed. Rerun with --apply to copy and verify files.')
            return 0
        count = copy_legacy_observations(plan['source'], plan['destination'])
        print(f'Migration complete: {count} newly copied, all originals retained.')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
