"""Background calibration identity, legacy compatibility and atomic persistence."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from hline.processing import Integrator


class BackgroundSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "background.npz"
        self.user_dir = patch("hline.processing.user_dir", return_value=self.tmp.name)
        self.user_dir.start()
        self.addCleanup(self.user_dir.stop)
        self.key = ("rtlsdr", 0, 1420.40575, 4, 2400000.0, "40.2", 0, False)
        self.psd = np.array([1., 2., 3., 4.])

    def test_matching_calibration_loads_and_survives_restart(self):
        i = Integrator()
        i.set_background(self.psd, self.key)
        self.assertTrue(i.background_valid(self.key))
        other = Integrator()
        self.assertTrue(other.background_valid(self.key))
        np.testing.assert_array_equal(other.background, self.psd)

    def test_gain_or_source_change_invalidates_calibration(self):
        i = Integrator()
        i.set_background(self.psd, self.key)
        gain = list(self.key)
        gain[5] = "36.4"
        self.assertFalse(i.background_valid(tuple(gain)))
        source = list(self.key)
        source[0] = "simulator"
        self.assertFalse(i.background_valid(tuple(source)))
        self.assertTrue(self.path.exists())  # preserved, not deleted

    def test_legacy_three_field_background_never_reused_silently(self):
        np.savez(self.path, bg=self.psd, key=np.array([1420.40575, 2400000., 4.]))
        i = Integrator()
        self.assertFalse(i.background_valid(self.key))
        self.assertTrue(self.path.exists())

    def test_invalid_calibration_rejected_before_save(self):
        i = Integrator()
        with self.assertRaises(ValueError):
            i.set_background([1., float('nan'), 3., 4.], self.key)
        self.assertFalse(self.path.exists())

    def test_failed_atomic_save_preserves_previous_file_and_memory(self):
        i = Integrator()
        i.set_background(self.psd, self.key)
        prior = self.path.read_bytes()
        with patch("hline.processing.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                i.set_background([4., 3., 2., 1.], self.key)
        self.assertEqual(self.path.read_bytes(), prior)
        np.testing.assert_array_equal(i.background, self.psd)
        self.assertFalse(list(Path(self.tmp.name).glob('.hline-bg-*.npz')))


if __name__ == "__main__":
    unittest.main()
