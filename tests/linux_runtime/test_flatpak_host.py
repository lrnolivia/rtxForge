"""Flatpak: process checks run on the host through flatpak-spawn, or refuse; never blind."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts')]
import desktop_frontend
import desktop_install
import engine_bridge
import flatpak_host
import hardware
import linux_overlay_helper as helper
import linux_overlay_host
import offline_routes
import proton_prefix
import steam_self_install

SYSTEM = '/var/lib/flatpak/app/io.github.lrnolivia.RTXForge/x86_64/beta/' + 'a' * 64 + '/files'
USER = '/var/home/lo w/.local/share/flatpak/app/io.github.lrnolivia.RTXForge/x86_64/beta/' + 'b' * 64 + '/files'


def info(directory, app_path=SYSTEM):
    path = Path(directory) / '.flatpak-info'
    path.write_text('[Application]\nname=io.github.lrnolivia.RTXForge\n\n'
                    f'[Instance]\ninstance-id=1\napp-path={app_path}\n')
    return path


class FakeHost:
    """Stands in for flatpak-spawn: records argv and answers like host_probe.py."""

    def __init__(self, answers=None, returncode=0, stdout=None):
        self.calls = []
        self.answers = answers or {}
        self.returncode = returncode
        self.stdout = stdout

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if self.stdout is not None:
            out = self.stdout
        elif argv[4:6] == [flatpak_host.HOST_PYTHON, '-I']:
            out = json.dumps({'ok': True, 'result': self.answers[argv[8]]})
        else:
            out = self.answers.get(argv[4], '')
        return subprocess.CompletedProcess(argv, self.returncode, out, 'Portal call failed' if self.returncode else '')


class Sandbox(unittest.TestCase):
    """Run with a fake /.flatpak-info and a fake flatpak-spawn on PATH."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.info = info(self.root)
        self.host = FakeHost()
        for target in (patch.object(flatpak_host, 'INFO', self.info),
                       patch.object(flatpak_host.shutil, 'which', lambda name: '/usr/bin/' + name),
                       patch.object(flatpak_host, '_run', self.host)):
            target.start()
            self.addCleanup(target.stop)

    def blind_proc(self):
        """A sandbox /proc that would answer 'nothing running' if anyone read it."""
        proc = self.root / 'proc'
        proc.mkdir()
        return proc


