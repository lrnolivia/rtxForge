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
 def existing_custom_slot(self):
  raw,appid,_=s.append_shortcut(None,self.entry,engine=self.engine)
  (self.folder/'shortcuts.vdf').write_bytes(raw)
  grid=self.folder/'grid';grid.mkdir()
  path=grid/(str(appid)+'p.jpg');path.write_bytes(b'personal artwork')
  return raw,path
 def test_review_is_read_only_and_unreviewed_call_preserves_custom_art(self):
  raw,path=self.existing_custom_slot()
  review=s.review(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  self.assertFalse((self.root/'state').exists())
  self.assertEqual(review['roles'][0]['status'],'replace')
  self.assertEqual(path.read_bytes(),b'personal artwork')
  result=s.install(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  self.assertEqual(result['preserved'],['poster']);self.assertEqual(path.read_bytes(),b'personal artwork')
  self.assertEqual((self.folder/'shortcuts.vdf').read_bytes(),raw)
 def test_reviewed_replacement_and_later_reset_keep_original(self):
  _,path=self.existing_custom_slot()
  review=s.review(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  result=s.install(self.config,self.settings,reviewed=review,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  self.assertEqual(result['errors'],[]);self.assertEqual(result['preserved'],[])
  self.assertFalse(path.exists())
  import steam_artwork
  steam_artwork.write_slot(self.config,self.folder/'grid',str(result['appid']),'poster',reset=True)
  self.assertEqual(path.read_bytes(),b'personal artwork')
 def test_stale_review_refuses_before_any_writes(self):
  raw,path=self.existing_custom_slot()
  review=s.review(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  path.write_bytes(b'newer custom artwork')
  with self.assertRaisesRegex(ValueError,'since your review'):
   s.install(self.config,self.settings,reviewed=review,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  self.assertFalse((self.root/'state').exists());self.assertEqual(path.read_bytes(),b'newer custom artwork')
  self.assertEqual((self.folder/'shortcuts.vdf').read_bytes(),raw)
 def test_slot_guard_refuses_a_change_after_preparation(self):
  _,path=self.existing_custom_slot()
  import steam_artwork
  fingerprint=steam_artwork.slot_hashes(path.parent,path.stem[:-1],'poster')
  path.write_bytes(b'newer custom artwork')
  with self.assertRaisesRegex(ValueError,'since your review'):
   steam_artwork.write_slot(self.config,path.parent,path.stem[:-1],'poster',PNG,expected_before=fingerprint)
  self.assertEqual(path.read_bytes(),b'newer custom artwork')

 def test_missing_shortcut_icon_refuses_before_any_writes(self):
  with patch.object(s,'ROOT',self.root/'missing-package'):
   with self.assertRaisesRegex(ValueError,'icon is missing'):
    s.review(self.config,self.settings,engine=self.engine,entry=self.entry,load_image=lambda p:PNG)
  self.assertFalse((self.root/'state').exists());self.assertFalse((self.folder/'shortcuts.vdf').exists())

 def test_remove_only_own_shortcut_preserves_other_entries_and_art(self):
  other,_,_=s.append_shortcut(None,self.root/'other',engine=self.engine,name='rtxForge')
  raw,_,_=s.append_shortcut(other,self.entry,engine=self.engine)
  path=self.folder/'shortcuts.vdf';path.write_bytes(raw)
  grid=self.folder/'grid';grid.mkdir();art=grid/'personal.png';art.write_bytes(PNG)
  kwargs={'engine':self.engine,'entry':self.entry}
  status=s.shortcut_status(self.config,self.settings,**kwargs);self.assertTrue(status['added'])
  result=s.remove(self.config,self.settings,reviewed=status,**kwargs)
  self.assertEqual(path.read_bytes(),other);self.assertEqual(art.read_bytes(),PNG)
  self.assertEqual((Path(result['backup'])/'shortcuts.vdf').read_bytes(),raw)
  self.assertFalse(s.shortcut_status(self.config,self.settings,**kwargs)['added'])

 def test_remove_refuses_running_steam_and_stale_review(self):
  raw,_,_=s.append_shortcut(None,self.entry,engine=self.engine)
  path=self.folder/'shortcuts.vdf';path.write_bytes(raw)
  kwargs={'engine':self.engine,'entry':self.entry}
  status=s.shortcut_status(self.config,self.settings,**kwargs)
  self.engine.steam_running=lambda:True
  with self.assertRaisesRegex(ValueError,'Close Steam'):s.remove(self.config,self.settings,reviewed=status,**kwargs)
  self.assertEqual(path.read_bytes(),raw);self.assertFalse((self.root/'state').exists())
  self.engine.steam_running=lambda:False
  changed,_,_=s.append_shortcut(raw,self.root/'other',engine=self.engine);path.write_bytes(changed)
  with self.assertRaisesRegex(ValueError,'since your review'):s.remove(self.config,self.settings,reviewed=status,**kwargs)
  self.assertEqual(path.read_bytes(),changed);self.assertFalse((self.root/'state').exists())

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
