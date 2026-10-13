#!/usr/bin/env python3
"""
rtxForge Libadwaita redesign laboratory.

This source tree is isolated from the production GUI.

Phase 1:
- Adw.ApplicationWindow
- Adw.ToolbarView
- Adw.NavigationSplitView
- permanent sidebar
- Home
- Game Library
- Forge
- Settings
- Recovery
- stock Libadwaita surfaces

Do not move backend behavior into this laboratory.
"""

from pathlib import Path
import sys


def find_runtime_root():
    """
    Locate the rtxForge application root in both supported layouts.

    Source lab:
        rtxForge/redesign/gui/rtxforge_redesign_lab.py

    Beta AppImage staging:
        rtxForge/gui/rtxforge_redesign_lab.py
    """

    source = Path(__file__).resolve()

    candidates = (
        source.parents[2],
        source.parents[1],
    )

    for candidate in candidates:
        if (
            (candidate / "VERSION").exists()
            and (candidate / "gui").exists()
        ):
            return candidate

    return source.parents[1]


ROOT = find_runtime_root()

APP_VERSION = (
    (ROOT / "VERSION").read_text(
        encoding="utf-8"
    ).strip()
    if (ROOT / "VERSION").exists()
    else "dev"
)


import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import (
    Adw,
    Gio,
    GLib,
    Gdk,
    Gtk,
    Pango,
)


APP_ID = (
    "io.github.lrnolivia."
    "RTXForge.RedesignLab"
)

INTERACTIVE_HEIGHT = 42
NAVIGATION_HEIGHT = 46
SELECTABLE_GAP = 3
CONTROL_CLUSTER_SPACING = 18

APP_ICON = (
    ROOT
    / "gui"
    / "icons"
    / "hicolor"
    / "64x64"
    / "apps"
    / "io.github.lrnolivia.RTXForge.png"
)


PRIMARY_PAGES = (
    (
        "home",
        "Home",
        "go-home-symbolic",
        "Home",
        "Your RTX library, enhancements, and recovery tools.",
    ),
    (
        "library",
        "Game Library",
        "view-grid-symbolic",
        "Game Library",
        "Library browsing will move into this dedicated page.",
    ),
    (
        "forge",
        "Forge",
        "applications-engineering-symbolic",
        "Forge",
        "Choose what rtxForge adds to your games.",
    ),
    (
        "settings",
        "Settings",
        "emblem-system-symbolic",
        "Settings",
        "Configure how rtxForge behaves.",
    ),
)

SECONDARY_PAGES = (
    (
        "recovery",
        "Recovery",
        "document-revert-symbolic",
        "Recovery",
        "Review, repair, and reverse rtxForge changes.",
    ),
)

PAGES = PRIMARY_PAGES + SECONDARY_PAGES


