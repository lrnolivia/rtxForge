#!/usr/bin/env python3
"""rtxForge — Libadwaita redesign shell (Phase 1 + Phase 2).

This is an ADDITIVE, separate entry point. It does not modify or replace
gui/rtxforge_gtk.py in any way — that file keeps working exactly as before.
This module reuses its backend imports and a couple of small shared helpers
so both UIs stay in sync with the same data, but owns its own window,
CSS and page layout.

Implements, per docs/rtxForge-Libadwaita-Redesign-Guide.md:
  Phase 1 — Application shell: AdwApplicationWindow, permanent sidebar,
            seamless flat headerbar, Home / Game Library / Forge / Settings /
            Recovery / Help & Support / About destinations.
  Phase 2 — Final Home dashboard: rotating library-art hero, four summary
            cards, Recent Games row, System Status, Quick Actions.

Later phases (Game Library rework, Forge preference rows, per-game pages,
Settings cleanup, Recovery/Support pages) are stubbed with AdwStatusPage
placeholders so the shell is fully navigable today; they're clearly marked
below (search for "PHASE STUB") and are the natural next slice of work.

Run:
    ./gui/rtxforge_gtk_redesign.py --demo
"""
from pathlib import Path
import sys, argparse, random, json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

# Reuse backend + small helpers from the existing GUI module rather than
# duplicating them. Importing this module does not run its UI (it's only
# invoked from rtxforge_gtk.main(), guarded by __main__).
import rtxforge_gtk as classic
from rtxforge_gtk import DesktopService, library_media, game_notes, demo_games, HeroPicture, CoverPicture

# ---------------------------------------------------------------------------
# Stock-Adwaita CSS. Only what Libadwaita doesn't already provide: no custom
# panel backgrounds, no slate-blue — see guide "Stock Adwaita Greys" section.
# Status colors stay semantic; the game hero supplies the rest of the color.
# ---------------------------------------------------------------------------
CSS = b'''
.rtx-sidebar-brand { padding: 18px 14px 10px; }
.rtx-sidebar-title { font-size: 15px; font-weight: 800; }
.rtx-sidebar-subtitle { font-size: 11px; opacity: 0.7; }
.rtx-hero { border-radius: 16px; }
.rtx-hero-scrim {
  background: linear-gradient(to right, alpha(black,0.72) 0%, alpha(black,0.55) 38%, alpha(black,0.05) 75%);
  border-radius: 16px;
}
.rtx-hero-eyebrow { color: #76b900; font-weight: 800; font-size: 11px; letter-spacing: 2px; }
.rtx-hero-title { font-size: 26px; font-weight: 800; color: white; }
.rtx-hero-body { color: alpha(white,0.85); font-size: 13px; }
.rtx-hero-primary { background: #76b900; color: #111508; font-weight: 700; }
.rtx-hero-primary:hover { background: #8fd914; }
.rtx-hero-secondary { background: alpha(white,0.14); color: white; font-weight: 700; }
.rtx-hero-secondary:hover { background: alpha(white,0.22); }
.rtx-hero-dot { min-width: 6px; min-height: 6px; border-radius: 99px; background: alpha(white,0.4); }
.rtx-hero-dot.active { background: white; }
.rtx-stat-icon { min-width: 40px; min-height: 40px; border-radius: 99px; background: alpha(@window_fg_color,0.08); }
.rtx-stat-number { font-size: 22px; font-weight: 800; }
.rtx-stat-caption { font-size: 12px; opacity: 0.75; }
.rtx-stat-warn .rtx-stat-icon { background: alpha(#e5a50a,0.18); }
.rtx-recent-card { border-radius: 12px; }
.rtx-recent-title { font-weight: 700; font-size: 12px; }
.rtx-status-dot { min-width: 8px; min-height: 8px; border-radius: 99px; margin-top: 2px; }
.rtx-status-dot.ok { background: #2ec27e; }
.rtx-status-dot.ready { background: alpha(@window_fg_color,0.35); }
.rtx-status-dot.warn { background: #e5a50a; }
.rtx-status-caption { font-size: 11px; opacity: 0.75; }
.rtx-section-heading { font-size: 15px; font-weight: 700; }
'''


