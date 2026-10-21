"""Verified release identity and bounded archive policy; no game or network writes."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import skynizz_provider as provider
import package_catalog
import transactions


def pe():
    data = bytearray(128)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:70] = b'PE\0\0\x64\x86'
    return bytes(data)


TEMPLATE = b'[Upscalers]\nDx12Upscaler=auto\n[Log]\nLogToFile=auto\nLogLevel=auto\n[DlssNr]\nEnabled=auto\nCacheEnabled=auto\nPreSr=auto\nWorkingScale=auto\n'


def fixture(path, extra=None, omit=None):
    files = {'DLSS5-Optimised/OptiScaler.dll': pe(), 'DLSS5-Optimised/OptiScaler.ini': TEMPLATE,
             'DLSS5-Optimised/nvngx.dll_dlssnr.dll': pe(), 'DLSS5-Optimised/INSTALL.bat': b'never execute'}
    files.update(extra or {})
    if omit:
        files.pop(omit)
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in files.items():
            member = zipfile.ZipInfo('entry')
            member.filename = name
            archive.writestr(member, data)
    record = json.loads((ROOT / 'providers/lock.json').read_text())['skynizz']
    return dict(record, release_size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def bridge_fixture(path, sr_path=None):
    fixture(path)
    spec=json.loads((ROOT/'providers/skynizz-bridge/source.json').read_text())
    record={'variant':'nr-mfg-bridge','repo':'lrnolivia/rtxForge','tag':'v1.2.1','commit':'b'*40,
            'archive':'rtxForge-Skynizz-v1.2.1-MFG.zip','url':'bundled:providers/skynizz-bridge/rtxForge-Skynizz-v1.2.1-MFG.zip',
            'upstream':spec['upstream'],'mfg_source':spec['mfg_source'],'patch_sha256':spec['patch_sha256'],
            'bridge_id':spec['id'],'runtime_verified':False}
    if sr_path is not None:
        lock=json.loads((ROOT/'providers/lock.json').read_text())['skynizz']
        for component,(filename,_) in provider.PRODUCTION_RUNTIMES.items():
            target=sr_path if component=='sr_runtime' else sr_path.parent/('production-'+filename)
            target.write_bytes(pe()+('production-'+component+'-fixture').encode())
            record[component]=lock[component] | {'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                                               'release_size':target.stat().st_size}
    with zipfile.ZipFile(path,'a') as archive:
        archive.writestr('DLSS5-Optimised/rtxforge-bridge.json',json.dumps(record))
    return provider.validate_release(record | {'release_size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})


class SkynizzPolicyTest(unittest.TestCase):
    def test_full_controls_use_real_ini_keys_and_round_trip(self):
        from types import SimpleNamespace
        import importlib.util
        spec = importlib.util.spec_from_file_location('preset_engine', ROOT / 'engine/rtxengine.py')
        engine = importlib.util.module_from_spec(spec); sys.modules[spec.name] = engine
        # Only the real INI parser/writer is exercised here. Windows has no
        # fcntl; the native lifecycle suite supplies the actual locking adapter.
        if sys.platform == 'win32':
            with patch.dict(sys.modules, {'fcntl': SimpleNamespace()}): spec.loader.exec_module(engine)
        else: spec.loader.exec_module(engine)
        controls = {item['key']: item['values'][-1] if 'values' in item else item['max'] for item in provider.control_schema()}
        text = provider.apply_controls(engine, '[Unrelated]\nKeep=please\n', controls)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'OptiScaler.ini'; path.write_text(text, encoding='utf-8')
            self.assertEqual(provider.read_controls(path), controls)
        self.assertIn('Keep=please', text)
        self.assertIn('Shader=lcda', text)
        self.assertIn('OverrideInterpolationCount=5', text)
        self.assertIn('OverrideForceDMFG=true', text)
        nr_only = provider.apply_controls(engine, '[DLSSG]\nOverrideInterpolationCount=auto\n', controls, 'nr-only')
        self.assertIn('OverrideInterpolationCount=auto', nr_only)
        self.assertNotIn('OverrideForceDMFG', nr_only)
        mfg_only = provider.apply_controls(engine, '[DlssNr]\nEnabled=false\n', controls, 'mfg-only')
        self.assertIn('Enabled=false', mfg_only)
        for invalid in ({'colour': 4.1}, {'passes': 1.5}, {'intensity': float('nan')}, {'multiplier': 1}, {'file': 'anything'}, {'enabled': True}):
            with self.assertRaises(transactions.Refusal): provider.validate_controls(invalid)

        # The UI's Auto / Custom / Dynamic tabs write the same two settings as the game panel.
        for ratio, dynamic, expected in ((-1, 0, 'auto'), (2, 0, '1'), (5, 0, '4'), (6, 1, '5'), (0, 0, '0')):
            with self.subTest(ratio=ratio, dynamic=dynamic):
                values = {'multiplier': ratio, 'dynamic_mfg': dynamic}
                updated = provider.apply_controls(engine, text, values)
                self.assertIn('OverrideInterpolationCount=' + expected, updated)
                self.assertIn('OverrideForceDMFG=' + ('true' if dynamic else 'false'), updated)
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / 'OptiScaler.ini'; path.write_text(updated, encoding='utf-8')
                    installed = provider.read_controls(path)
                    for key, value in values.items(): self.assertEqual(installed[key], value)
        with self.assertRaisesRegex(transactions.Refusal, 'integrated MFG route'):
            provider.apply_controls(engine, text, {'dynamic_mfg': 1}, external_mfg=True)
        external = provider.apply_controls(engine, text, {'dynamic_mfg': 0, 'multiplier': 2}, external_mfg=True)
        self.assertEqual(external, text)
        with self.assertRaises(transactions.Refusal): provider.validate_controls({'dynamic_mfg': 2})

        # DLSS presets: a choice turns OptiScaler's override on; Game default hands it back to the game.
        self.assertRegex(text, r'(?ms)^\[DLSS\].*?^RenderPresetOverride=true.*?^RenderPresetForAll=13')
        self.assertRegex(text, r'(?ms)^\[DLSSD\].*?^RenderPresetOverride=true.*?^RenderPresetForAll=5')
        default = provider.apply_controls(engine, text, {'dlss_preset': 0, 'rr_preset': 0})
        self.assertRegex(default, r'(?ms)^\[DLSS\].*?^RenderPresetOverride=false.*?^RenderPresetForAll=auto')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'OptiScaler.ini'
            path.write_text(default, encoding='utf-8')
            self.assertEqual({k: provider.read_controls(path)[k] for k in ('dlss_preset', 'rr_preset')}, {'dlss_preset': 0, 'rr_preset': 0})
            # A preset chosen in OptiScaler's own menu that rtxForge does not list is left alone, not refused.
            path.write_text('[DLSS]\nRenderPresetOverride=true\nRenderPresetForAll=14\n', encoding='utf-8')
            self.assertNotIn('dlss_preset', provider.read_controls(path))
        with self.assertRaises(transactions.Refusal): provider.validate_controls({'dlss_preset': 14})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Hosted Windows runners can expose TEMP through an 8.3 alias.
        # Supply a canonical fixture path, as the real Windows storage adapter does.
        self.archive = Path(self.temp.name).resolve() / 'release.zip'

    def test_normalizes_only_required_files_and_records_exact_source(self):
        record = fixture(self.archive)
        data, meta = provider.load_payload(self.archive, record)
        self.assertEqual(set(data), {'dxgi.dll', 'OptiScaler.ini', 'nvngx.dll_dlssnr.dll'})
        self.assertEqual(meta['release']['sha256'], record['sha256'])
        self.assertFalse(meta['runtime_verified'])
        self.assertEqual(meta['files']['OptiScaler.dll'], hashlib.sha256(pe()).hexdigest())

    def test_archive_hash_and_required_forwarder(self):
        record = fixture(self.archive)
        self.archive.write_bytes(self.archive.read_bytes() + b'drift')
        with self.assertRaises(transactions.Refusal):
            provider.load_payload(self.archive, record)
        record = fixture(self.archive, omit='DLSS5-Optimised/nvngx.dll_dlssnr.dll')
        with self.assertRaisesRegex(transactions.Refusal, 'layout'):
            provider.load_payload(self.archive, record)

    def test_combined_payload_binds_source_and_patch_receipt(self):
        record=bridge_fixture(self.archive)
        data,meta=provider.load_payload(self.archive,record)
        self.assertEqual(meta['release']['variant'],'nr-mfg-bridge')
        self.assertEqual(set(data),set(provider.FILES.values()))
        provider.require_mode('windows','nr-mfg',bridge=True)
        with self.assertRaisesRegex(transactions.Refusal,'receipt mismatch'):
            provider.load_payload(self.archive,record | {'patch_sha256':'c'*64})

    def test_production_sr_is_pinned_to_official_release_path_and_exact_bytes(self):
        path=Path(self.temp.name).resolve()/'nvngx_dlss.dll'
        record=bridge_fixture(self.archive,path)['sr_runtime']
        self.assertEqual(provider.load_sr_runtime(path,record),path.read_bytes())
        with self.assertRaises(transactions.Refusal):
            provider.validate_sr_runtime(record | {'url':record['url'].replace('/rel/','/dev/')})
        path.write_bytes(pe()+b'different-sr')
        with self.assertRaises(transactions.Refusal):
            provider.load_sr_runtime(path,record)

    def test_each_production_component_rejects_development_paths_and_component_substitution(self):
        path=Path(self.temp.name).resolve()/'production-sr.dll'
        release=bridge_fixture(self.archive,path)
        for component,(filename,_) in provider.PRODUCTION_RUNTIMES.items():
            with self.subTest(component=component):
                record=release[component]
                source=path if component=='sr_runtime' else path.parent/('production-'+filename)
                self.assertEqual(provider.load_production_runtime(source,record,component),source.read_bytes())
                with self.assertRaises(transactions.Refusal):
                    provider.validate_production_runtime(record | {'url':record['url'].replace('/rel/','/dev/')},component)
                wrong=next(k for k in provider.PRODUCTION_RUNTIMES if k!=component)
                with self.assertRaises(transactions.Refusal):
                    provider.validate_production_runtime(release[wrong],component)
                source.write_bytes(source.read_bytes()+b'drift')
                with self.assertRaises(transactions.Refusal):
                    provider.load_production_runtime(source,record,component)

    def test_traversal_case_collision_and_foreign_payloads_are_refused(self):
        for extra in ({'../escape.dll': pe()}, {'a\\b.dll': pe()}, {'dlss5-optimised/optiscaler.dll': pe()},
                      {'DLSS5-Optimised/OptiScaler.dll': b'MZ wrong architecture'}):
            with self.subTest(extra=list(extra)), self.assertRaises((transactions.Refusal, package_catalog.PackageError)):
                provider.load_payload(self.archive, fixture(self.archive, extra))

    def test_link_member_is_refused(self):
        record = fixture(self.archive)
        with zipfile.ZipFile(self.archive, 'a') as archive:
            link = zipfile.ZipInfo('linked')
            link.external_attr = 0o120777 << 16
            archive.writestr(link, 'target')
        record.update(release_size=self.archive.stat().st_size, sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())
        with self.assertRaises(transactions.Refusal):
            provider.load_payload(self.archive, record)

    def release(self, digest='sha256:'+'a'*64):
        tag='v1.2.1'
        return {'tag_name':tag,'draft':False,'prerelease':False,'assets':[
            {'name':'OptiScaler-DLSS5-1.2.1-win-x64.zip','browser_download_url':f'https://github.com/{provider.REPO}/releases/download/{tag}/OptiScaler-DLSS5-1.2.1-win-x64.zip',
             'size':1000,'digest':digest,'id':1}]}

    def test_latest_and_explicit_tag_preserve_selection_and_commit(self):
        for selection in ('latest', 'v1.2.1'):
            with patch.object(provider, 'get_json', side_effect=[self.release(), {'object':{'type':'commit','sha':'b'*40}}]) as fetch:
                record=provider.resolve(selection)
            self.assertEqual(record['selected_source'], selection)
            self.assertEqual(record['commit'], 'b'*40)
            self.assertEqual(record['sha256'], 'a'*64)
            self.assertIn('/releases/', fetch.call_args_list[0].args[0])

    def test_missing_digest_wrong_origin_ambiguous_asset_and_unknown_tag_refused(self):
        for release in (self.release(''), self.release().copy()):
            if release['assets'][0]['digest']:
                release['assets'][0]['browser_download_url']='https://example.com/payload.zip'
            with patch.object(provider,'get_json',side_effect=[release,{'object':{'type':'commit','sha':'b'*40}}]), self.assertRaises(transactions.Refusal):
                provider.resolve()
        release=self.release();release['assets']*=2
        with patch.object(provider,'get_json',return_value=release), self.assertRaises(transactions.Refusal):
            provider.resolve()
        with patch.object(provider,'get_json') as fetch, self.assertRaises(transactions.Refusal):
            provider.resolve('../../nightly')
        fetch.assert_not_called()

    def test_windows_catalog_keeps_existing_default_and_linux_excludes_skynizz(self):
        release=bridge_fixture(self.archive)
        with patch.object(provider,'bundled_bridge',return_value=(release,self.archive)):
            windows=package_catalog.catalog({'system':'Windows','architecture':'AMD64','ready':True})
        self.assertTrue(next(row for row in windows if row['id']=='skynizz')['available'])
        self.assertFalse(next(row for row in windows if row['id']=='skynizz')['recommended'])
        self.assertTrue(next(row for row in windows if row['id']=='dlss-unlocked')['recommended'])
        linux=package_catalog.catalog({'system':'Linux','architecture':'x86_64','ready':True})
        self.assertEqual([row['id'] for row in linux], ['dlss-unlocked','y4my'])

    def test_unsupported_modes_and_linux_refuse_before_resolution(self):
        provider.require_mode('windows', 'nr-only')
        for system,mode,fallback in [('linux','nr-only',False),('windows','nr-mfg',False),('windows','mfg-only',False),('windows','nr-only',True)]:
            with self.subTest(system=system,mode=mode), self.assertRaises(transactions.Refusal):
                provider.require_mode(system,mode,fallback)


if __name__ == '__main__':
    unittest.main()
