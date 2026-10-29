"""Package routing considers the executable and keeps install ownership separate."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'windows/engine-host')]
from tests import test_feeder_provider as fixtures
import provider_candidates as candidates


class CandidateTest(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.FeederTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.e=self.fixture.e

    def test_dx11_with_retained_dlss_files_tries_feeder_instead_of_skynizz(self):
        row=self.fixture.game('The Sims 4')|{'native_dlss':True,'native_dlssg':False}
        found=candidates.decorate(self.e,[row])[0]
        by_id={p['id']:p for p in found['provider_candidates']}
        self.assertFalse(by_id['skynizz']['compatible'])
        self.assertTrue(by_id['feeder']['ready'])
        self.assertEqual(found['recommended_provider'],'feeder')
        self.assertEqual(found['install_provider'],'feeder')
        self.assertFalse(found['blocked'])

    def test_incompatible_installed_native_package_does_not_erase_restore_ownership(self):
        row=self.fixture.game('InstalledDX11')|{'native_dlss':True,'installed':True,'managed':True,'runtime_provider':'skynizz'}
        self.e.load_baseline=lambda *a,**k:{'status':'active'}
        before=self.fixture.files(row)
        found=candidates.decorate(self.e,[row])[0]
        self.assertEqual(found['runtime_provider'],'skynizz')
        self.assertTrue(found['feeder_restore_first'])
        self.assertEqual(found['recommended_provider'],'feeder')
        self.assertIn('Restore',found['blocked'])
        self.assertEqual(self.fixture.files(row),before)

    def test_native_dx12_checks_all_native_packages_and_keeps_feeder_separate(self):
        row=self.fixture.game('NativeDX12')|{'native_dlss':True,'native_dlssg':True}
        self.e.pe_imported_dlls=lambda exe:{'d3d12.dll'}
        by_id={p['id']:p for p in candidates.assess(self.e,row)}
        for key in ('skynizz','y4my','dlss-unlocked'):
            self.assertTrue(by_id[key]['compatible'])
        self.assertFalse(by_id['feeder']['compatible'])

    def test_feeder_supplied_sr_dll_does_not_fabricate_native_dlss_support(self):
        row=self.fixture.game('InstalledFeeder',installed=True)|{'native_dlss':True,'installed':True,'runtime_provider':'feeder'}
        self.e.pe_imported_dlls=lambda exe:{'d3d12.dll'}
        by_id={p['id']:p for p in candidates.assess(self.e,row)}
        self.assertFalse(by_id['skynizz']['compatible'])
        self.assertTrue(by_id['feeder']['ready'])


if __name__=='__main__':unittest.main()