class Detection(unittest.TestCase):
    def test_outside_a_flatpak_nothing_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / '.flatpak-info'
            self.assertFalse(flatpak_host.sandboxed(missing))
            engine = types.SimpleNamespace(_running_processes_under_root='original')
            with patch.object(flatpak_host, 'INFO', missing):
                self.assertIs(flatpak_host.adopt(engine), engine)
            self.assertEqual(engine._running_processes_under_root, 'original')

    def test_host_path_of_this_deployment(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(flatpak_host.host_files(info(directory, USER)), Path(USER))

    def test_missing_app_path_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.flatpak-info'
            path.write_text('[Application]\nname=x\n')
            with self.assertRaises(flatpak_host.HostUnavailable):
                flatpak_host.host_files(path)

    def test_stable_path_survives_updates(self):
        self.assertEqual(flatpak_host.stable_files(SYSTEM),
                         Path('/var/lib/flatpak/app/io.github.lrnolivia.RTXForge/current/active/files'))
        self.assertEqual(flatpak_host.stable_files(USER),
                         Path('/var/home/lo w/.local/share/flatpak/app/io.github.lrnolivia.RTXForge/current/active/files'))

    def test_spawned_commands_leave_the_sandbox_cwd(self):
        argv = flatpak_host.spawn_argv(['python3'])
        self.assertEqual(argv[:2], ['flatpak-spawn', '--host'])
        self.assertIn('--directory=/', argv)


class Probe(Sandbox):
    def test_runs_host_python_on_this_apps_payload(self):
        self.host.answers['prefix-in-use'] = True
        self.assertIs(flatpak_host.probe('prefix-in-use', '/games/pfx'), True)
        argv = self.host.calls[0]
        self.assertEqual(argv[:2], ['flatpak-spawn', '--host'])
        self.assertEqual(argv[4:7], ['/usr/bin/python3', '-I', '-B'])
        self.assertEqual(argv[7], SYSTEM + '/share/rtxforge/scripts/host_probe.py')
        self.assertEqual(argv[8:], ['prefix-in-use', '/games/pfx'])

    def test_without_flatpak_spawn_it_refuses(self):
        with patch.object(flatpak_host.shutil, 'which', return_value=None):
            with self.assertRaises(flatpak_host.HostUnavailable) as caught:
                flatpak_host.probe('steam-processes')
        self.assertIn('--talk-name=org.freedesktop.Flatpak', str(caught.exception))

    def test_portal_failure_refuses(self):
        self.host.returncode = 1
        self.host.stdout = ''
        with self.assertRaises(flatpak_host.HostUnavailable) as caught:
            flatpak_host.probe('steam-processes')
        self.assertIn('Portal call failed', str(caught.exception))

    def test_a_failed_or_garbled_answer_refuses(self):
        for stdout, code in (('not json', 0), (json.dumps({'ok': False, 'error': 'boom'}), 1),
                             (json.dumps({'ok': True}), 0), (json.dumps([1]), 0)):
            self.host.stdout, self.host.returncode = stdout, code
            with self.subTest(stdout=stdout), self.assertRaises(flatpak_host.HostUnavailable):
                flatpak_host.probe('steam-processes')

    def test_spawn_error_refuses(self):
        def broken(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 60)
        with patch.object(flatpak_host, '_run', broken), self.assertRaises(flatpak_host.HostUnavailable):
            flatpak_host.probe('steam-processes')


class ProcessChecks(Sandbox):
    """Every check reads the host, and a host failure stops the operation."""

    def test_prefix_in_use_asks_the_host(self):
        self.host.answers['prefix-in-use'] = True
        self.assertTrue(proton_prefix.prefix_in_use(self.root / 'pfx'))
        self.assertEqual(self.host.calls[0][-1], str((self.root / 'pfx').resolve()))

    def test_prefix_in_use_never_passes_blind(self):
        self.host.returncode = 1
        self.host.stdout = ''
        with self.assertRaises(flatpak_host.HostUnavailable):
            proton_prefix.prefix_in_use(self.root / 'pfx')

    def test_prefix_writes_refuse_without_the_host(self):
        self.host.returncode = 1
        self.host.stdout = ''
        prefix = self.root / 'pfx'
        prefix.mkdir()
        (prefix / 'user.reg').write_text('WINE REGISTRY Version 2\n')
        with self.assertRaises(flatpak_host.HostUnavailable):
            proton_prefix.apply(prefix, ['dxgi'], self.root / 'state')
        self.assertEqual((prefix / 'user.reg').read_text(), 'WINE REGISTRY Version 2\n')

    def test_explicit_proc_roots_stay_local(self):
        # Tests and fixtures pass their own /proc; only the real one is the sandbox's.
        self.assertFalse(proton_prefix.prefix_in_use(self.root / 'pfx', self.blind_proc()))
        self.assertEqual(self.host.calls, [])

    def test_protected_launchers_are_found_on_the_host(self):
        self.host.answers['protected-running'] = True
        self.assertTrue(offline_routes.protected_running())

    def test_panel_binding_and_exe_scan_use_the_host(self):
        self.host.answers['mapped-process'] = 4242
        self.host.answers['exe-processes'] = {'game.exe': ['7', 8]}
        self.assertEqual(linux_overlay_host.mapped_process('/p', '/p/game.exe', '/p/ch'), 4242)
        self.assertEqual(linux_overlay_host.exe_processes(), {'game.exe': [7, 8]})

    def test_engine_checks_are_replaced(self):
        self.host.answers['processes-under-root'] = ['77:Game.exe[maps]']
        self.host.answers['steam-processes'] = ['steam']
        engine = engine_bridge.module({})
        self.assertEqual(engine._running_processes_under_root(self.root), ['77:Game.exe[maps]'])
        self.assertTrue(engine.steam_running())
        self.assertEqual(self.host.calls[0][-1], str(self.root.resolve()))

    def test_engine_checks_refuse_without_the_host(self):
        engine = engine_bridge.module({})
        self.host.returncode = 1
        self.host.stdout = ''
        for check in (lambda: engine._running_processes_under_root(self.root), engine.steam_running):
            with self.assertRaises(flatpak_host.HostUnavailable):
                check()

    def test_gpu_comes_from_the_host_driver(self):
        self.host.answers['nvidia-smi'] = 'NVIDIA GeForce RTX 4070, 580.95, 12282\n'
        with patch.object(hardware, 'ready', side_effect=lambda info: info):
            info = hardware.detect()
        self.assertEqual(info['gpu'], 'NVIDIA GeForce RTX 4070')
        self.assertEqual(self.host.calls[0][4], 'nvidia-smi')
        self.host.answers['nvidia-smi'] = 'NVIDIA GeForce RTX 4070\n'
        self.assertEqual(engine_bridge.module({}).nvidia_gpu_name(), 'NVIDIA GeForce RTX 4070')
        self.assertEqual(self.host.calls[-1][4:], ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'])

    def test_gpu_falls_back_to_the_kernel_driver(self):
        self.host.returncode = 1
        self.host.stdout = ''
        with patch.object(hardware, 'proc_gpus', return_value=[['NVIDIA GeForce RTX 4070', '580.95', 'Unknown']]), \
             patch.object(hardware, 'ready', side_effect=lambda info: info):
            self.assertEqual(hardware.detect()['gpu'], 'NVIDIA GeForce RTX 4070')
        with patch.object(hardware, 'proc_gpus', return_value=[]):
            self.assertIn('Cannot verify', hardware.detect()['reason'])


class HostProbe(unittest.TestCase):
    """host_probe.py itself, run the way flatpak-spawn runs it."""

    def run_probe(self, *args):
        result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts/host_probe.py'), *args],
                                capture_output=True, text=True, timeout=120, cwd='/')
        return result.returncode, json.loads(result.stdout.splitlines()[-1])

    @unittest.skipIf(os.path.exists('/.flatpak-info'), 'host-only')
    def test_answers_from_the_real_proc(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / 'pfx'
            prefix.mkdir()
            self.assertEqual(self.run_probe('prefix-in-use', str(prefix)), (0, {'ok': True, 'result': False}))
            child = subprocess.Popen(['sleep', '30'], cwd=directory, env={**os.environ, 'WINEPREFIX': str(prefix) + '/'})
            try:
                self.assertEqual(self.run_probe('prefix-in-use', str(prefix)), (0, {'ok': True, 'result': True}))
                code, answer = self.run_probe('processes-under-root', directory)
                self.assertEqual(code, 0)
                self.assertTrue(any(item.startswith(f'{child.pid}:') for item in answer['result']), answer)
            finally:
                child.kill()
                child.wait()
        code, answer = self.run_probe('steam-processes')
        self.assertEqual((code, type(answer['result'])), (0, list))

    def test_unknown_queries_are_refused(self):
        self.assertEqual(self.run_probe('rm', '-rf', '/'), (1, {'ok': False, 'error': 'unknown query'}))

    def test_refuses_inside_the_sandbox(self):
        import host_probe
        with patch.object(host_probe.os.path, 'exists', return_value=True), \
             patch('builtins.print') as printed:
            self.assertEqual(host_probe.main(['steam-processes']), 1)
        self.assertFalse(json.loads(printed.call_args[0][0])['ok'])


class OverlayHelper(Sandbox):
    def test_unit_runs_host_python_from_the_update_proof_path(self):
        text = flatpak_host.helper_unit(USER)
        script = '/var/home/lo w/.local/share/flatpak/app/io.github.lrnolivia.RTXForge/current/active/files/share/rtxforge/scripts/desktop_frontend.py'
        self.assertIn(f'ExecStart=/usr/bin/python3 -B "{script}" --overlay-helper\n', text)
        self.assertIn(f'ConditionPathExists={script}\n', text)
        self.assertNotIn('flatpak run', text)
        self.assertIn('WantedBy=default.target\n', text)

    def test_install_writes_enables_and_starts_on_the_host(self):
        unit = flatpak_host.install_helper(self.root / 'systemd/user')
        self.assertEqual(unit, self.root / 'systemd/user' / helper.SERVICE)
        self.assertEqual(unit.read_text(), flatpak_host.helper_unit(SYSTEM))
        commands = [argv[4:] for argv in self.host.calls]
        self.assertEqual(commands, [['systemctl', '--user', 'daemon-reload'],
                                    ['systemctl', '--user', 'enable', '--now', helper.SERVICE],
                                    ['systemctl', '--user', 'try-restart', helper.SERVICE]])
        self.assertTrue(all(argv[:2] == ['flatpak-spawn', '--host'] for argv in self.host.calls))
        self.host.calls.clear()
        flatpak_host.install_helper(self.root / 'systemd/user')
        self.assertNotIn(['systemctl', '--user', 'try-restart', helper.SERVICE], [argv[4:] for argv in self.host.calls],
                         'an unchanged helper is not restarted')

    def test_install_failure_is_reported(self):
        self.host.returncode = 1
        with self.assertRaises(flatpak_host.HostUnavailable):
            flatpak_host.install_helper(self.root / 'systemd/user')

    def test_helper_refuses_inside_the_sandbox(self):
        with patch.object(helper, 'main', side_effect=AssertionError('blind helper started')):
            self.assertEqual(desktop_frontend.main(['--overlay-helper']), 1)

    def test_appimage_launcher_and_steam_shortcut_are_left_alone(self):
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root / 'data')}):
            self.assertFalse(desktop_install.refresh_launcher_icon(True))
        with self.assertRaisesRegex(ValueError, 'Add a Non-Steam Game'):
            steam_self_install.executable()


