from pathlib import Path
import datetime
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.parse
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import beta_report
import compat_list
import cross_os
import transactions as t

HOST = {'gpu': 'NVIDIA GeForce RTX 4070', 'driver': '580.95', 'system': 'Linux'}
FORM = Path(__file__).resolve().parents[1] / '.github/ISSUE_TEMPLATE/beta-report.yml'
PAGE = Path(__file__).resolve().parents[1] / 'website/public/report.html'


class BetaReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.game = self.root / 'Example Game'
        (self.game / 'bin').mkdir(parents=True)
        self.row = {'name': 'Example Game', 'game': str(self.game), 'exe': 'bin/Example.exe', 'appid': '123'}
        self.facts = {'platform': ('Linux', 'detected'), 'distribution': ('Bazzite 42', 'detected'),
                      'gpu-series': ('RTX 40', 'detected'), 'gpu': ('NVIDIA GeForce RTX 4070 · driver 580.95', 'detected'),
                      'app-format': ('Flatpak', 'detected'), 'app-build': ('1.0.0-beta.3 · Beta', 'detected'),
                      'selected': 'Feeder NR 1.2'}

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, mode='nr-only', change=False):
        target = self.game / 'bin'
        (target / 'dxgi.dll').write_bytes(b'proxy')
        cross_os.write(target, 'linux', ['dxgi.dll'], {'id': 'feeder', 'name': 'Feeder NR', 'version': '1.1'}, mode, 'dxgi.dll')
        if change:(target / 'dxgi.dll').write_bytes(b'changed')

    # ---------- one schema everywhere ----------

    def test_fields_match_the_github_form_and_the_website(self):
        form = FORM.read_text(encoding='utf-8')
        page = PAGE.read_text(encoding='utf-8')
        for key, name in beta_report.FIELDS:
            self.assertIn(f'id: {key}\n', form)
            # Curation parses issues by these headings (compat_list.parse_issue).
            self.assertRegex(form, rf'id: {key}\n    attributes:\n      label: {re.escape(name)}\n')
            self.assertIn(f'name="{key}"', page)
        for key, choices in beta_report.CHOICES.items():
            if key == 'gpu-series':
                # A hidden field the page fills from the graphics card name.
                self.assertIn('id="gpu-series" name="gpu-series" value="Not sure"', page)
                continue
            for choice in choices:
                self.assertTrue(f'>{choice}<' in page or f'value="{choice}"' in page, f'{key}: {choice}')
        for key in beta_report.REQUIRED:
            self.assertRegex(form, rf'id: {key}\n(?:.*\n)*?    validations:\n      required: true')

    # ---------- host facts ----------

    def test_flatpak_reports_the_host_not_its_runtime(self):
        (self.root / 'etc').mkdir();(self.root / 'run/host').mkdir(parents=True)
        (self.root / 'etc/os-release').write_text('PRETTY_NAME="GNOME 51 (Flatpak runtime)"\n')
        (self.root / 'run/host/os-release').write_text('NAME="Bazzite"\nVERSION_ID=42\n')
        self.assertEqual(beta_report.distribution('Linux', self.root, sandboxed=True), ('Bazzite 42', 'detected'))
        self.assertEqual(beta_report.distribution('Linux', self.root, sandboxed=False), ('GNOME 51 (Flatpak runtime)', 'detected'))
        (self.root / 'run/host/os-release').unlink()
        self.assertEqual(beta_report.distribution('Linux', self.root, sandboxed=True), ('Not sure', 'unknown'))

    def test_app_format_comes_from_the_running_build_only(self):
        self.assertEqual(beta_report.app_format('Linux', {}, sandboxed=True), ('Flatpak', 'detected'))
        self.assertEqual(beta_report.app_format('Linux', {'APPIMAGE': '/x/rtxForge.AppImage'}, sandboxed=False), ('AppImage', 'detected'))
        self.assertEqual(beta_report.app_format('Linux', {}, sandboxed=False), ('Source / Other', 'detected'))
        # Windows never guesses installer or portable.
        self.assertEqual(beta_report.app_format('Windows', {}), ('Not sure', 'unknown'))
        self.assertEqual(beta_report.app_format('Windows', {}, windows_format='Windows installer'), ('Windows installer', 'detected'))

    def test_gpu_series_and_unknowns(self):
        series, model = beta_report.gpu(HOST)
        self.assertEqual(series, ('RTX 40', 'detected'))
        self.assertEqual(model, ('NVIDIA GeForce RTX 4070 · driver 580.95', 'detected'))
        self.assertEqual(beta_report.gpu({'gpu': 'Not detected'}), (('Not sure', 'unknown'), ('Not sure', 'unknown')))
        self.assertEqual(beta_report.app_build('Unknown'), ('Not sure', 'unknown'))

    # ---------- provenance ----------

    def test_selected_package_is_not_reported_as_installed(self):
        report = beta_report.draft(self.row, self.facts, {'status': 'Untested'})
        self.assertEqual(report['fields']['feature-package'], 'Feeder NR 1.2 (selected, not installed)')
        self.assertEqual(report['sources']['feature-package'], 'selected')
        self.assertEqual(report['fields']['features'], 'Not reached / Not sure')
        self.assertEqual((report['fields']['nr-result'], report['fields']['mfg-result']), ('Not sure', 'Not sure'))

    def test_installed_package_comes_from_the_install_record(self):
        self.install('nr-only')
        report = beta_report.draft(self.row, self.facts, {'status': 'Untested'})
        self.assertEqual(report['fields']['feature-package'], 'Feeder NR 1.1 (installed on Linux)')
        self.assertEqual(report['sources']['feature-package'], 'recorded')
        self.assertEqual(report['fields']['features'], 'NR only')
        # Installed files are not an in-game result.
        self.assertEqual(report['fields']['nr-result'], 'Installed, not tested')
        self.assertEqual(report['fields']['mfg-result'], 'Not installed')

    def test_changed_files_and_tested_games_leave_results_to_the_user(self):
        self.install('nr-mfg', change=True)
        report = beta_report.draft(self.row, self.facts, {'status': 'Working'})
        self.assertIn('files changed since', report['fields']['feature-package'])
        self.assertEqual((report['fields']['nr-result'], report['fields']['mfg-result']), ('Not sure', 'Not sure'))
        self.assertEqual(report['sources']['nr-result'], 'unknown')
        self.assertIn('files changed since', '\n'.join(beta_report.details(report)))

    def test_corrections_win_and_problems_name_what_is_missing(self):
        report = beta_report.draft(self.row, self.facts, {'status': 'Untested'})
        # Like the website, only the OS and what happened are required.
        self.assertEqual(beta_report.problems(report), ['What happened? is empty.'])
        beta_report.correct(report, 'game', '')
        self.assertEqual(beta_report.problems(report), ['What happened? is empty.'])
        beta_report.correct(report, 'nr-result', 'Working in-game')
        beta_report.correct(report, 'mfg-result', 'Not installed')
        beta_report.correct(report, 'features', 'NR only')
        beta_report.correct(report, 'observations', 'Sharper foliage with NR on.')
        self.assertEqual(report['sources']['nr-result'], 'yours')
        self.assertEqual(beta_report.problems(report), [])
        beta_report.correct(report, 'nr-result', 'Amazing')
        self.assertEqual(beta_report.problems(report), ['NR result: choose one of the listed answers.'])
        with self.assertRaises(t.Refusal):beta_report.correct(report, 'secret', 'x')

    # ---------- sharing ----------

    def ready(self):
        report = beta_report.draft(self.row, self.facts, {'status': 'Untested'})
        for key, value in (('features', 'NR only'), ('nr-result', 'Working in-game'), ('mfg-result', 'Not installed'),
                           ('observations', r'Crashed once in C:\Users\me\game; mail me@example.com')):
            beta_report.correct(report, key, value)
        return report

    def test_issue_link_prefills_the_form_and_redacts(self):
        report = self.ready()
        link = beta_report.issue_url(report)
        self.assertTrue(link['complete'])
        query = urllib.parse.parse_qs(urllib.parse.urlparse(link['url']).query)
        self.assertEqual(query['template'], ['beta-report.yml'])
        self.assertEqual(query['title'], ['[Beta report] Example Game · Linux'])
        self.assertEqual(query['nr-result'], ['Working in-game'])
        self.assertNotIn('Users', query['observations'][0])
        self.assertNotIn('example.com', query['observations'][0])
        self.assertIn('Report ID: ' + report['id'], query['observations'][0])

    def test_long_reports_are_cut_in_the_link_and_say_so(self):
        report = self.ready()
        # Non-Latin text grows ninefold when encoded into a link.
        beta_report.correct(report, 'observations', 'ゲーム' * 500)
        link = beta_report.issue_url(report)
        self.assertLessEqual(len(link['url']), beta_report.URL_LIMIT)
        self.assertFalse(link['complete'])

    def test_issue_text_parses_back_into_the_same_fields(self):
        report = self.ready()
        fields = compat_list.parse_issue(beta_report.text(report))
        for key in compat_list.REPORT_FIELDS:
            self.assertEqual(fields[key], report['fields'][key])

    def test_existing_issue_must_be_this_repository(self):
        url = 'https://github.com/lrnolivia/rtxForge/issues/42'
        for value in ('#42', '42', url, url + '/', url + '#issuecomment-1', url + '?x=1'):
            self.assertEqual(beta_report.existing_issue(value), {'number': 42, 'url': url})
        for value in ('https://github.com/someone/rtxForge/issues/42', 'http://github.com/lrnolivia/rtxForge/issues/42',
                      'https://github.com/lrnolivia/rtxForge/pull/42', 'https://evil.example/lrnolivia/rtxForge/issues/42',
                      '#0', 'forty-two', ''):
            with self.assertRaises(t.Refusal):beta_report.existing_issue(value)

    def test_app_link_accepts_only_the_log_scanner(self):
        self.assertEqual(beta_report.parse_link('rtxforge://support/logs'), {'action': 'logs', 'issue': None})
        self.assertEqual(beta_report.parse_link('rtxforge://support/logs/?issue=42'), {'action': 'logs', 'issue': 42})
        for value in ('rtxforge://support/logs?issue=42&issue=43', 'rtxforge://support/logs?path=/home',
                      'rtxforge://support/logs?issue=../x', 'rtxforge://support/install', 'rtxforge://evil/logs',
                      'https://support/logs', 'rtxforge://support/logs#x', 'rtxforge://support/logs?issue=0',
                      'rtxforge://support/logs?' + 'a' * 300, '', None):
            self.assertIsNone(beta_report.parse_link(value), value)

    def test_desktop_entries_register_the_app_link(self):
        flatpak = (Path(__file__).resolve().parents[1] / 'packaging/flatpak/io.github.lrnolivia.RTXForge.desktop').read_text()
        self.assertIn('Exec=rtxforge %u\n', flatpak)
        self.assertIn('MimeType=x-scheme-handler/rtxforge;\n', flatpak)
        installer = (Path(__file__).resolve().parents[1] / 'scripts/desktop_install.py').read_text()
        self.assertIn("'MimeType=x-scheme-handler/rtxforge;\\n'", installer)
        self.assertIn('%u', installer)

    # ---------- logs ----------

    def log(self, name, data, when=None):
        path = self.game / 'bin' / name
        path.write_bytes(data)
        if when:os.utime(path, (when.timestamp(), when.timestamp()))
        return path

    def test_logs_are_bounded_dated_and_tied_to_the_last_test(self):
        start = datetime.datetime(2026, 10, 29, 8, tzinfo=datetime.timezone.utc)
        record = {'sessions': [{'started': start.isoformat(), 'finished': (start + datetime.timedelta(hours=1)).isoformat()}]}
        self.log('OptiScaler.log', b'a' * 100 + b'TAIL', start + datetime.timedelta(minutes=30))
        self.log('sl.log', b'old', start - datetime.timedelta(days=1))
        logs = {item['name']: item for item in beta_report.collect(self.row, record, limit=4)}
        self.assertEqual(logs['OptiScaler.log']['data'], b'TAIL')
        self.assertTrue(logs['OptiScaler.log']['truncated'])
        self.assertEqual(logs['OptiScaler.log']['session'], 'From your last test')
        self.assertEqual(logs['sl.log']['session'], 'Older than your last test')
        self.assertEqual(logs['sl.dlss_g.log']['skipped'], 'Not found')
        self.assertEqual(beta_report.collect(self.row, {})[0]['session'], 'No test recorded; may include earlier runs')

    def test_only_known_names_beside_the_executable_are_read(self):
        self.log('rtxmfg-1.log', b'run');self.log('other.log', b'no');self.log('rtxmfg-1.status.json', b'{}')
        (self.game / 'OptiScaler.log').write_bytes(b'wrong folder')
        names = {item['name'] for item in beta_report.collect(self.row, {}) if 'data' in item}
        self.assertEqual(names, {'rtxmfg-1.log'})
        self.assertTrue(all('skipped' in item for item in beta_report.collect(dict(self.row, exe='../escape.exe'), {})))

    @unittest.skipUnless(hasattr(os, 'symlink') and os.name != 'nt', 'POSIX links')
    def test_links_and_fifos_are_refused(self):
        outside = self.root / 'secret.txt';outside.write_text('secret')
        os.symlink(outside, self.game / 'bin/OptiScaler.log')
        os.mkfifo(self.game / 'bin/sl.log')
        logs = {item['name']: item for item in beta_report.collect(self.row, {})}
        self.assertIn('skipped', logs['OptiScaler.log'])
        self.assertIn('skipped', logs['sl.log'])

    # ---------- preview and export ----------

    def test_export_writes_exactly_the_preview(self):
        report = self.ready()
        self.log('OptiScaler.log', b'token=abc123 path /home/me/game 76561198000000000')
        logs = {report['id']: beta_report.collect(self.row, {})}
        preview = beta_report.bundle([report], logs, {report['id']: 'note by me@example.com'})
        text = preview['files'][next(name for name in preview['files'] if name.endswith('logs/OptiScaler.log'))]
        self.assertNotIn('abc123', text);self.assertNotIn('/home/me', text);self.assertNotIn('76561198000000000', text)
        # The game's log changes after review; the export must not notice.
        self.log('OptiScaler.log', b'CHANGED')
        result = beta_report.export(preview, self.root / 'Reports')
        with zipfile.ZipFile(result['path']) as archive:
            self.assertEqual(set(archive.namelist()), set(preview['files']))
            for name, data in preview['files'].items():
                self.assertEqual(archive.read(name).decode(), data)
        manifest = json.loads(preview['files']['manifest.json'])
        self.assertEqual(len(manifest['files']), 1)
        self.assertIn({'report': report['id'], 'name': 'sl.log', 'reason': 'Not found'}, manifest['skipped'])
        self.assertEqual(result['included'], [manifest['files'][0]['path']])

    def test_a_changed_preview_is_refused(self):
        preview = beta_report.bundle([self.ready()])
        preview['files']['README.txt'] = 'edited'
        with self.assertRaises(t.Refusal):beta_report.export(preview, self.root / 'Reports')

    def test_incompressible_reports_over_the_limit_are_refused_and_cleaned_up(self):
        report = self.ready()
        noise = os.urandom(3 * 1024 ** 2).hex()
        logs = {report['id']: [{'name': 'OptiScaler.log', 'data': noise.encode(), 'size': len(noise), 'modified': 'x', 'truncated': False, 'session': 's'}]}
        preview = beta_report.bundle([report], logs)
        limit = beta_report.ZIP_LIMIT
        beta_report.ZIP_LIMIT = 1024 ** 2
        try:
            with self.assertRaises(t.Refusal) as caught:beta_report.export(preview, self.root / 'Reports')
        finally:
            beta_report.ZIP_LIMIT = limit
        self.assertIn('Choose fewer games', str(caught.exception))
        self.assertEqual(list((self.root / 'Reports').iterdir()), [])

    def test_too_much_before_compression_is_refused(self):
        report = self.ready()
        big = [{'name': 'OptiScaler.log', 'data': b'x' * (beta_report.TOTAL_LIMIT + 1), 'size': 1, 'modified': 'x', 'truncated': False, 'session': 's'}]
        with self.assertRaises(t.Refusal):beta_report.bundle([report], {report['id']: big})
        with self.assertRaises(t.Refusal):beta_report.bundle([])

    def test_reports_go_to_documents_when_it_exists(self):
        documents = self.root / 'Documents';documents.mkdir()
        self.assertEqual(beta_report.folder({}, documents), documents / 'rtxForge Reports')


