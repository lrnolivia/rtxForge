"""In-game panel host side under Proton: prefix registry preferences and the file-backed channel."""
from pathlib import Path
import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture as fx
import proton_overlay as overlay

ROOT = Path(__file__).resolve().parents[2]


class ShortcutTest(unittest.TestCase):
    def test_matches_the_windows_shortcut_vocabulary(self):
        self.assertEqual(overlay.parse_shortcut('Backtick'), ('Backtick', 0, 0xC0))
        self.assertEqual(overlay.parse_shortcut('shift+ctrl+f8'), ('Ctrl+Shift+F8', 6, 0x77))
        self.assertEqual(overlay.parse_shortcut('Disabled'), ('Disabled', 0, 0))
        # Retired defaults move to Delete; Insert and End belong to OptiScaler.
        for retired in ('Insert', 'End', '', None):
            self.assertEqual(overlay.parse_shortcut(retired), ('Delete', 0, 0x2E))
        for bad in ('F12', 'Win+A', 'Ctrl+Ctrl+A', 'Alt+F4', 'Ctrl+Alt+Delete', 'Hyper'):
            with self.subTest(bad=bad), self.assertRaises(overlay.OverlayError):
                overlay.parse_shortcut(bad)

    def test_windows_key_table_is_the_same(self):
        source = (ROOT / 'windows/RtxForge.Windows/Services/OverlayShortcut.cs').read_text()
        import re
        for name, code in re.findall(r'\["(\w+)"\] = (0x[0-9A-F]+|\d+)', source):
            self.assertEqual(overlay._KEYS[name], int(code, 0), name)

    def test_preferences_are_the_dwords_the_bridge_reads(self):
        values = overlay.preferences({'overlay_renderer': 'game', 'panel_hotkey': 'Backtick', 'overlay_controls': 'classic',
                                      'optiscaler_ui': True, 'optiscaler_hotkey': 'F8'})
        self.assertEqual(values, {'InGamePanel': 1, 'PanelKey': 192, 'PanelModifiers': 0, 'Advanced': 1,
                                  'UseOptiScaler': 1, 'ShortcutKey': 0x77})
        off = overlay.preferences({'overlay_renderer': 'standalone', 'optiscaler_ui': False, 'optiscaler_hotkey': 'Disabled'})
        self.assertEqual((off['InGamePanel'], off['UseOptiScaler'], off['ShortcutKey']), (0, 0, 0))
        for bad in ({'overlay_renderer': 'vulkan'}, {'optiscaler_ui': 'yes'}, {'optiscaler_hotkey': 'Home'}):
            with self.assertRaises(overlay.OverlayError):
                overlay.preferences(bad)
        bridge = (ROOT / 'providers/skynizz-bridge/ForgePanel.h').read_text()
        for name in ('InGamePanel', 'PanelKey', 'PanelModifiers', 'Advanced'):
            self.assertIn(f'Preference(L"{name}"', bridge)


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        lib = fx.proton(self.root)
        self.prefix = fx.prefix(self.root / 'library', 870780, lib)
        self.registry = self.prefix / 'user.reg'
        self.state = self.root / 'state'
        self.idle = fx.idle_proc(self.root)
        self.exe = self.root / 'library' / 'steamapps' / 'common' / 'Control' / 'Control_DX12.exe'
        self.settings = {'overlay_renderer': 'game', 'panel_hotkey': 'Backtick'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_edit_keeps_every_other_byte_and_reads_back(self):
        text = self.registry.read_text()
        edited = overlay.edit_values(text, overlay.OVERLAY_KEY, {'PanelKey': overlay.dword(192)})
        self.assertTrue(edited.startswith(text.rstrip('\n')))
        self.assertIn('[Software\\\\rtxForge\\\\Overlay] ', edited)
        self.assertEqual(overlay.read_values(edited, overlay.OVERLAY_KEY), {'PanelKey': 'dword:000000c0'})
        self.assertEqual(overlay.edit_values(edited, overlay.OVERLAY_KEY, {'PanelKey': None}).count('PanelKey'), 0)
        # Key and value names are case-insensitive, as in Wine.
        again = overlay.edit_values(edited, 'software\\RTXFORGE\\overlay', {'panelkey': overlay.dword(46)})
        self.assertEqual(overlay.read_values(again, overlay.OVERLAY_KEY), {'panelkey': 'dword:0000002e'})
        self.assertEqual(again.count('[Software\\\\rtxForge\\\\Overlay]'), 1)

    def test_strings_escape_backslashes_quotes_and_unicode(self):
        value = overlay.string('#EC3D28|Control "Ultimate" — é')
        self.assertEqual(value, '"#EC3D28|Control \\"Ultimate\\" \\x2014 \\x00e9"')
        text = overlay.edit_values('', overlay.GAMES_KEY, {'Z:\\games\\Control.exe': value})
        self.assertIn('"Z:\\\\games\\\\Control.exe"=', text)
        self.assertEqual(overlay.read_values(text, overlay.GAMES_KEY), {'Z:\\games\\Control.exe': value})

    def test_dos_paths_follow_dosdevices(self):
        paths = overlay.dos_paths(self.prefix, self.exe)
        self.assertEqual(paths[0], 'Z:' + str(self.exe).replace('/', '\\'))
        os.symlink(str(self.root / 'library'), self.prefix / 'dosdevices' / 'd:')
        self.assertEqual(overlay.dos_paths(self.prefix, self.exe)[0], 'D:\\steamapps\\common\\Control\\Control_DX12.exe')

    def test_review_apply_restore_round_trip_keeps_user_edits(self):
        original = self.registry.read_bytes()
        plan = overlay.plan(self.prefix, self.settings, self.exe, 'Control', '#ec3d28', proc=self.idle)
        self.assertEqual(self.registry.read_bytes(), original, 'review never writes')
        self.assertEqual(set(plan['changes'][overlay.OVERLAY_KEY]), set(overlay.PANEL_VALUES))
        self.assertIn('applies next launch', plan['summary'])
        overlay.apply(plan, self.state, proc=self.idle)
        values = overlay.read_values(self.registry.read_text(), overlay.OVERLAY_KEY)
        self.assertEqual(values['InGamePanel'], 'dword:00000001')
        self.assertEqual(values['PanelKey'], 'dword:000000c0')
        games = overlay.read_values(self.registry.read_text(), overlay.GAMES_KEY)
        self.assertEqual(games['Z:' + str(self.exe).replace('/', '\\')], '"#EC3D28|Control"')
        self.assertTrue(overlay.plan(self.prefix, self.settings, self.exe, 'Control', '#EC3D28', proc=self.idle)['unchanged'])
        # The person changes one value in the prefix themselves; restore keeps it.
        text = overlay.edit_values(self.registry.read_text(), overlay.OVERLAY_KEY, {'PanelKey': overlay.dword(0x2E)})
        self.registry.write_text(text)
        result = overlay.restore(self.state, proc=self.idle)
        self.assertEqual(result['kept'], ['PanelKey'])
        remaining = overlay.read_values(self.registry.read_text(), overlay.OVERLAY_KEY)
        self.assertEqual(remaining, {'PanelKey': 'dword:0000002e'})
        self.assertEqual(overlay.restore(self.state, proc=self.idle), {'status': 'none'})

    def test_restore_returns_exact_original_bytes_when_untouched(self):
        original = self.registry.read_text()
        overlay.apply(overlay.plan(self.prefix, self.settings, proc=self.idle), self.state, proc=self.idle)
        overlay.restore(self.state, proc=self.idle)
        restored = self.registry.read_text()
        # Only the now-empty key header (with its timestamp) remains.
        self.assertTrue(restored.startswith(original.rstrip('\n')))
        self.assertEqual(overlay.read_values(restored, overlay.OVERLAY_KEY), {})

    def test_existing_values_are_recorded_and_returned(self):
        seeded = overlay.edit_values(self.registry.read_text(), overlay.OVERLAY_KEY, {'PanelKey': overlay.dword(0x91)})
        self.registry.write_text(seeded)
        overlay.apply(overlay.plan(self.prefix, self.settings, proc=self.idle), self.state, proc=self.idle)
        overlay.restore(self.state, proc=self.idle)
        self.assertEqual(overlay.read_values(self.registry.read_text(), overlay.OVERLAY_KEY), {'PanelKey': 'dword:00000091'})

    def test_running_prefix_and_drift_refuse_without_writing(self):
        busy = fx.busy_proc(self.root, self.prefix)
        with self.assertRaisesRegex(overlay.OverlayError, 'running'):
            overlay.plan(self.prefix, self.settings, proc=busy)
        plan = overlay.plan(self.prefix, self.settings, proc=self.idle)
        with self.assertRaisesRegex(overlay.OverlayError, 'running'):
            overlay.apply(plan, self.state, proc=busy)
        self.registry.write_text(self.registry.read_text() + '[Software\\\\Other] 1\n')
        changed = self.registry.read_bytes()
        with self.assertRaisesRegex(overlay.OverlayError, 'changed since review'):
            overlay.apply(plan, self.state, proc=self.idle)
        self.assertEqual(self.registry.read_bytes(), changed)
        self.assertFalse((self.state / overlay.RECORD_NAME).exists())

    def test_unlaunched_game_refuses(self):
        with self.assertRaisesRegex(overlay.OverlayError, 'not been started'):
            overlay.plan(self.root / 'nowhere', self.settings, proc=self.idle)


class PanelSide:
    """What ForgePanelChannel.h does inside the game, byte for byte."""

    def __init__(self, path):
        self.path = path
        data = bytearray(overlay.SIZE)
        struct.pack_into('<10i', data, 0, overlay.MAGIC, 1, 4242, 0, 0, 1, 0, 0, 0, 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(data))
        self.last_revision = 0

    def field(self, index):
        with open(self.path, 'rb') as handle:
            handle.seek(index * 4)
            return struct.unpack('<i', handle.read(4))[0]

    def send(self, request):
        body = json.dumps(request).encode()
        with open(self.path, 'r+b') as handle:
            handle.seek(12)
            current = struct.unpack('<i', handle.read(4))[0]
            following = current + 2 if current < 0x7fffff00 else 2
            handle.seek(12); handle.write(struct.pack('<i', following | 1))
            handle.seek(64); handle.write(body)
            handle.seek(24); handle.write(struct.pack('<i', len(body)))
            handle.seek(12); handle.write(struct.pack('<i', following))
        return following

    def poll(self):
        revision, request, response = self.field(8), self.field(3), self.field(4)
        if revision == 0 or revision & 1 or revision == self.last_revision or response != request:
            return None
        length = self.field(7)
        with open(self.path, 'rb') as handle:
            handle.seek(64 + overlay.CAPACITY)
            body = handle.read(length)
        self.last_revision = revision
        return json.loads(body)


class ChannelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = overlay.channel_path(Path(self.tmp.name) / 'pfx', 4242)
        self.panel = PanelSide(self.path)
        self.host = overlay.PanelChannelFile(self.path)

    def tearDown(self):
        self.host.close()
        self.tmp.cleanup()

    def test_layout_matches_the_native_header(self):
        header = (ROOT / 'providers/skynizz-bridge/ForgePanelChannel.h').read_text()
        self.assertIn('constexpr LONG Magic = 0x%08X;' % overlay.MAGIC, header)
        self.assertIn('constexpr size_t Capacity = %d;' % overlay.CAPACITY, header)
        self.assertIn('static_assert(offsetof(Header,requestData) == 64);', header)
        self.assertEqual(self.path.name, 'panel.4242.map')

    def test_hello_round_trip_and_each_request_is_answered_once(self):
        self.assertTrue(self.host.visible)
        self.assertIsNone(self.host.try_read())
        request = self.panel.send({'op': 'hello'})
        rid, message = self.host.try_read()
        self.assertEqual((rid, message), (request, {'op': 'hello'}))
        self.assertIsNone(self.host.try_read(), 'already handled')
        self.host.reply(rid, overlay.handle(message, {'panel_hotkey': 'Backtick'}))
        response = self.panel.poll()
        self.assertEqual(response['op'], 'hello')
        self.assertEqual((response['settings']['panel_key'], response['settings']['panel_modifiers']), (192, 0))
        self.assertIsNone(self.panel.poll(), 'same revision is not re-read')
        self.assertEqual(self.host.header()['revision'] % 2, 0)

    def test_writes_stay_in_the_app_until_the_linux_helper_exists(self):
        rid, message = (self.panel.send({'op': 'save', 'changes': {'intensity': 1.0}}), None)
        rid, message = self.host.try_read()
        self.host.reply(rid, overlay.handle(message, {}))
        response = self.panel.poll()
        self.assertTrue(response['error'])
        self.assertIn('Use rtxForge on Linux', response['message'])

    def test_half_written_requests_and_bad_files_are_ignored(self):
        with open(self.path, 'r+b') as handle:
            handle.seek(12); handle.write(struct.pack('<i', 3))   # odd: panel still writing
        self.assertIsNone(self.host.try_read())
        with self.assertRaises(FileNotFoundError):
            overlay.PanelChannelFile(Path(self.tmp.name) / 'missing.map')
        short = Path(self.tmp.name) / 'short.map'
        short.write_bytes(b'0' * 10)
        with self.assertRaises(FileNotFoundError):
            overlay.PanelChannelFile(short)

    def test_response_fields_satisfy_the_native_validator(self):
        response = overlay.handle({'op': 'status'}, {})
        for name in ('overlay_controls', 'overlay_renderer', 'panel_hotkey', 'optiscaler_hotkey'):
            self.assertIsInstance(response['settings'][name], str)
        for name in ('panel_key', 'panel_modifiers'):
            self.assertIs(type(response['settings'][name]), int)
        for name in ('overlay_helper', 'overlay_start_with_windows', 'optiscaler_ui', 'optiscaler_intro', 'reshade_ui', 'reshade_intro'):
            self.assertIs(type(response['settings'][name]), bool)
        self.assertIsInstance(response['status'], dict)


if __name__ == '__main__':
    unittest.main()
