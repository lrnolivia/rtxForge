"""Real profiled app review/install/repair/restore with disposable game files."""
import contextlib
import os
from pathlib import Path
import shutil
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import transactions as t
import vulkan_app as app
from tests import test_vulkan_dlssg_provider as fixtures
pe = fixtures.pe


class AppRoutes(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.SharedBg3Tests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        loader=f.pin_path.parent/'loader-bg3/bink2w64.dll';loader.parent.mkdir();shutil.copyfile(f.loader,loader)
        self.bundle=patch.object(app,'bundled',return_value=(f.pin_path.parent,f.pin_path,f.archive,f.spec));self.bundle.start();self.addCleanup(self.bundle.stop)
        self.prefix=patch.object(app,'prefix_for',return_value=None);self.prefix.start();self.addCleanup(self.prefix.stop)
        self.state=patch.dict(os.environ,{'RTXFORGE_VULKAN_STATE':str(f.state)});self.state.start();self.addCleanup(self.state.stop)
        self.e=types.SimpleNamespace(STATE_ROOT=f.base/'engine',Stop=t.Refusal,_running_processes_under_root=lambda _:[],mutation_lock=contextlib.nullcontext)
        self.row={'game':str(f.game.parent),'name':'BG3','exe':'bin/bg3.exe','appid':'1086940','anti_cheat':False}
        self.settings={'runtime_provider':'skynizz','nr_on_launch':False}

    def prepare(self,operation='install',mode='nr-mfg',**settings):
        return app.prepare({},[self.row],mode,operation,self.settings|settings,self.e)

    def test_full_lifecycle_and_effective_choices(self):
        before=self.fixture.files()
        review=self.prepare(game_overlay_settings={self.row['game']:{'overlay_welcome':False,'panel_hotkey':'F8'}})
        self.assertFalse(review['blocked']);self.assertEqual(len(review['plans']),1)
        self.assertEqual(before,self.fixture.files());self.assertFalse(self.fixture.state.exists())
        self.assertIn('Vulkan',review['rows'][0]['detail']);self.assertIn('Welcome message: Off',review['rows'][0]['detail'])
        app.execute(review)
        self.assertIn('Enabled=0',(self.fixture.game/'NativeMods/fgvk.ini').read_text())
        rows=app.decorate([dict(self.row)],{})
        self.assertEqual(rows[0]['runtime_provider'],'vulkan-native');self.assertEqual(rows[0]['graphics_apis'],['Vulkan'])
        repair=self.prepare('repair');self.assertFalse(repair['blocked']);app.execute(repair)
        restore=self.prepare('uninstall');self.assertFalse(restore['blocked']);app.execute(restore)
        self.assertEqual(before,self.fixture.files())

    def test_automatic_route_known_profile_and_model_refusals(self):
        # On by default: no opt-in, and a profiled game is routed here whatever DLSS package is chosen.
        self.assertTrue(self.prepare(vulkan_experimental=False)['plans'])
        rows=app.decorate([dict(self.row)],{},selected=False)
        self.assertEqual((rows[0]['install_provider'],rows[0]['vulkan_available'],rows[0]['blocked']),('vulkan-native',True,''))
        self.assertIn("Baldur’s Gate 3",app.confirmed())
        with self.assertRaises(t.Refusal):self.prepare(mode='nr-only')
        foreign=self.fixture.base/'Unknown';foreign.mkdir();(foreign/'Game.exe').write_bytes(pe())
        result=app.prepare({},[dict(self.row,game=str(foreign))],'nr-mfg','install',self.settings,self.e)
        self.assertFalse(result['plans']);self.assertTrue(result['blocked'])
        invalid=self.fixture.base/'nr.dll';invalid.write_bytes(pe())
        with self.assertRaises(t.Refusal):self.prepare(nr_runtime=str(invalid))
        self.assertEqual(self.fixture.original,self.fixture.files())

    def test_drift_running_and_model_preservation(self):
        review=self.prepare()
        (self.fixture.game/'nvngx_dlss.dll').write_bytes(pe(b'updated after review'))
        with self.assertRaises(t.Refusal):app.execute(review)
        self.assertEqual(self.fixture.original['bink2w64.dll'],(self.fixture.game/'bink2w64.dll').read_bytes())
        (self.fixture.game/'nvngx_dlss.dll').write_bytes(self.fixture.original['nvngx_dlss.dll'])
        review=self.prepare();self.e._running_processes_under_root=lambda _:[123]
        with self.assertRaises(t.Refusal):app.execute(review)
        self.e._running_processes_under_root=lambda _:[]
        app.execute(self.prepare())
        model=(self.fixture.game/'NativeMods/nvngx_dlssnr.dll').read_bytes()
        app.execute(self.prepare('repair'))
        self.assertEqual(model,(self.fixture.game/'NativeMods/nvngx_dlssnr.dll').read_bytes())

    def test_bulk_overlay_update_preserves_model_tuning_and_originals(self):
        sys.path.append(str(Path(__file__).resolve().parents[1]/'windows/engine-host'))
        import overlay_package_routes as routes
        import global_controls as bulk
        app.execute(self.prepare())
        f=self.fixture
        state=f.state/('targets')/t.sha(str(f.game).casefold().encode())/'baseline.json'
        original=t.read_json(state)['originals']
        model=(f.game/'NativeMods/nvngx_dlssnr.dll').read_bytes()
        config=(f.game/'NativeMods/fgvk.ini').read_bytes()
        f.members['NativeMods/fgvk.dll']=pe(b'new overlay runtime');f.repack()
        params={'target_games':[self.row['game']],'overlay_welcome':False}
        with patch.object(bulk,'anti_cheat',return_value=None):
            plans,blocked,skipped=routes.vulkan_plans(self.e,params,lambda _:False)
            self.assertFalse(blocked);self.assertEqual(len(plans),1)
            self.assertIn('Welcome message: Off',plans[0]['note'])
            self.assertNotEqual((f.game/'NativeMods/fgvk.dll').read_bytes(),f.members['NativeMods/fgvk.dll'])
            from tests import test_feeder_provider as feeder_fixtures
            copying=patch('operation_session.subprocess.run',side_effect=feeder_fixtures.copy_command) if os.name=='nt' else contextlib.nullcontext()
            with copying:bulk.execute({'engine':self.e,'plans':plans})
            self.assertEqual((f.game/'NativeMods/fgvk.dll').read_bytes(),f.members['NativeMods/fgvk.dll'])
            self.assertEqual(t.read_json(state)['originals'],original)
            self.assertEqual((f.game/'NativeMods/nvngx_dlssnr.dll').read_bytes(),model)
            self.assertEqual((f.game/'NativeMods/fgvk.ini').read_bytes(),config)
            self.assertFalse(routes.vulkan_plans(self.e,params,lambda _:False)[0])
            (f.game/'NativeMods/fgvk.dll').write_bytes(b'foreign')
            plans,blocked,_=routes.vulkan_plans(self.e,params,lambda _:False)
            self.assertFalse(plans);self.assertTrue(blocked)


if __name__=='__main__':unittest.main()
