"""Game Mode bug reports: the desktop's report, with controller-sized controls.

One game: "What happened?" first, NR and MFG in three words each, logs on, then
Send. What rtxForge detected is folded under "Details we'll include". Choices
change with A or Left/Right; text uses Steam's on-screen keyboard. The desktop
window drafts and bundles (beta_report_drafts / beta_report_files), and
beta_report.deliver keeps a copy on this computer before the loew.fi report
service files the GitHub issue. Logs stay private.
"""
from pathlib import Path

from gi.repository import Gio, GLib, Gtk

import beta_report

RESULTS = (('Working in-game', 'Worked'), ('Not working in-game', 'Didn’t work'), (None, 'Didn’t test'))


class GameModeReports:
    def bug_report(self, games=None):
        """A report is about one game; with several to choose from, ask which."""
        games = list(games if games is not None else self.owner.games)
        if not games:
            return
        if len(games) == 1:
            self.draft_report(games[0])
            return
        rows = [self.row_button(game['name'], None, lambda game=game: (self.close_modal(), self.draft_report(game)), key=f'report-game-{index}')
                for index, game in enumerate(games)]
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(16))
        content.append(self.label('Which game is it about?', 'gm-p'))
        content.append(self.group(rows))
        self.show_modal('Bug Report', content, [self.button('Cancel', self.close_modal, key='report-cancel')], self.close_modal, 1000)

    def draft_report(self, game):
        owner = self.owner
        if owner.busy and owner.task_kind != 'art':
            self.toast('Wait for the current task to finish, then prepare the report.')
            return
        self.report_working('Checking this computer and the game’s install record…')
        owner.start('Preparing the bug report', lambda: owner.beta_report_drafts([game]),
                    lambda reports: self.close_report_working() and self.edit_report(game, reports[0], {'logs': True}))

    def report_working(self, text):
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(16))
        content.append(Gtk.Spinner(spinning=True, halign=Gtk.Align.START))
        content.append(self.label(text, 'gm-p', wrap=True))
        self._report_modal = self.show_modal('Bug Report', content, [], self.close_modal, 900)

    def close_report_working(self):
        """True when the working screen was still open: the user didn't back out meanwhile."""
        modal = getattr(self, '_report_modal', None)
        self._report_modal = None
        if modal is not None and modal in self.modals:
            self.close_modal(modal)
            return True
        return False

    def edit_report(self, game, report, options):
        t = self.theme
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(16))
        content.append(self.label('Goes to rtxForge’s issues on GitHub. What you write and the details below are public; logs stay private.', 'gm-p', wrap=True))
        send = self.button('Send Report', lambda: self.send_report(game, report, options), 'primary', key='report-send')
        def ready():
            # Preview mode shows the whole flow but never sends.
            send.set_sensitive(not beta_report.problems(report) and not self.owner.options.demo)
        content.append(self.report_text(report, 'observations', 'What happened?', ready, height=140,
                                        hint='What you did, what you expected, and what you saw. Include exact errors.'))
        rows = []
        for key, name in (('nr-result', 'NR'), ('mfg-result', 'MFG')):
            rows.append(self.report_result(report, key, name))
        logs = self.row_button('Include logs', 'On' if options['logs'] else 'Off', None,
                               description='Sent privately to the rtxForge maintainers.', key='report-logs')
        def flip(row):
            options['logs'] = not options['logs']
            row.get_child()._value.set_text('On' if options['logs'] else 'Off')
        logs.connect('clicked', flip)
        rows.append(logs)
        content.append(self.group(rows))
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(12), visible=False)
        detail_rows = []
        for key, name in beta_report.FIELDS:
            if key in ('observations', 'nr-result', 'mfg-result'):
                continue
            if key in beta_report.CHOICES:
                detail_rows.append(self.report_choice(report, key, name, ready))
            else:
                details.append(self.report_text(report, key, name, ready))
        if detail_rows:
            details.prepend(self.group(detail_rows))
        summary = ' · '.join(v for v in (report['fields'].get(k) for k in ('platform', 'gpu', 'feature-package')) if v)
        fold = self.row_button('Details we’ll include', None, lambda: details.set_visible(not details.get_visible()),
                               description=summary or None, key='report-details')
        content.append(self.group([fold]))
        content.append(details)
        content.append(self.label("Controller text entry uses Steam's on-screen keyboard (Steam + X).", 'gm-p', wrap=True))
        outline = self.button('See what’s sent', lambda: self.report_outline(game, report, options), key='report-outline')
        ready()
        self.show_modal('Report a problem · ' + (report['name'] or game['name']), content,
                        [self.button('Cancel', self.close_modal), outline, send], self.close_modal, 1200)

    def report_result(self, report, key, name):
        """Worked / Didn't work / Didn't test. 'Didn't test' keeps what the install record said."""
        original = report['fields'].get(key) or ''
        def caption():
            current = report['fields'].get(key) or ''
            return next((text for value, text in RESULTS if value == current), 'Didn’t test')
        row = self.row_button(name, caption(), None, key=f'report-{key}')
        def step(delta):
            index = next((i for i, (value, _) in enumerate(RESULTS) if value == report['fields'].get(key)), 2)
            value = RESULTS[(index + delta) % len(RESULTS)][0]
            if value is None:
                value = original if original not in ('Working in-game', 'Not working in-game', '') else 'Installed, not tested'
            beta_report.correct(report, key, value)
            row.get_child()._value.set_text(caption())
        row.connect('clicked', lambda *_: step(1))
        row._gm_adjust = step
        return row

    def report_choice(self, report, key, name, changed):
        choices = list(beta_report.CHOICES[key])
        row = self.row_button(name, report['fields'].get(key) or 'Choose', None, key=f'report-{key}')
        def step(delta):
            current = report['fields'].get(key) or ''
            picked = choices[((choices.index(current) if current in choices else -1) + delta) % len(choices)]
            beta_report.correct(report, key, picked)
            row.get_child()._value.set_text(picked)
            changed()
        row.connect('clicked', lambda *_: step(1))
        row._gm_adjust = step
        return row

    def report_text(self, report, key, name, changed, height=44, hint=None):
        t = self.theme
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(8))
        box.append(self.label(name, 'gm-strong'))
        if hint:
            box.append(self.label(hint, 'gm-p', wrap=True))
        view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False, height_request=t.px(height))
        view.add_css_class('gm-notes')
        view.get_buffer().set_text(report['fields'].get(key) or '')
        view.update_property([Gtk.AccessibleProperty.LABEL], [name])
        def typed(buffer):
            beta_report.correct(report, key, buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True))
            changed()
        view.get_buffer().connect('changed', typed)
        self.key(view, f'report-{key}')
        box.append(view)
        return box

    def report_outline(self, game, report, options):
        """'See what's sent', from the same redacted files Send uses. Back returns to the form."""
        owner = self.owner
        if owner.busy:
            self.toast('Wait for the current task to finish, then try again.')
            return
        include = options['logs']
        def work():
            preview = owner.beta_report_files([report], [game], include, False)
            return preview if 'error' in preview else beta_report.outline(report, preview)
        self.report_working('Reading logs and preparing what’s sent…' if include else 'Preparing what’s sent…')
        owner.start('Preparing what’s sent', work, lambda outline: self.close_report_working() and self.show_report_outline(outline, include))

    def show_report_outline(self, outline, include):
        if 'error' in outline:
            self.report_message('Could not prepare the report', outline['error'])
            return
        t = self.theme
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(14))
        content.append(self.label('Public on GitHub', 'gm-strong'))
        content.append(self.label(outline['title'], 'gm-p', wrap=True))
        content.append(self.report_view(outline['text']))
        content.append(self.label('Private: only the rtxForge maintainers' if include else 'Logs: not included', 'gm-strong'))
        for log in outline['logs']:
            content.append(self.label(f"{log['name']} · {log['detail']}", 'gm-p', wrap=True))
            content.append(self.report_view(log['text'] if len(log['text']) <= 8000 else '…' + log['text'][-8000:]))
        for item in outline['skipped']:
            content.append(self.label(f"Not included: {item['name']} · {item['reason']}", 'gm-p', wrap=True))
        back = self.button('Back', self.close_modal, 'primary', key='report-back')
        self.show_modal('What’s sent', content, [back], self.close_modal, 1200, back)

    def report_view(self, text):
        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR, cursor_visible=False)
        view.add_css_class('gm-notes')
        view.get_buffer().set_text(text)
        return view

    def send_report(self, game, report, options):
        owner = self.owner
        if owner.busy:
            self.toast('Wait for the current task to finish, then send again.')
            return
        if beta_report.problems(report) or owner.options.demo:
            return
        include = options['logs']
        documents = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
        def work():
            preview = owner.beta_report_files([report], [game], include, False)
            if 'error' in preview:
                return {'sent': False, 'error': preview['error'], 'path': ''}
            try:
                return beta_report.deliver(report, preview, beta_report.folder(owner.service.config, documents), include)
            except Exception as error:
                return {'sent': False, 'error': str(error), 'path': ''}
        self.report_working('Reading and redacting logs, then sending…' if include else 'Sending…')
        owner.start('Sending the bug report', work, lambda result: self.close_report_working() and self.report_sent(result))

    def report_sent(self, result):
        """The issue number, or why it couldn't go. Try again returns to the form, answers kept."""
        owner = self.owner
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(16))
        if result.get('sent'):
            self.close_modal()
            content.append(self.label(f"Thanks! It’s issue #{result['number']} on GitHub.", 'gm-strong', wrap=True))
            content.append(self.label(f"A copy is saved in {Path(result['path']).parent}.", 'gm-p', wrap=True))
            done = self.button('Done', self.close_modal, 'primary', key='report-done')
            view = self.button('View on GitHub', lambda: Gio.AppInfo.launch_default_for_uri(result['url'], None), key='report-view')
            self.show_modal('Report sent', content, [view, done], self.close_modal, 1000, done)
            return
        content.append(self.label(result.get('error') or 'The report service didn’t answer.', 'gm-strong', wrap=True))
        actions = []
        if result.get('path'):
            content.append(self.label('Saved on this computer: ' + result['path'], 'gm-p', wrap=True))
            actions.append(self.button('Open Folder', lambda: owner.open_report_folder(Path(result['path'])), key='report-folder'))
        retry = self.button('Try again', self.close_modal, 'primary', key='report-retry')
        self.show_modal('Couldn’t send the report', content, [*actions, retry], self.close_modal, 1000, retry)

    def report_message(self, title, text):
        done = self.button('Close', self.close_modal, 'primary')
        self.show_modal(title, self.label(text, 'gm-p', wrap=True), [done], self.close_modal, 900, done)
