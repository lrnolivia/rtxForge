"""On-demand Steam Store screenshots, in a bounded application-owned disk cache."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import time
import urllib.parse
import urllib.request

IMAGE_LIMIT = 8 * 1024 * 1024
CACHE_LIMIT = 128 * 1024 * 1024
TTL = 30 * 86400

# Reviewed against the Store's actual images. Immutable filename hashes keep
# a reordered or replaced Store gallery from silently approving a HUD frame.
CLEAN_SCREENSHOTS = {
    '3159330': frozenset((
        '81bbd04dae05b0a52dc62818dc5219abeb849f8d',
        'e53dc9ec73e3de9b8e680472898de775f0dc1cae',
        '2e74c5442faa027ea699dcfa15be173b43a8d37a',
    )),
}


def clean_screenshot(url, appid):
    approved = CLEAN_SCREENSHOTS.get(appid)
    match = re.search(r'/ss_([0-9a-f]{40})(?:\.|$)', urllib.parse.urlsplit(url).path)
    return approved is None or bool(match and match[1] in approved)


def clean_gallery(shots, appid):
    return [shot for shot in shots if clean_screenshot(shot.get('full', ''), appid)]


def dimensions(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24:
        return struct.unpack('>II', data[16:24])
    if data.startswith(b'\xff\xd8'):
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 255:
                break
            marker = data[pos + 1]
            pos += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            length = int.from_bytes(data[pos:pos + 2], 'big')
            if length < 2 or pos + length > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2) and length >= 7:
                height, width = struct.unpack('>HH', data[pos + 3:pos + 7])
                return width, height
            pos += length
    raise ValueError('Unsupported or incomplete screenshot')


def allowed(url, appid):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == 'https' and parsed.port in (None, 443) and not parsed.username
            and (parsed.hostname or '').endswith('.steamstatic.com')
            and any(parsed.path.startswith(prefix + appid + '/') for prefix in ('/steam/apps/', '/store_item_assets/steam/apps/'))
            and parsed.path.rsplit('/', 1)[-1].startswith('ss_'))


def fetch(url, limit):
    class Redirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            # Store metadata stays on the Store; image redirects stay on Valve's CDN.
            host = urllib.parse.urlsplit(newurl)
            if host.scheme != 'https' or not (host.hostname == 'store.steampowered.com' or (host.hostname or '').endswith('.steamstatic.com')):
                raise ValueError('Unexpected screenshot redirect')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    request = urllib.request.Request(url, headers={'User-Agent': 'rtxForge/1.0', 'Accept': '*/*'})
    with urllib.request.build_opener(Redirects()).open(request, timeout=8) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Screenshot response exceeds its limit')
    return data


def atomic(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.download-', delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(data)
            output.flush()
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_appid(appid):
    if not isinstance(appid, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', appid):
        raise ValueError('A Steam application ID is required')


def gallery(appid, cache, *, download=fetch, now=None):
    validate_appid(appid)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    record = cache / (appid + '.gallery.json')
    current = time.time() if now is None else now
    stored = {}
    try:
        if record.is_symlink() or record.stat().st_size > 256 * 1024:
            raise ValueError('Invalid screenshot catalog')
        stored = json.loads(record.read_text('utf-8'))
        if current - stored['checked'] < (TTL if stored.get('screenshots') else 900):
            return clean_gallery(stored.get('screenshots', []), appid)
    except (OSError, ValueError, KeyError, TypeError):
        stored = {}
    try:
        endpoint = 'https://store.steampowered.com/api/appdetails?' + urllib.parse.urlencode({'appids': appid, 'filters': 'screenshots'})
        response = json.loads(download(endpoint, 2 * 1024 * 1024))
        result = response.get(appid, {}) if isinstance(response, dict) else {}
        details = result.get('data') if isinstance(result, dict) and result.get('success') else None
        candidates = details.get('screenshots', []) if isinstance(details, dict) else []
        shots = []
        for item in candidates[:100] if isinstance(candidates, list) else []:
            if not isinstance(item, dict) or not allowed(item.get('path_full', ''), appid):
                continue
            identity = str(item.get('id', len(shots)))
            thumbnail = item.get('path_thumbnail', '')
            if not identity.isdecimal() or len(identity) > 6:
                continue
            shots.append({'id': identity, 'full': item['path_full'], 'thumbnail': thumbnail if allowed(thumbnail, appid) else item['path_full']})
        atomic(record, json.dumps({'checked': current, 'screenshots': shots}).encode())
        return clean_gallery(shots, appid)
    except (OSError, ValueError, TypeError):
        return clean_gallery(stored.get('screenshots', []), appid)


def background(appid, cache, *, screenshot=None, download=fetch, now=None):
    validate_appid(appid)
    if screenshot is not None and (not isinstance(screenshot, str) or not re.fullmatch(r'[0-9]{1,6}', screenshot)):
        raise ValueError('Invalid screenshot ID')
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    if cache.is_symlink():
        raise ValueError('Screenshot cache must be a directory')
    identity = appid + ('-' + screenshot if screenshot is not None else '')
    image, receipt = cache / (identity + '.image'), cache / (identity + '.json')
    current = time.time() if now is None else now
    stored, data = {}, None
    try:
        if receipt.is_symlink() or image.is_symlink() or receipt.stat().st_size > 4096:
            raise ValueError('Invalid screenshot cache entry')
        stored = json.loads(receipt.read_text('utf-8'))
        if stored.get('source') and not clean_screenshot(stored['source'], appid):
            raise ValueError('Cached screenshot is no longer approved for backgrounds')
        if stored.get('missing') and current - stored['checked'] < 900:
            return {'image': None}
        if image.stat().st_size > IMAGE_LIMIT:
            raise ValueError('Invalid cached screenshot size')
        data = image.read_bytes()
        if hashlib.sha256(data).hexdigest() != stored['sha256']:
            raise ValueError('Cached screenshot changed')
        dimensions(data)
    except (OSError, ValueError, KeyError, TypeError):
        stored, data = {}, None
    if data is None or stored.get('version') != 2 or current - stored.get('checked', 0) > TTL:
        try:
            candidates = gallery(appid, cache, download=download, now=current)
            if screenshot is not None:
                candidates = [item for item in candidates if item['id'] == screenshot]
            best = None
            for item in candidates[:3]:
                if not isinstance(item, dict):
                    continue
                url = item.get('full', '')
                if not allowed(url, appid):
                    continue
                # Steam's path_full can still name its 1920x1080 derivative.
                # Request the original of that exact screenshot before its derivative.
                original = re.sub(r'\.\d+x\d+(?=\.(?:jpg|png)(?:\?|$))', '', url)
                for source in dict.fromkeys((original, url)):
                    try:
                        content = download(source, IMAGE_LIMIT)
                        width, height = dimensions(content)
                        if width * height > 40_000_000 or min(width, height) < 480:
                            continue
                        if best is None or width * height > best[1] * best[2]:
                            best = content, width, height, source
                        break
                    except (OSError, ValueError):
                        continue
                if best and best[1] >= 3840 and best[2] >= 2160:
                    break
            if best:
                data, width, height, url = best
                stored = {'version': 2, 'width': width, 'height': height, 'source': url, 'checked': current, 'sha256': hashlib.sha256(data).hexdigest()}
                atomic(image, data)
                atomic(receipt, json.dumps(stored).encode())
                # Evict only old regular image/receipt pairs owned by this cache.
                files = sorted((p for p in cache.glob('*.image') if not p.is_symlink()), key=lambda p: p.stat().st_mtime, reverse=True)
                total = 0
                for path in files:
                    total += path.stat().st_size
                    if total > CACHE_LIMIT and path != image:
                        path.unlink(missing_ok=True)
                        path.with_suffix('.json').unlink(missing_ok=True)
            elif data is None:
                atomic(receipt, json.dumps({'missing': True, 'checked': current}).encode())
        except (OSError, ValueError, TypeError):
            pass  # Keep the last good image available offline.
    if data is None:
        return {'image': None}
    mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
    return {**stored, 'image': 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')}
