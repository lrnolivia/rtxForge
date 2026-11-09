"""Download pinned GitHub release assets for application builds."""

import hashlib
from http.client import IncompleteRead
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
import urllib.request


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download_verified_asset(public_url, api_url, expected_sha, target, *, size=None):
    target = Path(target)
    if target.is_file() and (size is None or target.stat().st_size == size) and digest(target) == expected_sha:
        return
    token = os.environ.get('GH_TOKEN')
    with tempfile.TemporaryDirectory(dir=target.parent) as directory:
        candidate = Path(directory) / target.name
        for attempt in range(3):
            use_api = bool(token) and attempt != 1
            request = urllib.request.Request(api_url + f'?fresh={time.time_ns()}' if use_api else public_url,
                                             headers={'Accept': 'application/octet-stream'})
            if use_api:
                request.add_unredirected_header('Authorization', f'Bearer {token}')
            try:
                with urllib.request.urlopen(request, timeout=90) as source:
                    if use_api and source.headers.get_content_type() == 'application/json':
                        raise URLError('GitHub returned asset metadata instead of the download')
                    with candidate.open('wb') as stream:
                        received = 0
                        while chunk := source.read(1024 * 1024):
                            received += len(chunk)
                            if size is not None and received > size:
                                raise ValueError(f'{target.name} exceeds its pinned size.')
                            stream.write(chunk)
                break
            except (URLError, TimeoutError, ConnectionError, IncompleteRead) as error:
                retryable = not isinstance(error, HTTPError) or error.code in (429, 500, 502, 503, 504)
                api_denied = use_api and isinstance(error, HTTPError) and error.code in (401, 403, 404)
                if attempt == 2 or not (retryable or api_denied):
                    raise
                print(f'{target.name} download failed ({error}); retrying.', flush=True)
                time.sleep(2 ** (attempt + 1))
        if size is not None and candidate.stat().st_size != size:
            raise ValueError(f'{target.name} download size mismatch.')
        if digest(candidate) != expected_sha:
            raise ValueError(f'{target.name} download hash mismatch.')
        candidate.replace(target)
