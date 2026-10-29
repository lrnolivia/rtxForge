"""The in-game panel helper without the app window: lock, entry point and login service."""
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[2]/'scripts')]
import desktop_frontend
import desktop_install
import library_media
import linux_overlay_helper as helper
import linux_overlay_host as host


class HostLock(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'host.lock'

    def test_one_host_per_user(self):
        first=host.host_lock(self.path)
        self.assertIsNotNone(first)
        self.assertIsNone(host.host_lock(self.path))
        os.close(first)
        again=host.host_lock(self.path)
        self.assertIsNotNone(again);os.close(again)

    def test_refuses_a_symlinked_lock(self):
        target=Path(self.directory.name)/'elsewhere';target.write_text('')
        self.path.symlink_to(target)
        with self.assertRaises(OSError):host.host_lock(self.path)

    def test_lock_lives_in_the_runtime_dir(self):
        with patch.dict(os.environ,{'XDG_RUNTIME_DIR':self.directory.name}):
            self.assertEqual(host.lock_path().parent,Path(self.directory.name))
        with patch.dict(os.environ,{'XDG_RUNTIME_DIR':'relative'}):
            self.assertEqual(host.lock_path().parent,Path('/tmp'))

    def test_second_host_waits_then_takes_over(self):
        polls=[]
        fake=types.SimpleNamespace(stop=threading.Event(),channels={},poll=lambda:polls.append(1),
                                   controls=types.SimpleNamespace(stop=threading.Event(),watcher=None,start=lambda:None))
        held=host.host_lock(self.path)
        thread=threading.Thread(target=host.Host.run,args=(fake,self.path));thread.start()
        try:
            time.sleep(.4)
            self.assertEqual(polls,[],'a second host must not answer channels the first one owns')
            os.close(held);held=None
            deadline=time.monotonic()+3
            while not polls and time.monotonic()<deadline:time.sleep(.05)
            self.assertTrue(polls,'the waiting host takes over once the first exits')
        finally:
            if held is not None:os.close(held)
            fake.stop.set();thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(fake.controls.stop.is_set())
        released=host.host_lock(self.path)
        self.assertIsNotNone(released,'a stopped host releases the lock');os.close(released)

    def test_saved_presets_wait_for_host_ownership_before_replay(self):
        controls=host.LinuxControls(Path(self.directory.name))
        controls.presets={'game':{'row':{}}}
        replay=threading.Event()
        def game(_):
            replay.set()
            raise OSError('Fixture game is not running')
        controls._game=game
        controls._start_watcher()
        self.assertIsNone(controls.watcher,'reloading presets cannot start an unowned host')
        fake=types.SimpleNamespace(stop=threading.Event(),channels={},poll=lambda:None,controls=controls)
        held=host.host_lock(self.path)
        thread=threading.Thread(target=host.Host.run,args=(fake,self.path));thread.start()
        try:
            self.assertFalse(replay.wait(.4),'the app still owns the channel')
            self.assertIsNone(controls.watcher)
            os.close(held);held=None
            self.assertTrue(replay.wait(4),'the standalone helper replays after taking ownership')
        finally:
            if held is not None:os.close(held)
            fake.stop.set();thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(controls.watcher.is_alive())


class LoginService(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)

    def test_unit_starts_the_installed_appimage_at_login(self):
        text=helper.unit_text(Path('/var/home/lo w/.local/share/rtxforge/application/RTX%Forge$.AppImage'))
        self.assertIn('ExecStart="/var/home/lo w/.local/share/rtxforge/application/RTX%%Forge$$.AppImage" --overlay-helper\n',text)
        self.assertIn('Restart=on-failure\n',text)
        self.assertIn('WantedBy=default.target\n',text)

    def test_install_starts_now_and_at_login_without_restarting_unchanged_unit(self):
        calls=[]
        app=self.root/'RTXForge.AppImage';app.write_text('')
        def run(argv,**kwargs):
            calls.append(argv)
            self.assertTrue(kwargs['text'])
            return types.SimpleNamespace(returncode=0,stderr='')
        unit=helper.install_service(app,self.root/'systemd/user','/usr/bin/systemctl',run=run)
        self.assertEqual(unit,self.root/'systemd/user'/helper.SERVICE)
        self.assertEqual(unit.read_text(),helper.unit_text(app.resolve()))
        self.assertEqual(calls,[['/usr/bin/systemctl','--user','daemon-reload'],
                                ['/usr/bin/systemctl','--user','enable','--now',helper.SERVICE],
                                ['/usr/bin/systemctl','--user','try-restart',helper.SERVICE]])
        stamp=unit.stat().st_mtime_ns
        calls.clear()
        helper.install_service(app,self.root/'systemd/user','/usr/bin/systemctl',run=run)
        self.assertEqual(unit.stat().st_mtime_ns,stamp,'an unchanged unit is not rewritten')
        self.assertEqual(calls,[['/usr/bin/systemctl','--user','daemon-reload'],
                                ['/usr/bin/systemctl','--user','enable','--now',helper.SERVICE]],
                         'registration starts a stopped helper but leaves a running one alone')

    def test_changed_launcher_refreshes_the_running_helper(self):
        unit_dir=self.root/'systemd/user'
        old=self.root/'old.AppImage';old.write_text('')
        new=self.root/'new.AppImage';new.write_text('')
        calls=[]
        def run(argv,**_):
            calls.append(argv)
            return types.SimpleNamespace(returncode=0,stderr='')
        helper.install_service(old,unit_dir,'systemctl',run=run)
        calls.clear()
        unit=helper.install_service(new,unit_dir,'systemctl',run=run)
        self.assertIn(str(new.resolve()),unit.read_text())
        self.assertEqual(calls[-1],['systemctl','--user','try-restart',helper.SERVICE])

    def test_each_systemctl_failure_is_reported_and_stops_followup_commands(self):
        app=self.root/'RTXForge.AppImage';app.write_text('')
        for failed_step in range(3):
            with self.subTest(step=failed_step):
                calls=[]
                def run(argv,**_):
                    calls.append(argv)
                    return types.SimpleNamespace(returncode=1 if len(calls)==failed_step+1 else 0,
                                                 stderr='No user bus')
                with self.assertRaisesRegex(RuntimeError,'No user bus'):
                    helper.install_service(app,self.root/str(failed_step),'systemctl',run=run)
                self.assertEqual(len(calls),failed_step+1)

    def test_without_systemctl_the_unit_is_still_written(self):
        app=self.root/'RTXForge.AppImage';app.write_text('')
        self.assertIsNone(helper.install_service(app,self.root/'units',None,run=lambda *a,**k:self.fail('no systemctl')))
        self.assertTrue((self.root/'units'/helper.SERVICE).is_file())

    def test_desktop_install_registers_the_service_beside_the_launcher(self):
        app=self.root/'RTXForge.AppImage';app.write_text('')
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data')}), \
             patch.object(desktop_install.shutil,'which',return_value=None):
            desktop_install.register(app)
        unit=self.root/'data/systemd/user'/helper.SERVICE
        self.assertIn('--overlay-helper',unit.read_text())

    def test_a_helper_that_cannot_start_does_not_fail_the_install(self):
        app=self.root/'RTXForge.AppImage';app.write_text('')
        failed=RuntimeError('The in-game panel helper could not be started: No user bus.')
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data')}), \
             patch.object(desktop_install.shutil,'which',return_value=None), \
             patch.object(helper,'install_service',side_effect=failed), \
             patch('sys.stderr',new_callable=io.StringIO) as stderr:
            self.assertEqual(desktop_install.register(app),str(app.resolve()))
        self.assertIn('No user bus',stderr.getvalue())
        self.assertTrue((self.root/'data/applications'/f'{desktop_install.APP_ID}.desktop').is_file())


class EntryPoint(unittest.TestCase):
    def test_overlay_helper_flag_skips_the_toolkit(self):
        with patch.object(helper,'main',return_value=0) as main, \
             patch.object(desktop_frontend,'choose',side_effect=AssertionError('no toolkit for the helper')):
            self.assertEqual(desktop_frontend.main(['--overlay-helper']),0)
        main.assert_called_once()

    def test_settings_are_reread_when_the_app_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json';path.write_text('{}')
            values=[{'overlay_helper':True},{'overlay_helper':False}]
            with patch.object(library_media,'settings_path',return_value=path), \
                 patch.object(library_media,'load_settings',side_effect=lambda _:values[0]):
                current=helper._settings({})
                self.assertTrue(current()['overlay_helper'])
                values.pop(0)
                self.assertTrue(current()['overlay_helper'],'unchanged file is not reread')
                path.write_text('{"x":1}');os.utime(path,ns=(1,time.time_ns()+10**9))
                self.assertFalse(current()['overlay_helper'])

    def test_helper_exits_when_turned_off(self):
        service=types.SimpleNamespace(config={})
        with patch('desktop_service.DesktopService',return_value=service), \
             patch.object(helper,'_settings',return_value=lambda:{'overlay_helper':False}), \
             patch('engine_bridge.module',side_effect=AssertionError('no engine when off')):
            self.assertEqual(helper.main(),0)


if __name__=='__main__':
    unittest.main()
