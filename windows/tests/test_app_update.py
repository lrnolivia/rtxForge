"""Windows Beta discovery keeps architecture and checksum verification intact."""
import json
import ast
import platform
from pathlib import Path
import re
import sys
import types
import urllib.request
import uuid
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'windows/engine-host')]
import transactions

# Exercise the actual updater functions without importing unrelated native artwork
# and credential adapters (or initializing the user's Windows engine state).
updates = types.ModuleType('windows_updater_test')
updates.__dict__.update(json=json, platform=platform, re=re, urllib=urllib, uuid=uuid,
                        t=transactions, ROOT=ROOT, _reviews={})
source = ast.parse((ROOT / 'windows/engine-host/win_features.py').read_text(encoding='utf-8'))
functions = {'_version_key', '_get', 'update_check', '_review', '_item'}
nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in functions
         or isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in ('RELEASES', 'DOWNLOAD_PREFIX') for target in node.targets)]
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'win_features.py', 'exec'), updates.__dict__)


class WindowsBetaUpdateTests(unittest.TestCase):
    def release(self, tag='beta', version='1.0.0-beta.2', draft=False):
        name = f'rtxForge-Setup-{version}-x64.exe'
        return {'tag_name': tag, 'draft': draft, 'published_at': '2026-10-27T00:00:00Z', 'assets': [
            {'name': name, 'size': 1234, 'browser_download_url': updates.DOWNLOAD_PREFIX + tag + '/' + name},
            {'name': name + '.sha256', 'browser_download_url': updates.DOWNLOAD_PREFIX + tag + '/' + name + '.sha256'}]}

    def check(self, releases, current='1.0.0-beta.1'):
        def get(url, limit=0):
            return json.dumps(releases).encode() if url == updates.RELEASES else ('a' * 64).encode()
        with patch.object(updates, '_get', side_effect=get), patch.object(updates.platform, 'machine', return_value='AMD64'):
            return updates.update_check({'version': current})

    def test_beta_channel_selects_versioned_installer_and_checksum(self):
        result = self.check([self.release()])
        self.assertIn('1.0.0-beta.2', str(result))
        self.assertEqual(updates._reviews[result['token']]['payload']['sha256'], 'a' * 64)
        self.assertIn('rtxForge-Setup-1.0.0-beta.2-x64.exe', str(result))

    def test_current_beta_is_not_offered_again(self):
        self.assertIn('up to date', str(self.check([self.release(version='1.0.0-beta.1')])))

    def test_drafts_development_and_other_architecture_are_not_offered(self):
        wrong_arch = self.release()
        for asset in wrong_arch['assets']:
            asset['name'] = asset['name'].replace('x64', 'arm64')
        result = self.check([self.release(draft=True), self.release(tag='development'), wrong_arch])
        self.assertIn('up to date', str(result))

    def test_legacy_versioned_release_still_updates_forward(self):
        result = self.check([self.release(tag='windows-v1.0.0-rc.2', version='1.0.0-rc.2')], current='1.0.0-rc.1')
        self.assertIn('rtxForge-Setup-1.0.0-rc.2-x64.exe', str(result))

    def test_rollback_copies_in_an_updated_beta_are_ignored(self):
        # Publishing beta.2 keeps beta.1 in the same release under .previous-<commit> names.
        release = self.release()
        rollback = self.release(version='1.0.0-beta.1')['assets']
        for asset in rollback:
            asset['name'] += '.previous-9bf40c6b54ec'
        release['assets'] += rollback
        result = self.check([release])
        self.assertIn('rtxForge-Setup-1.0.0-beta.2-x64.exe', str(result))
        self.assertNotIn('.previous', str(result))

    def test_checksum_is_still_required(self):
        release = self.release()
        release['assets'] = release['assets'][:1]
        with self.assertRaisesRegex(updates.t.Refusal, 'no verified'):
            self.check([release])


if __name__ == '__main__':
    unittest.main()
