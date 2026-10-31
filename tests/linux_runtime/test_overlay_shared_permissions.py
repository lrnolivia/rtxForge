"""An overlay update leaves the shared library readable and private state private."""
import contextlib
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'scripts'),str(root/'windows/engine-host')]
import global_controls as controls
import transactions as t


@unittest.skipIf(os.name=='nt','POSIX permission bits require the Linux runner')
class SharedOverlayPermissions(unittest.TestCase):
    def test_real_update_retains_private_state_and_repairs_shared_readability(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve();game=base/'library/Game';game.mkdir(parents=True)
            ini=game/'OptiScaler.ini';ini.write_bytes(b'old');ini.chmod(0o600)
            private=base/'private/presets.json';private.parent.mkdir();private.write_bytes(b'old');private.chmod(0o600)
            e=SimpleNamespace(STATE_ROOT=base/'engine',mutation_lock=contextlib.nullcontext,
                              _running_processes_under_root=lambda _:[],ANTI_CHEAT_PATTERNS=[],ANTI_CHEAT_DIRS=set(),IGNORE_DIRS=set())
            plan={'name':'Shared game','root':str(game),'target':str(game),
                  'checks':{str(ini):t.digest(ini),str(private):t.digest(private)},
                  'writes':{str(ini):b'new',str(private):b'new'}}
            controls.execute({'engine':e,'plans':[plan]})
            self.assertEqual(ini.read_bytes(),b'new');self.assertEqual(private.read_bytes(),b'new')
            self.assertEqual(stat.S_IMODE(ini.stat().st_mode),0o644)
            self.assertEqual(stat.S_IMODE(private.stat().st_mode),0o600)


if __name__=='__main__':unittest.main()
