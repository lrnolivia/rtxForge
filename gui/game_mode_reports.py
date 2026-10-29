"""Game Mode bug reports: Windows Game Mode's flow over the shared scripts/beta_report.py.

Choose games → answer the fields → review the redacted preview → save the ZIP →
open the prefilled GitHub form. The desktop window drafts, bundles and exports
(beta_report_drafts / beta_report_files / beta_report_export), so a report reads
the same from either interface. Choices cycle with A or Left/Right; text uses
Steam's on-screen keyboard. Nothing is uploaded.
"""
from pathlib import Path

from gi.repository import Gio, GLib, Gtk

import beta_report


class GameModeReports:
    def bug_report(self, games=None):
        """Pick one, a few or all games, and whether logs and notes go in the ZIP."""
        owner = self.owner
        games = list(games if games is not None else owner.games)
        if not games:
            return
        included = set(range(len(games)))
        options = {'logs': False, 'notes': False}
        rows = []
        go = self.button('Continue', lambda: (self.close_modal(), self.draft_reports([g for i, g in enumerate(games) if i in included], **options)),
                         'primary', key='report-continue')
        def toggle(index, row):
            included.symmetric_difference_update({index})
            row.get_child()._value.set_text('Included' if index in included else 'Excluded')
            go.set_sensitive(bool(included))
        for index, game in enumerate(games):
            row = self.row_button(game['name'], 'Included', None, key=f'report-game-{index}')
            row.connect('clicked', lambda button, index=index: toggle(index, button))
            rows.append(row)
        def flip(name, row):
            options[name] = not options[name]
            row.get_child()._value.set_text('On' if options[name] else 'Off')
        logs = self.row_button('Include logs', 'Off', None, description='Redacted, from each game’s latest test. You review them before saving.', key='report-logs')
        logs.connect('clicked', lambda button: flip('logs', button))
        notes = self.row_button('Include my notes', 'Off', None, key='report-notes')
        notes.connect('clicked', lambda button: flip('notes', button))
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(16))
        content.append(self.label('Choose one, a few or all games for a bug report. You review everything before it’s saved. Nothing is uploaded.', 'gm-p', wrap=True))
        content.append(self.group(rows))
        content.append(self.group([logs, notes]))
        self.show_modal('Bug Report', content, [self.button('Cancel', self.close_modal), go], self.close_modal, 1100, go)

    def draft_reports(self, games, logs=False, notes=False):
        owner = self.owner
        if not games:
            return
        if owner.busy and owner.task_kind != 'art':
            self.toast('Wait for the current task to finish, then prepare the report.')
            return
        self.report_working('Checking this computer and each game’s install record…')
        owner.start('Preparing bug reports', lambda: owner.beta_report_drafts(games),
                    lambda reports: self.edit_reports(games, reports, logs, notes))

    def report_working(self, text):
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(16))
        spinner = Gtk.Spinner(spinning=True, halign=Gtk.Align.START)
        content.append(spinner)
        content.append(self.label(text, 'gm-p', wrap=True))
        self._report_modal = self.show_modal('Bug Report', content, [], self.close_modal, 900)

    def close_report_working(self):
        modal = getattr(self, '_report_modal', None)
        self._report_modal = None
        if modal is not None and modal in self.modals:
            self.close_modal(modal)
            return True
        return False

    def edit_reports(self, games, reports, logs, notes):
        """Every field for every game; the preview opens once each report has its required answers."""
        if not self.close_report_working():
            return
        t = self.theme
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(16))
        content.append(self.label('rtxForge filled in what it could check. Change any answer, then say what you saw in game. '
                                  'Installed files don’t show whether NR or MFG worked.', 'gm-p', wrap=True))
        preview = self.button('Preview report', lambda: self.preview_reports(games, reports, logs, notes), 'primary', key='report-preview')
        def refresh():
            preview.set_sensitive(all(not beta_report.problems(report) for report in reports))
        for index, report in enumerate(reports):
            content.append(self.label(report['name'] or games[index]['name'], 'gm-strong', wrap=True))
            rows = []
            for key, name in beta_report.FIELDS:
                rows.append(self.report_field(index, report, key, name, refresh))
            content.append(self.group(rows))
        content.append(self.label("Controller text entry uses Steam's on-screen keyboard (Steam + X).", 'gm-p', wrap=True))
        refresh()
        self.show_modal('Bug Report', content, [self.button('Cancel', self.close_modal), preview], self.close_modal, 1200, preview)

    def report_field(self, index, report, key, name, changed):
        t = self.theme
        source = beta_report.SOURCES.get(report['sources'].get(key), '')
        value = report['fields'].get(key) or ''
        if key in beta_report.CHOICES:
            choices = list(beta_report.CHOICES[key])
            row = self.row_button(name, value or 'Choose', None, description=source or None, key=f'report-{index}-{key}')
            def step(delta):
                current = report['fields'].get(key) or ''
                picked = choices[((choices.index(current) if current in choices else -1) + delta) % len(choices)]
                beta_report.correct(report, key, picked)
                row.get_child()._value.set_text(picked)
                changed()
            row.connect('clicked', lambda *_: step(1))
            row._gm_adjust = step
            return row
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(8))
        for side in ('start', 'end', 'top', 'bottom'):
            getattr(box, 'set_margin_' + side)(t.px(20))
        required = key in beta_report.REQUIRED
        box.append(self.label(name + (' (required)' if required else ''), 'gm-strong'))
        if key == 'observations':
            box.append(self.label('What you did, what you expected, and what you saw. Include exact errors, or how you checked that a feature worked.', 'gm-p', wrap=True))
        elif source:
            box.append(self.label(source, 'gm-p', wrap=True))
        view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False, height_request=t.px(120 if key == 'observations' else 44))
        view.add_css_class('gm-notes')
        view.get_buffer().set_text(value)
        view.update_property([Gtk.AccessibleProperty.LABEL], [name])
        def typed(buffer):
            beta_report.correct(report, key, buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True))
            changed()
        view.get_buffer().connect('changed', typed)
        self.key(view, f'report-{index}-{key}')
        box.append(view)
        return box

    def preview_reports(self, games, reports, logs, notes):
        owner = self.owner
        if owner.busy:
            self.toast('Wait for the current task to finish, then preview again.')
            return
        self.close_modal()
        self.report_working('Reading logs and preparing a redacted preview…' if logs else 'Preparing a redacted preview…')
        owner.start('Preparing redacted preview', lambda: owner.beta_report_files(reports, games, logs, notes),
                    lambda preview: self.review_reports(reports, preview))

    def review_reports(self, reports, preview):
        """The exact redacted files: Save writes these bytes and reads nothing again."""
        if not self.close_report_working():
            return
        owner = self.owner
        if 'error' in preview:
            self.report_message('Could not prepare the report', preview['error'])
            return
        t = self.theme
        manifest = preview['manifest']
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(16))
        count = len(manifest['files'])
        content.append(self.label(f"{count} log{'s' if count != 1 else ''} included · {len(manifest['skipped'])} not included", 'gm-strong'))
        content.append(self.label('Review the exact text below. Redaction is best effort: check for anything personal before you share it. '
                                  'Logs show what ran, not what NR or MFG looked like.', 'gm-p', wrap=True))
        for name, text in preview['files'].items():
            entry = next((item for item in manifest['files'] if item['path'] == name), None)
            content.append(self.label(name, 'gm-strong', wrap=True))
            if entry:
                content.append(self.label(f"{entry['session']} · {entry['modified'][:16].replace('T', ' ')} UTC" + (' · newest part only' if entry['truncated'] else ''), 'gm-p'))
            view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR, cursor_visible=False)
            view.add_css_class('gm-notes')
            view.get_buffer().set_text(text)
            content.append(view)
        for item in manifest['skipped']:
            content.append(self.label(f"Not included: {item['name']} · {item['reason']}", 'gm-p', wrap=True))
        documents = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
        def save():
            if owner.busy:
                self.toast('Wait for the current task to finish, then save again.')
                return
            self.close_modal()
            self.report_working('Saving…')
            owner.start('Saving bug report', lambda: owner.beta_report_export(preview, documents), lambda result: self.saved_reports(reports, result))
        save_button = self.button('Save Report', save, 'primary', enabled=not owner.options.demo, key='report-save')
        self.show_modal('Review Bug Report', content, [self.button('Cancel', self.close_modal), save_button], self.close_modal, 1200, save_button)

    def saved_reports(self, reports, result):
        """Where the ZIP is, and a prefilled form per game to attach it to."""
        if not self.close_report_working():
            return
        owner = self.owner
        if 'error' in result:
            self.report_message('Could not save the report', result['error'])
            return
        path = Path(result['path'])
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(16))
        included = len(result['included'])
        content.append(self.label(f"{result['name']} · {result['size'] / 1024 ** 2:.1f} MB · {included} log{'s' if included != 1 else ''} included", 'gm-p', wrap=True))
        content.append(self.label('Open the prefilled form and attach the ZIP there before you submit. Attaching uploads it, and files on this repository are public.',
                                  'gm-p', wrap=True))
        rows = []
        for index, report in enumerate(reports):
            link = beta_report.issue_url(report)
            def opened(report=report, link=link):
                if not link['complete']:
                    owner.copy_text(beta_report.text(report), 'The report was too long for the link. The full text is copied: paste it into the form.')
                Gio.AppInfo.launch_default_for_uri(link['url'], None)
            rows.append(self.row_button('Open form · ' + (report['fields'].get('game') or report['name']), None, opened, key=f'report-form-{index}'))
        rows.append(self.row_button('Copy Path', str(path), lambda: owner.copy_text(str(path), 'Path copied'), key='report-copy-path'))
        rows.append(self.row_button('Open Folder', None, lambda: owner.open_report_folder(path), key='report-folder'))
        content.append(self.group(rows))
        done = self.button('Done', self.close_modal, 'primary', key='report-done')
        self.show_modal('Bug report saved', content, [done], self.close_modal, 1100, done)

    def report_message(self, title, text):
        done = self.button('Close', self.close_modal, 'primary')
        self.show_modal(title, self.label(text, 'gm-p', wrap=True), [done], self.close_modal, 900, done)
