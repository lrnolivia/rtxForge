"""The in-game panel helper without the app window: lock, entry point and login service."""
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
                                   controls=types.SimpleNamespace(stop=threading.Event(),watcher=None))
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


class LoginService(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)

    def test_unit_starts_the_installed_appimage_at_login(self):
        text=helper.unit_text(Path('/var/home/lo w/.local/share/rtxforge/application/RTX%Forge$.AppImage'))
        self.assertIn('ExecStart="/var/home/lo w/.local/share/rtxforge/application/RTX%%Forge$$.AppImage" --overlay-helper\n',text)
        self.assertIn('Restart=on-failure\n',text)
        self.assertIn('WantedBy=default.target\n',text)

    def test_install_writes_and_enables_the_unit(self):
        calls=[]
        app=self.root/'RTXForge.AppImage';app.write_text('')
        unit=helper.install_service(app,self.root/'systemd/user','/usr/bin/systemctl',run=lambda argv,**_:calls.append(argv))
        self.assertEqual(unit,self.root/'systemd/user'/helper.SERVICE)
        self.assertEqual(unit.read_text(),helper.unit_text(app.resolve()))
        self.assertEqual(calls,[['/usr/bin/systemctl','--user','daemon-reload'],
                                ['/usr/bin/systemctl','--user','enable',helper.SERVICE]])
        stamp=unit.stat().st_mtime_ns
        helper.install_service(app,self.root/'systemd/user','/usr/bin/systemctl',run=lambda argv,**_:None)
        self.assertEqual(unit.stat().st_mtime_ns,stamp,'an unchanged unit is not rewritten')

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
