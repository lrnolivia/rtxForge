"""NR add-on install and restore against disposable game folders. No downloads, no GPU."""
import contextlib
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nr_install
import renodx_hdr as hdr
import transactions as t

COMBO = {'environment': {'addon': 'lecram', 'build': '10.8', 'model': 'new', 'values': {'structure': 0.4, 'character': 0.1}},
         'character': {'addon': 'shortfuse', 'model': 'new', 'values': {'character': 0.68}}}


def pe(tag=b''):
    data = bytearray(256); data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64); data[64:70] = b'PE\0\0d\x86'
    return bytes(data) + tag


class Engine:
    def __init__(self):
        self.baseline = None; self.imports = {'dxgi.dll', 'd3d12.dll'}
    def _running_processes_under_root(self, root): return []
    def load_baseline(self, path, **kwargs): return self.baseline
    def pe_imported_dlls(self, path): return self.imports
    def mutation_lock(self): return contextlib.nullcontext()


class NrInstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.game = base / 'game'; self.game.mkdir(); self.state = base / 'state'; self.state.mkdir()
        (self.game / 'Game.exe').write_bytes(pe()); (self.game / 'save.dat').write_bytes(b'save')
        self.row = {'name': 'A Game', 'game': str(self.game), 'exe': 'Game.exe', 'native_dlss': True, 'source': 'Steam'}
        self.engine = Engine(); self.host = pe(b'ReShade'); self.model = pe(b'NR model')
        self.addons = {'renodx-dlss5.addon64': pe(b'Lecram'), 'renodx-dlss.addon64': pe(b'ShortFuse')}
        for target, name, value in [
            (hdr, '_eligible', lambda config, row: (self.game, self.game / 'Game.exe', None, self.engine)),
            (hdr.state_storage, 'storage', lambda config, required=0: self.state),
            (hdr, 'WINDOWS', True),
            (nr_install, '_fetch', lambda config, archive, name: b'verified archive'),
            (nr_install, '_members', lambda data, pins: {m: self.addons[Path(m).name] for m in pins}),
            (nr_install, '_model', lambda data, pin: self.model),
            (nr_install, '_reshade_host', lambda config, arch: self.host),
        ]:
            p = patch.object(target, name, value); p.start(); self.addCleanup(p.stop)

    def files(self):
        return {p.relative_to(self.game).as_posix(): p.read_bytes() for p in self.game.rglob('*') if p.is_file()}

    def test_install_then_restore_returns_the_original_folder(self):
        before = self.files()
        review = nr_install.prepare({}, self.row, COMBO)
        self.assertEqual(self.files(), before, 'review changed the game')
        self.assertIn('not been verified', ' '.join(review['notes']))
        nr_install.apply({}, review)
        self.assertEqual((self.game / 'dxgi.dll').read_bytes(), self.host)
        self.assertEqual((self.game / 'nvngx_dlssnr.dll').read_bytes(), self.model)
        for name, data in self.addons.items():
            self.assertEqual((self.game / name).read_bytes(), data)
        ini = t.ini((self.game / 'ReShade.ini').read_text(encoding='utf-8'))
        self.assertEqual(ini['RenoDX.DLSS5']['ForeignNr'], 'observe')
        self.assertEqual((ini['RenoDX.DLSS5']['NRLocalStructure'], ini['RENODX-DLSS']['DirectNeuralRenderingSkinStructureStrength']), ('0.40', '0.68'))
        self.assertTrue(nr_install.status(self.row)['installed'])
        with self.assertRaisesRegex(t.Refusal, 'already installed'):
            nr_install.prepare({}, self.row, COMBO)
        nr_install.apply({}, nr_install.prepare_remove({}, self.row))
        self.assertEqual(self.files(), before)
        self.assertFalse(nr_install.status(self.row)['installed'])

    def test_restore_keeps_the_users_reshade_settings_and_changed_files(self):
        (self.game / 'ReShade.ini').write_text('[GENERAL]\nPresetPath=.\\Mine.ini\n[RenoDX.DLSS5]\nNRLocalStructure=0.80\n', encoding='utf-8')
        nr_install.apply({}, nr_install.prepare({}, self.row, COMBO))
        text = (self.game / 'ReShade.ini').read_text(encoding='utf-8')
        (self.game / 'ReShade.ini').write_text(text + '[OVERLAY]\nTutorialProgress=4\n', encoding='utf-8')
        (self.game / 'renodx-dlss.addon64').write_bytes(pe(b'replaced by the user'))
        review = nr_install.prepare_remove({}, self.row)
        self.assertIn('renodx-dlss.addon64', ' '.join(review['notes']))
        nr_install.apply({}, review)
        ini = t.ini((self.game / 'ReShade.ini').read_text(encoding='utf-8'))
        self.assertEqual(ini['RenoDX.DLSS5']['NRLocalStructure'], '0.80', 'the earlier value came back')
        self.assertNotIn('ForeignNr', ini['RenoDX.DLSS5'])
        self.assertNotIn('DirectNeuralRenderingSkinStructureStrength', ini['RENODX-DLSS'] if ini.has_section('RENODX-DLSS') else {})
        self.assertEqual((ini['GENERAL']['PresetPath'], ini['OVERLAY']['TutorialProgress']), ('.\\Mine.ini', '4'))
        self.assertEqual((self.game / 'renodx-dlss.addon64').read_bytes(), pe(b'replaced by the user'))
        self.assertFalse((self.game / 'nvngx_dlssnr.dll').exists())

    def test_optiscaler_must_have_its_own_nr_off(self):
        proxy = self.game / 'dxgi.dll'; proxy.write_bytes(pe(b'OptiScaler'))
        (self.game / 'OptiScaler.ini').write_text('[Plugins]\nLoadReShade=false\n', encoding='utf-8')
        self.engine.baseline = {'status': 'active', 'current': {'provider_id': 'skynizz', 'proxy': 'dxgi.dll',
                                'feature_mode': 'nr-mfg', 'installed_hashes': {'dxgi.dll': t.digest(proxy)}}}
        with self.assertRaisesRegex(t.Refusal, 'MFG Only'):
            nr_install.prepare({}, self.row, COMBO)
        self.engine.baseline['current']['feature_mode'] = 'mfg-only'
        nr_install.apply({}, nr_install.prepare({}, self.row, COMBO))
        self.assertEqual((self.game / 'dxgi.dll').read_bytes(), pe(b'OptiScaler'), 'OptiScaler keeps its loader')
        self.assertIn('LoadReShade=true', (self.game / 'OptiScaler.ini').read_text(encoding='utf-8'))
        self.assertTrue((self.game / 'ReShade64.dll').is_file(), 'OptiScaler needs ReShade64.dll to load ReShade')
        nr_install.apply({}, nr_install.prepare_remove({}, self.row))
        self.assertIn('LoadReShade=false', (self.game / 'OptiScaler.ini').read_text(encoding='utf-8'))
        self.assertFalse((self.game / 'ReShade64.dll').exists())

    def test_another_tools_model_or_loader_is_never_overwritten(self):
        (self.game / 'nvngx_dlssnr.dll').write_bytes(pe(b'someone else'))
        with self.assertRaisesRegex(t.Refusal, 'Another tool owns nvngx_dlssnr.dll'):
            nr_install.prepare({}, self.row, COMBO)
        with self.assertRaisesRegex(t.Refusal, 'Feeder NR'):
            nr_install.prepare({}, dict(self.row, native_dlss=False), {'environment': {'addon': 'lecram'}})

    def test_gitc_keeps_its_model_in_its_own_folder(self):
        self.addons.update({'gitc-uplift.addon64': pe(b'GITC'), 'gitc-uplift.addon32': b'32', 'gitc-uplift-helper64.exe': pe(b'helper'),
                            'Uplift.fx': b'fx', 'UpliftMask.fx': b'mask', 'LICENSE': b'MIT', 'THIRD_PARTY_NOTICES.md': b'notices'})
        nr_install.apply({}, nr_install.prepare({}, self.row, {'environment': {'addon': 'gitc'}}))
        self.assertEqual((self.game / 'GITC-Uplift/nvngx_dlssnr.dll').read_bytes(), self.model)
        self.assertFalse((self.game / 'nvngx_dlssnr.dll').exists())
        self.assertTrue((self.game / 'reshade-shaders/Shaders/UpliftMask.fx').is_file())
        self.assertTrue((self.game / 'rtxForge-NR-Licenses/gitc-LICENSE').is_file())

    def test_archive_members_and_models_are_checked(self):
        blob = pe(b'addon')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('renodx-dlss5.addon64', blob)
        data = buffer.getvalue()
        patch.stopall()
        good = nr_install._members(data, {'renodx-dlss5.addon64': {'sha256': t.sha(blob), 'size': len(blob)}})
        self.assertEqual(good['renodx-dlss5.addon64'], blob)
        for pins in ({'renodx-dlss5.addon64': {'sha256': '0' * 64}}, {'missing.addon64': {'sha256': t.sha(blob)}}):
            with self.subTest(pins=pins), self.assertRaises(t.Refusal):
                nr_install._members(data, pins)
        small = io.BytesIO()
        with zipfile.ZipFile(small, 'w') as archive:
            archive.writestr('bin/nvngx_dlssnr.dll', blob)
        with self.assertRaisesRegex(t.Refusal, 'valid Windows library'):
            nr_install._model(small.getvalue(), {})


if __name__ == '__main__':
    unittest.main()
