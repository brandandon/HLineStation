"""Mandatory GUI smoke test; do not skip when Qt is unavailable."""
import os
import tempfile
import unittest
import pytest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip("PySide6", reason="Run in mandatory Qt CI job")
from PySide6.QtWidgets import QApplication, QMessageBox
from hline.app import MainWindow
from hline import config


class Patch05QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_main_window_opens_in_simulator_mode_without_hardware(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = dict(config.DEFAULTS, autostart=False, source='simulator',
                       observation_dir=str(Path(td)/'observations'))
            with patch('hline.app.config.load', return_value=cfg), \
                 patch('hline.app.user_dir', return_value=td), \
                 patch('hline.app.config.save'):
                window = MainWindow(demo=True)
                try:
                    self.assertEqual(window.observations.root, Path(td)/'observations')
                    self.assertIsNone(window.rx)
                finally:
                    window.close()

    def test_failed_settings_write_warns_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = dict(config.DEFAULTS, autostart=False, source='simulator',
                       observation_dir=str(Path(td)/'observations'))
            with patch('hline.app.config.load', return_value=cfg), \
                 patch('hline.app.user_dir', return_value=td), \
                 patch('hline.app.config.save', side_effect=OSError('permission denied')), \
                 patch.object(QMessageBox, 'warning') as warning:
                window = MainWindow(demo=True)
                try:
                    self.assertFalse(window._save())
                    self.assertIn('permission denied', window.last_save_error)
                    self.assertTrue(warning.called)
                finally:
                    window.close()


    def test_info_panel_refresh_handles_save_status_and_html_escaping(self):
        """AT-01: the information panel must refresh before and after saving."""
        with tempfile.TemporaryDirectory() as td:
            cfg = dict(config.DEFAULTS, autostart=False, source='simulator',
                       observation_dir=str(Path(td) / 'observations'))
            with patch('hline.app.config.load', return_value=cfg), \
                 patch('hline.app.user_dir', return_value=td), \
                 patch('hline.app.config.save'):
                window = MainWindow(demo=True)
                try:
                    # The initial state must not need a previous observation.
                    window.last_save = None
                    window.last_save_error = None
                    window._update_info()
                    self.assertIn('Last saved: not yet', window.info.text())

                    # The original defect was triggered after the first save.
                    window.last_save = ('2026-11-27T00:35:59Z', 'observation_<test>&.npz')
                    window._update_info()
                    display = window.info.text()
                    self.assertIn('Last saved:', display)
                    self.assertIn('observation_&lt;test&gt;&amp;.npz', display)
                    self.assertNotIn('observation_<test>&.npz', display)

                    # A storage warning must also be safely escaped.
                    window.last_save_error = 'Could not save <file> & recovery'
                    window._update_info()
                    self.assertIn('Could not save &lt;file&gt; &amp; recovery', window.info.text())

                    # No successful save but an outstanding error is also valid.
                    window.last_save = None
                    window._update_info()
                    self.assertIn('Last saved: not yet', window.info.text())
                    self.assertIn('WARNING:', window.info.text())
                finally:
                    window.close()

if __name__ == '__main__':
    unittest.main()
