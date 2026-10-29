import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('beta_release', ROOT / 'packaging/beta_release.py')
beta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(beta)

WIN_SHA = 'a' * 40
LINUX_SHA = 'b' * 40
WINDOWS = [
    'rtxForge-Setup-1.0.0-beta.2-x64.exe', 'rtxForge-Setup-1.0.0-beta.2-x64.exe.sha256',
    'rtxForge-Setup-1.0.0-beta.2-arm64.exe', 'rtxForge-Setup-1.0.0-beta.2-arm64.exe.sha256',
    'rtxForge-windows-1.0.0-beta.2-x64.zip', 'rtxForge-windows-1.0.0-beta.2-x64.zip.sha256',
]
LINUX = [
    'rtxForge-1.0.0-beta.2-x86_64.AppImage', 'rtxForge-1.0.0-beta.2-x86_64.AppImage.sha256',
    'rtxForge-1.0.0-beta.2-x86_64.flatpak', 'rtxForge-1.0.0-beta.2-x86_64.flatpak.sha256',
    'rtxforge-beta-linux.json',
]
# Published before the Flatpak joined the release.
LINUX_APPIMAGE_ONLY = [name for name in LINUX if '.flatpak' not in name]
PREVIOUS = ['rtxForge-Setup-1.0.0-beta.1-x64.exe.previous-cccccccccccc', 'rtxforge-beta-linux.json.previous-dddddddddddd']
LEGACY_BODY = ('rtxForge 1.0 Beta notes.\n\nThis build is unsigned.\n\n'
               f'Version: `1.0.0-beta.2` · Source: `{WIN_SHA}` · [Build](https://example/1)\n')


def release(names, body=''):
    return {'assets': [{'name': n} for n in names], 'body': body}


class OwnershipTests(unittest.TestCase):
    def test_each_os_counts_only_its_own_current_assets(self):
        mixed = release(WINDOWS + LINUX + PREVIOUS)
        self.assertEqual(beta.owned('windows', mixed), WINDOWS)
        self.assertEqual(beta.owned('linux', mixed), LINUX)

    def test_a_release_from_before_the_flatpak_is_still_linux(self):
        self.assertEqual(beta.owned('linux', release(WINDOWS + LINUX_APPIMAGE_ONLY)), LINUX_APPIMAGE_ONLY)

    def test_flatpak_rollback_copies_belong_to_neither(self):
        self.assertIsNone(beta.owner('rtxForge-1.0.0-beta.2-x86_64.flatpak.previous-bbbbbbbbbbbb'))
        self.assertIsNone(beta.owner('rtxForge-1.0.0-beta.2-x86_64.flatpakref'))

    def test_unknown_and_continuous_assets_belong_to_neither(self):
        for name in ['rtxForge-Bazzite-x86_64.AppImage', 'rtxforge-update.json', 'notes.txt',
                     'RTXForge-1.0.0-beta.2-Bazzite-x86_64.AppImage']:
            self.assertIsNone(beta.owner(name), name)


