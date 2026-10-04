import copy,json,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import steam_artwork as art
import library_media

PNG=b'\x89PNG\r\n\x1a\nnew'
JPG=b'\xff\xd8\xffold'

class SteamArtworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.folder=self.root/'Steam/userdata/42/config';self.folder.mkdir(parents=True)
        (self.folder/'localconfig.vdf').write_text('"UserLocalConfigStore" {}')
        self.grid=self.folder/'grid';self.grid.mkdir()
        self.config={'storage':{'root':str(self.root/'state'),'reserve_bytes':0}}
        self.settings=copy.deepcopy(library_media.DEFAULTS)
        self.account={'root':self.root/'Steam','userid':'42','config':self.folder,'shortcuts':self.folder/'shortcuts.vdf'}
        self.engine=SimpleNamespace(steam_roots_for_config=lambda:[self.root/'Steam'],choose_steam_user_config=lambda *a,**k:self.account)
        self.game={'game':str(self.root/'game'),'name':'Game','exe':'Game.exe','source':'Steam','appid':'123'}
    def test_roles_backup_and_reset_are_reversible(self):
        (self.grid/'123p.jpg').write_bytes(JPG)
        (self.grid/'999p.png').write_bytes(b'unrelated')
        result=art.write_slot(self.config,self.grid,'123','poster',PNG)
        self.assertTrue(result['changed']);self.assertEqual((self.grid/'123p.png').read_bytes(),PNG)
        self.assertFalse((self.grid/'123p.jpg').exists())
        art.write_slot(self.config,self.grid,'123','poster',PNG+b'next')
        art.write_slot(self.config,self.grid,'123','poster',reset=True)
        self.assertEqual((self.grid/'123p.jpg').read_bytes(),JPG)
        self.assertFalse((self.grid/'123p.png').exists());self.assertEqual((self.grid/'999p.png').read_bytes(),b'unrelated')
        for role,suffix in art.SUFFIX.items():
            art.write_slot(self.config,self.grid,'123',role,PNG)
            self.assertTrue((self.grid/('123'+suffix+'.png')).exists())
    def test_reset_preserves_newer_external_art(self):
        art.write_slot(self.config,self.grid,'123','hero',PNG)
        (self.grid/'123_hero.png').write_bytes(PNG+b'external')
        with self.assertRaisesRegex(ValueError,'outside rtxForge'):
            art.write_slot(self.config,self.grid,'123','hero',reset=True)
        self.assertEqual((self.grid/'123_hero.png').read_bytes(),PNG+b'external')
    def test_first_empty_baseline_reset_restores_automatic(self):
        art.write_slot(self.config,self.grid,'123','capsule',PNG)
        art.write_slot(self.config,self.grid,'123','capsule',reset=True)
        self.assertFalse((self.grid/'123.png').exists())
    def test_atomic_failure_keeps_original_and_records_rollback(self):
        (self.grid/'123p.jpg').write_bytes(JPG)
        original=art.t.atomic_file
        def fail(path,data,mode):
            if Path(path)==self.grid/'123p.png':raise OSError('disk full')
            return original(path,data,mode)
        with patch.object(art.t,'atomic_file',side_effect=fail):
            with self.assertRaises(OSError):art.write_slot(self.config,self.grid,'123','poster',PNG)
        self.assertEqual((self.grid/'123p.jpg').read_bytes(),JPG)
        self.assertFalse((self.grid/'123p.png').exists())
        records=list((self.root/'state').glob('**/operation-*/record.json'))
        self.assertEqual(json.loads(records[0].read_text())['status'],'rolled-back')
    def test_interrupted_write_recovers_before_next_sync(self):
        (self.grid/'123p.jpg').write_bytes(JPG)
        original=art.t.atomic_file
        def crash(path,data,mode):
            original(path,data,mode)
            if Path(path)==self.grid/'123p.png':raise SystemExit('simulated process exit')
        with patch.object(art.t,'atomic_file',side_effect=crash):
            with self.assertRaises(SystemExit):art.write_slot(self.config,self.grid,'123','poster',PNG)
        art.write_slot(self.config,self.grid,'123','poster',PNG+b'next')
        self.assertEqual((self.grid/'123p.png').read_bytes(),PNG+b'next')
        art.write_slot(self.config,self.grid,'123','poster',reset=True)
        self.assertEqual((self.grid/'123p.jpg').read_bytes(),JPG)
    def test_interrupted_recovery_preserves_external_changes(self):
        original=art.t.atomic_file
        def crash(path,data,mode):
            original(path,data,mode)
            if Path(path)==self.grid/'123p.png':raise SystemExit('simulated process exit')
        with patch.object(art.t,'atomic_file',side_effect=crash):
            with self.assertRaises(SystemExit):art.write_slot(self.config,self.grid,'123','poster',PNG)
        (self.grid/'123p.png').write_bytes(PNG+b'external')
        with self.assertRaisesRegex(ValueError,'newer external changes'):art.write_slot(self.config,self.grid,'123','poster',PNG+b'next')
        self.assertEqual((self.grid/'123p.png').read_bytes(),PNG+b'external')
    def test_rejects_traversal_symlink_invalid_ids_and_unsupported_bytes(self):
        for bad in ('../x','0','-1',str(2**32)):
            with self.assertRaises(ValueError):art.write_slot(self.config,self.grid,bad,'hero',PNG)
        with self.assertRaises(ValueError):art.write_slot(self.config,self.grid,'123','../x',PNG)
        with self.assertRaises(ValueError):art.write_slot(self.config,self.grid,'123','hero',b'RIFF1234WEBP')
        outside=self.root/'outside';outside.write_bytes(b'safe')
        (self.grid/'123p.png').symlink_to(outside)
        with self.assertRaises(art.t.Refusal):art.write_slot(self.config,self.grid,'123','poster',PNG)
        self.assertEqual(outside.read_bytes(),b'safe')
    def test_real_steam_id_and_selected_profile(self):
        self.assertEqual(art.target(self.config,self.settings,self.game,engine=self.engine),(self.grid,'123'))
        self.settings['steam_artwork_profile']={'root':str(self.root/'Steam'),'userid':'42'}
        self.assertEqual(art.target(self.config,self.settings,self.game,engine=self.engine)[1],'123')
        self.settings['steam_artwork_profile']['userid']='99'
        with self.assertRaisesRegex(ValueError,'unavailable'):art.target(self.config,self.settings,self.game,engine=self.engine)
    def test_nonsteam_uses_actual_shortcut_id_not_store_metadata(self):
        self.game.update(source='Non-Steam',appid='999')
        self.account['shortcuts'].write_bytes(b'fixture')
        self.engine.parse_shortcuts_spans=lambda b:['shortcut']
        self.engine.match_shortcut_span=lambda g,ss:ss[0]
        self.engine._shortcut_int=lambda s,k:-123
        self.assertEqual(art.target(self.config,self.settings,self.game,engine=self.engine)[1],str((-123)&0xffffffff))
        self.engine.match_shortcut_span=lambda *a:None
        with self.assertRaisesRegex(ValueError,'No unique'):art.target(self.config,self.settings,self.game,engine=self.engine)
    def test_ambiguous_account_does_not_write(self):
        def ambiguous(*a,**k):raise ValueError('Multiple Steam accounts')
        self.engine.choose_steam_user_config=ambiguous
        with self.assertRaisesRegex(ValueError,'Multiple'):art.sync_game(self.config,self.settings,self.game,engine=self.engine)
        self.assertEqual(list(self.grid.iterdir()),[])
    def test_sync_and_pending_reset_share_backend(self):
        p=self.root/'poster.png';p.write_bytes(PNG)
        self.settings['game_artwork'][self.game['game']]={'poster':{'path':str(p)}}
        results=art.sync_game(self.config,self.settings,self.game,engine=self.engine)
        self.assertEqual(len(results),1);self.assertTrue(results[0]['changed'])
        self.settings['game_artwork'].clear()
        art.sync_game(self.config,self.settings,self.game,reset_roles=['poster'],engine=self.engine)
        self.assertFalse((self.grid/'123p.png').exists())

if __name__=='__main__':unittest.main()
