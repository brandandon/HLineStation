"""Run with: python -m unittest discover -s tests -v"""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hline.observations import ObservationStore, utc_stamp
from hline.processing import Integrator


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ObservationStore(self.temp.name)
        self.cfg = {"source": "simulator", "center_mhz": 1420.40575,
                    "sample_rate": 2.4e6, "nfft": 4, "gain": 40.2, "integration_s": 0,
                    "dish_az": 180, "dish_el": 60}
        self.integ = Integrator()
        self.integ.add(np.array([1., 2., 3., 4.]), 0.5, 0)

    def test_round_trip_preserves_raw_average_and_metadata(self):
        path = self.store.save(self.cfg, self.integ, {"dish_az_deg": 180}, "new_pointing", utc_stamp())
        spectrum, meta = self.store.read(path)
        np.testing.assert_array_equal(spectrum, self.integ.avg)
        self.assertEqual(meta["reason"], "new_pointing")
        self.assertTrue(meta["synthetic"])
        self.assertEqual(meta["spectrum_count"], 1)
        self.assertEqual(meta["elapsed_integration_s"], 0.5)

    def test_checkpoint_and_final_file(self):
        self.store.save(self.cfg, self.integ, {}, "checkpoint", utc_stamp(), checkpoint=True)
        self.assertTrue(self.store.checkpoint.exists())
        self.store.save(self.cfg, self.integ, {}, "receiver_stop", utc_stamp())
        self.store.clear_checkpoint()
        self.assertFalse(self.store.checkpoint.exists())
        self.assertEqual(len(list(Path(self.temp.name).glob("observation_*.npz"))), 1)

    def test_invalid_file_rejected(self):
        path = Path(self.temp.name) / "bad.npz"
        path.write_bytes(b"bad")
        with self.assertRaises(Exception):
            self.store.read(path)

    def test_fft_mismatch_rejected_before_save(self):
        self.cfg["nfft"] = 8
        with self.assertRaisesRegex(ValueError, "FFT mismatch"):
            self.store.save(self.cfg, self.integ, {}, "receiver_stop", utc_stamp())
        self.assertFalse(list(Path(self.temp.name).glob("observation_*.npz")))

    def test_nonfinite_power_rejected_before_save(self):
        self.integ.avg = np.array([1.0, float("nan"), 3.0, 4.0])
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            self.store.save(self.cfg, self.integ, {}, "receiver_stop", utc_stamp())
        self.assertFalse(list(Path(self.temp.name).glob("observation_*.npz")))

    def test_reader_rejects_missing_required_metadata(self):
        path = self.store.save(self.cfg, self.integ, {}, "receiver_stop", utc_stamp())
        with np.load(path, allow_pickle=False) as z:
            power = z["power"].copy()
            import json
            metadata = json.loads(str(z["metadata"].item()))
        metadata.pop("spectrum_count")
        self.store._atomic_npz(path, power, metadata)
        with self.assertRaisesRegex(ValueError, "Missing observation metadata"):
            self.store.read(path)

    def test_distinct_observations_are_not_overwritten(self):
        first = self.store.save(self.cfg, self.integ, {}, "reset", utc_stamp())
        second = self.store.save(self.cfg, self.integ, {}, "stop", utc_stamp())
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())


if __name__ == "__main__":
    unittest.main()
