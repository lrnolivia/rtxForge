# Windows shell design map

The Windows shell carries the Linux desktop build (`gui/rtxforge_gtk.py`) over
to Windows: same features, copy, order and rtxForge identity. Where a GNOME
pattern doesn't fit WinUI 3 / Fluent guidance, the Windows shell uses the
native Windows pattern instead. Game Mode (`gui/couch_shell.py`) is being
ported; Settings › Gaming Mode already matches Linux.

## Windows-native adaptations

| Linux (GNOME / libadwaita) | Windows (WinUI 3 / Fluent) | Why |
| --- | --- | --- |
| Main menu (hamburger `Gtk.MenuButton`) | `NavigationView` items: Library, Packages, Extras, Activity, Settings | Windows apps navigate with a pane, not an app menu |
| Settings in a separate resizable window with a sidebar and Save Settings | Settings page in the main window (NavigationView Settings item); changes apply immediately | Windows settings live in-app and apply instantly |
| Game details `Adw.Dialog` with a sidebar list and close button | Game page reached by navigation, with back; sections in a `SelectorBar` | Large content belongs on a page, not a modal; no nested sidebars |
| Per-section footer action bar | Actions under the banner title; section actions inline | Fluent places primary commands with the content |
| Card "Details" button | Click the card (`ItemsView` invoke); right-click for the context menu | Native item hover/press/focus visuals |
| Selection via always-visible card checkboxes; Select all · Clear | Select mode (command bar toggle) shows checks on the art / at the start of the Game column; clicking toggles; Select all · Clear | Matches Photos / File Explorer selection |
| Compact dashboard reappearing in the header bar | Removed; the hero scrolls with the page | No GNOME-style dynamic header bar on Windows |
| Operation review / progress / done panels | Kept: one `ContentDialog` moving Install Features presets → Review → Progress (poster, counter, bar, Cancel) → Done | Matches Linux; reads as a native modal |
| `Adw.Toast` | `InfoBar` on an opaque surface | Native status surface |
| Corners setting (System / Rounded / Square) | Removed; Fluent radii for controls, rounder rtxForge radii for cards and art | Windows apps use system geometry |
| Game details tabs: Overview · Features · … | Overview · Presets · DLSS Files · Tools · Notes · Appearance | Presets names what the tab edits |
| Light / Dark / Night | Use system setting / Light / Dark / Night | Windows apps follow the system theme by default |
| libadwaita surfaces | Mica backdrop, Fluent layer and card fills | Windows 11 material |
| Notes saved with a button | Notes save when the field loses focus | Fluent apps autosave text |

## Widgets

| GTK / libadwaita | WinUI 3 |
| --- | --- |
| `Adw.PreferencesGroup` | Section header + stack of settings cards (`PreferencesGroup`) |
| `Adw.ActionRow` | Settings card with icon, title, description, control (`Prefs.Row`) |
| `Adw.SwitchRow` | Settings card + `ToggleSwitch` |
| `Adw.ComboRow` / `Gtk.DropDown` | Settings card + `ComboBox` |
| `Adw.EntryRow` | Settings card + `TextBox` |
| `Adw.ToggleGroup` / `Adw.Toggle` | Fluent segmented control (`ForgeSegmentStyle`: Fluent fills, accent pill) |
| `Gtk.Scale` + `Gtk.SpinButton` | `Slider` + `NumberBox` |
| `Gtk.SearchEntry` | `AutoSuggestBox` in the Library header, as in Linux |
| `Gtk.Expander` (Presets) | `Expander` |
| `Gtk.FlowBox` / `Gtk.ColumnView` library | `ItemsView` with `UniformGridLayout` / `StackLayout` |
| `Gtk.Popover` context menu | `MenuFlyout` |
| `Gtk.ListBox` sidebars | `NavigationView`, `SelectorBar` |
| `Gtk.Spinner` / `Gtk.ProgressBar` | `ProgressBar` in the operation dialog |
| `Gtk.FileDialog` | `FolderPicker` |
| `.suggested-action`, `.forge-primary` | `AccentButtonStyle` (GeForce green accent) |
| `.bulk-remove` | Standard button with a red restore icon |
| symbolic icons | Segoe Fluent Icons |

## Tokens