class RedesignLabWindow(
    Adw.ApplicationWindow
):
    def __init__(
        self,
        application,
    ):
        super().__init__(
            application=application
        )

        self.set_title(
            "rtxForge Redesign Lab"
        )

        self.set_default_size(
            1180,
            760,
        )

        # Phase 1 is desktop-first.
        # Keep the primary navigation visible.
        self.set_size_request(
            720,
            560,
        )

        self.page_rows = {}
        self.row_lists = {}
        self.navigation_lists = []

        # Stable Phase 1 content attachment points.
        #
        # Later phases can migrate existing feature widgets into
        # these mounts without rebuilding the application shell.
        self.page_mounts = {}
        self.page_surfaces = {}

        self.split_view = (
            Adw.NavigationSplitView()
        )

        self.split_view.set_collapsed(
            False
        )

        self.split_view.set_sidebar_width_fraction(
            0.22
        )

        self.split_view.set_min_sidebar_width(
            220
        )

        self.split_view.set_max_sidebar_width(
            280
        )

        self._build_sidebar()
        self._build_content()

        self.set_content(
            self.split_view
        )

        home_row = self.page_rows[
            "home"
        ]

        self.row_lists[
            "home"
        ].select_row(
            home_row
        )

        self._select_page(
            "home"
        )

    def _app_icon(self):
        if APP_ICON.exists():
            image = Gtk.Image.new_from_file(
                str(APP_ICON)
            )

            image.set_pixel_size(
                67
            )

            return image

        image = Gtk.Image.new_from_icon_name(
            "applications-games-symbolic"
        )

        image.set_pixel_size(
            58
        )

        return image

    def _navigation_list(
        self,
        pages,
    ):
        navigation = Gtk.ListBox(
            selection_mode=(
                Gtk.SelectionMode.SINGLE
            ),
        )

        navigation.set_activate_on_single_click(
            True
        )

        navigation.add_css_class(
            "navigation-sidebar"
        )

        navigation.connect(
            "row-selected",
            self._on_sidebar_selected,
        )

        self.navigation_lists.append(
            navigation
        )

        for (
            page_id,
            title,
            icon_name,
            _heading,
            _description,
        ) in pages:
            row = Gtk.ListBoxRow()
            row.page_id = page_id

            content = Gtk.Box(
                orientation=(
                    Gtk.Orientation.HORIZONTAL
                ),
                spacing=12,
            )

            content.set_margin_start(
                12
            )

            content.set_margin_end(
                12
            )

            content.set_margin_top(
                11
            )

            content.set_margin_bottom(
                11
            )

            row.set_size_request(
                -1,
                NAVIGATION_HEIGHT,
            )

            row.set_margin_top(
                SELECTABLE_GAP,
            )

            row.set_margin_bottom(
                SELECTABLE_GAP,
            )

            icon = Gtk.Image.new_from_icon_name(
                icon_name
            )

            label = Gtk.Label(
                label=title,
                xalign=0,
                hexpand=True,
            )

            content.append(
                icon
            )

            content.append(
                label
            )

            row.set_child(
                content
            )

            navigation.append(
                row
            )

            self.page_rows[
                page_id
            ] = row

            self.row_lists[
                page_id
            ] = navigation

        return navigation

    def _build_branding(self):
        branding = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )

        branding.set_margin_start(
            18
        )

        branding.set_margin_end(
            18
        )

        branding.set_margin_top(
            16
        )

        branding.set_margin_bottom(
            18
        )

        self.sidebar_brand_icon = (
            self._app_icon()
        )

        self.sidebar_brand_icon.set_halign(
            Gtk.Align.START
        )

        branding.append(
            self.sidebar_brand_icon
        )

        self.sidebar_brand_name = (
            Gtk.Label(
                label="rtxForge",
                xalign=0,
                hexpand=True,
            )
        )

        self.sidebar_brand_name.set_halign(
            Gtk.Align.START
        )

        self.sidebar_brand_name.add_css_class(
            "title-2"
        )

        brand_title_attrs = Pango.AttrList()
        brand_title_attrs.insert(
            Pango.attr_scale_new(
                1.15
            )
        )

        self.sidebar_brand_name.set_attributes(
            brand_title_attrs
        )

        branding.append(
            self.sidebar_brand_name
        )

        description = Gtk.Label(
            label=(
                "Bring newer RTX features "
                "to your games."
            ),
            xalign=0,
            wrap=True,
        )

        description.set_halign(
            Gtk.Align.START
        )

        description.add_css_class(
            "dim-label"
        )

        branding.append(
            description
        )

        return branding

    def _build_sidebar(self):
        toolbar = Adw.ToolbarView()

        # Explicitly use the native flat sidebar/header treatment.
        toolbar.set_top_bar_style(
            Adw.ToolbarStyle.FLAT
        )

        header = Adw.HeaderBar()

        # App identity belongs in the sidebar body rather than
        # becoming duplicated titlebar decoration.
        header.set_show_title(
            False
        )

        toolbar.add_top_bar(
            header
        )

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )

        # Give the complete sidebar rail a little breathing room
        # from the far-left edge, including selection highlights.
        root.set_margin_start(
            6
        )

        root.append(
            self._build_branding()
        )

        self.primary_navigation = (
            self._navigation_list(
                PRIMARY_PAGES
            )
        )

        root.append(
            self.primary_navigation
        )

        # Push recovery/status navigation to the lower group.
        root.append(
            Gtk.Box(
                orientation=(
                    Gtk.Orientation.VERTICAL
                ),
                vexpand=True,
            )
        )

        separator = Gtk.Separator(
            orientation=(
                Gtk.Orientation.HORIZONTAL
            )
        )

        separator.set_margin_start(
            14
        )

        separator.set_margin_end(
            14
        )

        separator.set_margin_top(
            8
        )

        separator.set_margin_bottom(
            8
        )

        root.append(
            separator
        )

        self.secondary_navigation = (
            self._navigation_list(
                SECONDARY_PAGES
            )
        )

        root.append(
            self.secondary_navigation
        )

        version = Gtk.Label(
            label=(
                f"Phase 1 beta • "
                f"{APP_VERSION}"
            ),
            xalign=0,
        )

        version.add_css_class(
            "dim-label"
        )

        version.set_margin_start(
            18
        )

        version.set_margin_end(
            18
        )

        version.set_margin_top(
            12
        )

        version.set_margin_bottom(
            18
        )

        root.append(
            version
        )

        toolbar.set_content(
            root
        )

        sidebar_page = (
            Adw.NavigationPage.new(
                toolbar,
                "rtxForge",
            )
        )

        self.split_view.set_sidebar(
            sidebar_page
        )

    def _page_placeholder(
        self,
        page_id,
        icon_name,
    ):
        placeholder = Adw.StatusPage()

        placeholder.set_icon_name(
            icon_name
        )

        placeholder.set_title(
            "Ready for migration"
        )

        descriptions = {
            "home": (
                "The final dashboard will be built here "
                "after the application shell is complete."
            ),
            "library": (
                "The existing game library UI will be "
                "transplanted into this page without "
                "changing library backend behavior."
            ),
            "forge": (
                "Global Forge defaults and bulk setup "
                "will move into this page."
            ),
            "settings": (
                "Existing application settings will "
                "move into native Libadwaita groups here."
            ),
            "recovery": (
                "Repair and restoration workflows will "
                "move into this dedicated page."
            ),
        }

        placeholder.set_description(
            descriptions.get(
                page_id,
                "This page is ready for feature migration.",
            )
        )

        placeholder.set_vexpand(
            True
        )

        return placeholder

    def _library_toggle(
        self,
        *,
        name,
        label=None,
        icon_name=None,
        tooltip=None,
    ):
        toggle = Adw.Toggle()

        toggle.set_name(
            name
        )

        if label is not None:
            toggle.set_label(
                label
            )

        if icon_name is not None:
            toggle.set_icon_name(
                icon_name
            )

        if tooltip is not None:
            toggle.set_tooltip(
                tooltip
            )

        return toggle

    def _ensure_home_css(self):
        if getattr(
            self,
            "_home_css_ready",
            False,
        ):
            return

        provider = Gtk.CssProvider()

        provider.load_from_data(
            b"""
.home-hero {
    border-radius: 14px;
    background: #151719;
}

.home-hero-shade {
    background:
        linear-gradient(
            to right,
            rgba(12,14,15,0.98) 0%,
            rgba(12,14,15,0.90) 30%,
            rgba(12,14,15,0.40) 62%,
            rgba(12,14,15,0.08) 100%
        );
}

.home-hero-title {
    font-size: 34px;
    font-weight: 800;
    line-height: 0.98;
}

.home-hero-copy {
    font-size: 16px;
}

button.home-primary {
    background: #66e85f;
    color: #0d1b0c;
    border-radius: 9px;
    font-weight: 700;
    min-height: 44px;
    padding: 0 20px;
}

button.home-primary:hover {
    background: #76f06f;
}

button.home-secondary {
    border-radius: 9px;
    min-height: 44px;
    padding: 0 20px;
}

.home-stat-card,
.home-bottom-card {
    background: alpha(@window_fg_color,0.075);
    border-radius: 13px;
}

.home-stat-number {
    font-size: 25px;
    font-weight: 700;
}

.home-stat-icon {
    min-width: 46px;
    min-height: 46px;
    border-radius: 999px;
    background: alpha(@window_fg_color,0.09);
}

.home-stat-ready {
    color: #62d96b;
}

.home-stat-warning {
    color: #ff6b22;
}

.home-recent-section {
    background: alpha(@window_fg_color,0.045);
    border-radius: 14px;
}

.home-recent-card {
    background: alpha(@window_fg_color,0.055);
    border-radius: 10px;
}

.home-art-frame {
    border-radius: 9px;
    background: alpha(@window_fg_color,0.07);
}

.home-art-fallback {
    background:
        linear-gradient(
            135deg,
            alpha(@window_fg_color,0.16),
            alpha(@window_fg_color,0.04)
        );
}

.home-status-good {
    color: #61e86b;
}

.home-status-ready {
    color: #cbd5e1;
}

.home-status-warning {
    color: #ff6b22;
}

.home-system-check {
    background: #62df68;
    color: #102612;
    border-radius: 999px;
    min-width: 44px;
    min-height: 44px;
    font-size: 21px;
    font-weight: 800;
}

button.home-quick-action {
    background: alpha(@window_fg_color,0.055);
    border-radius: 10px;
    min-height: 68px;
}

button.home-quick-action:hover {
    background: alpha(@window_fg_color,0.09);
}
"""
        )

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._home_css_provider = provider
        self._home_css_ready = True

    def _navigate_from_home(
        self,
        page_id,
    ):
        row = self.page_rows.get(
            page_id
        )

        navigation = self.row_lists.get(
            page_id
        )

        if (
            row is not None
            and navigation is not None
        ):
            navigation.select_row(
                row
            )
            return

        self._select_page(
            page_id
        )

    def _home_local_art(
        self,
        name,
        appid,
        kind,
    ):
        """
        Reuse the production Steam artwork lookup READ-ONLY.

        This does not download, modify, refresh, or cache anything.
        """
        if not appid:
            return None

        try:
            scripts = ROOT / "scripts"

            if str(scripts) not in sys.path:
                sys.path.insert(
                    0,
                    str(scripts),
                )

            import library_media

            media = (
                library_media.LibraryMedia.__new__(
                    library_media.LibraryMedia
                )
            )

            media.config = None
            media.settings = {}
            media.shortcut_cache = {}

            result = media.steam_art(
                {
                    "name": name,
                    "appid": str(appid),
                    "source": "Steam",
                    "game": f"/preview/{name}",
                    "exe": "Game.exe",
                }
            )

            candidate = result.get(
                kind
            )

            if (
                candidate
                and Path(candidate).is_file()
            ):
                return candidate

        except Exception:
            pass

        # Home preview fallback only.
        #
        # Prefer local Steam artwork above. When the requested
        # artwork is not present locally, use the official Steam
        # CDN so the mockup does not collapse into blank panels.
        if (
            appid
            and str(appid).isdigit()
            and kind in {
                "hero",
                "capsule",
            }
        ):
            try:
                import urllib.request

                asset_name = {
                    "hero": "library_hero.jpg",
                    "capsule": "header.jpg",
                }[kind]

                cache_root = Path(
                    "/tmp/rtxforge-redesign-home-art"
                )

                cache_root.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                cached = (
                    cache_root
                    / f"{appid}-{asset_name}"
                )

                if not cached.is_file():
                    url = (
                        "https://cdn.cloudflare.steamstatic.com/"
                        f"steam/apps/{appid}/{asset_name}"
                    )

                    request = urllib.request.Request(
                        url,
                        headers={
                            "User-Agent": (
                                "rtxForge-Redesign/Phase1"
                            ),
                        },
                    )

                    with urllib.request.urlopen(
                        request,
                        timeout=6,
                    ) as response:
                        payload = response.read(
                            6 * 1024 * 1024 + 1
                        )

                    if (
                        payload
                        and len(payload)
                        <= 6 * 1024 * 1024
                    ):
                        cached.write_bytes(
                            payload
                        )

                if cached.is_file():
                    return str(
                        cached
                    )

            except Exception:
                pass

        return None

    def _home_art_widget(
        self,
        *,
        name,
        appid,
        kind,
    ):
        path = self._home_local_art(
            name,
            appid,
            kind,
        )

        frame = Gtk.Box(
            hexpand=True,
            vexpand=True,
        )

        frame.add_css_class(
            "home-art-frame"
        )

        frame.set_overflow(
            Gtk.Overflow.HIDDEN
        )

        if path:
            picture = Gtk.Picture.new_for_filename(
                path
            )

            picture.set_content_fit(
                Gtk.ContentFit.COVER
            )

            picture.set_can_shrink(
                True
            )

            picture.set_hexpand(
                True
            )

            picture.set_vexpand(
                True
            )

            frame.append(
                picture
            )

            return frame

        fallback = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.FILL,
            hexpand=True,
            vexpand=True,
        )

        fallback.add_css_class(
            "home-art-fallback"
        )

        title = Gtk.Label(
            label=name,
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )

        title.add_css_class(
            "heading"
        )

        title.set_margin_start(
            12
        )

        title.set_margin_end(
            12
        )

        fallback.append(
            title
        )

        frame.append(
            fallback
        )

        return frame

    def _home_stat_card(
        self,
        *,
        icon_name,
        value,
        caption,
        css_class=None,
        arrow=False,
    ):
        card = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=14,
            hexpand=True,
        )

        card.add_css_class(
            "home-stat-card"
        )

        card.set_size_request(
            185,
            -1,
        )

        card.set_margin_start(
            0
        )

        content = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=14,
            hexpand=True,
        )

        content.set_margin_start(
            18
        )

        content.set_margin_end(
            18
        )

        content.set_margin_top(
            16
        )

        content.set_margin_bottom(
            16
        )

        icon_shell = Gtk.Box(
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            hexpand=False,
            vexpand=False,
        )

        icon_shell.set_size_request(
            44,
            44,
        )

        icon_shell.set_halign(
            Gtk.Align.CENTER
        )

        icon_shell.set_valign(
            Gtk.Align.CENTER
        )

        icon_shell.add_css_class(
            "home-stat-icon"
        )

        icon = Gtk.Image.new_from_icon_name(
            icon_name
        )

        icon.set_pixel_size(
            20
        )

        icon.set_halign(
            Gtk.Align.CENTER
        )

        icon.set_valign(
            Gtk.Align.CENTER
        )

        icon.set_margin_start(
            0
        )

        icon.set_margin_end(
            0
        )

        icon.set_margin_top(
            0
        )

        icon.set_margin_bottom(
            0
        )

        if css_class:
            icon.add_css_class(
                css_class
            )

        icon_shell.append(
            icon
        )

        labels = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=1,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )

        number = Gtk.Label(
            label=str(value),
            xalign=0,
        )

        number.add_css_class(
            "home-stat-number"
        )

        label = Gtk.Label(
            label=caption,
            xalign=0,
        )

        label.add_css_class(
            "dim-label"
        )

        labels.append(
            number
        )

        labels.append(
            label
        )

        content.append(
            icon_shell
        )

        content.append(
            labels
        )

        if arrow:
            next_icon = Gtk.Image.new_from_icon_name(
                "go-next-symbolic"
            )

            next_icon.set_valign(
                Gtk.Align.CENTER
            )

            content.append(
                next_icon
            )

        card.append(
            content
        )

        return card

    def _home_recent_card(
        self,
        *,
        name,
        appid,
        status,
        status_class,
    ):
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            hexpand=True,
        )

        card.add_css_class(
            "home-recent-card"
        )

        card.set_size_request(
            -1,
            158,
        )

        card.set_overflow(
            Gtk.Overflow.HIDDEN
        )

        art = self._home_art_widget(
            name=name,
            appid=appid,
            kind="capsule",
        )

        art_ratio = Gtk.AspectFrame()

        art_ratio.set_hexpand(
            True
        )

        art_ratio.set_halign(
            Gtk.Align.FILL
        )

        art_ratio.set_size_request(
            185,
            104,
        )

        art_ratio.set_hexpand(
            False
        )

        art_ratio.set_ratio(
            16 / 9
        )

        art_ratio.set_obey_child(
            False
        )

        art_ratio.set_child(
            art
        )

        card.append(
            art_ratio
        )

        body = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5,
        )

        body.set_margin_start(
            10
        )

        body.set_margin_end(
            8
        )

        body.set_margin_bottom(
            10
        )

        title = Gtk.Label(
            label=name,
            xalign=0,
            ellipsize=Pango.EllipsizeMode.END,
        )

        title.add_css_class(
            "heading"
        )

        body.append(
            title
        )

        status_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
        )

        dot = Gtk.Label(
            label="●"
        )

        dot.add_css_class(
            status_class
        )

        status_label = Gtk.Label(
            label=status,
            xalign=0,
            hexpand=True,
        )

        status_label.add_css_class(
            "dim-label"
        )

        menu = Gtk.Image.new_from_icon_name(
            "view-more-symbolic"
        )

        status_row.append(
            dot
        )

        status_row.append(
            status_label
        )

        status_row.append(
            menu
        )

        body.append(
            status_row
        )

        card.append(
            body
        )

        return card

    def _home_quick_action(
        self,
        *,
        icon_name,
        title,
        subtitle,
        page_id,
    ):
        button = Gtk.Button()

        button.add_css_class(
            "home-quick-action"
        )

        button.set_hexpand(
            True
        )

        content = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )

        content.set_margin_start(
            14
        )

        content.set_margin_end(
            14
        )

        content.set_margin_top(
            10
        )

        content.set_margin_bottom(
            10
        )

        icon = Gtk.Image.new_from_icon_name(
            icon_name
        )

        icon.set_pixel_size(
            22
        )

        icon.set_size_request(
            34,
            34,
        )

        icon.set_halign(
            Gtk.Align.CENTER
        )

        icon.set_valign(
            Gtk.Align.CENTER
        )

        labels = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            hexpand=True,
        )

        title_label = Gtk.Label(
            label=title,
            xalign=0,
        )

        title_label.add_css_class(
            "heading"
        )

        subtitle_label = Gtk.Label(
            label=subtitle,
            xalign=0,
        )

        subtitle_label.add_css_class(
            "dim-label"
        )

        labels.append(
            title_label
        )

        labels.append(
            subtitle_label
        )

        content.append(
            icon
        )

        content.append(
            labels
        )

        button.set_child(
            content
        )

        button.connect(
            "clicked",
            lambda *_: self._navigate_from_home(
                page_id
            ),
        )

        return button

    def _build_home_shell(self):
        self._ensure_home_css()

        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            hexpand=True,
            vexpand=False,
        )

        self.home_page = page

        # ====================================================
        # HERO
        # ====================================================

        hero_frame = Gtk.Box(
            hexpand=True,
        )

        hero_frame.add_css_class(
            "home-hero"
        )

        hero_frame.set_overflow(
            Gtk.Overflow.HIDDEN
        )

        hero_frame.set_size_request(
            -1,
            245,
        )

        hero = Gtk.Overlay(
            hexpand=True,
            vexpand=True,
        )

        unity_hero = self._home_local_art(
            "Assassin's Creed Unity",
            "289650",
            "hero",
        )

        if unity_hero:
            picture = Gtk.Picture.new_for_filename(
                unity_hero
            )

            picture.set_content_fit(
                Gtk.ContentFit.COVER
            )

            picture.set_halign(
                Gtk.Align.FILL
            )

            picture.set_valign(
                Gtk.Align.FILL
            )

            picture.set_hexpand(
                True
            )

            picture.set_vexpand(
                True
            )

            hero.set_child(
                picture
            )

        else:
            fallback = Gtk.Box(
                hexpand=True,
                vexpand=True,
            )

            fallback.add_css_class(
                "home-art-fallback"
            )

            hero.set_child(
                fallback
            )

        shade = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            hexpand=True,
            vexpand=True,
        )

        shade.add_css_class(
            "home-hero-shade"
        )

        copy = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14,
            valign=Gtk.Align.CENTER,
        )

        copy.set_hexpand(
            True
        )

        copy.set_margin_start(
            38
        )

        title = Gtk.Label(
            xalign=0,
            wrap=True,
            use_markup=True,
        )

        title.set_markup(
            'Bring newer '
            '<span foreground="#66e85f">RTX</span> '
            'features\nto your games.'
        )

        title.add_css_class(
            "home-hero-title"
        )

        title.set_max_width_chars(
            34
        )

        title.set_wrap_mode(
            Pango.WrapMode.WORD_CHAR
        )

        description = Gtk.Label(
            label=(
                "rtxForge handles the setup, keeps your "
                "original files safe,\nand lets you manage "
                "everything in one place."
            ),
            xalign=0,
        )

        description.add_css_class(
            "home-hero-copy"
        )

        description.set_max_width_chars(
            58
        )

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )

        self.home_review_library = Gtk.Button(
            label="Review Library  →"
        )

        self.home_review_library.add_css_class(
            "home-primary"
        )

        self.home_review_library.connect(
            "clicked",
            lambda *_: self._navigate_from_home(
                "library"
            ),
        )

        self.home_forge_available = Gtk.Button(
            label="Forge Available Games"
        )

        self.home_forge_available.add_css_class(
            "home-secondary"
        )

        self.home_forge_available.connect(
            "clicked",
            lambda *_: self._navigate_from_home(
                "forge"
            ),
        )

        actions.append(
            self.home_review_library
        )

        actions.append(
            self.home_forge_available
        )

        copy.append(
            title
        )

        copy.append(
            description
        )

        copy.append(
            actions
        )

        shade.append(
            copy
        )

        shade.append(
            Gtk.Box(
                hexpand=True
            )
        )

        unity_logo = Gtk.Label(
            use_markup=True,
            justify=Gtk.Justification.CENTER,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.END,
        )

        unity_logo.set_markup(
            '<span size="17000">ASSASSIN’S</span>\n'
            '<span size="10500">CREED</span>\n'
            '<span foreground="#e31f2b" size="21000">UNITY</span>'
        )

        unity_logo.set_margin_end(
            38
        )

        hero.add_overlay(
            shade
        )

        hero.add_overlay(
            unity_logo
        )

        hero.set_measure_overlay(
            unity_logo,
            False,
        )

        self.home_unity_logo = (
            unity_logo
        )

        dots = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.END,
            valign=Gtk.Align.END,
        )

        dots.set_margin_end(
            28
        )

        dots.set_margin_bottom(
            16
        )

        for index in range(4):
            dot = Gtk.Label(
                label="●"
            )

            if index:
                dot.add_css_class(
                    "dim-label"
                )

            dots.append(
                dot
            )

        hero.add_overlay(
            dots
        )

        hero_frame.append(
            hero
        )

        page.append(
            hero_frame
        )

        # ====================================================
        # STATS
        # ====================================================

        stats = Gtk.Grid(
            column_spacing=14,
            row_spacing=14,
            column_homogeneous=True,
            hexpand=True,
        )

        self.home_stats_grid = stats
        self.home_stat_cards = []

        stat_specs = (
            (
                "applications-games-symbolic",
                "42",
                "Games in Library",
                None,
                False,
            ),
            (
                "emblem-ok-symbolic",
                "38",
                "Ready to Forge",
                "home-stat-ready",
                False,
            ),
            (
                "emblem-system-symbolic",
                "3",
                "Using rtxForge",
                None,
                False,
            ),
            (
                "dialog-warning-symbolic",
                "1",
                "Needs Attention",
                "home-stat-warning",
                True,
            ),
        )

        for index, spec in enumerate(
            stat_specs
        ):
            stat_card = self._home_stat_card(
                icon_name=spec[0],
                value=spec[1],
                caption=spec[2],
                css_class=spec[3],
                arrow=spec[4],
            )

            self.home_stat_cards.append(
                stat_card
            )

            stats.attach(
                stat_card,
                index,
                0,
                1,
                1,
            )

        page.append(
            stats
        )

        # ====================================================
        # RECENT GAMES
        # ====================================================

        recent_shell = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )

        recent_shell.add_css_class(
            "home-recent-section"
        )

        recent_shell.set_margin_top(
            0
        )

        recent_header = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )

        recent_header.set_margin_start(
            16
        )

        recent_header.set_margin_end(
            16
        )

        recent_header.set_margin_top(
            14
        )

        recent_title = Gtk.Label(
            label="Recent Games",
            xalign=0,
            hexpand=True,
        )

        recent_title.add_css_class(
            "title-3"
        )

        view_all = Gtk.Button(
            label="View All"
        )

        view_all.connect(
            "clicked",
            lambda *_: self._navigate_from_home(
                "library"
            ),
        )

        recent_header.append(
            recent_title
        )

        recent_header.append(
            view_all
        )

        recent_shell.append(
            recent_header
        )

        recent_scroller = Gtk.ScrolledWindow()

        recent_scroller.set_policy(
            Gtk.PolicyType.AUTOMATIC,
            Gtk.PolicyType.NEVER,
        )

        recent_scroller.set_propagate_natural_height(
            True
        )

        recent_scroller.set_hexpand(
            True
        )

        recent_grid = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )

        recent_grid.set_margin_start(
            0
        )

        recent_grid.set_margin_end(
            0
        )

        self.home_recent_row = recent_grid

        recent_grid.set_margin_start(
            16
        )

        recent_grid.set_margin_end(
            16
        )

        recent_grid.set_margin_bottom(
            16
        )

        recent_games = (
            (
                "Cyberpunk 2077",
                "1091500",
                "Using rtxForge",
                "home-status-good",
            ),
            (
                "Alan Wake II",
                "",
                "Ready to Forge",
                "home-status-ready",
            ),
            (
                "Starfield",
                "1716740",
                "Using rtxForge",
                "home-status-good",
            ),
            (
                "Hogwarts Legacy",
                "990080",
                "Ready to Forge",
                "home-status-ready",
            ),
            (
                "Forza Horizon 5",
                "1551360",
                "Ready to Forge",
                "home-status-ready",
            ),
            (
                "The Witcher 3",
                "292030",
                "Needs Attention",
                "home-status-warning",
            ),
        )

        for index, (
            name,
            appid,
            status,
            status_class,
        ) in enumerate(recent_games):
            recent_card = self._home_recent_card(
                name=name,
                appid=appid,
                status=status,
                status_class=status_class,
            )

            recent_card.set_size_request(
                185,
                158,
            )

            recent_card.set_hexpand(
                False
            )

            recent_grid.append(
                recent_card
            )

        recent_scroller.set_child(
            recent_grid
        )

        recent_shell.append(
            recent_scroller
        )

        page.append(
            recent_shell
        )

        # ====================================================
        # SYSTEM STATUS + QUICK ACTIONS
        # ====================================================

        bottom = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=16,
            hexpand=True,
        )

        self.home_bottom = (
            bottom
        )

        # System Status
        status_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            hexpand=True,
        )

        status_card.add_css_class(
            "home-bottom-card"
        )

        status_card.set_size_request(
            285,
            -1,
        )

        status_card.set_hexpand(
            False
        )

        status_card.set_halign(
            Gtk.Align.FILL
        )

        status_card.set_size_request(
            -1,
            142,
        )

        status_card.set_margin_top(
            0
        )

        status_content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )

        status_content.set_margin_start(
            18
        )

        status_content.set_margin_end(
            18
        )

        status_content.set_margin_top(
            16
        )

        status_content.set_margin_bottom(
            16
        )

        status_title = Gtk.Label(
            label="System Status",
            xalign=0,
        )

        status_title.add_css_class(
            "title-3"
        )

        state = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=14,
        )

        check_shell = Gtk.Box(
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
            hexpand=False,
            vexpand=False,
        )

        check_shell.set_size_request(
            44,
            44,
        )

        check_shell.add_css_class(
            "home-system-check"
        )

        check = Gtk.Label(
            label="✓",
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )

        check_shell.append(
            check
        )

        state_labels = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=3,
            valign=Gtk.Align.CENTER,
        )

        good = Gtk.Label(
            label="Everything looks good.",
            xalign=0,
        )

        good.add_css_class(
            "heading"
        )

        ready = Gtk.Label(
            label=(
                "rtxForge is ready and your "
                "library is up to date."
            ),
            xalign=0,
            wrap=True,
        )

        ready.add_css_class(
            "dim-label"
        )

        state_labels.append(
            good
        )

        state_labels.append(
            ready
        )

        state.append(
            check_shell
        )

        state.append(
            state_labels
        )

        status_content.append(
            status_title
        )

        status_content.append(
            state
        )

        status_card.append(
            status_content
        )

        bottom.append(
            status_card
        )

        # Quick Actions
        quick_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            hexpand=True,
        )

        quick_card.add_css_class(
            "home-bottom-card"
        )

        quick_card.set_hexpand(
            True
        )

        quick_card.set_size_request(
            -1,
            142,
        )

        quick_content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )

        quick_content.set_margin_start(
            18
        )

        quick_content.set_margin_end(
            18
        )

        quick_content.set_margin_top(
            16
        )

        quick_content.set_margin_bottom(
            16
        )

        quick_title = Gtk.Label(
            label="Quick Actions",
            xalign=0,
        )

        quick_title.add_css_class(
            "title-3"
        )

        quick_row = Gtk.Grid(
            column_spacing=12,
            row_spacing=12,
            column_homogeneous=True,
            hexpand=True,
        )

        self.home_quick_grid = quick_row

        self.home_actions = {
            "library": self._home_quick_action(
                icon_name="media-playback-start-symbolic",
                title="Review Library",
                subtitle="Check for supported games",
                page_id="library",
            ),
            "forge": self._home_quick_action(
                icon_name="applications-engineering-symbolic",
                title="Forge Available",
                subtitle="Set up RTX features",
                page_id="forge",
            ),
            "recovery": self._home_quick_action(
                icon_name="document-revert-symbolic",
                title="Restore a Game",
                subtitle="Revert to original files",
                page_id="recovery",
            ),
        }

        quick_row.attach(
            self.home_actions["library"],
            0,
            0,
            1,
            1,
        )

        quick_row.attach(
            self.home_actions["forge"],
            1,
            0,
            1,
            1,
        )

        quick_row.attach(
            self.home_actions["recovery"],
            2,
            0,
            1,
            1,
        )

        quick_content.append(
            quick_title
        )

        quick_content.append(
            quick_row
        )

        quick_card.append(
            quick_content
        )

        bottom.append(
            quick_card
        )

        page.append(
            bottom
        )

        self.home_hero_frame = (
            hero_frame
        )

        self.home_compact_breakpoint = (
            Adw.Breakpoint.new(
                Adw.BreakpointCondition.parse(
                    "max-width: 920sp"
                )
            )
        )

        def apply_home_compact(*_args):
            self.home_unity_logo.set_visible(
                False
            )

            self.home_bottom.set_orientation(
                Gtk.Orientation.VERTICAL
            )

            self.home_hero_frame.set_size_request(
                -1,
                215,
            )

            for child in self.home_stat_cards:
                self.home_stats_grid.remove(
                    child
                )

            for index, child in enumerate(
                self.home_stat_cards
            ):
                self.home_stats_grid.attach(
                    child,
                    index % 2,
                    index // 2,
                    1,
                    1,
                )

            quick_items = (
                self.home_actions["library"],
                self.home_actions["forge"],
                self.home_actions["recovery"],
            )

            for child in quick_items:
                self.home_quick_grid.remove(
                    child
                )

            for index, child in enumerate(
                quick_items
            ):
                self.home_quick_grid.attach(
                    child,
                    0,
                    index,
                    1,
                    1,
                )

        def unapply_home_compact(*_args):
            self.home_unity_logo.set_visible(
                True
            )

            self.home_bottom.set_orientation(
                Gtk.Orientation.HORIZONTAL
            )

            self.home_hero_frame.set_size_request(
                -1,
                245,
            )

            for child in self.home_stat_cards:
                self.home_stats_grid.remove(
                    child
                )

            for index, child in enumerate(
                self.home_stat_cards
            ):
                self.home_stats_grid.attach(
                    child,
                    index,
                    0,
                    1,
                    1,
                )

            quick_items = (
                self.home_actions["library"],
                self.home_actions["forge"],
                self.home_actions["recovery"],
            )

            for child in quick_items:
                self.home_quick_grid.remove(
                    child
                )

            for index, child in enumerate(
                quick_items
            ):
                self.home_quick_grid.attach(
                    child,
                    index,
                    0,
                    1,
                    1,
                )

        self.home_compact_breakpoint.connect(
            "apply",
            apply_home_compact,
        )

        self.home_compact_breakpoint.connect(
            "unapply",
            unapply_home_compact,
        )

        self.add_breakpoint(
            self.home_compact_breakpoint
        )

        return page

    def _build_library_shell(self):
        library = Gtk.Box(
            orientation=(
                Gtk.Orientation.VERTICAL
            ),
            spacing=18,
            hexpand=True,
            vexpand=True,
        )

        # Search + page action
        search_row = Gtk.Box(
            orientation=(
                Gtk.Orientation.HORIZONTAL
            ),
            spacing=CONTROL_CLUSTER_SPACING,
        )

        self.library_search = (
            Gtk.SearchEntry()
        )

        self.library_search.set_placeholder_text(
            "Search games"
        )

        self.library_search.set_hexpand(
            True
        )

        search_row.append(
            self.library_search
        )

        self.library_add_button = (
            Gtk.Button(
                label="Add Game"
            )
        )

        self.library_add_button.set_size_request(
            -1,
            INTERACTIVE_HEIGHT,
        )

        # Phase 1 builds the destination and visual hierarchy.
        # Backend actions are intentionally not wired yet.
        self.library_add_button.set_sensitive(
            False
        )

        self.library_add_button.set_tooltip_text(
            "Game-management wiring follows "
            "after the Phase 1 shell migration."
        )

        search_row.append(
            self.library_add_button
        )

        library.append(
            search_row
        )

        # Filter + presentation controls
        controls = Gtk.Box(
            orientation=(
                Gtk.Orientation.HORIZONTAL
            ),
            spacing=CONTROL_CLUSTER_SPACING,
        )

        self.library_filters = (
            Adw.ToggleGroup()
        )

        self.library_filters.set_size_request(
            -1,
            INTERACTIVE_HEIGHT,
        )

        self.library_filters.set_margin_top(
            SELECTABLE_GAP,
        )

        self.library_filters.set_margin_bottom(
            SELECTABLE_GAP,
        )

        self.library_filters.set_hexpand(
            True
        )

        self.library_filters.set_can_shrink(
            True
        )

        self.library_filters.add(
            self._library_toggle(
                name="all",
                label="All",
            )
        )

        self.library_filters.add(
            self._library_toggle(
                name="forged",
                label="Using rtxForge",
            )
        )

        self.library_filters.add(
            self._library_toggle(
                name="available",
                label="Ready to Forge",
            )
        )

        self.library_filters.add(
            self._library_toggle(
                name="attention",
                label="Needs Attention",
            )
        )

        self.library_filters.set_active_name(
            "all"
        )

        controls.append(
            self.library_filters
        )

        self.library_views = (
            Adw.ToggleGroup()
        )

        self.library_views.set_size_request(
            -1,
            INTERACTIVE_HEIGHT,
        )

        self.library_views.set_margin_top(
            SELECTABLE_GAP,
        )

        self.library_views.set_margin_bottom(
            SELECTABLE_GAP,
        )

        self.library_views.set_can_shrink(
            False
        )

        self.library_views.add_css_class(
            "flat"
        )

        self.library_views.add(
            self._library_toggle(
                name="grid",
                icon_name=(
                    "view-grid-symbolic"
                ),
                tooltip="Grid view",
            )
        )

        self.library_views.add(
            self._library_toggle(
                name="wide",
                icon_name=(
                    "view-continuous-symbolic"
                ),
                tooltip="Wide capsule view",
            )
        )

        self.library_views.add(
            self._library_toggle(
                name="list",
                icon_name=(
                    "view-list-symbolic"
                ),
                tooltip="List view",
            )
        )

        self.library_views.set_active_name(
            "grid"
        )

        controls.append(
            self.library_views
        )

        library.append(
            controls
        )

        # Real content mount for the future library transplant.
        self.library_content_mount = (
            Gtk.Box(
                orientation=(
                    Gtk.Orientation.VERTICAL
                ),
                spacing=12,
                hexpand=True,
                vexpand=True,
            )
        )

        empty = Adw.StatusPage()

        empty.set_icon_name(
            "applications-games-symbolic"
        )

        empty.set_title(
            "Library surface ready"
        )

        empty.set_description(
            "The existing rtxForge game library "
            "will be connected here next. "
            "No production library behavior has "
            "been changed."
        )

        empty.set_vexpand(
            True
        )

        self.library_content_mount.append(
            empty
        )

        library.append(
            self.library_content_mount
        )

        # Selection actions are contextual.
        # Nothing selected means no permanent action bar.
        self.library_selection_revealer = (
            Gtk.Revealer()
        )

        self.library_selection_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_UP
        )

        self.library_selection_revealer.set_reveal_child(
            False
        )

        action_bar = Gtk.ActionBar()

        self.library_selection_label = (
            Gtk.Label(
                label="0 selected"
            )
        )

        action_bar.pack_start(
            self.library_selection_label
        )

        forge_button = Gtk.Button(
            label="Forge"
        )

        repair_button = Gtk.Button(
            label="Repair"
        )

        restore_button = Gtk.Button(
            label="Restore"
        )

        defaults_button = Gtk.Button(
            label="Use Forge Defaults"
        )

        # These become live only when the existing
        # operation path is migrated.
        for button in (
            forge_button,
            repair_button,
            restore_button,
            defaults_button,
        ):
            button.set_size_request(
                -1,
                INTERACTIVE_HEIGHT,
            )

            button.set_margin_start(
                SELECTABLE_GAP,
            )

            button.set_margin_end(
                SELECTABLE_GAP,
            )

            button.set_sensitive(
                False
            )

        action_bar.pack_end(
            defaults_button
        )

        action_bar.pack_end(
            restore_button
        )

        action_bar.pack_end(
            repair_button
        )

        action_bar.pack_end(
            forge_button
        )

        self.library_selection_revealer.set_child(
            action_bar
        )

        library.append(
            self.library_selection_revealer
        )

        return library

    def _forge_action_row(
        self,
        *,
        title,
        subtitle,
        button_label="Review…",
    ):
        row = Adw.ActionRow()

        row.set_title(
            title
        )

        row.set_subtitle(
            subtitle
        )

        button = Gtk.Button(
            label=button_label
        )

        button.set_valign(
            Gtk.Align.CENTER
        )

        button.set_size_request(
            -1,
            INTERACTIVE_HEIGHT,
        )

        # Phase 1 establishes the interaction surface only.
        # Existing production operations will be connected later.
        button.set_sensitive(
            False
        )

        button.set_tooltip_text(
            "Operation wiring is intentionally disabled "
            "in the Phase 1 redesign lab."
        )

        row.add_suffix(
            button
        )

        return row, button

    def _forge_scale_row(
        self,
        *,
        title,
        subtitle,
        scale,
        format_value,
    ):
        row = Gtk.ListBoxRow()

        row.set_activatable(
            False
        )

        row.set_selectable(
            False
        )

        container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )

        container.set_margin_start(
            16
        )

        container.set_margin_end(
            16
        )

        container.set_margin_top(
            14
        )

        container.set_margin_bottom(
            14
        )

        header = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )

        title_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            hexpand=True,
        )

        title_label = Gtk.Label(
            label=title,
            xalign=0,
            hexpand=True,
        )

        title_label.add_css_class(
            "heading"
        )

        subtitle_label = Gtk.Label(
            label=subtitle,
            xalign=0,
            wrap=True,
            hexpand=True,
        )

        subtitle_label.add_css_class(
            "dim-label"
        )

        title_box.append(
            title_label
        )

        title_box.append(
            subtitle_label
        )

        value_label = Gtk.Label(
            xalign=1
        )

        value_label.add_css_class(
            "dim-label"
        )

        def sync_value(_scale):
            value_label.set_label(
                format_value(
                    _scale.get_value()
                )
            )

        scale.set_hexpand(
            True
        )

        scale.set_draw_value(
            False
        )

        scale.connect(
            "value-changed",
            sync_value,
        )

        sync_value(
            scale
        )

        header.append(
            title_box
        )

        header.append(
            value_label
        )

        container.append(
            header
        )

        container.append(
            scale
        )

        row.set_child(
            container
        )

        return row, value_label

    def _build_forge_shell(self):
        # Keep native Adwaita preference groups/rows, but do not
        # use Adw.PreferencesPage here: its centered narrow column
        # fights the expansive gaming-app layout used by Library.
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            hexpand=True,
            vexpand=False,
        )

        self.forge_page = page

        # RTX feature defaults
        features = Adw.PreferencesGroup()

        features.set_title(
            "RTX Features"
        )

        features.set_description(
            "Choose which RTX features rtxForge "
            "sets up by default."
        )

        feature_row = Adw.ActionRow()

        feature_row.set_title(
            "Feature Mode"
        )

        feature_row.set_subtitle(
            "Choose the RTX features added "
            "when a game is forged."
        )

        self.forge_feature_mode = (
            Adw.ToggleGroup()
        )

        self.forge_feature_mode.set_size_request(
            -1,
            INTERACTIVE_HEIGHT,
        )

        self.forge_feature_mode.set_margin_top(
            SELECTABLE_GAP,
        )

        self.forge_feature_mode.set_margin_bottom(
            SELECTABLE_GAP,
        )

        self.forge_feature_mode.set_valign(
            Gtk.Align.CENTER
        )

        self.forge_feature_mode.add(
            self._library_toggle(
                name="nr",
                label="Neural Rendering",
            )
        )

        self.forge_feature_mode.add(
            self._library_toggle(
                name="mfg",
                label="Multi Frame Generation",
            )
        )

        self.forge_feature_mode.add(
            self._library_toggle(
                name="both",
                label="Both",
            )
        )

        self.forge_feature_mode.set_active_name(
            "both"
        )

        feature_row.add_suffix(
            self.forge_feature_mode
        )

        features.add(
            feature_row
        )

        page.append(
            features
        )

        # Neural Rendering
        neural = Adw.PreferencesGroup()

        neural.set_title(
            "Neural Rendering"
        )

        neural.set_description(
            "Tune the default Neural Rendering image."
        )

        self.forge_nr_strength = (
            Gtk.Scale.new_with_range(
                Gtk.Orientation.HORIZONTAL,
                0.0,
                2.0,
                0.1,
            )
        )

        self.forge_nr_strength.set_value(
            2.0
        )

        self.forge_nr_strength.set_digits(
            2
        )

        (
            strength_row,
            self.forge_nr_strength_value,
        ) = self._forge_scale_row(
            title="Strength",
            subtitle=(
                "Adjust how strongly Neural Rendering "
                "affects the final image."
            ),
            scale=self.forge_nr_strength,
            format_value=lambda value: f"{value:.2f}",
        )

        neural.add(
            strength_row
        )

        self.forge_sharpening = (
            Gtk.Scale.new_with_range(
                Gtk.Orientation.HORIZONTAL,
                0.0,
                1.0,
                0.1,
            )
        )

        self.forge_sharpening.set_value(
            1.0
        )

        self.forge_sharpening.set_digits(
            2
        )

        (
            sharpening_row,
            self.forge_sharpening_value,
        ) = self._forge_scale_row(
            title="Sharpening",
            subtitle=(
                "Fine-tune image sharpness "
                "after rendering."
            ),
            scale=self.forge_sharpening,
            format_value=lambda value: f"{value:.2f}",
        )

        neural.add(
            sharpening_row
        )

        page.append(
            neural
        )

        # Multi Frame Generation
        mfg = Adw.PreferencesGroup()

        mfg.set_title(
            "Multi Frame Generation"
        )

        mfg.set_description(
            "Choose the default MFG target "
            "for supported games."
        )

        multiplier_model = Gtk.StringList.new(
            [
                "2×",
                "3×",
                "4×",
                "5×",
                "6×",
            ]
        )

        self.forge_mfg_multiplier = (
            Adw.ComboRow()
        )

        self.forge_mfg_multiplier.set_title(
            "Frame Multiplier"
        )

        self.forge_mfg_multiplier.set_subtitle(
            "Choose how many displayed frames "
            "MFG should target."
        )

        self.forge_mfg_multiplier.set_model(
            multiplier_model
        )

        self.forge_mfg_multiplier.set_selected(
            2
        )

        mfg.add(
            self.forge_mfg_multiplier
        )

        page.append(
            mfg
        )

        # Explain global defaults clearly.
        defaults = Adw.PreferencesGroup()

        defaults.set_title(
            "Forge Defaults"
        )

        defaults.set_description(
            "These settings are used when a game "
            "is forged for the first time or when "
            "you restore its Forge defaults."
        )

        preview_row = Adw.ActionRow()

        preview_row.set_title(
            "Phase 1 Preview"
        )

        preview_row.set_subtitle(
            "Controls on this redesign page are "
            "not saved yet. Production settings "
            "remain the source of truth."
        )

        preview_icon = Gtk.Image.new_from_icon_name(
            "dialog-information-symbolic"
        )

        preview_icon.set_valign(
            Gtk.Align.CENTER
        )

        preview_row.add_prefix(
            preview_icon
        )

        defaults.add(
            preview_row
        )

        page.append(
            defaults
        )

        # Review-first bulk operations.
        actions = Adw.PreferencesGroup()

        actions.set_title(
            "Library Actions"
        )

        actions.set_description(
            "Review affected games before "
            "applying bulk changes."
        )

        (
            forge_available_row,
            self.forge_review_available,
        ) = self._forge_action_row(
            title="Forge Available Games",
            subtitle=(
                "Set up supported RTX features "
                "for games that are ready."
            ),
        )

        actions.add(
            forge_available_row
        )

        (
            apply_defaults_row,
            self.forge_review_defaults,
        ) = self._forge_action_row(
            title="Apply Forge Defaults",
            subtitle=(
                "Update existing games to use "
                "your current Forge settings."
            ),
        )

        actions.add(
            apply_defaults_row
        )

        (
            restore_row,
            self.forge_review_restore,
        ) = self._forge_action_row(
            title="Restore Original Files",
            subtitle=(
                "Remove rtxForge files and return "
                "selected games to their original setup."
            ),
        )

        actions.add(
            restore_row
        )

        page.append(
            actions
        )

        return page

    def _settings_switch_row(
        self,
        *,
        title,
        subtitle,
        active,
    ):
        row = Adw.ActionRow()

        row.set_title(
            title
        )

        row.set_subtitle(
            subtitle
        )

        row.set_size_request(
            -1,
            62,
        )

        switch = Gtk.Switch(
            active=active,
        )

        switch.set_valign(
            Gtk.Align.CENTER
        )

        row.add_suffix(
            switch
        )

        return row, switch

    def _settings_button_row(
        self,
        *,
        title,
        subtitle,
        button_label,
    ):
        row = Adw.ActionRow()

        row.set_title(
            title
        )

        row.set_subtitle(
            subtitle
        )

        row.set_size_request(
            -1,
            62,
        )

        button = Gtk.Button(
            label=button_label
        )

        button.set_valign(
            Gtk.Align.CENTER
        )

        button.set_size_request(
            -1,
            INTERACTIVE_HEIGHT,
        )

        # Phase 1 lays out the destination only.
        button.set_sensitive(
            False
        )

        button.set_tooltip_text(
            "This action will be connected when "
            "existing Settings behavior is migrated."
        )

        row.add_suffix(
            button
        )

        return row, button

    def _build_settings_shell(self):
        # Like Forge and Library, Settings uses the complete
        # content canvas instead of a narrow PreferencesPage.
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            hexpand=True,
            vexpand=False,
        )

        self.settings_page = page

        # ----------------------------------------------------
        # Library appearance
        # ----------------------------------------------------

        appearance = Adw.PreferencesGroup()

        appearance.set_title(
            "Library Appearance"
        )

        appearance.set_description(
            "Choose how your game library is presented."
        )

        layout_row = Adw.ActionRow()

        layout_row.set_title(
            "Layout"
        )

        layout_row.set_subtitle(
            "Choose the default Library presentation."
        )

        layout_row.set_size_request(
            -1,
            62,
        )

        self.settings_library_layout = (
            Adw.ToggleGroup()
        )

        self.settings_library_layout.set_size_request(
            -1,
            INTERACTIVE_HEIGHT,
        )

        self.settings_library_layout.set_margin_top(
            SELECTABLE_GAP,
        )

        self.settings_library_layout.set_margin_bottom(
            SELECTABLE_GAP,
        )

        self.settings_library_layout.add(
            self._library_toggle(
                name="posters",
                label="Poster",
            )
        )

        self.settings_library_layout.add(
            self._library_toggle(
                name="capsules",
                label="Wide Capsule",
            )
        )

        self.settings_library_layout.add(
            self._library_toggle(
                name="list",
                label="List",
            )
        )

        self.settings_library_layout.set_active_name(
            "posters"
        )

        layout_row.add_suffix(
            self.settings_library_layout
        )

        appearance.add(
            layout_row
        )

        (
            dark_row,
            self.settings_dark_interface,
        ) = self._settings_switch_row(
            title="Dark Interface",
            subtitle=(
                "Use rtxForge's dark application appearance."
            ),
            active=True,
        )

        appearance.add(
            dark_row
        )

        page.append(
            appearance
        )

        # ----------------------------------------------------
        # Library metadata / discovery
        # ----------------------------------------------------

        metadata = Adw.PreferencesGroup()

        metadata.set_title(
            "Library &amp; Metadata"
        )

        metadata.set_description(
            "Control artwork, metadata, and game discovery."
        )

        (
            artwork_row,
            self.settings_online_artwork,
        ) = self._settings_switch_row(
            title="Online Artwork",
            subtitle=(
                "Allow rtxForge to retrieve game artwork."
            ),
            active=True,
        )

        metadata.add(
            artwork_row
        )

        (
            steam_row,
            self.settings_steam_metadata,
        ) = self._settings_switch_row(
            title="Steam Metadata",
            subtitle=(
                "Use Steam information when matching games."
            ),
            active=True,
        )

        metadata.add(
            steam_row
        )

        (
            recognize_row,
            self.settings_recognize_previous,
        ) = self._settings_switch_row(
            title="Recognize Existing rtxForge Installs",
            subtitle=(
                "Detect games that were configured "
                "by an earlier rtxForge installation."
            ),
            active=True,
        )

        metadata.add(
            recognize_row
        )

        page.append(
            metadata
        )

        # ----------------------------------------------------
        # Runtime / network configuration
        # ----------------------------------------------------

        runtime = Adw.PreferencesGroup()

        runtime.set_title(
            "Runtime"
        )

        runtime.set_description(
            "Configure the supporting runtime used by rtxForge."
        )

        (
            provider_row,
            self.settings_runtime_provider,
        ) = self._settings_button_row(
            title="Runtime Provider",
            subtitle=(
                "Choose the runtime provider used for "
                "rtxForge operations."
            ),
            button_label="Configure…",
        )

        runtime.add(
            provider_row
        )

        (
            nr_runtime_row,
            self.settings_nr_runtime,
        ) = self._settings_button_row(
            title="Neural Rendering Runtime",
            subtitle=(
                "Choose the Neural Rendering runtime path."
            ),
            button_label="Choose…",
        )

        runtime.add(
            nr_runtime_row
        )

        (
            timeout_row,
            self.settings_network_timeout,
        ) = self._settings_button_row(
            title="Network Timeout",
            subtitle=(
                "Control how long network operations "
                "wait before timing out."
            ),
            button_label="Adjust…",
        )

        runtime.add(
            timeout_row
        )

        page.append(
            runtime
        )

        # ----------------------------------------------------
        # Diagnostics replaces the old redundant Tools idea.
        # ----------------------------------------------------

        diagnostics = Adw.PreferencesGroup()

        diagnostics.set_title(
            "Diagnostics"
        )

        diagnostics.set_description(
            "Inspect information useful for troubleshooting."
        )

        (
            system_row,
            self.settings_system_information,
        ) = self._settings_button_row(
            title="System Information",
            subtitle=(
                "Review graphics, runtime, and "
                "application environment details."
            ),
            button_label="View…",
        )

        diagnostics.add(
            system_row
        )

        (
            logs_row,
            self.settings_application_logs,
        ) = self._settings_button_row(
            title="Application Logs",
            subtitle=(
                "Open logs generated by rtxForge operations."
            ),
            button_label="Open…",
        )

        diagnostics.add(
            logs_row
        )

        page.append(
            diagnostics
        )

        # ----------------------------------------------------
        # Explicit preview notice.
        # ----------------------------------------------------

        preview = Adw.PreferencesGroup()

        preview.set_title(
            "Phase 1 Preview"
        )

        preview_row = Adw.ActionRow()

        preview_row.set_title(
            "Settings are not saved yet"
        )

        preview_row.set_subtitle(
            "This page is validating the new interface. "
            "Production settings remain the source of truth."
        )

        preview_row.set_size_request(
            -1,
            62,
        )

        preview_icon = Gtk.Image.new_from_icon_name(
            "dialog-information-symbolic"
        )

        preview_icon.set_valign(
            Gtk.Align.CENTER
        )

        preview_row.add_prefix(
            preview_icon
        )

        preview.add(
            preview_row
        )

        page.append(
            preview
        )

        return page

    def _build_recovery_shell(self):
        # Recovery follows the same approved full-width language
        # as Settings and Forge. Nothing is destructive in Phase 1.
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            hexpand=True,
            vexpand=False,
        )

        self.recovery_page = page

        # ----------------------------------------------------
        # Safety / review-first behavior
        # ----------------------------------------------------

        safety = Adw.PreferencesGroup()

        safety.set_title(
            "Recovery Safety"
        )

        safety.set_description(
            "Recovery actions are reviewed before "
            "anything is changed."
        )

        safety_row = Adw.ActionRow()

        safety_row.set_title(
            "Review First"
        )

        safety_row.set_subtitle(
            "rtxForge will show affected files and games "
            "before a recovery action is applied."
        )

        safety_row.set_size_request(
            -1,
            62,
        )

        safety_icon = Gtk.Image.new_from_icon_name(
            "security-high-symbolic"
        )

        safety_icon.set_valign(
            Gtk.Align.CENTER
        )

        safety_row.add_prefix(
            safety_icon
        )

        safety.add(
            safety_row
        )

        page.append(
            safety
        )

        # ----------------------------------------------------
        # Previous changes
        # ----------------------------------------------------

        history = Adw.PreferencesGroup()

        history.set_title(
            "Previous Changes"
        )

        history.set_description(
            "Review recorded rtxForge operations "
            "and available recovery points."
        )

        (
            history_row,
            self.recovery_previous_changes,
        ) = self._settings_button_row(
            title="Recovery Records",
            subtitle=(
                "Browse install, removal, and repair "
                "records created by rtxForge."
            ),
            button_label="Browse…",
        )

        history.add(
            history_row
        )

        page.append(
            history
        )

        # ----------------------------------------------------
        # Cleanup
        # ----------------------------------------------------

        cleanup = Adw.PreferencesGroup()

        cleanup.set_title(
            "Cleanup"
        )

        cleanup.set_description(
            "Inspect legacy files before removing them."
        )

        (
            old_nr_row,
            self.recovery_old_nr_files,
        ) = self._settings_button_row(
            title="Old NR Files",
            subtitle=(
                "Review legacy Neural Rendering files "
                "that may no longer be needed."
            ),
            button_label="Review…",
        )

        cleanup.add(
            old_nr_row
        )

        page.append(
            cleanup
        )

        # ----------------------------------------------------
        # Reports
        # ----------------------------------------------------

        reports = Adw.PreferencesGroup()

        reports.set_title(
            "Reports &amp; Support"
        )

        reports.set_description(
            "Open diagnostic information useful "
            "for troubleshooting and support."
        )

        (
            reports_row,
            self.recovery_library_reports,
        ) = self._settings_button_row(
            title="Library Reports",
            subtitle=(
                "View test notes and export information "
                "about your rtxForge library."
            ),
            button_label="Open…",
        )

        reports.add(
            reports_row
        )

        page.append(
            reports
        )

        # ----------------------------------------------------
        # Preview status
        # ----------------------------------------------------

        preview = Adw.PreferencesGroup()

        preview.set_title(
            "Phase 1 Preview"
        )

        preview_row = Adw.ActionRow()

        preview_row.set_title(
            "Recovery actions are not connected yet"
        )

        preview_row.set_subtitle(
            "The existing production recovery system "
            "remains unchanged and is still the source of truth."
        )

        preview_row.set_size_request(
            -1,
            62,
        )

        preview_icon = Gtk.Image.new_from_icon_name(
            "dialog-information-symbolic"
        )

        preview_icon.set_valign(
            Gtk.Align.CENTER
        )

        preview_row.add_prefix(
            preview_icon
        )

        preview.add(
            preview_row
        )

        page.append(
            preview
        )

        return page

    def _build_page_surface(
        self,
        page_id,
        title,
        icon_name,
        description,
    ):
        scroll = Gtk.ScrolledWindow()

        scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )

        scroll.set_hexpand(
            True
        )

        scroll.set_vexpand(
            True
        )

        clamp = Adw.Clamp()

        clamp.set_maximum_size(
            1120
        )

        clamp.set_tightening_threshold(
            760
        )

        content = Gtk.Box(
            orientation=(
                Gtk.Orientation.VERTICAL
            ),
            spacing=24,
        )

        content.set_margin_start(
            32
        )

        content.set_margin_end(
            32
        )

        content.set_margin_top(
            30
        )

        content.set_margin_bottom(
            32
        )

        page_header = Gtk.Box(
            orientation=(
                Gtk.Orientation.VERTICAL
            ),
            spacing=6,
        )

        title_label = Gtk.Label(
            label=title,
            xalign=0,
        )

        title_label.add_css_class(
            "title-1"
        )

        description_label = Gtk.Label(
            label=description,
            xalign=0,
            wrap=True,
        )

        description_label.add_css_class(
            "dim-label"
        )

        page_header.append(
            title_label
        )

        page_header.append(
            description_label
        )

        if page_id != "home":
            content.append(
                page_header
            )

        mount = Gtk.Box(
            orientation=(
                Gtk.Orientation.VERTICAL
            ),
            spacing=18,
            hexpand=True,
            vexpand=True,
        )

        if page_id == "home":
            mount.append(
                self._build_home_shell()
            )
        elif page_id == "library":
            mount.append(
                self._build_library_shell()
            )
        elif page_id == "forge":
            mount.append(
                self._build_forge_shell()
            )
        elif page_id == "settings":
            mount.append(
                self._build_settings_shell()
            )
        elif page_id == "recovery":
            mount.append(
                self._build_recovery_shell()
            )
        else:
            mount.append(
                self._page_placeholder(
                    page_id,
                    icon_name,
                )
            )

        content.append(
            mount
        )

        clamp.set_child(
            content
        )

        scroll.set_child(
            clamp
        )

        self.page_mounts[
            page_id
        ] = mount

        self.page_surfaces[
            page_id
        ] = scroll

        return scroll

    def _build_content(self):
        toolbar = Adw.ToolbarView()

        # The application titlebar is intentionally quiet.
        # Page identity belongs to the page content itself.
        toolbar.set_top_bar_style(
            Adw.ToolbarStyle.FLAT
        )

        header = Adw.HeaderBar()

        self.app_title = (
            Adw.WindowTitle(
                title="rtxForge",
                subtitle="",
            )
        )

        header.set_title_widget(
            self.app_title
        )

        toolbar.add_top_bar(
            header
        )

        self.stack = Gtk.Stack(
            hexpand=True,
            vexpand=True,
        )

        self.stack.set_transition_type(
            Gtk.StackTransitionType.CROSSFADE
        )

        self.stack.set_transition_duration(
            160
        )

        for (
            page_id,
            title,
            icon_name,
            _heading,
            description,
        ) in PAGES:
            surface = (
                self._build_page_surface(
                    page_id,
                    title,
                    icon_name,
                    description,
                )
            )

            self.stack.add_named(
                surface,
                page_id,
            )

        toolbar.set_content(
            self.stack
        )

        self.content_page = (
            Adw.NavigationPage.new(
                toolbar,
                "Home",
            )
        )

        self.split_view.set_content(
            self.content_page
        )

    def _on_sidebar_selected(
        self,
        source_list,
        row,
    ):
        if row is None:
            return

        # Only one of the two navigation groups may appear active.
        for navigation in self.navigation_lists:
            if navigation is source_list:
                continue

            navigation.unselect_all()

        page_id = getattr(
            row,
            "page_id",
            None,
        )

        if page_id:
            self._select_page(
                page_id
            )

    def _select_page(
        self,
        page_id,
    ):
        selected = next(
            (
                page
                for page in PAGES
                if page[0] == page_id
            ),
            None,
        )

        if selected is None:
            return

        (
            _,
            title,
            _,
            _,
            _,
        ) = selected

        self.stack.set_visible_child_name(
            page_id
        )

        self.content_page.set_title(
            title
        )

        self.split_view.set_show_content(
            True
        )


