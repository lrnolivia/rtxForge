"""An installed game is judged in the mode it runs, not the default for new installs."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / 'scripts'), str(REPO / 'engine/tests')]
import desktop_service
import discovery
import engine_bridge
from test_v13_core_hardening import load_engine


class InstalledModeVerdictTest(unittest.TestCase):
    def scan(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            engine = load_engine()
            engine.STATE_ROOT = root / 'state'
            target = root / 'Game'
            target.mkdir()
            (target / 'Game.exe').write_bytes(b'MZfixture')
            (target / 'nvngx_dlss.dll').write_bytes(b'MZdlss')
            ini = target / 'OptiScaler.ini'
            ini.write_text('[DlssNr]\nEnabled=true\n')
            engine.state_dir_for(target).mkdir(parents=True)
            engine.save_json_atomic(engine.baseline_path(target), {
                'schema': 13, 'status': 'active', 'target_dir': str(target), 'originals': {},
                'managed_paths': ['OptiScaler.ini'], 'history': [],
                'current': {'feature_mode': mode, 'provider_id': 'y4my',
                            'installed_hashes': {'OptiScaler.ini': engine.sha256_file(ini)}}})

            def inspect(game):
                game.exe = str(target / 'Game.exe')
                game.upscalers = [str(target / 'nvngx_dlss.dll')]
                return game

            service = desktop_service.DesktopService.__new__(desktop_service.DesktopService)
            service.config = {}
            with (patch.object(engine_bridge, 'module', return_value=engine),
                  patch.object(desktop_service.library_media, 'load_settings', return_value={}),
                  patch.object(discovery, 'inspect_game', side_effect=inspect)):
                return service.scan(None, [str(target)])[0]

    def test_nr_only_install_without_frame_generation_is_not_unsupported(self):
        row = self.scan('nr-only')
        self.assertTrue(row['installed'])
        self.assertTrue(row['native_dlss'])
        self.assertFalse(row['native_dlssg'])
        self.assertEqual(row['blocked'], '')

    def test_nr_mfg_install_still_needs_native_frame_generation(self):
        self.assertEqual(self.scan('nr-mfg')['blocked'], 'No native DLSS-G detected')


if __name__ == '__main__':
    unittest.main()