class NoBlindProcessReads(unittest.TestCase):
    """New /proc readers must route through flatpak_host before they ship."""

    ROUTED = {
        # Read /proc only after asking flatpak_host (or through prefix_in_use).
        ('scripts/proton_prefix.py', 'prefix_in_use'), ('scripts/proton_prefix.py', 'apply'),
        ('scripts/proton_prefix.py', 'restore'), ('scripts/proton_overlay.py', 'plan'),
        ('scripts/proton_overlay.py', 'apply'), ('scripts/proton_overlay.py', 'restore'),
        ('scripts/offline_routes.py', 'protected_running'), ('scripts/linux_overlay_host.py', 'mapped_process'),
        ('scripts/linux_overlay_host.py', 'exe_processes'),
        # Replaced by flatpak_host.adopt in every engine the app loads.
        ('engine/rtxengine.py', '_steam_process_names'), ('engine/rtxengine.py', '_running_processes_under_root'),
        # Kernel-wide driver and CPU facts, the same inside the sandbox.
        ('scripts/hardware.py', 'detect'), ('scripts/hardware.py', 'proc_gpus'),
        ('scripts/proton_stack.py', '<module>'), ('scripts/desktop_frontend.py', 'run_container'),
    }

    def test_every_proc_reader_is_accounted_for(self):
        shipped = [*(ROOT / 'scripts').glob('*.py'), *(ROOT / 'gui').glob('*.py'), ROOT / 'engine/rtxengine.py',
                   *(ROOT / 'windows/engine-host').glob('*.py')]
        found = set()
        for path in shipped:
            def visit(node, owner):
                for child in ast.iter_child_nodes(node):
                    name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else owner
                    if isinstance(child, ast.Constant) and isinstance(child.value, str) and child.value.startswith('/proc'):
                        found.add((path.relative_to(ROOT).as_posix(), owner))
                    visit(child, name)
            visit(ast.parse(path.read_text(encoding='utf-8')), '<module>')
        self.assertEqual(found - self.ROUTED, set(),
                         'Route new /proc reads through flatpak_host (host_probe.py), or the Flatpak checks blind.')

    def test_adopt_replaces_the_engine_readers(self):
        names = {name for path, name in self.ROUTED if path == 'engine/rtxengine.py'}
        engine = types.SimpleNamespace()
        with tempfile.TemporaryDirectory() as directory, patch.object(flatpak_host, 'INFO', info(directory)):
            flatpak_host.adopt(engine)
        self.assertLessEqual(names, set(vars(engine)))


if __name__ == '__main__':
    unittest.main()
