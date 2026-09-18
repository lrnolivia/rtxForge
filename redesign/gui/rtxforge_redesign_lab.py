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
    Gtk,
    Pango,
)


APP_ID = (
    "io.github.lrnolivia."
    "RTXForge.RedesignLab"
)

INTERACTIVE_HEIGHT = 42
NAVIGATION_HEIGHT = 46

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
        "Choose what rtxForge adds to your games.",
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
            spacing=12,
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
            spacing=12,
        )

        self.library_filters = (
            Adw.ToggleGroup()
        )

        self.library_filters.set_size_request(
            -1,
            INTERACTIVE_HEIGHT,
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

        if page_id == "library":
            mount.append(
                self._build_library_shell()
            )
        elif page_id == "forge":
            mount.append(
                self._build_forge_shell()
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