def stat_card(icon_name, number, caption, warn=False, on_click=None):
    """One of the four Home summary cards. Simple: the number is the point."""
    box = Gtk.Box(spacing=12, margin_top=14, margin_bottom=14, margin_start=16, margin_end=16)
    box.add_css_class('card')
    if warn:
        box.add_css_class('rtx-stat-warn')
    icon_wrap = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    icon_wrap.add_css_class('rtx-stat-icon')
    icon = Gtk.Image.new_from_icon_name(icon_name)
    icon.set_pixel_size(18)
    if warn:
        icon.add_css_class('warning')
    icon_wrap.append(icon)
    box.append(icon_wrap)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, valign=Gtk.Align.CENTER)
    n = Gtk.Label(label=str(number), xalign=0)
    n.add_css_class('rtx-stat-number')
    c = Gtk.Label(label=caption, xalign=0)
    c.add_css_class('rtx-stat-caption')
    text.append(n)
    text.append(c)
    box.append(text)
    if on_click:
        button = Gtk.Button(child=box)
        button.add_css_class('flat')
        button.connect('clicked', on_click)
        return button
    return box


def recent_game_card(game, status):
    """Small artwork + title + status row for the Recent Games strip."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=140)
    pic = CoverPicture(content_fit=Gtk.ContentFit.COVER)
    pic.add_css_class('rtx-recent-card')
    pic.cover_width = 140
    art = (game.get('media') or {}).get('poster')
    if art and Path(art).is_file():
        try:
            pic.set_filename(art)
        except Exception:
            pass
    box.append(pic)
    title = Gtk.Label(label=game['name'], xalign=0, wrap=True, lines=2, ellipsize=3)
    title.add_css_class('rtx-recent-title')
    box.append(title)
    status_row = Gtk.Box(spacing=6)
    dot = Gtk.Box(width_request=8, height_request=8, valign=Gtk.Align.CENTER)
    dot.add_css_class('rtx-status-dot')
    dot.add_css_class({'using': 'ok', 'ready': 'ready', 'attention': 'warn'}[status])
    status_row.append(dot)
    caption = {'using': 'Using rtxForge', 'ready': 'Ready to Forge', 'attention': 'Needs Attention'}[status]
    label = Gtk.Label(label=caption, xalign=0)
    label.add_css_class('rtx-status-caption')
    status_row.append(label)
    box.append(status_row)
    return box


class HomePage(Gtk.Box):
    """Phase 2 — the approved Home dashboard: hero, stats, recent, status, actions."""

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.append(scroll)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        classic.margins(content, 24)
        scroll.set_child(content)

        # --- Hero -----------------------------------------------------
        self.hero_games = []
        self.hero_index = 0
        self.hero_overlay = Gtk.Overlay(height_request=280)
        self.hero_overlay.add_css_class('rtx-hero')
        self.hero_overlay.set_overflow(Gtk.Overflow.HIDDEN)
        self.hero_pic = HeroPicture(content_fit=Gtk.ContentFit.COVER)
        self.hero_overlay.set_child(self.hero_pic)
        scrim = Gtk.Box()
        scrim.add_css_class('rtx-hero-scrim')
        self.hero_overlay.add_overlay(scrim)

        hero_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                             halign=Gtk.Align.START, valign=Gtk.Align.CENTER,
                             margin_start=28, margin_end=180, width_request=380)
        eyebrow = Gtk.Label(label='RTXFORGE', xalign=0)
        eyebrow.add_css_class('rtx-hero-eyebrow')
        hero_text.append(eyebrow)
        title = Gtk.Label(label='Bring newer RTX features\nto your games.', xalign=0, wrap=True)
        title.add_css_class('rtx-hero-title')
        hero_text.append(title)
        body = Gtk.Label(label='rtxForge handles the setup, keeps your original files safe, '
                                'and lets you manage everything in one place.', xalign=0, wrap=True)
        body.add_css_class('rtx-hero-body')
        hero_text.append(body)
        actions = Gtk.Box(spacing=10, margin_top=4)
        review = Gtk.Button(label='Review Library')
        review.add_css_class('rtx-hero-primary')
        review.connect('clicked', lambda *_: win.go_to('library'))
        forge = Gtk.Button(label='Forge Available Games')
        forge.add_css_class('rtx-hero-secondary')
        forge.connect('clicked', lambda *_: win.go_to('forge'))
        actions.append(review)
        actions.append(forge)
        hero_text.append(actions)
        self.hero_overlay.add_overlay(hero_text)

        self.hero_dots = Gtk.Box(spacing=6, halign=Gtk.Align.END, valign=Gtk.Align.END,
                                  margin_end=18, margin_bottom=14)
        self.hero_overlay.add_overlay(self.hero_dots)
        content.append(self.hero_overlay)

        # --- Summary cards ---------------------------------------------
        self.stats_row = Gtk.Box(spacing=14, homogeneous=True)
        content.append(self.stats_row)

        # --- Recent Games -------------------------------------------------
        recent_head = Gtk.Box(spacing=8)
        recent_title = Gtk.Label(label='Recent Games', xalign=0, hexpand=True)
        recent_title.add_css_class('rtx-section-heading')
        recent_head.append(recent_title)
        view_all = Gtk.Button(label='View All')
        view_all.add_css_class('flat')
        view_all.connect('clicked', lambda *_: win.go_to('library'))
        recent_head.append(view_all)
        content.append(recent_head)
        recent_scroll = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.recent_box = Gtk.Box(spacing=14)
        recent_scroll.set_child(self.recent_box)
        content.append(recent_scroll)

        # --- System Status + Quick Actions ---------------------------------
        lower = Gtk.Box(spacing=14)
        content.append(lower)
        self.status_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                                    margin_top=16, margin_bottom=16, margin_start=18, margin_end=18,
                                    hexpand=True)
        self.status_card.add_css_class('card')
        lower.append(self.status_card)

        quick_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        quick_box.add_css_class('card')
        for icon, title_, subtitle, target in [
            ('folder-visiting-symbolic', 'Review Library', 'Check for supported games', 'library'),
            ('applications-utilities-symbolic', 'Forge Available', 'Set up RTX features', 'forge'),
            ('edit-undo-symbolic', 'Restore a Game', 'Revert to original files', 'recovery'),
        ]:
            r = Adw.ActionRow(title=title_, subtitle=subtitle, activatable=True)
            r.add_prefix(Gtk.Image.new_from_icon_name(icon))
            r.connect('activated', lambda *_a, t=target: win.go_to(t))
            quick_box.append(r)
        actions_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        actions_heading = Gtk.Label(label='Quick Actions', xalign=0)
        actions_heading.add_css_class('rtx-section-heading')
        actions_wrap.append(actions_heading)
        actions_wrap.append(quick_box)
        lower.append(actions_wrap)

        GLib.timeout_add_seconds(20, self._rotate_hero)

    def refresh(self, games):
        """Recompute everything on Home from the current game list."""
        using = ready = attention = 0
        recent = []
        for g in games:
            status = self._status_of(g)
            recent.append((g, status))
            if status == 'using':
                using += 1
            elif status == 'attention':
                attention += 1
            else:
                ready += 1

        classic.clear(self.stats_row)
        self.stats_row.append(stat_card('applications-games-symbolic', len(games), 'Games in Library'))
        self.stats_row.append(stat_card('emblem-ok-symbolic', ready, 'Ready to Forge'))
        self.stats_row.append(stat_card('applications-utilities-symbolic', using, 'Using rtxForge'))
        self.stats_row.append(stat_card('dialog-warning-symbolic', attention, 'Needs Attention',
                                         warn=True, on_click=lambda *_: self.win.go_to('library')))

        classic.clear(self.recent_box)
        for g, status in recent[:6]:
            self.recent_box.append(recent_game_card(g, status))

        classic.clear(self.status_card)
        if attention:
            head = f'{attention} game{"s" if attention != 1 else ""} need{"s" if attention == 1 else ""} attention.'
            sub = 'Review the game before applying Forge changes.'
            icon = 'dialog-warning-symbolic'
        else:
            head = 'Everything looks good.'
            sub = 'rtxForge is ready and your library is up to date.'
            icon = 'emblem-ok-symbolic'
        top = Gtk.Box(spacing=10)
        top.append(Gtk.Image.new_from_icon_name(icon))
        heading = Gtk.Label(label=head, xalign=0)
        heading.add_css_class('heading')
        top.append(heading)
        self.status_card.append(top)
        subtitle = Gtk.Label(label=sub, xalign=0, wrap=True)
        subtitle.add_css_class('dim-label')
        self.status_card.append(subtitle)

        # Hero pool: any game with cached hero artwork; shuffled, no immediate repeats.
        self.hero_games = [g for g in games if (g.get('media') or {}).get('hero') and Path(g['media']['hero']).is_file()]
        random.shuffle(self.hero_games)
        self.hero_index = 0
        self._paint_hero()

    @staticmethod
    def _status_of(game):
        note = game.get('_note_status')
        if note == 'Problem':
            return 'attention'
        return 'using' if game.get('installed') else 'ready'

    def _paint_hero(self):
        classic.clear(self.hero_dots)
        if not self.hero_games:
            self.hero_pic.set_paintable(None)
            return
        for i in range(len(self.hero_games)):
            dot = Gtk.Box(width_request=6, height_request=6)
            dot.add_css_class('rtx-hero-dot')
            if i == self.hero_index:
                dot.add_css_class('active')
            self.hero_dots.append(dot)
        game = self.hero_games[self.hero_index]
        try:
            self.hero_pic.set_paintable(Gdk.Texture.new_from_filename(game['media']['hero']))
        except Exception:
            self.hero_pic.set_paintable(None)

    def _rotate_hero(self):
        if len(self.hero_games) > 1:
            self.hero_index = (self.hero_index + 1) % len(self.hero_games)
            self._paint_hero()
        return True


def stub_page(title, description, icon='applications-utilities-symbolic'):
    """PHASE STUB — placeholder for a destination not yet migrated to the new shell.

    Each of these corresponds to a later phase in the redesign guide
    (Game Library rework = Phase 3, Forge = Phase 4, per-game pages = Phase 5,
    Settings cleanup = Phase 6, Recovery/Support = Phase 7). Home (Phase 1+2)
    is the only page fully built out in this pass.
    """
    status = Adw.StatusPage(title=title, description=description, icon_name=icon)
    status.set_vexpand(True)
    return status


class RedesignWindow(Adw.ApplicationWindow):
    NAV = [
        ('home', 'Home', 'go-home-symbolic'),
        ('library', 'Game Library', 'applications-games-symbolic'),
        ('forge', 'Forge', 'applications-utilities-symbolic'),
        ('settings', 'Settings', 'preferences-system-symbolic'),
        None,
        ('recovery', 'Recovery', 'edit-undo-symbolic'),
        ('help', 'Help & Support', 'help-faq-symbolic'),
        ('about', 'About', 'help-about-symbolic'),
    ]

    def __init__(self, application, options):
        super().__init__(application=application, title='rtxForge',
                          default_width=1280, default_height=860)
        self.options = options
        self.service = DesktopService(options.provider)
        self.games = []

        toolbar = Adw.ToolbarView()
        toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
        self.set_content(toolbar)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title='rtxForge'))
        toolbar.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar.set_content(body)

        # --- Sidebar ----------------------------------------------------
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=232)
        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        brand.add_css_class('rtx-sidebar-brand')
        brand_row = Gtk.Box(spacing=10)
        icon = Gtk.Image.new_from_icon_name('io.github.lrnolivia.RTXForge')
        icon.set_pixel_size(28)
        brand_row.append(icon)
        name = Gtk.Label(label='rtxForge', xalign=0)
        name.add_css_class('rtx-sidebar-title')
        brand_row.append(name)
        brand.append(brand_row)
        subtitle = Gtk.Label(label='Bring newer RTX features to your games.',
                              xalign=0, wrap=True)
        subtitle.add_css_class('rtx-sidebar-subtitle')
        brand.append(subtitle)
        sidebar.append(brand)

        self.nav_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.nav_list.add_css_class('navigation-sidebar')
        self.nav_keys = []
        for entry in self.NAV:
            if entry is None:
                self.nav_list.append(Gtk.Separator(margin_top=6, margin_bottom=6))
                continue
            key, title, icon_name = entry
            row = Adw.ActionRow(title=title)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))
            self.nav_list.append(row)
            self.nav_keys.append(key)
        self.nav_list.connect('row-selected', self._nav_changed)
        nav_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        nav_scroll.set_child(self.nav_list)
        sidebar.append(nav_scroll)
        body.append(sidebar)

        # --- Content stack ------------------------------------------------
        self.stack = Gtk.Stack(hexpand=True, vexpand=True,
                                transition_type=Gtk.StackTransitionType.CROSSFADE)
        body.append(self.stack)

        self.home = HomePage(self)
        self.stack.add_named(self.home, 'home')
        self.stack.add_named(stub_page(
            'Game Library', 'Browsing, search, filters and bulk actions move here next '
                             '(Phase 3 of the redesign) — the classic window already has all of this today.',
            'applications-games-symbolic'), 'library')
        self.stack.add_named(stub_page(
            'Forge', 'NR strength, sharpening and frame-multiplier defaults land here '
                     '(Phase 4) as native Adwaita preference rows.',
            'applications-utilities-symbolic'), 'forge')
        self.stack.add_named(stub_page(
            'Settings', 'Provider, appearance and install preferences move here '
                        '(Phase 6) as AdwPreferencesPage/-Group/-Row.',
            'preferences-system-symbolic'), 'settings')
        self.stack.add_named(stub_page(
            'Recovery', 'Undo previous installs/uninstalls and the old-NR-file cleanup '
                        'tool get a first-class page here (Phase 7).',
            'edit-undo-symbolic'), 'recovery')
        self.stack.add_named(stub_page(
            'Help & Support', 'Diagnostics, support-report export and logs (Phase 7).',
            'help-faq-symbolic'), 'help')
        self.stack.add_named(stub_page(
            'About', 'rtxForge — GeForce tools, built for Linux.',
            'help-about-symbolic'), 'about')

        self.nav_list.select_row(self.nav_list.get_row_at_index(0))

        if options.demo:
            self._load_demo()
        else:
            self._scan_real()

    def go_to(self, key):
        for i, entry in enumerate(self.NAV):
            if entry is not None and entry[0] == key:
                self.nav_list.select_row(self.nav_list.get_row_at_index(i))
                return

    def _nav_changed(self, _list, row):
        if row is None:
            return
        index = row.get_index()
        entry = self.NAV[index]
        if entry is None:
            return
        self.stack.set_visible_child_name(entry[0])

    def _load_demo(self):
        games = demo_games()
        for i, g in enumerate(games):
            path = ROOT / 'dist/demo-media' / ((g['appid'] or 'forza') + '.json')
            if path.exists():
                try:
                    g['media'] = json.loads(path.read_text())
                except Exception:
                    g['media'] = {}
            else:
                g['media'] = {}
            # Demo-only: give one game a synthetic "Problem" status so the
            # Needs Attention card/row has something to show without a real
            # test history.
            if i == len(games) - 1:
                g['_note_status'] = 'Problem'
        self.games = games
        self.home.refresh(self.games)

    def _scan_real(self):
        def work():
            return self.service.scan_all()

        def done(rows):
            settings = library_media.load_settings(self.service.config)
            media = library_media.LibraryMedia(self.service.config, settings)
            for g in rows:
                g['media'] = media.enrich(g) if settings.get('online_art') else {}
                g['_note_status'] = game_notes.load(self.service.config, g['game']).get('status', 'Untested')
            self.games = rows
            self.home.refresh(self.games)

        # Minimal synchronous fallback: the classic window's threaded task
        # runner (self.start/self.event) is the real pattern to reuse here;
        # kept simple in this first slice so Home has data to show.
        try:
            done(work())
        except Exception:
            self.games = []
            self.home.refresh(self.games)


class RedesignApplication(Adw.Application):
    def __init__(self, options):
        super().__init__(application_id='io.github.lrnolivia.RTXForge.Redesign',
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.options = options

    def do_activate(self):
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(ROOT / 'gui/icons'))
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                   Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        window = RedesignWindow(self, self.options)
        window.present()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', type=Path)
    parser.add_argument('--demo', action='store_true')
    options = parser.parse_args()
    app = RedesignApplication(options)
    return app.run([sys.argv[0]])


if __name__ == '__main__':
    sys.exit(main())
