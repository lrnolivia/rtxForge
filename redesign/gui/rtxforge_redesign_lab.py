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
- Tools
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
    Gtk,
)


APP_ID = (
    "io.github.lrnolivia."
    "RTXForge.RedesignLab"
)

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
        "The new rtxForge application shell begins here.",
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
        "RTX defaults and Forge actions will move here.",
    ),
    (
        "tools",
        "Tools",
        "applications-utilities-symbolic",
        "Tools",
        "Diagnostics and supporting utilities will live here.",
    ),
    (
        "settings",
        "Settings",
        "emblem-system-symbolic",
        "Settings",
        "Application preferences will live here.",
    ),
)

SECONDARY_PAGES = (
    (
        "recovery",
        "Recovery",
        "document-revert-symbolic",
        "Recovery",
        "Repair and restoration workflows will live here.",
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
            900,
            620,
        )

        self.page_rows = {}
        self.row_lists = {}
        self.navigation_lists = []

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
                48
            )

            return image

        image = Gtk.Image.new_from_icon_name(
            "applications-games-symbolic"
        )

        image.set_pixel_size(
            42
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
                9
            )

            content.set_margin_bottom(
                9
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
            spacing=9,
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

        identity = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )

        identity.append(
            self._app_icon()
        )

        name = Gtk.Label(
            label="rtxForge",
            xalign=0,
            hexpand=True,
        )

        name.add_css_class(
            "title-2"
        )

        identity.append(
            name
        )

        branding.append(
            identity
        )

        description = Gtk.Label(
            label=(
                "Bring newer RTX features "
                "to your games."
            ),
            xalign=0,
            wrap=True,
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

    def _build_content(self):
        toolbar = Adw.ToolbarView()

        # Flat is Libadwaita's intended treatment for split/sidebar apps.
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
            _title,
            icon_name,
            heading,
            description,
        ) in PAGES:
            page = Adw.StatusPage()

            page.set_icon_name(
                icon_name
            )

            page.set_title(
                heading
            )

            page.set_description(
                description
            )

            self.stack.add_named(
                page,
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
                "Tools / Settings / Recovery"
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
