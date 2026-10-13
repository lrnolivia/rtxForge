import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import package_catalog as pc

class PackageCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def package(self, files):
        p = self.root / 'custom.zip'
        with zipfile.ZipFile(p, 'w') as z:
            for name, data in files.items(): z.writestr(name, data)
        return p
    def test_recognizes_wrapped_layout_without_executing_instructions(self):
        p = self.package({'release/dxgi.dll': b'MZfixture', 'release/OptiScaler.ini': '[DlssNr]\nIntensity=1.5',
            'release/OptiScaler/streamline/sl.interposer.dll': b'MZfixture',
            'release/OptiScaler/streamline/sl.dlss_g.dll': b'MZfixture',
            'README.md': 'sudo touch /never-run\nrun install.sh', 'install.sh': 'exit 1'})
        r = pc.inspect_archive(p)
        self.assertEqual(r['family'], 'dlss-unlocked')
        self.assertEqual(r['prefix'], 'release/')
        self.assertFalse(r['deployable'])
        self.assertEqual(r['parameters'][1]['value'], '1.5')
        self.assertTrue(any('will not be run' in x for x in r['warnings']))
        self.assertEqual(list(self.root.iterdir()), [p])
    def test_unknown_stays_unknown(self):
        self.assertEqual(pc.inspect_archive(self.package({'readme.txt': 'Install anything'}))['family'], 'unknown')
    def test_unsafe_paths_rejected(self):
        for name in ('../escape.dll', '/absolute.dll', 'a\\b.dll', 'C:/foo.dll', 'AUX.dll'):
            with self.subTest(name=name), self.assertRaises(pc.PackageError):
                pc.inspect_archive(self.package({name: b'x'}))
    def test_case_collision_rejected(self):
        with self.assertRaises(pc.PackageError):pc.inspect_archive(self.package({'A.dll': b'a', 'a.dll': b'b'}))
    def test_symlink_member_rejected(self):
        p=self.root/'link.zip'
        with zipfile.ZipFile(p,'w') as z:
            info=zipfile.ZipInfo('link');info.external_attr=0o120777<<16;z.writestr(info,'target')
        with self.assertRaises(pc.PackageError):pc.inspect_archive(p)
    def test_archive_link_rejected(self):
        p=self.package({'ok.ini':'[A]\na=b'});link=self.root/'alias.zip';link.symlink_to(p)
        with self.assertRaises(pc.PackageError):pc.inspect_archive(link)
    def test_ambiguous_payloads_not_guessed(self):
        r=pc.inspect_archive(self.package({'a/OptiScaler.ini':'','b/OptiScaler.ini':''}))
        self.assertEqual(r['family'],'unknown')
    def test_config_bounds_and_nonfinite(self):
        for value in ('nan','inf','-1','3','$(touch x)'):
            with self.assertRaises(pc.PackageError):pc.validate_parameters({'Intensity':value})
        self.assertEqual(pc.validate_parameters({'Sharpness':'.4'}),{'Sharpness':.4})
    def test_unsupported_system_does_not_get_install_recommendation(self):
        for host in ({'system':'Linux','architecture':'aarch64','ready':True}, {'system':'Linux','architecture':'x86_64','ready':False}):
            self.assertTrue(all(not x['available'] for x in pc.catalog(host)))
    def test_catalog_uses_existing_pins(self):
        rows=pc.catalog({'system':'Linux','architecture':'x86_64','ready':True})
        self.assertTrue(rows[0]['recommended']);self.assertEqual(len(rows[0]['sha256']),64)

class CustomDeploymentBoundaryTests(PackageCatalogTests):
    def fixture(self,extra=None):
        files={'dxgi.dll':b'MZfixture','OptiScaler.ini':b'[DLSSG]\nAdaMfgUnlock=true',
               'OptiScaler/streamline/sl.interposer.dll':b'MZfixture',
               'OptiScaler/streamline/sl.dlss_g.dll':b'MZfixture',
               'install.sh':b'touch /never', 'run.exe':b'MZuntrusted-program'}
        files.update(extra or {})
        return self.package(files)
    def test_explicit_trust_required(self):
        result=pc.inspect_archive(self.fixture())
        with self.assertRaises(pc.PackageError):pc.custom_record(result,{},trusted=False)
    def test_only_supported_payload_files_leave_inspection(self):
        result=pc.inspect_archive(self.fixture())
        record=pc.custom_record(result,{},trusted=True)
        data,meta=pc.load_custom_payload(record)
        self.assertNotIn('install.sh',data);self.assertNotIn('run.exe',data)
        self.assertEqual(meta['instruction_policy'],'read-only')
        self.assertTrue(record['id'].startswith('custom-'))
    def test_changed_archive_refused(self):
        result=pc.inspect_archive(self.fixture());record=pc.custom_record(result,{},trusted=True)
        self.fixture({'extra.txt':b'changed'})
        with self.assertRaises(pc.PackageError):pc.load_custom_payload(record)
    def test_root_native_replacement_refused(self):
        result=pc.inspect_archive(self.fixture({'nvngx_dlss.dll':b'MZnative'}))
        record=pc.custom_record(result,{},trusted=True)
        with self.assertRaises(pc.PackageError):pc.load_custom_payload(record)
    def test_invalid_binary_refused(self):
        result=pc.inspect_archive(self.fixture({'dxgi.dll':b'not a DLL'}))
        record=pc.custom_record(result,{},trusted=True)
        with self.assertRaises(pc.PackageError):pc.load_custom_payload(record)
    def test_unknown_format_cannot_be_force_installed(self):
        result=pc.inspect_archive(self.package({'random.dll':b'MZ'}))
        with self.assertRaises(pc.PackageError):pc.custom_record(result,{},trusted=True)

if __name__=='__main__':unittest.main()
