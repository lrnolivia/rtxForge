import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def test_standalone_install_cannot_escape_versions(self):
        self.folder.rename(self.root/'not-bundled')
        data=self.root/'data';installed=data/'rtxforge-game-mode';installed.mkdir(parents=True)
        (installed/'installed.json').write_text(json.dumps({'path':str(self.root/'outside')}))
        with self.assertRaises(ValueError):launcher.resolve(self.root,data)
