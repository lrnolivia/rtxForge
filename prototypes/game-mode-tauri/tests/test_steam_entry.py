import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('linux_host', Path(__file__).resolve().parents[1] / 'bridge/linux_host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class SteamEntryTests(unittest.TestCase):
    def test_explicit_executable_wins_over_existing_desktop_appimage(self):
        with patch.dict(os.environ, {'RTXFORGE_APP_EXE': sys.executable, 'APPIMAGE': '/old/Desktop.AppImage'}):
            self.assertEqual(Path(sys.executable).resolve(), host.app_entry())

    def test_missing_entry_never_falls_back_to_desktop(self):
        with patch.dict(os.environ, {'APPIMAGE': '/old/Desktop.AppImage'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Game Mode'):
                host.app_entry()

    def test_unavailable_entry_is_refused(self):
        with patch.dict(os.environ, {'RTXFORGE_APP_EXE': str(Path(__file__).parent / 'missing-game-mode')}):
            with self.assertRaises(OSError):
                host.app_entry()
