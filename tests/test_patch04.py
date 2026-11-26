"""Patch 04: scientific regression, immutable reference spectra and migrations."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from hline.processing import Integrator, process
from hline.observations import ObservationStore, utc_stamp
from hline.storage_migration import copy_legacy_observations, migration_preflight
from hline.receiver_events import is_current_event


class Patch04Tests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(source='rtlsdr', nfft=4096, gain=40.2,
                        integration_s=60., center_mhz=1420.40575,
                        sample_rate=2400000., mode='baseline',
                        dc_notch=False, remove_spikes=False, smooth_kms=0.,
                        band_use_fraction=.76, line_window_kms=150.,
                        baseline_order=2, show_peaks=False)

    def _process(self, power, vel, **config):
        integ = Integrator()
        integ.avg = power
        cfg = dict(self.cfg, **config)
        return process(cfg, integ, np.linspace(1420., 1421., len(power)), vel, False)

    def test_positive_baseline_sloping_continuum(self):
        n = 4096
        vel = np.linspace(-600., 600., n)
        x = np.linspace(-1., 1., n)
        power = .15 * np.exp(.30 * x + .15 * x*x)
        result = self._process(power, vel)
        self.assertFalse(result['baseline_failed'])
        self.assertTrue(np.all(np.isfinite(result['y'])))
        self.assertLess(float(np.max(np.abs(result['y']))), 1.5)

    def test_positive_baseline_preserves_injected_broad_feature(self):
        n = 4096
        vel = np.linspace(-600., 600., n)
        x = np.linspace(-1., 1., n)
        power = .15 * np.exp(.20*x + .08*x*x)
        power *= 1 + .20 * np.exp(-.5 * ((vel - 40)/35)**2)
        result = self._process(power, vel)
        self.assertFalse(result['baseline_failed'])
        peak = float(np.max(result['y']))
        self.assertGreater(peak, 12.)
        self.assertLess(peak, 28.)

    def test_one_sided_continuum_never_invents_a_peak(self):
        n = 4096
        vel = np.linspace(-100., 300., n)
        power = .15 * np.exp(.2 * np.linspace(-1, 1, n))
        result = self._process(power, vel, show_peaks=True)
        self.assertTrue(result['baseline_failed'])
        self.assertEqual(result['peaks'], [])

    def test_true_raw_display_ignores_optional_transformations(self):
        n = 4096
        vel = np.linspace(-600., 600., n)
        power = np.ones(n) * 0.15
        power[n//2] = 15.  # spike would be removed by DC notch / RFI filter
        cfg = dict(mode='raw', dc_notch=True, remove_spikes=True, smooth_kms=80.)
        result = self._process(power, vel, **cfg)
        raw_expected = 10 * np.log10(power)
        # Display velocity is sorted; compare the spectra in sorted-velocity order.
        np.testing.assert_allclose(result['y'], raw_expected[np.argsort(vel)])
        self.assertEqual(result['peaks'], [])
        self.assertEqual(result['spikes'], [])

    def test_immutable_calibration_catalog_and_observation_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch('hline.processing.user_dir', return_value=tmp), patch('hline.observations.user_dir', return_value=tmp):
                integ = Integrator()
                key = ('rtlsdr',0,1420.40575,4,2400000.0,'40.2',0,False)
                first = np.array([1.,2.,3.,4.])
                integ.set_background(first, key)
                first_id = integ.background_calibration_id
                self.assertTrue((root/'calibrations'/f'{first_id}.npz').exists())
                integ.add(first, 1., 60.)
                store = ObservationStore(root/'observations')
                cfg = dict(self.cfg, nfft=4)
                saved = store.save(cfg, integ, {}, 'receiver_stop', utc_stamp())
                _, metadata = store.read(saved)
                bg = metadata['processing_provenance']['background_calibration']
                self.assertEqual(bg['calibration_id'], first_id)
                copy = store.root/bg['archived_relative_path']
                self.assertTrue(copy.exists())
                with np.load(copy, allow_pickle=False) as data:
                    np.testing.assert_array_equal(data['bg'], first)
                integ.set_background(np.array([2.,3.,4.,5.]), key)
                self.assertNotEqual(first_id, integ.background_calibration_id)
                with np.load(copy, allow_pickle=False) as data:
                    np.testing.assert_array_equal(data['bg'], first)

    def test_calibration_write_failure_preserves_active_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('hline.processing.user_dir', return_value=tmp):
                integ = Integrator()
                key = ('rtlsdr',0,1420.40575,4,2400000.0,'40.2',0,False)
                integ.set_background(np.ones(4), key)
                original = integ.background_calibration_id
                with patch('hline.processing.os.link', side_effect=OSError('disk full')):
                    with self.assertRaises(OSError):
                        integ.set_background(np.ones(4)*2, key)
                self.assertEqual(integ.background_calibration_id, original)

    def test_preflight_detects_late_conflicts_without_partial_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp)/'src', Path(tmp)/'dest'
            src.mkdir(); dest.mkdir()
            (src/'observation_a.npz').write_bytes(b'a')
            (src/'observation_z.npz').write_bytes(b'new')
            (dest/'observation_z.npz').write_bytes(b'old')
            with self.assertRaises(FileExistsError):
                copy_legacy_observations(src, dest)
            self.assertFalse((dest/'observation_a.npz').exists())

    def test_migration_copies_recovery_sidecars_and_calibration_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp)/'src', Path(tmp)/'dest'
            src.mkdir(); (src/'calibrations').mkdir()
            (src/'recovered_a.npz').write_bytes(b'bytes')
            (src/'recovered_a.recovery.json').write_text('{"status":"recovered"}')
            (src/'calibrations'/'123.npz').write_bytes(b'cal')
            plan = migration_preflight(src, dest)
            self.assertEqual(len(plan['copy']),3)
            self.assertEqual(copy_legacy_observations(src, dest),3)
            self.assertEqual((dest/'recovered_a.recovery.json').read_bytes(),
                             (src/'recovered_a.recovery.json').read_bytes())
            self.assertEqual((dest/'calibrations'/'123.npz').read_bytes(), b'cal')

    def test_weight_based_effective_independent_blocks(self):
        i = Integrator()
        for _ in range(5):
            i.add(np.ones(16), 1.0, 0)
        self.assertAlmostEqual(i.effective_independent_blocks(), 5.0)
        i.reset()
        self.assertEqual(i.effective_independent_blocks(),0.0)

    def test_generation_gate(self):
        self.assertTrue(is_current_event(4,4,True))
        self.assertFalse(is_current_event(3,4,True))
        self.assertFalse(is_current_event(4,4,False))


if __name__ == '__main__':
    unittest.main()
