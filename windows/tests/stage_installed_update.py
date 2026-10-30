"""CI integration: hand off the built installer to replace an isolated installation."""
import hashlib
import os
from pathlib import Path
import sys

exe, setup, pid, folder = sys.argv[1:]
root = Path(exe).parent / 'engine'
sys.path[:0] = [str(root / 'scripts'), str(root / 'windows/engine-host')]
import app_updates

os.environ['RTXFORGE_APP_EXE'] = exe
setup = Path(setup)
with setup.open('rb') as handle:
    sha = hashlib.file_digest(handle, 'sha256').hexdigest()
version = (root / 'VERSION').read_text().strip()
info = {'sha256': sha, 'size': setup.stat().st_size, 'version': version, 'from_version': version}
app_updates.launch(info, setup, pid=int(pid), restart=False, game_mode=False, helper=False, folder=folder)
