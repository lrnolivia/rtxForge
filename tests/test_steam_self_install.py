import copy,os,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import steam_self_install as s
import engine_bridge,library_media,desktop_install
PNG=b'\x89PNG\r\n\x1a\nfixture'
class SelfInstallTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.config={'storage':{'root':str(self.root/'state'),'reserve_bytes':0}};self.settings=copy.deepcopy(library_media.DEFAULTS)
  self.engine=engine_bridge.module(self.config)
  self.folder=self.root/'Steam/userdata/42/config';self.folder.mkdir(parents=True)
  (self.folder/'localconfig.vdf').write_text('{}')
  self.engine.steam_roots_for_config=lambda:[self.root/'Steam']
  self.engine.choose_steam_user_config=lambda *a,**k:{'root':self.root/'Steam','userid':'42','config':self.folder,'shortcuts':self.folder/'shortcuts.vdf'}
  self.engine.steam_running=lambda:False
  self.entry=self.root/'rtxforge';self.entry.write_text('#!/bin/sh\n');self.entry.chmod(0o755)
 def test_append_and_repeat_preserves_old_bytes_and_ids(self):
  first,oldid,_=s.append_shortcut(None,self.root/'other',engine=self.engine,name='Other')
  result,appid,created=s.append_shortcut(first,self.entry,engine=self.engine)
  self.assertTrue(created);self.assertEqual(result[:len(first)-2],first[:-2]);self.assertNotEqual(appid,oldid)
  same,sameid,created=s.append_shortcut(result,self.entry,engine=self.engine)
  self.assertFalse(created);self.assertEqual(same,result);self.assertEqual(appid,sameid)
  self.assertEqual(len(self.engine.parse_shortcuts_spans(result)),2)
 def test_closed_steam_adds_all_four_art_roles_without_key(self):
  result=s.install(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  self.assertTrue(result['created']);self.assertEqual(result['errors'],[]);self.assertEqual(len(result['artwork']),4)
  original=(self.folder/'shortcuts.vdf').read_bytes()
  self.engine.steam_running=lambda:True
  second=s.install(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  self.assertFalse(second['created']);self.assertEqual((self.folder/'shortcuts.vdf').read_bytes(),original)
 def test_running_steam_refuses_new_shortcut_without_mutation(self):
  self.engine.steam_running=lambda:True
  with self.assertRaisesRegex(ValueError,'Close Steam'):s.install(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  self.assertFalse((self.folder/'shortcuts.vdf').exists());self.assertFalse((self.folder/'grid').exists())
 def test_missing_asset_refuses_before_shortcut_change(self):
  def missing(p):raise FileNotFoundError(str(p))
  with self.assertRaises(FileNotFoundError):s.install(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=missing)
  self.assertFalse((self.folder/'shortcuts.vdf').exists())
 def test_malformed_config_never_rewritten(self):
  path=self.folder/'shortcuts.vdf';path.write_bytes(b'broken')
  with self.assertRaises(Exception):s.install(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  self.assertEqual(path.read_bytes(),b'broken')
 def test_launcher_flip_only_changes_managed_launcher_icon(self):
  with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data')}):
   self.assertFalse(desktop_install.refresh_launcher_icon(False))
   d=Path(os.environ['XDG_DATA_HOME'])/'applications'/f'{desktop_install.APP_ID}.desktop';d.parent.mkdir(parents=True)
   text='[Desktop Entry]\nName=rtxForge\nExec=/safe/app\nIcon=old\nStartupWMClass='+desktop_install.APP_ID+'\n'
   d.write_text(text)
   self.assertTrue(desktop_install.refresh_launcher_icon(False));self.assertIn('-light.svg',d.read_text());self.assertIn('Exec=/safe/app',d.read_text())
   self.assertFalse(desktop_install.refresh_launcher_icon(False))
   self.assertTrue(desktop_install.refresh_launcher_icon(True));self.assertNotIn('-light.svg',d.read_text())
if __name__=='__main__':unittest.main()
