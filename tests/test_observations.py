"""Run with: python -m unittest discover -s tests -v"""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hline.observations import ObservationStore
from hline.processing import Integrator


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ObservationStore(self.temp.name)
        self.cfg = {"source": "simulator", "center_mhz": 1420.40575,
                    "sample_rate": 2.4e6, "nfft": 4, "integration_s": 0,
                    "dish_az": 180, "dish_el": 60}
        self.integ = Integrator()
        self.integ.add(np.array([1., 2., 3., 4.]), 0.5, 0)

    def test_round_trip_preserves_raw_average_and_metadata(self):
        path = self.store.save(self.cfg, self.integ, {"dish_az_deg": 180}, "new_pointing", "start")
        spectrum, meta = self.store.read(path)
        np.testing.assert_array_equal(spectrum, self.integ.avg)
        self.assertEqual(meta["reason"], "new_pointing")
        self.assertTrue(meta["synthetic"])
        self.assertEqual(meta["spectrum_count"], 1)
        self.assertEqual(meta["elapsed_integration_s"], 0.5)

    def test_checkpoint_and_final_file(self):
        self.store.save(self.cfg, self.integ, {}, "checkpoint", "start", checkpoint=True)
        self.assertTrue(self.store.checkpoint.exists())
        self.store.save(self.cfg, self.integ, {}, "receiver_stop", "start")
        self.store.clear_checkpoint()
        self.assertFalse(self.store.checkpoint.exists())
        self.assertEqual(len(list(Path(self.temp.name).glob("observation_*.npz"))), 1)

    def test_invalid_file_rejected(self):
        path = Path(self.temp.name) / "bad.npz"
        path.write_bytes(b"bad")
        with self.assertRaises(Exception):
            self.store.read(path)

    def test_distinct_observations_are_not_overwritten(self):
        first = self.store.save(self.cfg, self.integ, {}, "reset", "start")
        second = self.store.save(self.cfg, self.integ, {}, "stop", "start")
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())


if __name__ == "__main__":
    unittest.main()
