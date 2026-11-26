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

if __name__ == '__main__':
    unittest.main()
