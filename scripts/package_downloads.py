"""Fetch pinned provider inputs without running upstream installer scripts."""
from pathlib import Path
import urllib.error
import urllib.request
import zipfile

import packages
import transactions as t
import ui


def inputs(e, sources, expected):
    files = {}
    for source in sources:
        ui.progress('Getting ' + source['name'], phase='package-download')
        destination = e.STATE_ROOT / 'packages' / source['sha256'] / source['archive']
        try:
            request = urllib.request.Request(source['url'], headers={'User-Agent': 'rtxForge/1.0 (+https://github.com/lrnolivia/rtxForge)'})
            archive = packages.download(request, destination,
                                        expected=source['sha256'], size=source['size'])
        except (OSError, urllib.error.URLError) as error:
            raise t.Refusal('Could not download ' + source['name'] + '. Check your connection and retry. ' + str(error)) from error
        for member, name in source['members'].items():
            item = expected[name]
            if source.get('raw'):
                data = archive.read_bytes()
            else:
                with zipfile.ZipFile(archive) as zipped:
                    entries = [entry for entry in zipped.infolist() if entry.filename == member]
                    t.need(len(entries) == 1 and not entries[0].is_dir() and entries[0].file_size == item['size'],
                           'Unexpected file in ' + source['name'] + ': ' + member)
                    data = zipped.read(entries[0])
            t.need(len(data) == item['size'] and t.sha(data) == item['sha256'],
                   'Downloaded provider file failed verification: ' + name)
            cached = t.safe(e.STATE_ROOT / 'feeder-cache' / item['sha256'])
            if not cached.exists():
                t.atomic_file(cached, data, 0o600)
            t.need(cached.stat().st_size == item['size'] and t.digest(cached) == item['sha256'],
                   'Cached provider file changed: ' + name)
            files[name] = {'path': str(cached), 'sha256': item['sha256']}
    return files
