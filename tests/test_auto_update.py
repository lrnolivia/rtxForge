"""Update downloads and handoffs use fixture payloads; never launch an installer."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'windows/engine-host')]
import auto_update
import app_update
import app_updates


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b'real fixture bytes'
        self.info = dict(name='rtxForge-test.exe', sha256=hashlib.sha256(self.payload).hexdigest(),
                         size=len(self.payload), url=auto_update.PREFIX + 'beta/rtxForge-test.exe')

    def download(self, data=None):
        with patch.object(auto_update.urllib.request, 'urlopen', return_value=io.BytesIO(self.payload if data is None else data)):
            return auto_update.download(self.info, self.root)

    def test_verified_download_is_reused_without_network(self):
        path = self.download()
        self.assertEqual(path.read_bytes(), self.payload)
        with patch.object(auto_update.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            self.assertEqual(auto_update.download(self.info, self.root), path)

    def test_corrupt_cache_is_replaced_not_trusted(self):
        path = self.download()
        path.write_bytes(b'X' * len(self.payload))
        self.assertEqual(self.download().read_bytes(), self.payload)

    def test_truncated_oversized_and_wrong_hash_never_publish(self):
        for payload in (b'short', self.payload + b'extra', b'X' * len(self.payload)):
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                self.download(payload)
            self.assertEqual(list(self.root.rglob('*test.exe')), [])
            self.assertEqual(list(self.root.rglob('.download-*')), [])

    def test_interrupted_transfer_leaves_current_app_and_no_partial(self):
        current = self.root / 'current.exe'
        current.write_bytes(b'installed')
        class Broken(io.BytesIO):
            def read(self, size):
                raise OSError('connection lost')
        with patch.object(auto_update.urllib.request, 'urlopen', return_value=Broken()), self.assertRaises(OSError):
            auto_update.download(self.info, self.root)
        self.assertEqual(current.read_bytes(), b'installed')
        self.assertEqual(list(self.root.rglob('.download-*')), [])

    def test_invalid_release_facts_cannot_write_or_download(self):
        for changes in ({'name': '../outside.exe'}, {'name': 'C:\\outside.exe'}, {'sha256': 'bad'},
                        {'size': -1}, {'size': True}, {'url': 'https://example.com/evil.exe'}):
            with self.subTest(changes=changes), patch.object(auto_update.urllib.request, 'urlopen') as fetch:
                with self.assertRaises(ValueError):
                    auto_update.download({**self.info, **changes}, self.root)
                fetch.assert_not_called()

    def test_appimage_apply_rechecks_cache_and_preserves_channel(self):
        path = self.download()
        info = {**self.info, 'appimage': self.info['name'], 'format': 'appimage', 'update_channel': 'beta'}
        with patch.dict(os.environ, APPIMAGE='/installed/RTXForge.AppImage'), \
             patch.object(app_update.desktop_install, 'install_from', return_value='/installed/new') as install, \
             patch.object(app_update.desktop_install, 'record_channel') as channel:
            self.assertEqual(app_update.apply(info, path), '/installed/new')
            channel.assert_called_once_with('beta')
            path.write_bytes(b'corrupt')
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                app_update.apply(info, path)
            self.assertEqual(install.call_count, 1)

    def test_flatpak_updates_same_installation_and_reports_failure(self):
        path = self.download()
        info = {**self.info, 'appimage': self.info['name'], 'format': 'flatpak'}
        for location, scope in ((Path('/var/lib/flatpak/app/files'), '--system'),
                                (Path.home() / '.local/share/flatpak/app/files', '--user')):
            with patch.object(app_update.flatpak_host, 'host_files', return_value=location), \
                 patch.object(app_update.flatpak_host, 'run_host', return_value=types.SimpleNamespace(returncode=0)) as run:
                app_update.apply(info, path)
                self.assertEqual(run.call_args.args[0][:3], ['flatpak', 'install', scope])
        with patch.object(app_update.flatpak_host, 'host_files', return_value=Path('/var/lib/flatpak/app/files')), \
             patch.object(app_update.flatpak_host, 'run_host', return_value=types.SimpleNamespace(returncode=1, stderr='permission denied')):
            with self.assertRaisesRegex(RuntimeError, 'permission denied'):
                app_update.apply(info, path)

    def test_windows_handoff_waits_for_app_and_targets_same_folder(self):
        path = self.download()
        exe = self.root / 'Installed rtxForge/rtxForge.exe'
        exe.parent.mkdir()
        exe.write_bytes(b'app')
        (exe.parent / 'unins000.exe').write_bytes(b'uninstall')
        flags = {'CREATE_NO_WINDOW': 0x08000000, 'DETACHED_PROCESS': 8}
        with patch.dict(os.environ, RTXFORGE_APP_EXE=str(exe), SystemRoot='C:/Windows'), \
             patch.multiple(app_updates.subprocess, create=True, **flags), \
             patch.object(app_updates.subprocess, 'Popen') as launch:
            app_updates.launch(self.info, path, pid=42, restart=True, game_mode=True, helper=True, folder=self.root / 'runner')
            args = launch.call_args.args[0]
            receipt = json.loads(Path(args[-1]).read_text())
            self.assertEqual(receipt['folder'], str(exe.parent))
            self.assertEqual(receipt['pid'], 42)
            self.assertTrue(receipt['game_mode'])
            self.assertIn('WaitForExit', Path(args[-3]).read_text())
            self.assertIn('Get-FileHash', Path(args[-3]).read_text())
            self.assertIn('/VERYSILENT', Path(args[-3]).read_text())
            path.write_bytes(b'bad')
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                app_updates.launch(self.info, path, pid=42, restart=False, game_mode=False, helper=False, folder=self.root)
            self.assertEqual(launch.call_count, 1)

    def test_portable_windows_cannot_launch_setup(self):
        with patch.dict(os.environ, RTXFORGE_APP_EXE=str(self.root / 'rtxForge.exe')):
            with self.assertRaisesRegex(RuntimeError, 'portable'):
                app_updates.installed_executable()


class BackgroundPolicyTests(unittest.TestCase):
    """Execute the GTK lifecycle without GTK; assert its externally visible policy."""
    def make(self):
        tree = ast.parse((ROOT / 'gui/rtxforge_gtk.py').read_text(encoding='utf-8'))
        owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and any(
            isinstance(f, ast.FunctionDef) and f.name == 'poll_app_update' for f in n.body))
        functions = [n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name in
                     ('poll_app_update', 'check_app_update', 'apply_pending_app_update')]
        namespace = {'time': types.SimpleNamespace(monotonic=lambda: 100), 'threading': types.SimpleNamespace(), 'Path': Path}
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'gtk-update-policy', 'exec'), namespace)
        host = types.SimpleNamespace(options=types.SimpleNamespace(demo=False), settings={'auto_update': True},
                                     app_update_running=False, app_update_applying=False, app_update_next_check=0,
                                     busy=False, pending_app_update=None, toast=lambda text: None)
        for name in ('poll_app_update', 'check_app_update', 'apply_pending_app_update'):
            setattr(host, name, types.MethodType(namespace[name], host))
        return host, namespace

    def test_opt_out_busy_demo_and_ready_state_do_not_start_downloads(self):
        for changes in ({'settings': {'auto_update': False}}, {'busy': True},
                        {'options': types.SimpleNamespace(demo=True)}, {'pending_app_update': ({}, 'staged')}):
            host, namespace = self.make()
            host.__dict__.update(changes)
            with patch.object(app_update, 'supported', return_value=True), patch.object(app_update, 'check') as check:
                host.poll_app_update()
                check.assert_not_called()
                self.assertFalse(host.app_update_running)

    def test_manual_check_can_override_automatic_opt_out_but_not_active_operation(self):
        host, namespace = self.make()
        host.settings['auto_update'] = False
        thread = types.SimpleNamespace(start=lambda: None)
        namespace['threading'].Thread = lambda **kwargs: thread
        with patch.object(app_update, 'supported', return_value=True):
            host.poll_app_update(True)
        self.assertTrue(host.app_update_running)
        host, _ = self.make()
        host.busy = True
        host.pending_app_update = ({}, 'staged')
        host.apply_pending_app_update(True)
        self.assertFalse(host.app_update_applying)


if __name__ == '__main__':
    unittest.main()