The GeForce green replaces the Fluent accent ramp in `App.xaml`, so every
accent surface (primary buttons, toggles, sliders, selection) is green while
staying a native control.

| Linux token | Windows | Value |
| --- | --- | --- |
| `@accent_bg_color` | `SystemAccentColor` | `#76B900` |
| `@accent_color` | `SystemAccentColorLight2` (dark-theme accent fill) | `#95CF38` |
| light-theme greens | `SystemAccentColorDark1` / `Dark2` | `#437500` / `#376B18` |
| `@window_bg_color`, `@view_bg_color`, `@sidebar_bg_color` | Mica + NavigationView content layer | native |
| `@forge_panel_bg` (`.control-pod`) | `CardBackgroundFillColorDefault` + `CardStrokeColorDefault` | native |
| `@forge_library_card_a/_b` | `CardBackgroundFillColorDefault` | native |
| boxed-list rows | settings cards (`CardBackgroundFillColorDefault`, `ControlCornerRadius`) | native |
| `.mode-selector` | `ControlAltFillColorSecondary` + `ControlStrokeColorDefault` | native |
| toggle checked / hover | `ControlFillColorDefault` / `SubtleFillColorSecondary` | native |
| `@window_fg_color`, `.dim-label` | `TextFillColorPrimary` / `TextFillColorSecondary` | native |
| `.eyebrow` | `ForgeEyebrowBrush` | `#76B900` dark, `#437500` light |
| `.bulk-remove` | `ForgeRemoveBrush` (icon only) | `#FF928C` dark, `#9B3028` light |
| `.library-test-pill.test-tested` | `ForgePillTestedBrush` | `#76B900` dark, `#315B15` light |
| `.banner-shade` | `ForgeBannerShadeBrush` | fades into the content layer |
| Night palette | Mica off, black window, Fluent dark fills | `#000000` |

### Per-game accents

`Services/ArtAccent.cs` ports `artwork_accent()` and `ui_colors.py` exactly:
dominant hue from a 32×32 poster thumbnail (24 buckets, s × v weighting),
rebuilt at s 0.62 / v 0.90, muted for unsupported games, overridden by
Settings › `game_accents`. Games without artwork use a light neutral grey.
Every derived color keeps its Linux name (`color`, `accent_fg`, `accent_dark`,
`accent_shadow`, `button_fg`, `selected_title`, `source_bg/fg`, `nav_accent`,
`hero_accent`) and is applied where the Linux `.art-*` CSS applies it:

| Linux rule | Windows |
| --- | --- |
| `.game-card:hover .gallery-artwork-ring`, `:hover .card-title` | Card ring and title tint on hover (the 2px ring is always reserved) |
| `.game-card.selected` and its pills, check, title | Selected card fills with the accent |
| `columnview row.game-selected`, `.library-column-actions.selected-actions` | Selected list row fills with the accent; accent action buttons |
| `.library-column-art` hover / selected | List thumbnail ring |
| `.game-banner-title`, `.progress-poster-frame` | Game page title (`hero_accent`) and poster ring |
| `button.suggested-action`, `toggle:checked`, `scale highlight`, `progressbar` | Page-level accent overrides on the game page and operation dialog |
| `.game-detail-nav row:selected` | Selected tab: accent pill, `alpha(color, 0.10)` fill, `nav_accent` label |
| `.review-game` bezel and badge, `.job-title` | Review thumbnails and badges, progress title |
| `.artwork-editor .artwork-preview` | Appearance artwork previews |

Geometry: `ControlCornerRadius` (4) for controls, settings cards and segments,
`OverlayCornerRadius` (8) for pods; game cards and posters use 12 and small
artwork 8, closer to the Linux 14px cards. Layouts are responsive: margins,
hero, poster and title scale with the window; actions, tools and pods wrap or
stack when narrow; the list drops Location, then Features.
Typography is Segoe UI Variable, except `Bakbak One` (shared `gui/fonts`) for
the rtxForge wordmark and the game banner title.

## Known differences

- Packages, Extras, artwork search and the Recovery tools show placeholders
  until the Windows engine bridge lands. The shell runs in preview mode
  (sample library, no game writes), matching `rtxforge_gtk.py --demo`.
- Settings › Gaming Mode matches Linux (Steam Library, Interface, Controller). Big Picture UI and Add to Steam are saved/stubbed until Game Mode and the engine bridge land.
