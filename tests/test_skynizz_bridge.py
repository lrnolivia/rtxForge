"""Check the real compiled dependency produced by the Windows build."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import skynizz_provider


@unittest.skipUnless((ROOT / 'windows/out/skynizz-bridge/package.json').is_file(),
                     'The Windows build produces the compiled bridge')
class CompiledBridgeTest(unittest.TestCase):
    def test_compiled_archive_matches_its_source_receipt(self):
        record, archive = skynizz_provider.bundled_bridge()
        payload, meta = skynizz_provider.load_payload(archive, record)
        for source, destination in skynizz_provider.FILES.items():
            self.assertEqual(hashlib.sha256(payload[destination]).hexdigest(), record['files'][source])
        self.assertGreater(len(payload['dxgi.dll']), 64 * 1024)
        self.assertFalse(meta['runtime_verified'])
        skynizz_provider.require_mode('windows', 'nr-mfg', bridge=True)


if __name__ == '__main__':
    unittest.main()