class CompatibilityListTest(unittest.TestCase):
    def fields(self, **changes):
        fields = {'platform': 'Linux', 'distribution': 'Bazzite 42', 'gpu-series': 'RTX 40', 'gpu': 'RTX 4070 · driver 580',
                  'app-format': 'Flatpak', 'app-build': '1.0.0-beta.3', 'game': 'Example Game · 1.2', 'feature-package': 'Feeder NR 1.1',
                  'features': 'NR only', 'nr-result': 'Working in-game', 'mfg-result': 'Not installed', 'observations': 'Fine.'}
        fields.update(changes);return fields

    def test_reviewed_reports_join_the_list_without_hardware_specifics(self):
        data = {'schema': 1, 'games': []}
        entry = compat_list.add_report(data, self.fields(), 7, 'Working', appid='123', date='2026-10-29')
        self.assertEqual(data['schema'], 2)
        self.assertEqual(entry['name'], 'Example Game')
        self.assertEqual(entry['reports'], [{'issue': 7, 'date': '2026-10-29', 'os': 'Linux', 'distribution': 'Bazzite 42', 'gpu_series': 'RTX 40',
                                             'app': '1.0.0-beta.3', 'package': 'Feeder NR 1.1', 'features': 'NR only',
                                             'nr': 'Working in-game', 'mfg': 'Not installed'}])
        self.assertNotIn('4070', json.dumps(data))
        compat_list.add_report(data, self.fields(platform='Windows', **{'nr-result': 'Not working in-game'}), 8, 'Problem', appid='123')
        self.assertEqual(len(data['games']), 1)
        self.assertEqual(data['games'][0]['verdict'], 'Problem')
        self.assertEqual(compat_list.summary(data['games'][0]), ['Linux: NR working in 1 of 1', 'Windows: NR working in 0 of 1'])
        with self.assertRaises(t.Refusal):compat_list.add_report(data, self.fields(), 7, 'Working', appid='123')
        with self.assertRaises(t.Refusal):compat_list.add_report(data, self.fields(**{'nr-result': '', 'mfg-result': 'Not sure'}), 9, 'Working', appid='123')
        with self.assertRaises(t.Refusal):compat_list.add_report(data, self.fields(platform=''), 9, 'Working', appid='123')
        # Optional answers the reporter left blank are listed as Not sure.
        sparse = compat_list.add_report(data, self.fields(distribution='', **{'gpu-series': ''}), 9, 'Working', appid='123')
        self.assertEqual((sparse['reports'][-1]['distribution'], sparse['reports'][-1]['gpu_series']), ('Not sure', 'Not sure'))
        with self.assertRaises(t.Refusal):compat_list.add_report(data, self.fields(), 10, 'Maybe', appid='123')

    def test_listed_reports_are_found_by_game(self):
        listed = [{'appid': '123', 'verdict': 'Working', 'reports': [{'issue': 1, 'date': '2026-10-01'}, {'issue': 2, 'date': '2026-10-20'}]}]
        self.assertEqual([r['issue'] for r in compat_list.reports({'appid': '123'}, listed)], [2, 1])
        self.assertEqual(compat_list.reports({'appid': '9'}, listed), [])

    def test_shipped_list_is_schema_two(self):
        data = json.loads(compat_list.LIST.read_text(encoding='utf-8'))
        self.assertEqual(data['schema'], 2)
        for entry in data['games']:
            self.assertIn(entry['verdict'], compat_list.VERDICTS)
            self.assertTrue(entry.get('appid') or entry.get('exe'))
            self.assertTrue(entry.get('name'))
            for report in entry.get('reports', []):
                self.assertEqual(set(report), {'issue', 'date', *compat_list.REPORT_FIELDS.values()})


if __name__ == '__main__':
    unittest.main()
