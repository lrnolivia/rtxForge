import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('rtxforge_setup', ROOT / 'scripts/setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            'RTXFORGE_STATE_ROOT': str(self.root / 'state'),
            'XDG_DATA_HOME': str(self.root / 'data'),
        })
        self.env.start()
        self.config = {'storage': {'reserve_bytes': 0}}

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_fresh_setup_selects_dlss_unlocked_without_writing(self):
        settings, change = setup.selected_settings(self.config)
        self.assertEqual(settings['runtime_provider'], 'dlss-unlocked')
        self.assertEqual(settings['default_profile'], 'mfg-only')
        self.assertTrue(change)
        self.assertFalse((self.root / 'state').exists())

    def test_existing_settings_untouched_and_explicit_change_backed_up(self):
        path = setup.library_media.settings_path(self.config)
        path.parent.mkdir(parents=True)
        original = b'{"runtime_provider":"y4my","theme":"night","future_key":42}'
        path.write_bytes(original)
        settings, change = setup.selected_settings(self.config)
        setup.save_preferences(self.config, settings, change)
        self.assertEqual(path.read_bytes(), original)
        settings, change = setup.selected_settings(self.config, 'nr-only')
        setup.save_preferences(self.config, settings, change)
        saved = json.loads(path.read_text())
        self.assertEqual(saved['future_key'], 42)
        self.assertEqual(saved['theme'], 'night')
        self.assertEqual(saved['runtime_provider'], 'dlss-unlocked')
        self.assertEqual(next((self.root / 'state/setup-backups').iterdir()).read_bytes(), original)

    def test_corrupt_preferences_are_not_silently_reset(self):
        path = setup.library_media.settings_path(self.config)
        path.parent.mkdir(parents=True)
        path.write_text('{broken')
        with self.assertRaises(ValueError):
            setup.selected_settings(self.config)
        self.assertEqual(path.read_text(), '{broken')

    def test_host_failure_never_installs_or_downloads(self):
        with patch.object(setup.rtxforge, 'load_provider', return_value=self.config), \
             patch.object(setup, 'host_report', return_value={'ready': False, 'checks': [], 'note': 'fixture'}), \
             patch.object(setup.os, 'geteuid', return_value=1000), \
             patch.object(setup, 'prepare_runtime') as prepare, \
             patch.object(setup.desktop_install, 'install') as install:
            self.assertEqual(setup.main(['install']), 1)
            prepare.assert_not_called()
            install.assert_not_called()

    def test_failed_runtime_does_not_replace_application_or_preferences(self):
        with patch.object(setup.rtxforge, 'load_provider', return_value=self.config), \
             patch.object(setup, 'host_report', return_value={'ready': True, 'checks': [], 'note': 'fixture'}), \
             patch.object(setup.os, 'geteuid', return_value=1000), \
             patch.object(setup, 'prepare_runtime', side_effect=RuntimeError('bad archive')), \
             patch.object(setup.desktop_install, 'install') as install:
            self.assertEqual(setup.main(['install']), 1)
            install.assert_not_called()
            self.assertFalse((self.root / 'state').exists())

    def test_app_install_and_rollback_preserve_game_and_state_files(self):
        game = self.root / 'Game'
        game.mkdir()
        (game / 'save.dat').write_bytes(b'keep')
        first, second = self.root / 'first.AppImage', self.root / 'second.AppImage'
        first.write_bytes(b'first build')
        second.write_bytes(b'second build')
        with patch.object(setup.desktop_install.shutil, 'which', return_value=None):
            target = Path(setup.desktop_install.install_from(first))
            setup.desktop_install.install_from(second)
            self.assertEqual(target.read_bytes(), b'second build')
            setup.rollback_app()
            self.assertEqual(target.read_bytes(), b'first build')
            self.assertEqual(target.with_name('RTXForge.previous.AppImage').read_bytes(), b'second build')
        self.assertEqual((game / 'save.dat').read_bytes(), b'keep')
        self.assertFalse((self.root / 'state').exists())
        launcher = self.root / 'data/applications/io.github.lrnolivia.RTXForge.desktop'
        self.assertIn(str(target), launcher.read_text())

    def test_zip_provider_does_not_need_7zip(self):
        from types import SimpleNamespace
        with patch.object(setup.hardware.platform, 'system', return_value='Linux'), \
             patch.object(setup.hardware.platform, 'machine', return_value='x86_64'), \
             patch.object(setup.hardware.subprocess, 'run', return_value=SimpleNamespace(stdout='NVIDIA GeForce RTX 4070, 615.0, 12282\n')), \
             patch.object(setup.hardware.shutil, 'which', return_value=None):
            self.assertTrue(setup.hardware.detect()['ready'])


if __name__ == '__main__':
    unittest.main()
