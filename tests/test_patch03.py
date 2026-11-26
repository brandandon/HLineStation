"""Patch 03 recovery, provenance and migration regression tests."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np

from hline.migrate_cli import migration_preview, main
from hline.observations import ObservationStore, utc_stamp
from hline.processing import Integrator
from hline.recovery import preserve_checkpoint


class Patch03Tests(unittest.TestCase):
    def test_recovery_preserves_bytes_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / 'recovery_checkpoint.npz'
            checkpoint.write_bytes(b'original checkpoint bytes')
            original = checkpoint.read_bytes()
            metadata = {'saved_utc': '2026-11-26T15:00:00+00:00',
                        'started_utc': '2026-11-26T14:55:00+00:00',
                        'session_id': 'abc123', 'spectrum_count': 50,
                        'elapsed_integration_s': 5.0}
            saved, warning = preserve_checkpoint(checkpoint, metadata)
            self.assertIsNone(warning)
            self.assertFalse(checkpoint.exists())
            self.assertEqual(saved.read_bytes(), original)
            sidecar = json.loads(saved.with_suffix('.recovery.json').read_text())
            self.assertEqual(sidecar['recovery_status'], 'recovered_from_checkpoint')
            self.assertEqual(sidecar['termination_reason'], 'unknown_unexpected_exit')
            self.assertEqual(sidecar['original_checkpoint_saved_utc'], metadata['saved_utc'])

    def test_recovery_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / 'recovery_checkpoint.npz'
            checkpoint.write_bytes(b'new')
            when = datetime(2026, 11, 26, tzinfo=timezone.utc)
            target = Path(tmp) / 'recovered_test_20261126T000000_000000Z_000.npz'
            target.write_bytes(b'keep')
            saved, _ = preserve_checkpoint(checkpoint, {'session_id':'test'}, now=when)
            self.assertEqual(target.read_bytes(), b'keep')
            self.assertNotEqual(saved, target)
            self.assertEqual(saved.read_bytes(), b'new')

    def test_recovery_failure_does_not_destroy_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / 'recovery_checkpoint.npz'
            checkpoint.write_bytes(b'untouched')
            with patch('hline.recovery.os.replace', side_effect=OSError('denied')):
                with self.assertRaises(OSError):
                    preserve_checkpoint(checkpoint, {'session_id':'a'})
            self.assertEqual(checkpoint.read_bytes(), b'untouched')

    def test_metadata_snapshot_and_processing_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(tmp)
            cfg = {'source':'simulator','nfft':4,'gain':40.2,
                   'integration_s':60,'center_mhz':1420.40575,
                   'sample_rate':2400000,'dish_diameter_m':0.7,
                   'baseline_order':2,'smooth_kms':4,'mode':'baseline'}
            integ = Integrator()
            integ.add(np.ones(4), 0.5, 60)
            start = utc_stamp()
            path = store.save(cfg,integ,{},'receiver_stop',start)
            _, m = store.read(path)
            self.assertEqual(m['pointing_reference_utc'], start)
            p = m['processing_provenance']
            self.assertEqual(p['processing_settings']['baseline_order'], 2)
            self.assertEqual(p['processing_settings']['smooth_kms'], 4)
            self.assertFalse(p['background_calibration']['available'])

    def test_background_fingerprint_and_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(tmp)
            cfg = {'source':'simulator','nfft':4,'gain':40.2,
                   'integration_s':60,'center_mhz':1420.40575,
                   'sample_rate':2400000}
            integ = Integrator()
            integ.add(np.ones(4), 0.5, 60)
            integ.background = np.ones(4)
            integ.background_key = ('simulator',0,40.2,4,1420.40575,2400000,0,False)
            path = store.save(cfg,integ,{},'receiver_stop',utc_stamp())
            _, m = store.read(path)
            bg = m['processing_provenance']['background_calibration']
            self.assertTrue(bg['available'])
            self.assertEqual(bg['spectrum_bins'],4)
            self.assertEqual(len(bg['spectrum_sha256']),64)

    def test_migration_preview_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp)/'old',Path(tmp)/'new'
            src.mkdir()
            (src/'observation_a.npz').write_bytes(b'raw')
            plan=migration_preview(src,dest)
            self.assertEqual(plan['copy'],['observation_a.npz'])
            self.assertFalse(dest.exists())
            self.assertEqual(main(['--source',str(src),'--destination',str(dest)]),0)
            self.assertFalse(dest.exists())
            self.assertEqual(main(['--source',str(src),'--destination',str(dest),'--apply']),0)
            self.assertEqual((dest/'observation_a.npz').read_bytes(),b'raw')
            self.assertEqual((src/'observation_a.npz').read_bytes(),b'raw')

    def test_migration_blocks_pending_checkpoint_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp)/'old',Path(tmp)/'new'
            src.mkdir(); dest.mkdir()
            (src/'recovery_checkpoint.npz').write_bytes(b'checkpoint')
            self.assertEqual(main(['--source',str(src),'--destination',str(dest),'--apply']),2)
            self.assertFalse(list(dest.iterdir()))
            (src/'recovery_checkpoint.npz').unlink()
            (src/'observation_x.npz').write_bytes(b'first')
            (dest/'observation_x.npz').write_bytes(b'different')
            self.assertEqual(main(['--source',str(src),'--destination',str(dest),'--apply']),2)
            self.assertEqual((dest/'observation_x.npz').read_bytes(),b'different')

if __name__ == '__main__':
    unittest.main()
