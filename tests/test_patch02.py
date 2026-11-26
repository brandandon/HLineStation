"""Patch 02: reconnect policy, timing metadata and copy-only migration."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

from hline.reconnect import retry_delay
from hline.paths import observation_dir
from hline.storage_migration import copy_legacy_observations, sha256
from hline.observations import ObservationStore, utc_stamp
from hline.processing import Integrator


class Patch02Tests(unittest.TestCase):
    def test_reconnect_bounded_backoff(self):
        self.assertEqual([retry_delay(i) for i in range(1, 7)], [5, 10, 20, 40, 60, None])
        self.assertIsNone(retry_delay(0))
        self.assertIsNone(retry_delay(2, maximum=1))

    def test_documents_default_and_override(self):
        self.assertTrue(observation_dir().endswith(str(Path('H-Line Station')/'Observations')))
        with tempfile.TemporaryDirectory() as temporary_directory:
            self.assertEqual(observation_dir(temporary_directory), str(Path(temporary_directory)))

    def test_migration_copy_preserves_original_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp)/'old', Path(tmp)/'new'
            old.mkdir()
            (old/'observation_1.npz').write_bytes(b'original')
            (old/'recovered_a.npz').write_bytes(b'recovered')
            (old/'recovery_checkpoint.npz').write_bytes(b'checkpoint')
            original = sha256(old/'observation_1.npz')
            self.assertEqual(copy_legacy_observations(old, new), 2)
            self.assertEqual(copy_legacy_observations(old, new), 0)
            self.assertEqual(sha256(old/'observation_1.npz'), original)
            self.assertEqual(sha256(new/'observation_1.npz'), original)
            self.assertTrue((old/'recovery_checkpoint.npz').exists())
            self.assertFalse((new/'recovery_checkpoint.npz').exists())
            (new/'observation_1.npz').write_bytes(b'conflict')
            with self.assertRaises(FileExistsError): copy_legacy_observations(old, new)

    def test_timing_and_beam_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(tmp)
            cfg = dict(source='simulator', nfft=4, gain=40.2, integration_s=60,
                       center_mhz=1420.40575, sample_rate=2400000, dish_diameter_m=0.7,beam_deg=0)
            integ = Integrator()
            integ.add(np.array([1.,2.,3.,4.]), .25, 60)
            path = store.save(cfg, integ, {}, 'receiver_stop', utc_stamp())
            _, metadata = store.read(path)
            timing = metadata['acquisition_timing']
            self.assertEqual(timing['acquired_sample_duration_s'], .25)
            self.assertEqual(timing['averaging_time_constant_s'], 60)
            self.assertTrue(timing['effective_integration_is_estimate'])
            self.assertEqual(metadata['beam_metadata']['beam_width_method'], 'approx_70_lambda_over_D')
