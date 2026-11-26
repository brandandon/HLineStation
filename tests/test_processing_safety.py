"""Regression coverage for baseline safety and unsupported local-gas distances."""
import unittest

import numpy as np

from hline.processing import Integrator, describe_peaks, process


class ProcessingSafetyTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "mode": "baseline", "sample_rate": 2.048e6,
            "band_use_fraction": 0.76, "line_window_kms": 150,
            "baseline_order": 2, "dc_notch": False,
            "remove_spikes": False, "smooth_kms": 0,
            "show_peaks": True,
        }

    def test_one_sided_baseline_falls_back_without_false_peaks(self):
        n = 4096
        # As in the two RTL-SDR failures, only one receiver band edge has
        # frequencies outside the exclusion window.
        v = np.linspace(-100, 300, n)
        f = np.linspace(1420.0, 1421.0, n)
        p = 0.1 + 0.015 * np.linspace(-1, 1, n) ** 2
        integ = Integrator()
        integ.avg = p
        result = process(self.cfg, integ, f, v, False)
        self.assertTrue(result["baseline_failed"])
        self.assertTrue(result["fallback"])
        self.assertEqual(result["mode"], "raw")
        self.assertEqual(result["peaks"], [])
        self.assertTrue(np.isfinite(result["y"]).all())
        self.assertLess(np.max(np.abs(result["y"])), 20)

    def test_two_sided_flat_spectrum_is_numerically_safe(self):
        n = 4096
        v = np.linspace(-600, 600, n)
        f = np.linspace(1420.0, 1421.0, n)
        integ = Integrator()
        integ.avg = np.full(n, 0.1)
        result = process(self.cfg, integ, f, v, False)
        self.assertFalse(result["baseline_failed"])
        self.assertEqual(result["mode"], "baseline")
        self.assertTrue(np.isfinite(result["y"]).all())
        self.assertLess(np.max(np.abs(result["y"])), 1e-5)

    def test_near_zero_or_negative_baseline_cannot_explode(self):
        n = 4096
        v = np.linspace(-600, 600, n)
        f = np.linspace(1420.0, 1421.0, n)
        x = np.linspace(-1, 1, n)
        integ = Integrator()
        integ.avg = 0.01 + 0.2 * x ** 2
        result = process(self.cfg, integ, f, v, False)
        self.assertTrue(np.isfinite(result["y"]).all())
        self.assertLess(np.max(np.abs(result["y"])), 1e6)

    def test_local_velocity_has_no_invented_distance(self):
        cloud = describe_peaks(30.0, 0.0, [(4.0, 5.0)])[0]
        self.assertTrue(cloud["local"])
        self.assertEqual(cloud["d"], [])


if __name__ == "__main__":
    unittest.main()
