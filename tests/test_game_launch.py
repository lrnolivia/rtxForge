import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import game_launch
from controller_input import family, GLYPHS

class LaunchTests(unittest.TestCase):
    def test_store_id_only_for_actual_steam_install(self):
        self.assertEqual(game_launch.resolve({}, {'source':'Steam','appid':'123'}),'steam://rungameid/123')
        for bad in (None,'',0,'12/../1',-1,2**32):
            with self.assertRaises(ValueError):game_launch.steam_uri(bad)

    def test_shortcut_id_signed_and_unsigned(self):
        expected=f'steam://rungameid/{(0x87654321<<32)|0x02000000}'
        self.assertEqual(game_launch.steam_uri(0x87654321,shortcut=True),expected)
        self.assertEqual(game_launch.steam_uri(0x87654321-2**32,shortcut=True),expected)
        with self.assertRaises(ValueError):game_launch.steam_uri(None,shortcut=True)

    def test_existing_shortcut_uses_path_match_not_enrichment_id(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);shortcuts=root/'shortcuts.vdf';shortcuts.write_bytes(b'fixture')
            engine=SimpleNamespace(choose_steam_user_config=Mock(return_value={'shortcuts':shortcuts}),parse_shortcuts_spans=Mock(return_value=['shortcut']),match_shortcut_span=Mock(return_value='exact-match'),_shortcut_int=Mock(return_value=0x87654321))
            row={'source':'Folder','appid':'999','name':'Game','game':str(root),'exe':'Game.exe'}
            self.assertEqual(game_launch.resolve({},row,engine=engine),game_launch.steam_uri(0x87654321,shortcut=True))
            game=engine.match_shortcut_span.call_args.args[0]
            self.assertIsNone(game.appid);self.assertEqual(game.exe,root/'Game.exe')
            self.assertEqual(shortcuts.read_bytes(),b'fixture')
            engine.match_shortcut_span.return_value=None
            with self.assertRaisesRegex(ValueError,'unique'):game_launch.resolve({},row,engine=engine)
            engine.choose_steam_user_config.return_value=None
            with self.assertRaisesRegex(ValueError,'configured launcher'):game_launch.resolve({},row,engine=engine)
            row['exe']='../outside.exe'
            with self.assertRaisesRegex(ValueError,'executable'):game_launch.resolve({},row,engine=engine)

    def test_diagnostics_distinguish_resolution_submission_and_failure(self):
        events=[]
        record=lambda _,event:events.append(event)
        row={'source':'Steam','appid':'123','name':'Fixture','game':'/fixture','launch_options':'SECRET'}
        request=game_launch.prepare_launch({},row,recorder=record)
        game_launch.dispatch_launch({},request,lambda uri:None,recorder=record)
        self.assertEqual([e['phase'] for e in events],['resolving','resolved','submitted'])
        self.assertEqual(len({e['request_id'] for e in events}),1)
        self.assertNotIn('SECRET',str(events))
        def fail(uri):raise RuntimeError('URI handler unavailable')
        with self.assertRaises(RuntimeError):game_launch.dispatch_launch({},request,fail,recorder=record)
        self.assertEqual(events[-1]['phase'],'dispatch-failed')
        with self.assertRaises(ValueError):game_launch.prepare_launch({},dict(row,appid=None),recorder=record)
        self.assertEqual(events[-1]['phase'],'resolution-failed')

    def test_optional_diagnostic_failure_does_not_block_launch(self):
        def fail(*args):raise RuntimeError('State directory unavailable')
        request=game_launch.prepare_launch({}, {'source':'Steam','appid':'123'},recorder=fail)
        dispatch=Mock()
        game_launch.dispatch_launch({},request,dispatch,recorder=fail)
        dispatch.assert_called_once_with('steam://rungameid/123')

    def test_bounded_private_diagnostic_file(self):
        import json
        with TemporaryDirectory() as directory:
            config={'storage':{'root':directory,'reserve_bytes':0}}
            game_launch.record_launch(config,{'phase':'submitted'})
            path=Path(directory)/'desktop/launch-logs/requests.jsonl'
            self.assertEqual(json.loads(path.read_text())['phase'],'submitted')
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            path.write_text('x'*1024*1024)
            game_launch.record_launch(config,{'phase':'resolved'})
            self.assertEqual(json.loads(path.read_text())['phase'],'resolved')
            self.assertEqual(path.with_name('requests.previous.jsonl').stat().st_size,1024*1024)

    def test_steam_controller_name_and_existing_families(self):
        self.assertEqual(family(0,'Steam Controller'),'steam')
        self.assertEqual(family(0,'Steam Virtual Gamepad'),'steam')
        self.assertEqual(GLYPHS['steam'][:3],('A','B','Y'))
        self.assertEqual(family(7,'DualSense'),'playstation')
        self.assertEqual(family(999),'generic')

if __name__=='__main__':unittest.main()
