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


class SkynizzPolicyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / 'release.zip'

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
