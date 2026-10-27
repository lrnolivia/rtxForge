"""Shared downloads complete before per-game review; staging never writes games."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'windows/engine-host')]
import install_prefetch as stage
import runtime_updates as runtime


class InstallPrefetchTests(unittest.TestCase):
    def test_each_dlss_file_and_distinct_package_is_staged_once_in_order(self):
        events = []
        entries = {'sr': {'name': 'sr'}, 'rr': {'name': 'rr'}, 'fg': {'name': 'fg'}}
        first = {'mode': 'nr-mfg', 'settings': {'runtime_provider': 'skynizz'}}
        second = {'mode': 'nr-only', 'settings': {'runtime_provider': 'feeder'}}
        with patch.object(runtime, 'catalog', return_value={'entries': entries}) as lookup, \
             patch.object(runtime, 'download', side_effect=lambda config, entry: events.append(entry['name'])), \
             patch.object(stage, 'package', side_effect=lambda config, mode, settings: events.append(settings['runtime_provider'])):
            result = stage.prepare({}, [first, second, first])
        lookup.assert_called_once()
        self.assertEqual(events, ['sr', 'rr', 'fg', 'skynizz', 'feeder'])
        self.assertEqual(result['packages'], 2)
        self.assertEqual(result['dlss_files'], 3)

    def test_optional_rate_limit_does_not_prevent_feature_package_staging(self):
        with patch.object(runtime, 'catalog', side_effect=runtime.CatalogRateLimit('GitHub rate limit')), \
             patch.object(stage, 'package') as package:
            result = stage.prepare({}, [{'mode': 'nr-only', 'settings': {'runtime_provider': 'skynizz'}}])
        package.assert_called_once()
        self.assertEqual(result['dlss_files'], 0)
        self.assertIn('rate limit', result['dlss_unavailable'])

    def test_disabled_dlss_updates_do_not_contact_catalog(self):
        with patch.object(runtime, 'catalog', side_effect=AssertionError('Unexpected network lookup')):
            self.assertEqual(stage.prepare({}, [], manage_dlss=False)['dlss_files'], 0)

    def test_invalid_download_still_refuses_before_packages_are_staged(self):
        with patch.object(runtime, 'catalog', return_value={'entries': {'sr': {'name': 'sr'}}}), \
             patch.object(runtime, 'download', side_effect=stage.t.Refusal('Runtime source content mismatch')), \
             patch.object(stage, 'package') as package:
            with self.assertRaisesRegex(stage.t.Refusal, 'content mismatch'):
                stage.prepare({}, [{'mode': 'nr-only', 'settings': {}}])
        package.assert_not_called()


if __name__ == '__main__':
    unittest.main()
