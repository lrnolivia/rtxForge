"""Verified, reusable update downloads. Downloading never installs or closes an app."""
import hashlib
import os
from pathlib import Path
import re
import tempfile
import urllib.request

PREFIX = 'https://github.com/lrnolivia/rtxForge/releases/download/'


def verified(path, info):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != info['size']:
        return False
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest() == info['sha256'].lower()


def download(info, folder, progress=None):
    """Cache by content hash; partial, corrupt and republished assets cannot be reused."""
    name = info['name']
    if (not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name
            or not re.fullmatch(r'[A-Za-z0-9_.-]+', name)):
        raise ValueError('Invalid update filename.')
    if not re.fullmatch(r'[0-9a-fA-F]{64}', str(info['sha256'])):
        raise ValueError('Invalid update checksum.')
    size = info['size']
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= 2 * 1024**3:
        raise ValueError('Invalid update size.')
    url = info['url']
    if not url.startswith(PREFIX) or url.rsplit('/', 1)[-1] != name:
        raise ValueError('Refusing unexpected update download address.')
    folder = Path(folder) / info['sha256'].lower()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if verified(target, info):
        return target
    fd, temporary = tempfile.mkstemp(prefix='.download-', dir=folder)
    stage = Path(temporary)
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'rtxForge-Updater/2'})
        received = 0
        with os.fdopen(fd, 'wb') as output, urllib.request.urlopen(request, timeout=60) as response:
            while block := response.read(1024 * 1024):
                received += len(block)
                if received > size:
                    raise RuntimeError('Update download exceeds the release size.')
                output.write(block)
                if progress:
                    progress(received / size, received, size)
            output.flush()
            os.fsync(output.fileno())
        if not verified(stage, info):
            raise RuntimeError('Update size or checksum verification failed. Nothing was installed.')
        os.replace(stage, target)
        return target
    finally:
        stage.unlink(missing_ok=True)
