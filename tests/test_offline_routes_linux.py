"""On Linux the offline-only exception checks for protected launchers among Proton's host processes."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import offline_routes


def proc(root, *commands):
    for pid, command in enumerate(commands, 100):
        (root / str(pid)).mkdir()
        (root / str(pid) / 'cmdline').write_bytes(b'\0'.join(arg.encode() for arg in command) + b'\0')
    (root / 'self').mkdir()


class ProtectedProcessTest(unittest.TestCase):
    def running(self, *commands):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(offline_routes.os, 'name', 'posix'):
            proc(Path(tmp), *commands)
            return offline_routes.protected_running(Path(tmp))

    def test_proton_protected_launcher_counts(self):
        self.assertTrue(self.running(['Z:\\games\\Gears\\start_protected_game.exe', '-x']))
        self.assertTrue(self.running(['C:\\Program Files (x86)\\EasyAntiCheat_EOS\\EasyAntiCheat_EOS.exe']))

    def test_offline_executable_and_steam_do_not(self):
        self.assertFalse(self.running(['/usr/bin/steam'], ['Z:\\games\\Gears\\FairlightConcept\\Binaries\\Win64\\GoWEDay-Steam.exe']))

    def test_no_processes(self):
        self.assertFalse(self.running())


if __name__ == '__main__':
    unittest.main()
