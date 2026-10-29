"""Vulkan NR + Universal MFG installs share their install record with the other OS."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path[:0] = [str(Path(__file__).resolve().parents[2] / 'scripts')]
import cross_os  # noqa: E402
import vulkan_app  # noqa: E402


class VulkanCrossOsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'Baldurs Gate 3'
        self.target = self.root / 'bin'
        (self.target / 'NativeMods/rtxForge-vulkan').mkdir(parents=True)
        (self.target / 'bg3.exe').write_bytes(b'MZ')
        (self.target / 'bink2w64.dll').write_bytes(b'loader')
        (self.target / 'NativeMods/fgvk.dll').write_bytes(b'fg')

    def legacy_windows_layout(self):
        (self.target / 'NativeMods/rtxForge-vulkan/source-receipt.json').write_text('{}')
        (self.target / 'bink2w64_rtxforge_original.dll').write_bytes(b'stock bink')

    def test_install_writes_the_shared_record(self):
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            vulkan_app.write_record(self.target)
        record = cross_os.read(self.target)
        self.assertEqual((record['os'], record['provider']['id'], record['proxy'], record['proton_overrides']),
                         ('windows', vulkan_app.ID, 'bink2w64.dll', ['bink2w64']))
        self.assertIn('NativeMods/fgvk.dll', record['files'])
        self.assertIn('bink2w64.dll', record['files'])

    def test_linux_recognises_windows_installs_with_or_without_a_record(self):
        with patch.object(cross_os, 'THIS_OS', 'linux'):
            self.assertIsNone(vulkan_app.windows_record(self.target), 'no package layout, no record')
            self.legacy_windows_layout()
            legacy = vulkan_app.windows_record(self.target)
            self.assertEqual((legacy['os'], legacy['proton_overrides'], legacy['legacy']), ('windows', ['bink2w64'], True))
        with patch.object(cross_os, 'THIS_OS', 'windows'):
            vulkan_app.write_record(self.target)
        with patch.object(cross_os, 'THIS_OS', 'linux'):
            self.assertNotIn('legacy', vulkan_app.windows_record(self.target))
            # A Linux install of the package is not a Windows install.
            vulkan_app.write_record(self.target)
            self.assertIsNone(vulkan_app.windows_record(self.target))

    def test_the_library_shows_a_windows_install_not_an_available_game(self):
        self.legacy_windows_layout()
        row = {'name': "Baldur's Gate 3", 'game': str(self.root), 'exe': 'bin/bg3.exe'}
        with patch.object(cross_os, 'THIS_OS', 'linux'), patch.object(vulkan_app, 'owned', lambda row, config=None: None), \
             patch.object(vulkan_app, 'bundled', lambda: (None, None, None, None)):
            vulkan_app.decorate([row])
        self.assertEqual((row['installed'], row['installed_on'], row['runtime_provider'], row['blocked']),
                         (True, 'windows', vulkan_app.ID, ''))
        self.assertTrue(row['vulkan_windows'])


if __name__ == '__main__':
    unittest.main()
