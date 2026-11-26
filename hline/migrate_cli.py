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

from .storage_migration import copy_legacy_observations, migration_preflight


def migration_preview(source, destination, *, calibration_source=None):
    src, dest = Path(source).expanduser().resolve(), Path(destination).expanduser().resolve()
    if not src.is_dir():
        raise FileNotFoundError(src)
    if src == dest or src in dest.parents or dest in src.parents:
        raise ValueError('Source and destination directories must not overlap')
    plan = migration_preflight(src, dest, calibration_source=calibration_source)
    # This summary is compatible with the preview-only CLI used in Patch 03.
    return {'source': str(src), 'destination': str(dest),
            'copy': plan['copy'], 'identical': plan['identical'],
            'conflicts': plan['conflicts'], 'pending_checkpoint': plan['pending_checkpoint'],
            'total_source_observations': len(list(src.glob('*.npz'))) - int(plan['pending_checkpoint']),
            'recovery_sidecars': len(list(src.glob('*.recovery.json'))),
            'calibration_archives': len([p for p in plan['copy'] + plan['identical'] + plan['conflicts'] if p.startswith('calibrations/')])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', required=True, help='Original observations folder')
    parser.add_argument('--destination', required=True, help='New observations folder')
    parser.add_argument('--calibration-source', default=None, help='Optional legacy application-data calibrations folder')
    parser.add_argument('--apply', action='store_true', help='Explicitly approve copying after preview')
    args = parser.parse_args(argv)
    try:
        plan = migration_preview(args.source, args.destination, calibration_source=args.calibration_source)
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
        count = copy_legacy_observations(plan['source'], plan['destination'], calibration_source=args.calibration_source)
        print(f'Migration complete: {count} newly copied, all originals retained.')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
