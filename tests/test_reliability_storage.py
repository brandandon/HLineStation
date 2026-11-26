"""Storage fault-injection checks; no SDR or Qt installation required."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from hline.observations import ObservationStore, utc_stamp
from hline.processing import Integrator


class ReliabilityStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ObservationStore(self.temp.name)
        self.cfg = {"source": "simulator", "nfft": 4, "integration_s": 0,
                    "center_mhz": 1420.40575, "sample_rate": 2400000, "gain": 40.2}
        self.integ = Integrator()
        self.integ.add(np.array([1., 2., 3., 4.]), 0.25, 0)

    def test_failed_checkpoint_replace_preserves_prior_checkpoint(self):
        self.store.save(self.cfg, self.integ, {}, "checkpoint", utc_stamp(), checkpoint=True)
        old = self.store.checkpoint.read_bytes()
        self.integ.add(np.array([5., 6., 7., 8.]), 0.25, 0)
        with patch("hline.observations.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.store.save(self.cfg, self.integ, {}, "checkpoint", utc_stamp(), checkpoint=True)
        self.assertEqual(self.store.checkpoint.read_bytes(), old)
        self.assertFalse(list(Path(self.temp.name).glob(".hline-*.npz")))

    def test_interruption_reason_is_preserved(self):
        path = self.store.save(self.cfg, self.integ, {}, "receiver_interrupted", utc_stamp())
        power, metadata = self.store.read(path)
        np.testing.assert_array_equal(power, self.integ.avg)
        self.assertEqual(metadata["reason"], "receiver_interrupted")
        self.assertEqual(metadata["elapsed_integration_s"], 0.25)

    def test_repeated_final_saves_keep_separate_files(self):
        a = self.store.save(self.cfg, self.integ, {}, "receiver_interrupted", utc_stamp())
        b = self.store.save(self.cfg, self.integ, {}, "receiver_stop", utc_stamp())
        self.assertNotEqual(a, b)
        self.assertTrue(a.exists() and b.exists())


if __name__ == "__main__":
    unittest.main()
