import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
spec=importlib.util.spec_from_file_location('game_mode_launcher',Path(__file__).resolve().parents[1]/'scripts/game_mode_launcher.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)


class NativeHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'game-mode';self.folder.mkdir()
        self.image=self.folder/'rtxforge-game-mode.AppImage';self.image.write_bytes(b'fixture native image')
        self.receipt={'schema':1,'desktopIntegration':1,'source':'reviewed-source','size':self.image.stat().st_size,'sha256':hashlib.sha256(self.image.read_bytes()).hexdigest()}
        (self.folder/'game-mode.json').write_text(json.dumps(self.receipt))

    def test_bundled_ui_is_verified_and_preferred(self):
        self.assertEqual(launcher.resolve(self.root),(self.image,True))
        self.assertEqual(launcher.validate_image(self.folder,'reviewed-source'),self.image)
        with self.assertRaises(ValueError):launcher.validate_image(self.folder,'different-source')
        self.image.write_bytes(b'changed')
        with self.assertRaises(ValueError):launcher.resolve(self.root)

    def test_parent_and_environment_are_explicit(self):
        with patch.dict(os.environ,{'APPIMAGE':'/portable/rtxForge.AppImage','RTXFORGE_ROOT':'parent-engine',
                                    'RTXFORGE_PYTHON':'parent-python','LD_LIBRARY_PATH':'parent-libs','SteamAppId':'123'}),patch.object(launcher.subprocess,'Popen') as start:
            launcher.start(self.root,True)
            args=start.call_args.args[0];env=start.call_args.kwargs['env']
            self.assertEqual(args,[str(self.image),'--appimage-extract-and-run','--desktop-parent',str(os.getpid())])
            for name in ('APPIMAGE','RTXFORGE_ROOT','RTXFORGE_PYTHON','LD_LIBRARY_PATH','SteamAppId'):self.assertNotIn(name,env)
            self.assertEqual(json.loads(env['RTXFORGE_DESKTOP_COMMAND']),[os.path.abspath('/portable/rtxForge.AppImage'),'--desktop-mode'])
            self.assertEqual(env['RTXFORGE_APP_EXE'],os.path.abspath('/portable/rtxForge.AppImage'))
            self.assertEqual(env['RTXFORGE_PREVIEW_READ_ONLY'],'1')

    def test_preview_uses_the_requested_read_only_route(self):
        with patch.object(launcher.subprocess,'Popen') as start:
            for route in ('library', 'details'):
                launcher.activate(self.root, preview=route)
                self.assertIn('--preview-'+route, start.call_args.args[0])
                self.assertEqual(start.call_args.kwargs['env']['RTXFORGE_PREVIEW_READ_ONLY'], '1')
        with self.assertRaises(ValueError):
            launcher.activate(self.root, preview='settings')

    def test_standalone_install_cannot_escape_versions(self):
        self.folder.rename(self.root/'not-bundled')
        data=self.root/'data';installed=data/'rtxforge-game-mode';installed.mkdir(parents=True)
        (installed/'installed.json').write_text(json.dumps({'path':str(self.root/'outside')}))
        with self.assertRaises(ValueError):launcher.resolve(self.root,data)

    def test_integrated_mode_uses_desktop_engine_with_native_providers(self):
        for name in ('scripts/desktop_service.py','engine/rtxengine.py'):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
        with patch.object(launcher.subprocess,'Popen') as start:
            launcher.start(self.root)
            self.assertEqual(start.call_args.kwargs['env']['RTXFORGE_ROOT'],str(self.root.resolve()))

    def test_existing_activation_and_return_use_clean_environment(self):
        with patch.dict(os.environ,{'APPIMAGE':'/parent/Desktop.AppImage','LD_LIBRARY_PATH':'parent-libs'}),patch.object(launcher.subprocess,'Popen') as child:
            launcher.activate(self.root)
            self.assertEqual(child.call_args.args[0], [str(self.image),'--appimage-extract-and-run','--desktop-parent',str(os.getpid())])
            launcher.return_to_desktop(self.root)
            self.assertEqual(child.call_args.args[0],[str(self.image),'--appimage-extract-and-run','--desktop-mode'])
            self.assertNotIn('APPIMAGE',child.call_args.kwargs['env'])
            self.assertNotIn('LD_LIBRARY_PATH',child.call_args.kwargs['env'])

    def test_existing_native_window_outlives_single_instance_launcher(self):
        child=Mock();child.wait.return_value=0
        with patch.object(launcher,'native_instances',side_effect=[{42:'original'}, {42:'original'}, {42:'reused'}]) as instances,patch.object(launcher.time,'sleep') as sleep:
            self.assertEqual(launcher.NativeSession(child).wait(),0)
            self.assertEqual(instances.call_count,3)
            self.assertEqual(sleep.call_count,2)
        child.wait.return_value=1
        with patch.object(launcher,'native_instances') as instances:
            self.assertEqual(launcher.NativeSession(child).wait(),1)
            instances.assert_not_called()

    @unittest.skipUnless(hasattr(os,'getuid'),'Requires Linux process ownership and symlinks')
    def test_native_ui_wait_uses_local_pid_namespace_and_start_identity(self):
        import flatpak_host
        proc=self.root/'local-proc';proc.mkdir()
        native=proc/'42';native.mkdir()
        (native/'exe').symlink_to(self.root/'rtxforge-game-mode')
        def identity(start):return '42 (rtxforge-game-mode) '+' '.join(['S']+['0']*18+[start])
        (native/'stat').write_text(identity('1234'))
        (native/'cmdline').write_bytes(b'rtxforge-game-mode\0')
        preview=proc/'44';preview.mkdir()
        (preview/'exe').symlink_to(self.root/'rtxforge-game-mode')
        (preview/'stat').write_text(identity('5678'))
        (preview/'cmdline').write_bytes(b'rtxforge-game-mode\0--preview-details\0')
        unrelated=proc/'43';unrelated.mkdir()
        (unrelated/'exe').symlink_to(self.root/'game-executable')
        (unrelated/'stat').write_text(identity('9999'))
        with patch.dict(os.environ,{'FLATPAK_ID':'io.github.lrnolivia.RTXForge'}),patch.object(flatpak_host,'sandboxed',return_value=True),patch.object(flatpak_host,'probe',side_effect=AssertionError('UI lifetime must use the local namespace')):
            self.assertEqual(launcher.native_instances(proc),{42:'1234'})
            (native/'stat').write_text(identity('5678'))
            self.assertEqual(launcher.native_instances(proc,pids=[42]),{42:'5678'})
            self.assertEqual(launcher.native_instances(proc,pids=[99]),{})

    @unittest.skipUnless(os.environ.get('RTXFORGE_TEST_NATIVE_DESKTOP')=='1','Requires a Linux GTK display and isolated D-Bus session')
    def test_repeated_process_activations_keep_one_gtk_owner(self):
        repo=Path(__file__).resolve().parents[1]
        events=self.root/'activation-events.jsonl'
        probe=self.root/'activation-probe.py'
        probe.write_text('''import json, os, sys
from pathlib import Path
sys.path[:0]=[str(Path(REPO)/'gui'),str(Path(REPO)/'scripts')]
import rtxforge_gtk as app
def record(event):
    with open(os.environ['RTXFORGE_ACTIVATION_LOG'],'a') as stream:stream.write(json.dumps([os.getpid(),event])+'\\n')
class Window(app.Adw.ApplicationWindow):
    def __init__(self,application,options):
        super().__init__(application=application)
        self.busy=False
        record('created')
        quit_action=app.Gio.SimpleAction.new('fixture-quit',None)
        quit_action.connect('activate',lambda *_:application.quit())
        application.add_action(quit_action)
    def present(self):record('desktop');super().present()
    def set_input_surface(self,couch,wait_for_idle=False):record('game-queued' if couch and wait_for_idle else 'wrong-mode')
app.Window=Window
if '--fixture-quit' in sys.argv:
    remote=app.Gio.Application(application_id='io.github.lrnolivia.RTXForge',flags=app.Gio.ApplicationFlags.DEFAULT_FLAGS)
    remote.register(None)
    assert remote.get_is_remote()
    remote.activate_action('fixture-quit',None)
    remote.get_dbus_connection().flush_sync(None)
else:sys.exit(app.main())
'''.replace('REPO',repr(str(repo))))
        env=os.environ|{'RTXFORGE_ACTIVATION_LOG':str(events)}
        def entries():return [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
        def await_event(event,count):
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if sum(row[1]==event for row in entries())>=count:return
                time.sleep(.05)
            self.fail('Missing activation '+event+': '+repr(entries()))
        owner=subprocess.Popen([sys.executable,str(probe),'--desktop-mode'],env=env)
        try:
            await_event('created',1)
            for index in (1,2):
                subprocess.run([sys.executable,str(probe),'--game-mode'],env=env,check=True,timeout=15)
                await_event('game-queued',index)
            subprocess.run([sys.executable,str(probe),'--desktop-mode'],env=env,check=True,timeout=15)
            await_event('desktop',2)
            self.assertEqual({row[0] for row in entries()},{owner.pid})
            self.assertEqual(sum(row[1]=='created' for row in entries()),1)
            subprocess.run([sys.executable,str(probe),'--fixture-quit'],env=env,check=True,timeout=15)
            self.assertEqual(owner.wait(timeout=15),0)
        finally:
            if owner.poll() is None:owner.terminate();owner.wait(timeout=15)
