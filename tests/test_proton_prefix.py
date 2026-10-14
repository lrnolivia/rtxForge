from pathlib import Path
import sys, tempfile, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import proton_prefix as pp

# Shape of a real Proton prefix registry (pfx/user.reg).
USER_REG = '''WINE REGISTRY Version 2
;; All keys relative to REGISTRY\\\\User\\\\S-1-5-21-0-0-1000-1000

#arch=win64

[Software\\\\Wine\\\\AppDefaults\\\\Game.exe\\\\DllOverrides] 1788804309
#time=1dd3ef36b7f3bbe
"atiadlxx"="builtin"

[Software\\\\Wine\\\\DllOverrides] 1788804309
#time=1dd3ef36b7e21fc
"api-ms-win-crt-conio-l1-1-0"="native,builtin"
"atiadlxx"="disabled"
"winmm"="builtin"

[Software\\\\Wine\\\\Drivers] 1788804309
"Audio"="pulse"
'''


class ProtonPrefixTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.library = root / 'SteamLibrary' / 'steamapps'
        self.game = self.library / 'common' / 'Game'
        self.game.mkdir(parents=True)
        self.prefix = self.library / 'compatdata' / '1091500' / 'pfx'
        self.prefix.mkdir(parents=True)
        (self.prefix / 'user.reg').write_text(USER_REG)
        self.state = root / 'state'
        self.proc = root / 'proc'
        self.proc.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def registry(self):
        return (self.prefix / 'user.reg').read_text()

    def test_override_names_from_launch_options(self):
        self.assertEqual(pp.override_names('WINEDLLOVERRIDES="dxgi=n,b;winmm=n,b" %command%'), ['dxgi', 'winmm'])
        self.assertEqual(pp.override_names('WINEDLLOVERRIDES="dxgi,version=n,b" %command%'), ['dxgi', 'version'])
        self.assertEqual(pp.override_names('%command%'), [])

    def test_finds_prefix_in_the_games_library(self):
        self.assertEqual(pp.find_prefix(self.game, '1091500'), self.prefix)

    def test_missing_prefix_and_non_steam_have_next_steps(self):
        with self.assertRaisesRegex(pp.PrefixError, 'Play it once'):
            pp.find_prefix(self.game, '999')
        with self.assertRaisesRegex(pp.PrefixError, 'Close Steam'):
            pp.find_prefix(self.game, None)

    def test_apply_sets_only_the_needed_overrides(self):
        record = pp.apply(self.prefix, ['dxgi', 'winmm'], self.state, proc=self.proc)
        values = pp.read_overrides(self.registry())
        self.assertEqual(values['dxgi'], 'native,builtin')
        self.assertEqual(values['winmm'], 'native,builtin')
        self.assertEqual(values['atiadlxx'], 'disabled')
        self.assertEqual(record['original'], {'dxgi': None, 'winmm': 'builtin'})
        # Other sections are untouched, byte for byte.
        self.assertIn('[Software\\\\Wine\\\\Drivers] 1788804309\n"Audio"="pulse"\n', self.registry())
        self.assertIn('[Software\\\\Wine\\\\AppDefaults\\\\Game.exe\\\\DllOverrides] 1788804309\n#time=1dd3ef36b7f3bbe\n"atiadlxx"="builtin"\n', self.registry())

    def test_restore_returns_exactly_to_the_original(self):
        pp.apply(self.prefix, ['dxgi', 'winmm'], self.state, proc=self.proc)
        self.assertEqual(pp.restore(self.state, proc=self.proc)['status'], 'restored')
        self.assertEqual(self.registry(), USER_REG)
        self.assertIsNone(pp.load_record(self.state))

    def test_repair_keeps_the_first_original(self):
        pp.apply(self.prefix, ['winmm'], self.state, proc=self.proc)
        pp.apply(self.prefix, ['winmm'], self.state, proc=self.proc)
        pp.restore(self.state, proc=self.proc)
        self.assertEqual(pp.read_overrides(self.registry())['winmm'], 'builtin')

    def test_restore_keeps_values_the_person_changed(self):
        pp.apply(self.prefix, ['dxgi'], self.state, proc=self.proc)
        text = pp.edit_overrides(self.registry(), {'dxgi': 'native'})
        (self.prefix / 'user.reg').write_text(text)
        result = pp.restore(self.state, proc=self.proc)
        self.assertEqual(result['kept'], ['dxgi'])
        self.assertEqual(pp.read_overrides(self.registry())['dxgi'], 'native')

    def test_creates_the_section_when_missing(self):
        (self.prefix / 'user.reg').write_text('WINE REGISTRY Version 2\n\n#arch=win64\n')
        pp.apply(self.prefix, ['dxgi'], self.state, proc=self.proc)
        self.assertEqual(pp.read_overrides(self.registry()), {'dxgi': 'native,builtin'})
        pp.restore(self.state, proc=self.proc)
        self.assertEqual(pp.read_overrides(self.registry()), {})

    def test_running_game_blocks_changes(self):
        process = self.proc / '4242'
        process.mkdir()
        (process / 'environ').write_bytes(b'HOME=/home/x\0STEAM_COMPAT_DATA_PATH=' + str(self.prefix.parent).encode() + b'\0')
        with self.assertRaisesRegex(pp.PrefixError, 'running'):
            pp.apply(self.prefix, ['dxgi'], self.state, proc=self.proc)
        self.assertEqual(self.registry(), USER_REG)


if __name__ == '__main__':
    unittest.main()
