"""Review summaries must describe the checked action without rewriting its plan."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine-host'))
import review_copy


class ReviewCopyTests(unittest.TestCase):
    def review(self, operation='install', mode='nr-mfg'):
        return dict(operation=operation, apply_requested_presets=True, mfg_multiplier=4,
                    plans=[{'preview': {'feature_mode': mode}, 'payload': b'exact bytes'}],
                    rows=[dict(name='PRAGMATA', detail='Full path and SHA-256 digest',
                               native_summary='Update 3 DLSS files. Originals will be backed up.',
                               display_summary='Set Borderless in the game for the overlay.')],
                    blocked=[])

    def test_summary_preserves_payload_and_diagnostics(self):
        review = self.review()
        plans = copy.deepcopy(review['plans'])
        review_copy.attach(review)
        row = review['rows'][0]
        self.assertIn('Install NR + MFG. Request 4× frame generation.', row['summary'])
        self.assertIn('Update 3 DLSS files.', row['summary'])
        self.assertIn('Set Borderless in the game', row['summary'])
        self.assertNotIn('SHA-256', row['summary'])
        self.assertEqual(row['detail'], 'Full path and SHA-256 digest')
        self.assertEqual(review['plans'], plans)

    def test_nr_only_does_not_claim_frame_generation(self):
        review = self.review(mode='nr-only')
        review_copy.attach(review)
        self.assertTrue(review['rows'][0]['summary'].startswith('Install NR.'))
        self.assertNotIn('frame generation', review['rows'][0]['summary'])

    def test_repair_does_not_claim_requested_presets_will_be_applied(self):
        review = self.review(operation='repair')
        review['apply_requested_presets'] = False
        review_copy.attach(review)
        self.assertTrue(review['rows'][0]['summary'].startswith('Repair NR + MFG. Keep your current tuning.'))
        self.assertNotIn('4×', review['rows'][0]['summary'])

    def test_restore_and_presets_do_not_claim_package_installation(self):
        for operation in ('uninstall', 'reset'):
            review = self.review(operation)
            review_copy.attach(review)
            self.assertNotIn('Install NR', review['rows'][0]['summary'])

    def test_adoption_keeps_its_distinct_effects(self):
        review = self.review()
        review['plans'][0]['preview'] = {'launch_options': 'Already installed on Linux; no game files change'}
        review_copy.attach(review)
        self.assertTrue(review['rows'][0]['summary'].startswith('Already installed on Linux; no game files change'))

    def test_restored_support_files_are_disclosed(self):
        review = self.review()
        review['plans'][0]['preview']['restored_support_tree'] = True
        review_copy.attach(review)
        self.assertIn('Back up the support files kept by your earlier restore.', review['rows'][0]['summary'])

    def test_blocked_reason_is_preserved_and_unknown_errors_stay_visible(self):
        reason = 'Existing OptiScaler configuration/runtime is unmanaged. Restore or remove it before installing Skynizz.'
        review = self.review()
        review['blocked'] = [{'reason': reason}, {'reason': 'Close the running game before continuing.'}]
        review_copy.attach(review)
        self.assertEqual(review['blocked'][0]['reason'], reason)
        self.assertIn('Restore or remove that mod', review['blocked'][0]['summary'])
        self.assertEqual(review['blocked'][1]['summary'], review['blocked'][1]['reason'])


if __name__ == '__main__':
    unittest.main()
