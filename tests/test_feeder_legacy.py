"""Exercise architecture-specific Feeder deploy, drift refusal and exact restore."""
import copy
import json
from pathlib import Path
import struct
import sys
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import feeder_legacy as legacy
import feeder_provider as feeder
import transactions as t
from tests import test_feeder_provider as fixtures


def pe(machine, suffix=b''):
    data = bytearray(fixtures.pe(suffix))
    struct.pack_into('<H', data, 68, machine)
    return bytes(data)


class LegacyFeederTest(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.FeederTest()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.e = self.case.e
        self.settings = self.case.settings
        original = legacy.lock()
        assets = {}
        data = {}
        for name, spec in original['assets'].items():
            data[name] = (pe(spec['machine'], name.encode()) if spec.get('machine') else
                          b'Version=0x287\n[General]\nOutputAPI=bestavailable\n[Glide]\nVideoCard=voodoo_2\n[DirectX]\nVideoCard=internal3D\nVRAM=256\nDisableAndPassThru=false\ndgVoodooWatermark=true\n')
            assets[name] = spec | {'sha256': t.sha(data[name]), 'size': len(data[name])}
        self.spec = original | {'assets': assets}
        self.asset_data = data
        replacement = patch.object(legacy, 'lock', lambda: copy.deepcopy(self.spec))
        replacement.start(); self.addCleanup(replacement.stop)
        folder = self.case.source / 'legacy'
        folder.mkdir()
        for name, contents in data.items():
            (folder / name).write_bytes(contents)

    def game(self, recipe):
        row = self.case.game(recipe)
        bits, api = recipe.split('-')
        (Path(row['game']) / row['exe']).write_bytes(pe(0x14c if bits == 'x86' else 0x8664, api.encode()))
        self.e.pe_imported_dlls = lambda exe: {api + '.dll'}
        return row

    def prepare(self, row, operation='install', **settings):
        return feeder.prepare({}, [row], 'nr-only', operation, self.settings | settings, self.e)

    def test_all_recipes_deploy_correct_architectures_preserve_tuning_and_restore(self):
        for recipe in sorted(legacy.RECIPES):
            with self.subTest(recipe=recipe):
                row = self.game(recipe)
                directory = Path(row['game'])
                before = self.case.files(row)
                scan = feeder.expand_rows(self.e, [row | {'native_dlss': False}])[0]
                self.assertTrue(scan['feeder_available'])
                self.assertIn('experimental', scan['nr_route_note'])
                review = self.prepare(row)
                self.assertFalse(review['blocked'], review['blocked'])
                self.assertEqual(self.case.files(row), before, 'review wrote game files')
                feeder.execute(review)
                loader = directory / 'dxgi.dll'
                self.assertEqual(legacy.machine(loader), 0x14c if recipe.startswith('x86') else 0x8664)
                if legacy.helper(recipe):
                    self.assertTrue((directory / 'host64/dlss5-feed-host64.exe').is_file())
                    self.assertEqual(legacy.machine(directory / 'host64/dxgi.dll'), 0x8664)
                    self.assertFalse((directory / 'renodx-dlss5.addon64').exists())
                    self.assertFalse((directory / 'nvngx_dlssnr.dll').exists())
                self.assertEqual(feeder.inspect(self.e, row)['nr_runtime']['version'], '310.9.16.0')
                self.assertTrue(feeder.inspect(self.e, row)['nr_enabled'], 'consumer and technique were checked in different processes')
                control = legacy.runtime(directory, recipe) / 'ReShade.ini'
                text = control.read_text()
                self.assertEqual(t.ini(text)['RenoDX.DLSS5']['NeuralUplift'], '1')
                control.write_text(text + '\n[Depth fixture]\nSelected=keep\n')
                feeder.execute(self.prepare(row, 'apply', feature_controls={'intensity': .75}))
                self.assertEqual(t.ini(control.read_text())['RenoDX.DLSS5']['NRIntensity'], '0.75')
                self.assertIn('Selected=keep', control.read_text())
                if recipe.endswith('d3d9'):
                    wrapper = (directory / 'dgVoodoo.conf').read_text()
                    self.assertIn('OutputAPI=d3d11_fl11_0', wrapper)
                    self.assertIn('VRAM=1024', wrapper)
                    self.assertIn('VideoCard=voodoo_2', wrapper, 'changed unrelated Glide profile')
                feeder.execute(self.prepare(row, 'uninstall'))
                self.assertEqual(self.case.files(row), before)
                self.assertEqual(feeder.state(self.e, directory)['status'], 'restored')
                if legacy.helper(recipe):
                    self.assertFalse((directory / 'host64').exists(), 'restore left an empty helper directory that blocks reinstall')
                feeder.execute(self.prepare(row))
                feeder.execute(self.prepare(row, 'uninstall'))
                self.assertEqual(self.case.files(row), before)

    def test_changed_executable_or_payload_refuses_before_first_write(self):
        row = self.game('x86-d3d10')
        before = self.case.files(row)
        review = self.prepare(row)
        (Path(row['game']) / row['exe']).write_bytes(pe(0x14c, b'changed'))
        with self.assertRaisesRegex(t.Refusal, 'executable changed'):
            feeder.execute(review)
        self.assertEqual(set(self.case.files(row)), set(before))

    def test_manual_exe_rechecks_feeder_when_other_binaries_ship_dlss(self):
        row = self.game('x86-d3d9') | {'native_dlss': True, 'executable_selected': True}
        found = feeder.expand_rows(self.e, [row])[0]
        self.assertTrue(found['feeder_available'])
        self.assertEqual(found['install_provider'], 'feeder')
        self.assertFalse(found['blocked'])

    def test_foreign_helper_and_anticheat_are_not_adopted(self):
        row = self.game('x86-d3d9')
        directory = Path(row['game'])
        (directory / 'host64').mkdir()
        (directory / 'host64/save.dat').write_bytes(b'keep')
        before = self.case.files(row)
        self.assertTrue(self.prepare(row)['blocked'])
        self.assertEqual(self.case.files(row), before)
        self.assertTrue(self.prepare(row | {'anti_cheat': True})['blocked'])

    def test_download_checks_archive_members_and_keeps_the_last_verified_stack(self):
        for index, source in enumerate(self.spec['sources']):
            archive = self.case.root / f'support-{index}.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                for member, name in source['members'].items():
                    zipped.writestr(member, self.asset_data[name])
            source.update(download_url=archive.as_uri(), archive_name=archive.name,
                          archive_size=archive.stat().st_size, archive_sha256=t.digest(archive))
        result = legacy.download_assets(self.e)
        self.assertEqual(set(result['files']), set(self.spec['assets']))
        before = legacy.store_path(self.e).read_bytes()
        source = self.spec['sources'][0]
        archive = self.case.root / 'changed-support.zip'
        with zipfile.ZipFile(archive, 'w') as zipped:
            for member, name in source['members'].items():
                zipped.writestr(member, self.asset_data[name].replace(b'MZ', b'ZZ', 1))
        source.update(download_url=archive.as_uri(), archive_name=archive.name,
                      archive_size=archive.stat().st_size, archive_sha256=t.digest(archive))
        with self.assertRaisesRegex(t.Refusal, 'support file changed'):
            legacy.download_assets(self.e)
        self.assertEqual(legacy.store_path(self.e).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