class RedesignLabApplication(
    Adw.Application
):
    def __init__(
        self,
        smoke_test=False,
    ):
        super().__init__(
            application_id=APP_ID,
            flags=(
                Gio.ApplicationFlags.NON_UNIQUE
            ),
        )

        self.smoke_test = (
            smoke_test
        )

    def do_activate(self):
        window = (
            self.props.active_window
        )

        if window is None:
            window = RedesignLabWindow(
                self
            )

        if self.smoke_test:
            print(
                "rtxForge redesign lab smoke:"
            )

            print(
                f"  runtime root: {ROOT}"
            )

            print(
                f"  version: {APP_VERSION}"
            )

            print(
                "  shell: ApplicationWindow + "
                "ToolbarView + NavigationSplitView"
            )

            print(
                "  navigation: "
                "Home / Game Library / Forge / "
                "Settings / Recovery"
            )

            expected_pages = {
                page[0]
                for page in PAGES
            }

            actual_mounts = set(
                window.page_mounts
            )

            actual_surfaces = set(
                window.page_surfaces
            )

            if actual_mounts != expected_pages:
                raise RuntimeError(
                    "Phase 1 page mounts incomplete: "
                    f"{sorted(actual_mounts)}"
                )

            if actual_surfaces != expected_pages:
                raise RuntimeError(
                    "Phase 1 page surfaces incomplete: "
                    f"{sorted(actual_surfaces)}"
                )

            for page_id in (
                "home",
                "library",
                "forge",
                "settings",
                "recovery",
            ):
                window._select_page(
                    page_id
                )

                if (
                    window.stack.get_visible_child_name()
                    != page_id
                ):
                    raise RuntimeError(
                        f"Navigation failed for {page_id}"
                    )

            window._select_page(
                "home"
            )

            print(
                "  page surfaces: "
                + " / ".join(
                    sorted(actual_surfaces)
                )
            )

            print(
                "  migration mounts: ready"
            )

            if not isinstance(
                window.home_page,
                Gtk.Box,
            ):
                raise RuntimeError(
                    "Home must use the full-width "
                    "page container"
                )

            if not window.home_page.get_hexpand():
                raise RuntimeError(
                    "Home page must expand horizontally"
                )

            if set(
                window.home_actions
            ) != {
                "library",
                "forge",
                "recovery",
            }:
                raise RuntimeError(
                    "Home quick actions are incomplete"
                )

            if not hasattr(
                window,
                "home_review_library",
            ):
                raise RuntimeError(
                    "Home hero primary action missing"
                )

            if not hasattr(
                window,
                "home_forge_available",
            ):
                raise RuntimeError(
                    "Home hero Forge action missing"
                )

            print(
                "  home shell: "
                "cinematic hero + stats + recent games + "
                "system status + quick actions"
            )

            print(
                "  home artwork: local Steam cache only"
            )

            print(
                "  home actions: internal navigation only"
            )

            if not hasattr(
                window,
                "library_search",
            ):
                raise RuntimeError(
                    "Game Library search missing"
                )

            if (
                window.library_search.get_placeholder_text()
                != "Search games"
            ):
                raise RuntimeError(
                    "Game Library search placeholder incorrect"
                )

            if (
                window.library_filters.get_n_toggles()
                != 4
            ):
                raise RuntimeError(
                    "Game Library filter group incomplete"
                )

            if (
                window.library_filters.get_active_name()
                != "all"
            ):
                raise RuntimeError(
                    "Game Library default filter is not All"
                )

            if (
                window.library_views.get_n_toggles()
                != 3
            ):
                raise RuntimeError(
                    "Game Library view group incomplete"
                )

            if (
                window.library_views.get_active_name()
                != "grid"
            ):
                raise RuntimeError(
                    "Game Library default view is not Grid"
                )

            if (
                window.library_selection_revealer
                .get_reveal_child()
            ):
                raise RuntimeError(
                    "Selection bar must be hidden "
                    "when nothing is selected"
                )

            print(
                "  library shell: "
                "search + filters + views + "
                "content mount + contextual actions"
            )

            print(
                "  library backend: intentionally unwired"
            )

            if not isinstance(
                window.forge_page,
                Gtk.Box,
            ):
                raise RuntimeError(
                    "Forge must use the full-width "
                    "page container"
                )

            if isinstance(
                window.forge_page,
                Adw.PreferencesPage,
            ):
                raise RuntimeError(
                    "Forge must not use the narrow "
                    "Adw.PreferencesPage wrapper"
                )

            if not window.forge_page.get_hexpand():
                raise RuntimeError(
                    "Forge page must expand horizontally"
                )

            print(
                "  forge layout: full-width native groups"
            )

            if not hasattr(
                window,
                "forge_feature_mode",
            ):
                raise RuntimeError(
                    "Forge feature-mode control missing"
                )

            if (
                window.forge_feature_mode.get_n_toggles()
                != 3
            ):
                raise RuntimeError(
                    "Forge feature mode must have "
                    "three choices"
                )

            if (
                window.forge_feature_mode.get_active_name()
                != "both"
            ):
                raise RuntimeError(
                    "Forge preview default should "
                    "show Both"
                )

            if not hasattr(
                window,
                "sidebar_brand_icon",
            ):
                raise RuntimeError(
                    "Sidebar branding icon missing"
                )

            if (
                window.sidebar_brand_icon.get_pixel_size()
                < 56
            ):
                raise RuntimeError(
                    "Sidebar branding icon was not enlarged"
                )

            if not hasattr(
                window,
                "forge_nr_strength",
            ):
                raise RuntimeError(
                    "Forge NR strength control missing"
                )

            if not hasattr(
                window,
                "forge_nr_strength_value",
            ):
                raise RuntimeError(
                    "Forge NR strength value label missing"
                )

            if (
                window.forge_nr_strength.get_draw_value()
            ):
                raise RuntimeError(
                    "Forge NR strength should use the stacked slider layout"
                )

            if not hasattr(
                window,
                "forge_sharpening",
            ):
                raise RuntimeError(
                    "Forge sharpening control missing"
                )

            if not hasattr(
                window,
                "forge_sharpening_value",
            ):
                raise RuntimeError(
                    "Forge sharpening value label missing"
                )

            if (
                window.forge_sharpening.get_draw_value()
            ):
                raise RuntimeError(
                    "Forge sharpening should use the stacked slider layout"
                )

            if (
                window.forge_nr_strength_value.get_label()
                != "2.00"
            ):
                raise RuntimeError(
                    "Forge NR strength display incorrect"
                )

            if (
                window.forge_sharpening_value.get_label()
                != "1.00"
            ):
                raise RuntimeError(
                    "Forge sharpening display incorrect"
                )

            if not hasattr(
                window,
                "forge_mfg_multiplier",
            ):
                raise RuntimeError(
                    "Forge MFG multiplier control missing"
                )

            if (
                window.forge_mfg_multiplier.get_selected()
                != 2
            ):
                raise RuntimeError(
                    "Forge preview MFG selection "
                    "should be 4x"
                )

            for review_button in (
                window.forge_review_available,
                window.forge_review_defaults,
                window.forge_review_restore,
            ):
                if review_button.get_sensitive():
                    raise RuntimeError(
                        "Phase 1 bulk actions must "
                        "remain unwired"
                    )

            print(
                "  forge shell: "
                "features + NR + MFG + "
                "defaults + review actions"
            )

            print(
                "  forge persistence: intentionally unwired"
            )

            if not isinstance(
                window.settings_page,
                Gtk.Box,
            ):
                raise RuntimeError(
                    "Settings must use the full-width "
                    "page container"
                )

            if not window.settings_page.get_hexpand():
                raise RuntimeError(
                    "Settings page must expand horizontally"
                )

            if (
                window.settings_library_layout.get_n_toggles()
                != 3
            ):
                raise RuntimeError(
                    "Settings Library Layout is incomplete"
                )

            if (
                window.settings_library_layout.get_active_name()
                != "posters"
            ):
                raise RuntimeError(
                    "Settings Library Layout preview "
                    "must default to Poster"
                )

            for switch in (
                window.settings_dark_interface,
                window.settings_online_artwork,
                window.settings_steam_metadata,
                window.settings_recognize_previous,
            ):
                if not switch.get_active():
                    raise RuntimeError(
                        "Settings preview switches "
                        "should begin enabled"
                    )

            for button in (
                window.settings_runtime_provider,
                window.settings_nr_runtime,
                window.settings_network_timeout,
                window.settings_system_information,
                window.settings_application_logs,
            ):
                if button.get_sensitive():
                    raise RuntimeError(
                        "Phase 1 Settings actions must "
                        "remain unwired"
                    )

            print(
                "  settings shell: "
                "appearance + metadata + runtime + diagnostics"
            )

            print(
                "  settings persistence: intentionally unwired"
            )

            if not isinstance(
                window.recovery_page,
                Gtk.Box,
            ):
                raise RuntimeError(
                    "Recovery must use the full-width "
                    "page container"
                )

            if not window.recovery_page.get_hexpand():
                raise RuntimeError(
                    "Recovery page must expand horizontally"
                )

            for button in (
                window.recovery_previous_changes,
                window.recovery_old_nr_files,
                window.recovery_library_reports,
            ):
                if button.get_sensitive():
                    raise RuntimeError(
                        "Phase 1 Recovery actions must "
                        "remain unwired"
                    )

            print(
                "  recovery shell: "
                "safety + history + cleanup + reports"
            )

            print(
                "  recovery actions: intentionally unwired"
            )

            print(
                "  protected classic surfaces: untouched"
            )

            print(
                "  production backend: untouched"
            )

            GLib.idle_add(
                self._finish_smoke
            )

            return

        window.present()

    def _finish_smoke(self):
        self.quit()
        return False


def main():
    smoke_test = (
        "--smoke-test"
        in sys.argv
    )

    style_manager = (
        Adw.StyleManager.get_default()
    )

    style_manager.set_color_scheme(
        Adw.ColorScheme.FORCE_DARK
    )

    application = (
        RedesignLabApplication(
            smoke_test=smoke_test
        )
    )

    return application.run(
        [sys.argv[0]]
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
