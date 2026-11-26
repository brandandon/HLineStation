"""Patch 05 storage-transition, preferences and external-calibration regressions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hline import config
from hline.observations import ObservationStore
from hline.storage_migration import copy_legacy_observations, migration_preflight


class Patch05Tests(unittest.TestCase):
    def test_preferences_replace_atomically(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'settings.json'
            target.write_text('{"original":true}', encoding='utf-8')
            with patch('hline.config._path', return_value=str(target)):
                config.save({'source': 'rtlsdr', 'gain': 36.4})
            self.assertEqual(json.loads(target.read_text())['gain'], 36.4)
            self.assertEqual(list(Path(td).glob('.hline-settings-*.tmp')), [])

    def test_preferences_disk_failure_preserves_previous_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'settings.json'
            original = b'{"safe":"original"}'
            target.write_bytes(original)
            with patch('hline.config._path', return_value=str(target)), patch(
                    'hline.config.os.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    config.save({'safe': 'modified'})
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(list(Path(td).glob('.hline-settings-*.tmp')), [])

    def test_unserializable_settings_preserve_prior_file(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'settings.json'
            target.write_text('previous')
            with patch('hline.config._path', return_value=str(target)):
                with self.assertRaises(TypeError):
                    config.save({'bad': object()})
            self.assertEqual(target.read_text(), 'previous')

    def test_folder_change_creates_distinct_session_and_preserves_old(self):
        with tempfile.TemporaryDirectory() as td:
            old = ObservationStore(Path(td) / 'old')
            legacy = old.root / 'observation_existing.npz'
            legacy.write_bytes(b'original')
            next_store = ObservationStore.prepare_directory_change(old, Path(td) / 'new')
            self.assertNotEqual(next_store.session_id, old.session_id)
            self.assertEqual(next_store.root, Path(td) / 'new')
            self.assertEqual(legacy.read_bytes(), b'original')
            self.assertIs(ObservationStore.prepare_directory_change(old, old.root), old)

    def test_switch_blocks_pending_checkpoint_in_old_or_new_directory(self):
        with tempfile.TemporaryDirectory() as td:
            old = ObservationStore(Path(td) / 'old')
            dest = Path(td) / 'new'
            dest.mkdir()
            old.checkpoint.write_bytes(b'checkpoint')
            with self.assertRaisesRegex(RuntimeError, 'current folder'):
                ObservationStore.prepare_directory_change(old, dest)
            # Active acquisition may finish its checkpoint into its original folder.
            candidate = ObservationStore.prepare_directory_change(old, dest, active_segment=True)
            self.assertEqual(candidate.root, dest)
            old.checkpoint.unlink()
            (dest / 'recovery_checkpoint.npz').write_bytes(b'existing')
            with self.assertRaisesRegex(RuntimeError, 'destination'):
                ObservationStore.prepare_directory_change(old, dest)

    def test_external_calibration_catalog_migrates_copy_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, dest, cal = root/'observations', root/'destination', root/'appdata'/'calibrations'
            src.mkdir(); cal.mkdir(parents=True)
            (src/'observation_001.npz').write_bytes(b'spectrum')
            (cal/'ref1.npz').write_bytes(b'calibration')
            plan = migration_preflight(src, dest, calibration_source=cal)
            self.assertEqual(set(plan['copy']), {'observation_001.npz', 'calibrations/ref1.npz'})
            self.assertEqual(copy_legacy_observations(src, dest, calibration_source=cal), 2)
            self.assertEqual((dest/'calibrations/ref1.npz').read_bytes(), b'calibration')
            self.assertEqual((cal/'ref1.npz').read_bytes(), b'calibration')
            self.assertEqual(copy_legacy_observations(src, dest, calibration_source=cal), 0)

    def test_calibration_collision_preflights_before_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, dest, cal = root/'old', root/'new', root/'external'
            src.mkdir(); dest.mkdir(); cal.mkdir()
            (src/'observation_a.npz').write_bytes(b'a')
            (cal/'c.npz').write_bytes(b'new')
            (dest/'calibrations').mkdir()
            (dest/'calibrations'/'c.npz').write_bytes(b'old')
            plan = migration_preflight(src, dest, calibration_source=cal)
            self.assertEqual(plan['conflicts'], ['calibrations/c.npz'])
            with self.assertRaises(FileExistsError):
                copy_legacy_observations(src, dest, calibration_source=cal)
            self.assertFalse((dest/'observation_a.npz').exists())


if __name__ == '__main__':
    unittest.main()
