"""Release candidates must update forward without downgrading to older previews."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import app_update

class ApplicationUpdateTest(unittest.TestCase):
    def check_remote(self,remote):
        name='RTXForge.AppImage'
        manifest={'version':remote,'commit':'remote','appimage':name,'sha256':'a'*64,'size':100}
        release={'assets':[
            {'name':app_update.MANIFEST_NAME,'browser_download_url':'fixture-manifest'},
            {'name':name,'browser_download_url':'https://github.com/lrnolivia/rtxForge/releases/download/continuous/'+name},
        ]}
        with patch.object(app_update,'_json',side_effect=[release,manifest]),patch.object(app_update,'current_build',return_value={'version':'1.0.0-rc.1','commit':'local'}):
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

if __name__=='__main__':unittest.main()
