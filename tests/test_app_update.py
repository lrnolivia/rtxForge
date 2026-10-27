"""Release candidates must update forward without downgrading to older previews."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import os, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import app_update, desktop_install

class ApplicationUpdateTest(unittest.TestCase):
    def check_remote(self,remote):
        name='RTXForge.AppImage'
        manifest={'version':remote,'commit':'remote','appimage':name,'sha256':'a'*64,'size':100}
        release={'assets':[
            {'name':app_update.MANIFEST_NAME,'browser_download_url':'fixture-manifest'},
            {'name':name,'browser_download_url':'https://github.com/lrnolivia/rtxForge/releases/download/continuous/'+name},
        ]}
        with patch.object(app_update,'channel',return_value='continuous'),patch.object(app_update,'_json',side_effect=[release,manifest]),patch.object(app_update,'current_build',return_value={'version':'1.0.0-rc.1','commit':'local'}):
            return app_update.check()['available']
    def test_release_candidate_update_paths(self):
        self.assertFalse(self.check_remote('0.7.0'))
        self.assertFalse(self.check_remote('1.0.0-rc.0'))
        self.assertTrue(self.check_remote('1.0.0-rc.2'))
        self.assertTrue(self.check_remote('1.0.0'))
    def test_final_release_is_newer_than_candidate(self):
        self.assertGreater(app_update._version_key('1.0.0'),app_update._version_key('1.0.0-rc.99'))
        self.assertEqual(app_update._version_key('v1.0'),app_update._version_key('1.0.0'))
        with self.assertRaises(ValueError):app_update._version_key('1.0.0-rc.bad')

    def test_beta_versions_update_forward_and_remain_before_release_candidates(self):
        self.assertLess(app_update._version_key('1.0.0-beta.1'), app_update._version_key('1.0.0-beta.2'))
        self.assertLess(app_update._version_key('1.0.0-beta.99'), app_update._version_key('1.0.0-rc.1'))
        self.assertLess(app_update._version_key('1.0.0-beta.1'), app_update._version_key('1.0.0'))
        with self.assertRaises(ValueError):app_update._version_key('1.0.0-beta.bad')


class UpdateChannelTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'XDG_DATA_HOME':self.tmp.name},clear=False)
        self.env.start()
        for key in ('APPIMAGE','RTXFORGE_UPDATE_CHANNEL'):os.environ.pop(key,None)
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()

    def install(self,name):
        source=Path(self.tmp.name)/name
        source.write_bytes(b'appimage')
        with patch.object(desktop_install,'register'):desktop_install.install_from(source)

    def test_installs_default_to_continuous(self):
        self.assertEqual(app_update.channel(),'continuous')

    def test_beta_download_records_the_beta_channel(self):
        self.install('rtxForge-1.0.0-beta.3-x86_64.AppImage')
        self.assertEqual(desktop_install.installed_channel(),'beta')
        self.assertEqual(app_update.channel(),'beta')

    def test_continuous_download_records_continuous(self):
        self.install('rtxForge-1.0.0-beta.3-x86_64.AppImage')
        self.install('rtxForge-Bazzite-x86_64.AppImage')
        self.assertEqual(app_update.channel(),'continuous')

    def test_staged_updates_keep_the_recorded_channel(self):
        self.install('rtxForge-1.0.0-beta.3-x86_64.AppImage')
        self.install('.rtxforge-download-abc.AppImage')
        self.assertEqual(app_update.channel(),'beta')

    def test_running_the_beta_download_follows_beta_before_installing(self):
        os.environ['APPIMAGE']='/home/me/Downloads/rtxForge-1.0.0-beta.3-x86_64.AppImage'
        self.assertEqual(app_update.channel(),'beta')

    def test_override_wins_and_is_validated(self):
        self.install('rtxForge-1.0.0-beta.3-x86_64.AppImage')
        os.environ['RTXFORGE_UPDATE_CHANNEL']='continuous'
        self.assertEqual(app_update.channel(),'continuous')
        os.environ['RTXFORGE_UPDATE_CHANNEL']='nightly'
        with self.assertRaises(RuntimeError):app_update.channel()

    def test_beta_channel_reads_the_beta_release_and_manifest(self):
        name='rtxForge-1.0.0-beta.3-x86_64.AppImage'
        manifest={'channel':'beta','version':'1.0.0-beta.3','commit':'remote','appimage':name,'sha256':'b'*64,'size':10}
        release={'assets':[
            {'name':'rtxforge-beta-linux.json','browser_download_url':'beta-manifest'},
            {'name':name,'browser_download_url':'https://github.com/lrnolivia/rtxForge/releases/download/beta/'+name},
        ]}
        calls=[]
        def fetch(url):
            calls.append(url);return release if len(calls)==1 else manifest
        with patch.object(app_update,'channel',return_value='beta'),patch.object(app_update,'_json',side_effect=fetch),\
                patch.object(app_update,'current_build',return_value={'version':'1.0.0-beta.2','commit':'local'}):
            info=app_update.check()
        self.assertEqual(calls,[app_update.CHANNELS['beta'][0],'beta-manifest'])
        self.assertTrue(info['available']);self.assertEqual(info['update_channel'],'beta')

    def test_beta_release_without_a_linux_build_says_so(self):
        release={'assets':[{'name':'rtxForge-Setup-1.0.0-beta.2-x64.exe','browser_download_url':'x'}]}
        with patch.object(app_update,'channel',return_value='beta'),patch.object(app_update,'_json',return_value=release):
            with self.assertRaisesRegex(RuntimeError,'no Linux build yet'):app_update.check()

if __name__=='__main__':unittest.main()
