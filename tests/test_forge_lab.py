"""Forge Lab copies launch with the authentication their protection needs."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import forge_lab  # noqa: E402


def pe(*names):
    """A minimal PE header with these section names."""
    data = bytearray(1024)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', data, 0x80 + 6, len(names))
    struct.pack_into('<H', data, 0x80 + 20, 0xF0)
    start = 0x80 + 24 + 0xF0
    for i, name in enumerate(names):
        data[start + 40 * i:start + 40 * i + 8] = name.encode().ljust(8, b'\0')
    return bytes(data)


class ForgeLab(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.copy = Path(self.tmp.name) / 'Forge Lab' / 'games-windows' / 'Game'
        (self.copy / 'Bin').mkdir(parents=True)

    def write(self, *names, extra=()):
        (self.copy / 'Bin' / 'Game.exe').write_bytes(pe('.text', *names))
        for name in extra:
            (self.copy / 'Bin' / name).write_bytes(b'')

    def test_steamworks_needs_steam_and_the_app_id_only(self):
        self.write(extra=('steam_api64.dll',))
        plan = forge_lab.plan(self.copy, 'Bin/Game.exe', 123)
        self.assertEqual((plan['protection'], plan['needs'], plan['env'], plan['appid']), ('steamworks', ['steam.exe'], {}, '123'))

    def test_steamstub_also_gets_steams_launch_variables(self):
        self.write('.bind', extra=('steam_api64.dll',))
        plan = forge_lab.plan(self.copy, 'Bin/Game.exe', 123)
        self.assertEqual(plan['protection'], 'steamstub')
        self.assertEqual(plan['env'], {'SteamAppId': '123', 'SteamGameId': '123', 'SteamOverlayGameId': '123'})

    def test_ea_needs_the_ea_app_and_no_steam_id(self):
        self.write('.ooa')
        plan = forge_lab.plan(self.copy, 'Bin/Game.exe', '')
        self.assertEqual((plan['protection'], plan['needs'], plan['appid']), ('ea', ['EADesktop.exe'], None))

    def test_ubisoft_is_reported(self):
        self.write(extra=('uplay_r1_loader64.dll',))
        self.assertEqual(forge_lab.plan(self.copy, 'Bin/Game.exe', '')['protection'], 'ubisoft')

    def test_a_store_install_is_never_launched_as_a_copy(self):
        store = Path(self.tmp.name) / 'SteamLibrary' / 'steamapps' / 'common' / 'Game'
        store.mkdir(parents=True); (store / 'Game.exe').write_bytes(pe('.text'))
        with self.assertRaises(ValueError):
            forge_lab.plan(store, 'Game.exe', 123)

    def test_steam_titles_need_an_app_id(self):
        self.write(extra=('steam_api64.dll',))
        with self.assertRaises(ValueError):
            forge_lab.plan(self.copy, 'Bin/Game.exe', '')

    def test_launch_refuses_while_the_store_is_closed(self):
        self.write(extra=('steam_api64.dll',))
        original = forge_lab.running
        forge_lab.running = lambda name: False
        try:
            with self.assertRaises(RuntimeError):
                forge_lab.launch(self.copy, 'Bin/Game.exe', 123)
        finally:
            forge_lab.running = original
        self.assertFalse((self.copy / 'Bin' / 'steam_appid.txt').exists())


if __name__ == '__main__':
    unittest.main()