class NotesTests(unittest.TestCase):
    def test_legacy_windows_line_is_read_as_windows_source(self):
        self.assertEqual(beta.source('windows', release(WINDOWS, LEGACY_BODY)), WIN_SHA)
        self.assertIsNone(beta.source('linux', release(WINDOWS, LEGACY_BODY)))

    def test_linux_publish_keeps_the_windows_line(self):
        text = beta.notes('linux', 'Base notes.\n', release(WINDOWS, LEGACY_BODY),
                          '1.0.0-beta.2', LINUX_SHA, 'https://example/2')
        self.assertTrue(text.startswith('Base notes.\n\n'))
        self.assertNotIn('Version: `', text)
        published = release(WINDOWS + LINUX, text)
        self.assertEqual(beta.source('windows', published), WIN_SHA)
        self.assertEqual(beta.source('linux', published), LINUX_SHA)
        self.assertLess(text.index('Windows:'), text.index('Linux:'))

    def test_windows_publish_replaces_only_its_line(self):
        both = beta.notes('linux', 'Base.\n', release([], LEGACY_BODY), '1.0.0-beta.2', LINUX_SHA, 'u')
        new_win = 'e' * 40
        text = beta.notes('windows', 'New base.\n', release([], both), '1.0.0-beta.3', new_win, 'v',
                          'This build is unsigned.')
        self.assertEqual(beta.source('windows', release([], text)), new_win)
        self.assertEqual(beta.source('linux', release([], text)), LINUX_SHA)
        self.assertIn('[Build](v). This build is unsigned.', text)
        self.assertEqual(text.count('Windows:'), 1)

    def test_first_publish_has_only_its_own_line(self):
        text = beta.notes('linux', 'Base.\n', None, '1.0.0-beta.2', LINUX_SHA, 'u')
        self.assertIsNone(beta.source('windows', release([], text)))
        self.assertRaises(ValueError, beta.notes, 'linux', 'Base.', None, '1.0.0-beta.2', 'main', 'u')

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, 'release.json')
            path.write_text(json.dumps(release(WINDOWS + LINUX, LEGACY_BODY)))
            run = lambda *a: subprocess.run([sys.executable, str(ROOT / 'packaging/beta_release.py'), *a],
                                            capture_output=True, text=True)
            self.assertEqual(run('owned', 'linux', str(path)).stdout.split(), LINUX)
            self.assertEqual(run('source', 'windows', str(path)).stdout.strip(), WIN_SHA)
            self.assertNotEqual(run('source', 'linux', str(path)).returncode, 0)


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import yaml
        except ImportError:
            raise unittest.SkipTest('PyYAML is not installed')
        load = lambda name: yaml.safe_load((ROOT / '.github/workflows' / name).read_text(encoding='utf-8'))
        cls.linux, cls.windows = load('linux-build.yml'), load('windows-build.yml')

    def test_publish_jobs_share_one_serial_group(self):
        for workflow in (self.linux, self.windows):
            job = workflow['jobs']['publish-beta']
            self.assertEqual(job['concurrency'], {'group': 'rtxforge-beta-release', 'cancel-in-progress': False})
            self.assertIn("github.ref == 'refs/heads/main'", job['if'])
            script = job['steps'][-1]['run']
            self.assertIn('test "$GITHUB_SHA" = "$EXPECTED_SHA"', script)
            self.assertIn('git/ref/heads/main', script)
            self.assertIn('beta_release.py owned', script)
            self.assertNotIn('target_commitish', script)

    def test_linux_dispatch_gates_before_building(self):
        inputs = self.linux[True]['workflow_dispatch']['inputs']  # PyYAML reads the 'on' key as True
        self.assertIn('publish_beta', inputs)
        self.assertIn('expected_sha', inputs)
        first = self.linux['jobs']['build-appimage']['steps'][0]
        self.assertEqual(first['name'], 'Validate explicit Beta publication')
        self.assertIn('publish_preview', first['run'].lower())

    def test_push_never_cancels_a_manual_publication(self):
        # Groups are per event, so pushes and pull requests never share one with a manual run,
        # and manual runs are never cancelled.
        concurrency = self.linux['concurrency']
        self.assertTrue(concurrency['group'].startswith('rtxforge-linux-${{ github.event_name }}'))
        self.assertEqual(concurrency['cancel-in-progress'], "${{ github.event_name != 'workflow_dispatch' }}")
        triggers = self.linux.get('on', self.linux.get(True))  # YAML 1.1 reads 'on' as true
        self.assertNotIn('publish', str(triggers['pull_request']))

    def test_flatpak_builds_on_every_review_and_joins_the_beta(self):
        job = self.linux['jobs']['build-flatpak']
        self.assertNotIn('if', job, 'pull requests and main pushes build the Flatpak too')
        steps = {s.get('name'): s for s in job['steps']}
        self.assertIn('packaging/build_flatpak.py', steps['Build Flatpak bundle']['run'])
        self.assertIn('verify_bundle.py', steps['Verify the installed Flatpak']['run'])
        self.assertIn('inputs.publish_beta', steps['Create Beta Flatpak assets']['if'])
        self.assertIn('dist/beta-flatpak/', steps['Upload Actions artifact']['with']['path'])
        publish = self.linux['jobs']['publish-beta']
        self.assertEqual(sorted(publish['needs']), ['build-appimage', 'build-flatpak'])
        script = publish['steps'][-1]['run']
        self.assertIn('test "$(ls | wc -l)" = 5', script)
        self.assertIn('sha256sum -c "$FLATPAK.sha256"', script)
        # A release from before the Flatpak (3 Linux files) is replaced with rollback copies too.
        self.assertIn('test "$CURRENT_COUNT" = 3', script)
        self.assertIn('x86_64.flatpak.sha256")', script)
        self.assertIn('"$FLATPAK" "$FLATPAK.sha256" rtxforge-beta-linux.json', script)

    def test_continuous_channel_is_unchanged(self):
        steps = {s.get('name'): s for s in self.linux['jobs']['build-appimage']['steps']}
        step = steps['Publish continuous updater release']
        self.assertIn('inputs.publish_preview', step['if'])
        self.assertIn('rtxForge-Bazzite-x86_64.AppImage', step['run'])


if __name__ == '__main__':
    unittest.main()
