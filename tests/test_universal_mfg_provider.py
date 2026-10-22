"""Universal MFG as an OptiScaler plugin: pinned sourcing, INI ownership and target checks."""
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
import universal_mfg_provider as provider
import skynizz_provider
import transactions as t

# The real platform-independent INI helpers, without the POSIX terminal runtime.
tree = ast.parse((ROOT / 'engine/rtxengine.py').read_text(encoding='utf-8'))
helpers = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                         and node.name in ('_section_span', 'set_ini_value')], type_ignores=[])
namespace = {'re': re}
exec(compile(helpers, 'engine-ini-helpers', 'exec'), namespace)
set_ini_value = namespace['set_ini_value']


def amd64(extra=b''):
    dll = bytearray(128)
    dll[:2] = b'MZ'
    dll[60:64] = (64).to_bytes(4, 'little')
    dll[64:70] = b'PE\0\0\x64\x86'
    return bytes(dll) + extra


class UniversalMfgTest(unittest.TestCase):
    def test_pinned_identity_matches_source_and_rejects_changes(self):
        pinned = provider.pinned()
        self.assertEqual(provider.validate(pinned), pinned)
        self.assertEqual(pinned['commit'], '29504cdd5d209a25e3b91e809a7e0d6f9db8cbdc')
        for key, value in [('url', 'https://example.org/MFGUnlocker-v1.6.1.zip'), ('sha256', 'a' * 64),
                           ('commit', 'a' * 40), ('version', '1.6.2'), ('release_size', 1), ('id', 'mfg-unlock')]:
            with self.subTest(key=key), self.assertRaises(t.Refusal):
                provider.validate(pinned | {key: value})
        changed = copy.deepcopy(pinned)
        changed['dll']['sha256'] = 'b' * 64
        with self.assertRaises(t.Refusal):
            provider.validate(changed)
        changed = copy.deepcopy(pinned)
        changed['notices'].pop('NOTICE.md')
        with self.assertRaises(t.Refusal):
            provider.validate(changed)

    def test_component_dispatch_by_recorded_id(self):
        import ada_mfg_provider
        self.assertIs(skynizz_provider.mfg_component_module(provider.pinned()), provider)
        self.assertIs(skynizz_provider.mfg_component_module(ada_mfg_provider.pinned()), ada_mfg_provider)

    def test_payload_is_only_the_verified_plugin_and_notices(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            dll = amd64()
            archive = folder / 'MFGUnlocker-v1.6.1.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('MFGUnlocker.dll', dll)
                bundle.writestr('../never-extract.dll', b'never')
            notice = folder / 'notice'
            notice.write_bytes(b'legal fixture')
            record = provider.pinned()
            record.update(sha256=t.digest(archive), release_size=archive.stat().st_size,
                          dll={'sha256': hashlib.sha256(dll).hexdigest(), 'size': len(dll)})
            for value in record['notices'].values():
                value.update(sha256=t.digest(notice), release_size=notice.stat().st_size)
            known = {'1.6.1': (record['commit'], record['sha256'], record['release_size'], record['dll']['sha256'], len(dll))}
            download = lambda url, *args, **kwargs: archive if url == record['url'] else notice
            with patch.object(provider, 'KNOWN', known), patch.object(provider, 'storage', return_value=folder), \
                 patch.object(provider.packages, 'download', side_effect=download):
                data = provider.load_payload({}, record)
                self.assertEqual(data[provider.PLUGIN], dll)
                self.assertEqual(set(data), {provider.PLUGIN, 'OptiScaler/licenses/MFG-Unlocker-LICENSE.txt',
                                             'OptiScaler/licenses/MFG-Unlocker-NOTICE.md'})
                self.assertFalse((folder.parent / 'never-extract.dll').exists())
                with zipfile.ZipFile(archive, 'w') as bundle:
                    bundle.writestr('MFGUnlocker.dll', amd64(b'drift'))
                with self.assertRaises(t.Refusal):
                    provider.load_payload({}, record)

    def test_ini_hands_the_unlock_to_the_plugin_and_keeps_native_dlssg(self):
        e = SimpleNamespace(set_ini_value=set_ini_value, Y4MY_PROVIDER={'mfg_component': provider.pinned()},
                            visual_defaults=lambda nr, mfg, sharp: {'DLSSG': {'OverrideInterpolationCount': '3'}})
        source = b'[DLSSG]\nAdaMfgUnlock=true\nAdaBlackwellKernels=true\n[FrameGen]\nEnabled=true\n[Plugins]\nLoadAsiPlugins=false\n[DlssNr]\nEnabled=true\n'
        text, _ = skynizz_provider.configure(e, source, mode='nr-mfg', mfg_multiplier=4)
        for key, value in {'AdaMfgUnlock': 'false', 'AdaBlackwellKernels': 'false', 'AmpereMfgUnlock': 'false'}.items():
            self.assertRegex(text, rf'(?m)^{key}=\s*{value}\b')
        self.assertRegex(text, r'(?m)^LoadAsiPlugins=\s*true\b')
        # The game's own DLSS-G stays the FG path; OptiScaler keeps the requested count.
        self.assertRegex(text, r'(?m)^FGOutput=\s*nofg\b')
        self.assertRegex(text, r'(?m)^OverrideInterpolationCount=\s*3\b')
        self.assertNotRegex(text, r'(?m)^LoadReShade=\s*true\b')

    def test_refuses_manual_unlocker_installs_and_component_switches(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            e = SimpleNamespace(Y4MY_PROVIDER={'mfg_component': provider.pinned()})
            game = SimpleNamespace(target_dir=target)
            provider.check_target(e, game, None)
            for name in ('RTXMFG.ini', 'RTX40MFGCore.dll', 'MFGUnlocker.dll'):
                (target / name).write_bytes(b'manual')
                with self.subTest(name=name), self.assertRaisesRegex(t.Refusal, 'unmanaged MFG Unlocker'):
                    provider.check_target(e, game, None)
                (target / name).unlink()
            plugin = target / provider.PLUGIN
            plugin.parent.mkdir(parents=True)
            plugin.write_bytes(b'manual plugin')
            with self.assertRaisesRegex(t.Refusal, 'unmanaged MFG Unlocker plugin'):
                provider.check_target(e, game, None)
            integrated = {'current': {'archive': {'release': {}}}}
            with self.assertRaisesRegex(t.Refusal, 'Restore before changing MFG components'):
                provider.check_target(e, game, integrated)
            # Repairing the same recorded component is allowed with its own plugin present.
            same = {'current': {'archive': {'release': {'mfg_component': provider.pinned()}}}}
            provider.check_target(e, game, same)

    def test_plugin_run_reports_left_by_a_restore_do_not_block_reinstall(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            e = SimpleNamespace(Y4MY_PROVIDER={'mfg_component': provider.pinned()})
            (target / 'RTXMFG-halocampaignevolved-B3DAE402A7B7D259.log').write_text('run')
            (target / 'RTXMFG-halocampaignevolved-B3DAE402A7B7D259-intervals.csv').write_text('ms\n8.3\n')
            (target / provider.STATUS).write_text('{}')
            provider.check_target(e, SimpleNamespace(target_dir=target), None)

    def test_dynamic_support_follows_the_plugin_report(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertIsNone(provider.dynamic_support(target))
            for report, expected in [({'dynamicMfgSupportKnown': True, 'dynamicMfgSupported': True}, True),
                                     ({'dynamicMfgSupportKnown': True, 'dynamicMfgSupported': False}, False),
                                     ({'dynamicMfgSupportKnown': False, 'dynamicMfgSupported': False}, None),
                                     ([], None)]:
                with self.subTest(report=report):
                    (target / provider.STATUS).write_text(json.dumps(report))
                    self.assertIs(provider.dynamic_support(target), expected)
            (target / provider.STATUS).write_text('{not json')
            self.assertIsNone(provider.dynamic_support(target))

    def test_dynamic_preset_is_refused_only_where_the_plugin_reported_no_support(self):
        e = SimpleNamespace(set_ini_value=set_ini_value, Y4MY_PROVIDER={'mfg_component': provider.pinned()},
                            visual_defaults=lambda nr, mfg, sharp: {'DLSSG': {}})
        with tempfile.TemporaryDirectory() as directory:
            game = SimpleNamespace(target_dir=Path(directory), exe=None, appid=None)
            dynamic = {'multiplier': 4, 'dynamic_mfg': 1}
            text, _ = skynizz_provider.configure(e, b'[DLSSG]\n', mode='nr-mfg', game=game, controls=dynamic)
            self.assertRegex(text, r'(?m)^OverrideForceDMFG=\s*true\b')
            (game.target_dir / provider.STATUS).write_text(json.dumps({'dynamicMfgSupportKnown': True, 'dynamicMfgSupported': False}))
            with self.assertRaisesRegex(t.Refusal, 'Dynamic'):
                skynizz_provider.configure(e, b'[DLSSG]\n', mode='nr-mfg', game=game, controls=dynamic)
            skynizz_provider.configure(e, b'[DLSSG]\n', mode='nr-mfg', game=game, controls={'multiplier': 4, 'dynamic_mfg': 0})


if __name__ == '__main__':
    unittest.main()
