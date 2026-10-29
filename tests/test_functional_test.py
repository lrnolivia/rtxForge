"""Functional verdicts must be backed by this session's real provider signals."""
from pathlib import Path
import json
import math
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import beta_report
import cross_os
import functional_test as ft
import game_notes
import transactions as t


def snapshot(**changes):
    found = dict(state='running', telemetry_source='skynizz-mailbox', pid=12, sequence=4, version=7,
                 can_nr=True, can_mfg=True, nr_running=True, nr_ms=1.2, rendered_fps=60,
                 nr_placement_verified=True, nr_placement=3, native_fresh=True,
                 native_status=0, native_presented=4, native_generated=3, native_mode=1, fg_successes=100,
                 values={'enabled': 1, 'intensity': 1, 'multiplier': 4, 'dynamic_mfg': 0})
    found.update(changes)
    return found


class FunctionalEvidenceTests(unittest.TestCase):
    def results(self, found=None, logs=None, route='skynizz', **checks):
        samples = [ft.compact(snapshot(sequence=2), 1), ft.compact(snapshot(), 2)] if found is None else found
        preflight = dict(route=route, files_ok=True, settings_ok=True, shortcut_ok=True,
                         platform='windows', feature_mode='nr-mfg', **checks)
        helper = dict(start=True, finish=True, channel_valid=True, pid=12)
        return {r['part']: r for r in ft.evaluate(ft.summarize(samples), logs, helper, checks=preflight)}

    def test_live_execution_has_gpu_time_placement_generated_frames_and_attachment(self):
        results = self.results()
        self.assertEqual([r['part'] for r in results.values()], [p for p, _ in ft.PARTS])
        for part in ('files', 'settings', 'shortcut', 'hook', 'nr', 'mfg', 'panel', 'helper'):
            self.assertEqual(results[part]['state'], ft.WORKING, results[part])
        self.assertIn('1.20 ms', str(results['nr']['evidence']))
        self.assertIn('after super resolution', str(results['nr']['evidence']))
        self.assertEqual(ft.suggestion(list(results.values())), 'Working')

    def test_a_process_or_file_status_is_not_a_live_hook(self):
        found = [ft.compact(snapshot(telemetry_source=None, version=None), 1)]
        results = self.results(found)
        for part in ('hook', 'nr', 'mfg'):
            self.assertNotEqual(results[part]['state'], ft.WORKING)

    def test_stalled_and_frozen_nr_values_never_pass(self):
        for samples in ([ft.compact(snapshot(state='stalled'), 1)],
                        [ft.compact(snapshot(), 1), ft.compact(snapshot(), 2)],
                        [ft.compact(snapshot(sequence=2, nr_ms=None), 1), ft.compact(snapshot(nr_ms=0), 2)]):
            with self.subTest(samples=samples):
                self.assertNotEqual(self.results(samples)['nr']['state'], ft.WORKING)

    def test_nonfinite_measurements_are_unknown(self):
        found = ft.compact(snapshot(nr_ms=math.nan, rendered_fps=math.inf), 1)
        self.assertIsNone(found['nr_ms']); self.assertIsNone(found['fps'])

    def test_old_protocol_cannot_claim_mfg_success(self):
        found = [ft.compact(snapshot(native_presented=None, native_generated=None, native_fresh=False), 1)]
        self.assertEqual(self.results(found)['mfg']['state'], ft.NOT_REPORTED)

    def test_requested_multiplier_and_successful_calls_are_not_generated_frames(self):
        found = [ft.compact(snapshot(native_generated=0, native_presented=1), 1)]
        result = self.results(found)['mfg']
        self.assertEqual(result['state'], ft.PROBLEM)
        self.assertIn('game’s own settings', result['fix'])

    def test_requested_generated_count_is_never_reported_as_measured_frames(self):
        found=ft.compact(snapshot(native_generated=5,native_presented=2),1)
        summary=ft.summarize([found])
        self.assertEqual(summary['configured_generated'],5)
        self.assertEqual(summary['generated'],1)

    def test_brief_success_does_not_hide_mostly_failed_or_refused_generation(self):
        found=[ft.compact(snapshot(native_presented=1),i) for i in range(8)]+[ft.compact(snapshot(),9)]
        self.assertEqual(self.results(found)['mfg']['state'],ft.PROBLEM)
        self.assertEqual(self.results([ft.compact(snapshot(native_status=2),1)])['mfg']['state'],ft.PROBLEM)

    def test_mfg_settings_changes_do_not_compare_different_requests(self):
        a = snapshot(sequence=2); b = snapshot(values=dict(a['values'], multiplier=2))
        self.assertEqual(self.results([ft.compact(a, 1), ft.compact(b, 2)])['mfg']['state'], ft.NOT_TESTED)

    def test_dynamic_mfg_does_not_require_fixed_multiplier(self):
        found = snapshot(native_presented=2, native_generated=1, dynamic_supported=True,
                         values={'enabled': 1, 'intensity': 1, 'multiplier': 4, 'dynamic_mfg': 1})
        self.assertEqual(self.results([ft.compact(found, 1)])['mfg']['state'], ft.WORKING)
        found['dynamic_supported'] = False
        self.assertEqual(self.results([ft.compact(found, 1)])['mfg']['state'], ft.PROBLEM)

    def test_streamline_error_has_specific_remedy(self):
        result = self.results([ft.compact(snapshot(native_generated=0, native_status=2), 1)])['mfg']
        self.assertIn('Reflex', result['fix'])

    def test_feeder_evaluation_is_distinct_from_feed_requests_and_model_creation(self):
        created = {'ReShade.log': 'feature 18 created via the signed snippet'}
        self.assertEqual(self.results([], created, 'feeder')['nr']['state'], ft.PROBLEM)
        evaluated = dict(created, **{'host64/ReShade.log': 'feature 18 evaluation succeeded (count=42)'})
        result = self.results([], evaluated, 'feeder')
        self.assertEqual(result['nr']['state'], ft.WORKING)
        self.assertEqual(result['mfg']['state'], ft.NOT_TESTED)
        self.assertIn('42', str(result['nr']['evidence']))
        self.assertNotEqual(self.results([], {'dlss5-feed.log': 'feed count=9000'}, 'feeder')['nr']['state'], ft.WORKING)

    def test_vulkan_uses_observed_displayed_frames_and_status(self):
        logs = {'fgvk.log': 'fgvk log start\nFG stats: 300 presents -> 1200 frames displayed (x4.00) status=0'}
        results = self.results([], logs, 'vulkan-native', requested=4)
        self.assertEqual(results['mfg']['state'], ft.WORKING)
        self.assertEqual(results['nr']['state'], ft.NOT_REPORTED)
        logs['fgvk.log'] = 'FG stats: 300 presents -> 300 frames displayed (x1.00) status=2'
        self.assertEqual(self.results([], logs, 'vulkan-native')['mfg']['state'], ft.PROBLEM)

    def test_vulkan_nr_uses_completed_evaluations_and_positive_timing(self):
        for ms,state in [('1.25',ft.WORKING),('0.00',ft.NOT_REPORTED)]:
            result=self.results([],{'fgvk.log':f'NR stats: 120 native Vulkan evaluations composed, GPU {ms}ms'},'vulkan-native')['nr']
            self.assertEqual(result['state'],state)

    def test_zero_feeder_evaluations_and_zero_gpu_windows_are_not_passes(self):
        for route,logs in [('feeder',{'ReShade.log':'feature 18 evaluation succeeded (count=0)'}),
                           ('y4my',{'OptiScaler.log':'DLSS-NR GPU window: 0 samples'})]:
            self.assertNotEqual(self.results([],logs,route)['nr']['state'],ft.WORKING)

    def test_every_catalog_package_gets_all_parts_and_unknown_never_passes(self):
        catalog = json.loads((Path(__file__).resolve().parents[1] / 'providers/lock.json').read_text())
        for route in [*catalog, 'feeder', 'vulkan-native', 'custom-package']:
            with self.subTest(route=route):
                results = self.results([], route=route)
                self.assertEqual(set(results), {p for p, _ in ft.PARTS})
                self.assertNotEqual(results['nr']['state'], ft.WORKING)
                self.assertNotEqual(results['mfg']['state'], ft.WORKING)
                self.assertIsNone(ft.suggestion(list(results.values())))
                for part in ('hook', 'nr', 'panel'):
                    self.assertTrue(results[part]['fix'])

    def test_counter_resets_and_long_sessions_are_bounded(self):
        samples = [ft.compact(snapshot(fg_successes=100, pid=12), 1), ft.compact(snapshot(fg_successes=3, pid=14), 2)]
        self.assertEqual(ft.summarize(samples)['fg_calls'], 0)
        for i in range(ft.SAMPLE_LIMIT * 2): ft.keep(samples, {'t': i})
        self.assertLessEqual(len(samples), ft.SAMPLE_LIMIT)
        self.assertEqual(samples[-1]['t'], ft.SAMPLE_LIMIT * 2 - 1)


class FunctionalSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.game = self.root / 'game'; self.game.mkdir()
        (self.game / 'Game.exe').write_bytes(b'MZ')
        self.row = dict(game=str(self.game), exe='Game.exe', name='Example Game')
        patcher = patch.object(game_notes, 'root', return_value=self.root / 'reports')
        patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(game_notes.library_media, 'load_settings', return_value={'runtime_provider': 'skynizz'})
        patcher.start(); self.addCleanup(patcher.stop)

    def test_preflight_checks_actual_installed_package_not_selected_package(self):
        (self.game / 'dxgi.dll').write_bytes(b'owned')
        cross_os.write(self.game, 'windows', ['dxgi.dll'], {'id': 'y4my'}, 'nr-mfg', 'dxgi.dll')
        (self.game / 'OptiScaler.ini').write_text('[DlssNr]\nEnabled=true\nIntensity=9\n')
        check = ft.preflight(self.row, {'runtime_provider': 'skynizz'})
        self.assertEqual(check['route'], 'y4my'); self.assertTrue(check['files_ok']); self.assertFalse(check['settings_ok'])
        (self.game / 'dxgi.dll').write_bytes(b'other')
        self.assertFalse(ft.preflight(self.row)['files_ok'])

    def test_old_log_appended_does_not_reuse_old_success(self):
        log = self.game / 'OptiScaler.log'
        log.write_text('OptiScaler v1 loaded\nCreateFeature(18) result=0x1\nDLSS-NR GPU window: 256 samples\n')
        baseline = ft.log_baseline(self.row)
        with log.open('a') as stream: stream.write('some new unrelated warning\n')
        _, fresh = ft.session_logs(self.row, baseline)
        self.assertFalse(ft.log_evidence(fresh, 'y4my')['nr_evaluated'])
        self.assertFalse(ft.log_evidence(fresh, 'y4my')['hook'])

    def test_new_log_and_log_rotation_are_real_session_evidence(self):
        baseline = ft.log_baseline(self.row)
        log = self.game / 'OptiScaler.log'; log.write_text('OptiScaler v2 loaded\nDLSS-NR GPU window: 256 samples\n')
        _, fresh = ft.session_logs(self.row, baseline)
        self.assertTrue(ft.log_evidence(fresh, 'y4my')['nr_evaluated'])
        baseline = ft.log_baseline(self.row)
        log.write_text('OptiScaler v3 loaded\n')
        self.assertTrue(ft.log_evidence(ft.session_logs(self.row, baseline)[1], 'y4my')['hook'])

    def test_finish_persists_results_and_never_overwrites_user_verdict(self):
        game_notes.start({}, self.row, {'route': 'feeder', 'platform': 'windows', 'helper': True})
        (self.game / 'ReShade.log').write_text('feature 18 created via the signed snippet\nfeature 18 evaluation succeeded (count=42)')
        record = game_notes.finish({}, self.row, samples=[], helper={'running': True})
        self.assertEqual(record['status'], 'Untested')
        self.assertNotIn('active', record)
        test = game_notes.latest_test(record)
        self.assertEqual(test['route'], 'feeder'); self.assertIn('Suggested fix:', test['text'])
        answers, _ = ft.report_answers(test['results'])
        self.assertEqual(answers['nr-result'], 'Working in-game'); self.assertNotIn('mfg-result', answers)
        with self.assertRaises(t.Refusal): game_notes.finish({}, self.row)

    def test_finish_refuses_changed_executable(self):
        game_notes.start({}, self.row, {'route': 'skynizz'})
        with self.assertRaises(t.Refusal): game_notes.finish({}, dict(self.row, exe='Other.exe'))

    def test_sampler_persistence_is_bound_to_session_identity(self):
        path = ft._sample_path({}, self.row); path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'session': 'old', 'samples': [ft.compact(snapshot(), 1)]}))
        self.assertEqual(ft.read_samples({}, self.row, {'id': 'new'}), [])
        self.assertEqual(len(ft.read_samples({}, self.row, {'id': 'old'})), 1)

    def test_report_prefills_are_editable_and_keep_visual_judgment_explicit(self):
        results = FunctionalEvidenceTests().results()
        record = {'status': 'Untested', 'sessions': [{'functional': {'results': list(results.values())}}]}
        facts = {k: ('Windows' if k == 'platform' else 'Not sure', 'unknown') for k in ('platform', 'distribution', 'gpu-series', 'gpu', 'app-format', 'app-build')}
        report = beta_report.draft(self.row, facts, record)
        self.assertEqual(report['fields']['nr-result'], 'Working in-game')
        self.assertEqual(report['sources']['nr-result'], 'functional')
        self.assertEqual(report['fields']['observations'], '')
        self.assertIn('Test ·', '\n'.join(beta_report.details(report)))
        beta_report.correct(report, 'nr-result', 'Not working in-game')
        self.assertEqual(report['sources']['nr-result'], 'yours')


if __name__ == '__main__': unittest.main()
