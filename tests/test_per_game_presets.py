"""Disposable real reset + fresh-scan regression. No live games or repository writes."""
import pathlib
import sys
import tempfile
from unittest.mock import patch

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'scripts'), str(REPO / 'engine/tests')]
import desktop_service
import engine_bridge
import discovery
from test_v13_core_hardening import load_engine


def test_independent_per_game_presets():
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        engine = load_engine()
        engine.STATE_ROOT = root / 'state'
        pairs = []
        for name in ('A', 'B'):
            target = root / name
            target.mkdir()
            exe = target / 'Game.exe'
            exe.write_bytes(b'MZfixture')
            ini = target / 'OptiScaler.ini'
            ini.write_text(
                '[DlssNr]\nEnabled=true\nIntensity=2.0\nSkinStructure=2.0\n'
                '[Sharpness]\nSharpness=0.5\n'
                '[DLSSG]\nOverrideInterpolationCount=auto\n'
            )
            game = engine.Game('', name, target, 'Folder', exe=exe, target_dir=target)
            baseline = {
                'schema': 13,
                'status': 'active',
                'target_dir': str(target),
                'originals': {},
                'managed_paths': ['OptiScaler.ini'],
                'history': [],
                'current': {
                    'feature_mode': 'nr-mfg',
                    'provider_id': 'y4my',
                    'installed_hashes': {'OptiScaler.ini': engine.sha256_file(ini)},
                },
            }
            engine.state_dir_for(target).mkdir(parents=True)
            engine.save_json_atomic(engine.baseline_path(target), baseline)
            row = {
                'game': str(target), 'exe': 'Game.exe', 'name': name,
                'source': 'Folder', 'installed': True,
            }
            pairs.append((game, row))

        service = desktop_service.DesktopService.__new__(desktop_service.DesktopService)
        service.config = {}
        defaults = {
            'runtime_provider': 'y4my', 'nr_strength': 2.0,
            'sharpening_strength': 0.5, 'mfg_multiplier': 'auto',
        }

        def inspect(game):
            game.exe = str(pathlib.Path(game.root) / 'Game.exe')
            game.upscalers = []
            return game

        def resolve_game(_engine, row):
            return next(game for game, original in pairs if original['game'] == row['game'])

        with (
            patch.object(engine_bridge, 'module', return_value=engine),
            patch.object(engine_bridge, 'game', side_effect=resolve_game),
            patch.object(desktop_service.library_media, 'load_settings', side_effect=lambda _config: dict(defaults)),
            patch.object(engine, '_running_processes_under_root', return_value=[]),
            patch.object(discovery, 'inspect_game', side_effect=inspect),
            patch.object(desktop_service.library_media, 'save_settings') as save,
        ):
            requests = [
                {'nr_strength': 1.2, 'sharpening_strength': 0.3, 'mfg_multiplier': 4},
                {'nr_strength': 0.7, 'sharpening_strength': 0.8, 'mfg_multiplier': 6},
            ]
            for (_, row), values in zip(pairs, requests):
                other_files = {
                    other.root / 'OptiScaler.ini': (other.root / 'OptiScaler.ini').read_bytes()
                    for other, other_row in pairs if other_row['game'] != row['game']
                }
                review = service.prepare([row], 'mfg-only', 'reset', visual_settings=values)
                assert not review['blocked'], review['blocked']
                assert len(review['plans']) == 1
                assert 'save_defaults' not in review
                service.execute(review)
                for path, before in other_files.items():
                    assert path.read_bytes() == before, path

            fresh = service.scan(None, [str(game.root) for game, _ in pairs])
            actual = [
                (row['name'], row['nr_strength'], row['sharpening_strength'], row['mfg_multiplier'])
                for row in fresh
            ]
            assert actual == [('A', 1.2, 0.3, 4), ('B', 0.7, 0.8, 6)], actual
            assert all(row['feature_mode'] == 'nr-mfg' for row in fresh)
            save.assert_not_called()
            assert defaults == {
                'runtime_provider': 'y4my', 'nr_strength': 2.0,
                'sharpening_strength': 0.5, 'mfg_multiplier': 'auto',
            }
            print('PASS', actual, 'global saves:', save.call_count)


if __name__ == '__main__':
    test_independent_per_game_presets()
