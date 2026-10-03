"""Focused tests for diagnostics, opt-in reports, metadata and tool ownership."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import controller_input as controls
import extra_tools
import game_notes
import library_media
import runtime_diagnostics as diag
import transactions as t


def pe():
    data=bytearray(256);data[:2]=b'MZ';struct.pack_into('<I',data,60,64);data[64:70]=b'PE\0\0\x64\x86'
    return bytes(data)

class Engine:
    def load_baseline(self,*_,**__):return None
    def _running_processes_under_root(self,*_):return []

class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.game=self.root/'game';self.game.mkdir()
        (self.game/'Game.exe').write_bytes(pe());(self.game/'save.dat').write_bytes(b'valuable save')
        self.row={'name':'Test Game','game':str(self.game),'exe':'Game.exe','source':'Folder'}
        self.config={'storage':{'root':str(self.root/'state'),'reserve_bytes':0}}
        self.dll=self.root/'ReShade64.dll';self.dll.write_bytes(pe()+b'ReShade')
        p=patch.object(extra_tools.engine_bridge,'module',return_value=Engine());p.start();self.addCleanup(p.stop)

    def test_ngx_callback_is_not_nr_success(self):
        self.assertFalse(diag.parse_log('NR diagnostic NGX [feature=11] initialized')['model_created'])
        report=diag.parse_log('CreateFeature(18) result=0x00000001 handle=1\nDLSS-NR GPU window: 256 samples\n')
        self.assertTrue(report['model_created']);self.assertTrue(report['gpu_samples_observed'])

    def test_latest_run_does_not_inherit_old_success(self):
        log='OptiScaler v1 loaded\nDLSS-NR GPU window: 256 samples\nOptiScaler v2 loaded\nDlssNr.Enabled: false'
        self.assertFalse(diag.parse_log(log)['gpu_samples_observed'])

    def test_debug_toggle_events_are_distinct_from_saved_state(self):
        log='DlssNr.Enabled: true\nNeural Rendering toggle key pressed, setting DlssNrEnabled to false'
        result=diag.parse_log(log)
        self.assertTrue(result['logged_enabled'])
        self.assertEqual(result['hotkey_toggle_events'],[False])
        self.assertEqual(diag.parse_log('DlssNr.Enabled: true')['hotkey_toggle_events'],[])

    def test_disabled_zero_and_stale_log_are_separate(self):
        ini=self.game/'OptiScaler.ini';ini.write_text('[DlssNr]\nEnabled=false\nIntensity=0.00\n')
        log=self.game/'OptiScaler.log';log.write_text('DLSS-NR GPU window: 256 samples');os.utime(log,(1,1))
        result=diag.inspect(self.row)
        self.assertTrue(result['log']['predates_config']);self.assertTrue(result['log']['gpu_samples_observed'])
        self.assertEqual(len(result['observations']),5)
        self.assertFalse(result['files']['nvngx_dlssnr.dll']['present'])

    def test_diagnostics_refuses_linked_log(self):
        (self.game/'OptiScaler.log').symlink_to(self.dll)
        self.assertIn('No readable OptiScaler log.',diag.inspect(self.row)['observations'])

    def test_report_defaults_exclude_notes_and_logs(self):
        game_notes.save(self.config,self.row['game'],{'status':'Problem','notes':'secret note','sessions':[]})
        files=game_notes.preview(self.config,[self.row]);payload=json.loads(files['library.json'])
        self.assertNotIn('notes',payload[0]);self.assertFalse(any(n.startswith('logs/') for n in files))
        self.assertNotIn('secret note',str(files));self.assertNotIn(str(self.game),str(files))

    def test_redaction_and_exact_preview_export(self):
        import zipfile
        text='Authorization: Bearer abc123\npassword=secret\n/home/alice/private\nC:\\Users\\Alice\\file\n76561199012345678\na@example.org\n'
        redacted=game_notes.redact(text)
        for private in ('abc123','secret','alice','Alice','76561199012345678','a@example.org'):self.assertNotIn(private,redacted)
        files={'library.json':'{"approved":true}'};out=game_notes.export_preview(self.config,files)
        with zipfile.ZipFile(out) as z:self.assertEqual(z.read('library.json').decode(),files['library.json'])
        self.assertEqual(out.stat().st_mode & 0o777,0o600)

    def test_tool_apply_restore_preserves_save(self):
        plan=extra_tools.prepare(self.config,self.row,self.dll,'reshade')
        self.assertFalse((self.game/'dxgi.dll').exists())
        state=extra_tools.apply(self.config,plan);self.assertEqual((self.game/'dxgi.dll').read_bytes(),self.dll.read_bytes())
        extra_tools.restore(self.config,state);self.assertFalse((self.game/'dxgi.dll').exists())
        self.assertEqual((self.game/'save.dat').read_bytes(),b'valuable save')

    def test_tool_refuses_collision_and_drift(self):
        plan=extra_tools.prepare(self.config,self.row,self.dll,'reshade')
        (self.game/'dxgi.dll').write_bytes(b'existing provider')
        with self.assertRaises(t.Refusal):extra_tools.apply(self.config,plan)
        with self.assertRaises(t.Refusal):extra_tools.prepare(self.config,self.row,self.dll,'reshade')
        self.assertEqual((self.game/'dxgi.dll').read_bytes(),b'existing provider')

    def test_tool_restore_refuses_modified_tool(self):
        state=extra_tools.apply(self.config,extra_tools.prepare(self.config,self.row,self.dll,'reshade'))
        (self.game/'dxgi.dll').write_bytes(pe()+b'new user version')
        with self.assertRaises(t.Refusal):extra_tools.restore(self.config,state)

    def test_addon_needs_reshade_and_stays_separate(self):
        addon=self.root/'renodx-test.addon64';addon.write_bytes(pe()+b'addon')
        with self.assertRaises(t.Refusal):extra_tools.prepare(self.config,self.row,addon,'addon')
        (self.game/'dxgi.dll').write_bytes(self.dll.read_bytes())
        plan=extra_tools.prepare(self.config,self.row,addon,'addon');self.assertEqual(plan['changes'][0]['path'],addon.name)

    def test_controller_edges_and_repeats(self):
        edges=controls.Edges()
        self.assertEqual(edges.update({'accept','down'},0),['accept','down'])
        self.assertEqual(edges.update({'accept','down'},0.2),[])
        self.assertEqual(edges.update({'accept','down'},0.5),['down'])
        self.assertEqual(edges.update(set(),0.6),[])
        self.assertEqual(edges.update({'accept'},0.7),['accept'])
        self.assertEqual(controls.family(7),'playstation');self.assertEqual(controls.family(999),'generic')

    def test_metadata_without_id_or_online_art_preserves_local_art(self):
        settings={**library_media.DEFAULTS,'online_art':False}
        media=library_media.LibraryMedia(self.config,settings)
        def request(url,**kwargs):
            if 'storesearch?' in url:return {'items':[{'name':'Test Game','id':123}]}
            return {'123':{'success':True,'data':{'short_description':'A game','developers':['Dev']}}}
        with patch.object(media,'steam_art',return_value={'poster':'local.png'}),patch.object(library_media,'json_request',side_effect=request):
            result=media.enrich(self.row)
        self.assertEqual(result['description'],'A game');self.assertEqual(result['poster'],'local.png')
        self.assertEqual(result['metadata_appid'],'123');self.assertNotIn('appid',self.row)

    def test_ambiguous_metadata_does_not_guess(self):
        media=library_media.LibraryMedia(self.config,{**library_media.DEFAULTS,'online_art':False})
        with patch.object(media,'steam_art',return_value={}),patch.object(library_media,'json_request',return_value={'items':[{'name':'Test Game','id':1},{'name':'Test Game','id':2}]}) as request:
            result=media.enrich(self.row)
        self.assertNotIn('metadata_appid',result);self.assertEqual(request.call_count,1)

if __name__=='__main__':unittest.main()
