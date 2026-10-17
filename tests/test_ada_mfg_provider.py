"""Immutable addon sourcing and independent configuration ownership."""
import ast
import copy
import hashlib
import json
import re
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ada_mfg_provider as provider
import skynizz_provider
import transactions as t

# Load the real platform-independent INI helpers without importing the POSIX
# terminal runtime. The Windows lifecycle test loads the complete host adapter.
tree = ast.parse((ROOT / 'engine/rtxengine.py').read_text(encoding='utf-8'))
helpers = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                         and node.name in ('_section_span', 'set_ini_value')], type_ignores=[])
namespace = {'re': re}
exec(compile(helpers, 'engine-ini-helpers', 'exec'), namespace)
engine = SimpleNamespace(set_ini_value=namespace['set_ini_value'])


class AdaMfgTest(unittest.TestCase):
    def test_saved_recipe_rejects_changed_binary_host_or_source(self):
        pinned = provider.pinned()
        self.assertEqual(provider.validate(pinned), pinned)
        for key, value in [('url', 'https://example.org/other.addon64'), ('sha256', 'a' * 64),
                           ('commit', 'a' * 40), ('version', '1.4.5'), ('release_size', 1)]:
            with self.subTest(key=key), self.assertRaises(t.Refusal):
                provider.validate(pinned | {key: value})
        for key in ('sha256', 'dll_sha256', 'url'):
            changed = copy.deepcopy(pinned)
            changed['host'][key] = 'a' * 64
            with self.subTest(host=key), self.assertRaises(t.Refusal):
                provider.validate(changed)
        changed = copy.deepcopy(pinned)
        changed['notices'] = {}
        with self.assertRaises(t.Refusal):
            provider.validate(changed)

    def test_payload_extracts_only_verified_host_and_addon_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            # A minimal valid AMD64 fixture, plus an unselected ZIP member.
            dll = bytearray(128)
            dll[:2] = b'MZ'
            dll[60:64] = (64).to_bytes(4, 'little')
            dll[64:70] = b'PE\0\0\x64\x86'
            dll = bytes(dll)
            addon = folder / 'addon'; addon.write_bytes(dll)
            setup = folder / 'setup.exe'
            with zipfile.ZipFile(setup, 'w') as archive:
                archive.writestr('ReShade64.dll', dll)
                archive.writestr('../never-extract.exe', b'never execute')
            record = provider.pinned()
            record.update(sha256=hashlib.sha256(dll).hexdigest(), release_size=len(dll))
            host = record['host']
            host.update(sha256=t.digest(setup), release_size=setup.stat().st_size,
                        dll_sha256=hashlib.sha256(dll).hexdigest(), dll_size=len(dll))
            notice = folder / 'notice'; notice.write_bytes(b'legal fixture')
            for value in record['notices'].values():
                value.update(sha256=t.digest(notice), release_size=notice.stat().st_size)
            def download(url, *args, **kwargs):
                if isinstance(url, provider.urllib.request.Request):
                    self.assertEqual(url.get_header('User-agent'), 'rtxForge/1.0')
                    url = url.full_url
                return setup if url == host['url'] else addon if url == record['url'] else notice
            with patch.object(provider, 'KNOWN', {'1.4.4': (record['commit'], record['sha256'], len(dll))}), \
                 patch.object(provider, 'HOST', (host['sha256'], host['release_size'], host['dll_sha256'], len(dll))), \
                 patch.object(provider, 'storage', return_value=folder), patch.object(provider.packages, 'download', side_effect=download):
                data = provider.load_payload({}, record)
                self.assertEqual(data['ReShade64.dll'], dll)
                self.assertEqual(data['renodx-mfgunlock.addon64'], dll)
                self.assertEqual(len(data), 4)
                self.assertFalse((folder.parent / 'never-extract.exe').exists())
                addon.write_bytes(dll + b'drift')
                with self.assertRaises(t.Refusal):
                    provider.load_payload({}, record)

    def test_fixed_four_and_repair_preserve_separate_addon_preset(self):
        with tempfile.TemporaryDirectory() as directory:
            game = SimpleNamespace(target_dir=Path(directory))
            e = SimpleNamespace(set_ini_value=engine.set_ini_value)
            path = game.target_dir / 'ReShade.ini'
            path.write_text('[Other]\nKeep=1\n')
            text = provider.configure(e, game, None, 4).decode()
            self.assertIn('ForceMultiplier=4', text)
            self.assertIn('DynamicMFG=0', text)
            self.assertIn('Keep=1', text)
            text = text.replace('ForceMultiplier=4', 'ForceMultiplier=3') + '\n; user tuning\n'
            path.write_bytes(text.encode())
            baseline = {'current': {'archive': {'release': {'mfg_component': provider.pinned()}}}}
            self.assertEqual(provider.configure(e, game, baseline, 6).decode(), text)
            self.assertEqual(provider.configured_state(game.target_dir, provider.pinned())['mfg_multiplier'], 3)
            with self.assertRaises(t.Refusal):
                provider.configure(e, game, None, 4)
            path.write_text('malformed settings')
            with self.assertRaises(t.Refusal):
                provider.configured_state(game.target_dir, provider.pinned())


if __name__ == '__main__':
    unittest.main()
