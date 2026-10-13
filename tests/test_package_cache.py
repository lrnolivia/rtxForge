from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import packages
import transactions as t


MEMBERS = {
    'OptiScaler.dll': b'opti',
    'OptiScaler.ini': b'[FrameGen]\nEnabled=true\n',
    'OptiScaler/streamline/sl.interposer.dll': b'streamline',
}


def provider():
    return {
        'url': 'https://example.invalid/payload.7z',
        'asset': 'payload.7z',
        'sha256': 'pinned-archive-id',
    }


def patch_extractor(monkeypatch, tmp_path):
    archive = tmp_path / 'payload.7z'
    archive.write_bytes(b'fixture archive')
    monkeypatch.setattr(packages, 'download', lambda *a, **k: archive)
    monkeypatch.setattr(packages, 'entries', lambda *a, **k: list(MEMBERS))

    def fake_extract(_archive, member, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(MEMBERS[member])

    monkeypatch.setattr(packages, 'extract', fake_extract)


def expected_manifest(c, pkg):
    return {
        'archive_sha256': c['sha256'],
        'files': {n: t.digest(pkg / n) for n in t.files(pkg).values()},
    }


def test_listing_drift_rebuilds_disposable_payload(monkeypatch, tmp_path):
    c = provider()
    cache = tmp_path / 'cache'
    pkg = cache / 'payload'
    record = cache / 'files.json'
    pkg.mkdir(parents=True)
    for name, data in MEMBERS.items():
        p = pkg / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    manifest = expected_manifest(c, pkg)
    record.write_text(json.dumps(manifest), encoding='utf-8')
    (pkg / 'stale-extra.dll').write_bytes(b'stale')

    patch_extractor(monkeypatch, tmp_path)
    rebuilt = packages._load_base_payload(c, cache, pkg, record, readonly=False)

    assert not (pkg / 'stale-extra.dll').exists()
    packages.verify(pkg, rebuilt)
    assert rebuilt == t.read_json(record)


def test_partial_payload_without_manifest_rebuilds(monkeypatch, tmp_path):
    c = provider()
    cache = tmp_path / 'cache'
    pkg = cache / 'payload'
    record = cache / 'files.json'
    pkg.mkdir(parents=True)
    (pkg / 'partial.tmp').write_bytes(b'partial')

    patch_extractor(monkeypatch, tmp_path)
    rebuilt = packages._load_base_payload(c, cache, pkg, record, readonly=False)

    assert not (pkg / 'partial.tmp').exists()
    packages.verify(pkg, rebuilt)
    assert record.is_file()


def test_readonly_reports_drift_without_mutating(monkeypatch, tmp_path):
    c = provider()
    cache = tmp_path / 'cache'
    pkg = cache / 'payload'
    record = cache / 'files.json'
    pkg.mkdir(parents=True)
    for name, data in MEMBERS.items():
        p = pkg / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    manifest = expected_manifest(c, pkg)
    record.write_text(json.dumps(manifest), encoding='utf-8')
    stale = pkg / 'stale-extra.dll'
    stale.write_bytes(b'stale')

    with pytest.raises(t.Refusal, match='run Prepare/Install once to rebuild'):
        packages._load_base_payload(c, cache, pkg, record, readonly=True)

    assert stale.exists()
    assert record.exists()
