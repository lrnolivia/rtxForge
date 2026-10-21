using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    string settingsSection = "Graphics";
    Func<Tuning>? presetValue;

    // ---------- Presets (library presets) ----------

    UIElement BuildPresets()
    {
        // A wide column centered in the window: equal side margins computed from the
        // view width (alignment inside the ScrollViewer drifted right), never less
        // than the Library / Settings page margin.
        var column = Math.Min(t.Px(1600), Math.Max(0, ActualWidth - t.Px(56) * 2));
        var side = Math.Max(t.Px(56), (ActualWidth - column) / 2);
        var page = new Grid
        {
            RowSpacing = t.Px(20), HorizontalAlignment = HorizontalAlignment.Stretch,
            Padding = new Thickness(side, t.Px(24), side, t.Px(20)),
        };
        page.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        page.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        page.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        var head = new StackPanel { Spacing = t.Px(10) };
        head.Children.Add(ui.H1("Presets", 1.4));
        head.Children.Add(ui.P("Save defaults for new installs, or review changes for configured games.", .78));
        page.Children.Add(head);
        var fields = new StackPanel { Spacing = t.Px(16), Padding = new Thickness(t.Px(4), t.Px(4), t.Px(4), t.Px(8)) };
        Action? refreshFooter = null;
        var (rows, value) = PresetRows(shell.Settings.Presets, changed: () => refreshFooter?.Invoke());
        presetValue = value;
        foreach (var row in rows) fields.Children.Add(row);
        var scroll = new ScrollViewer { Content = fields, HorizontalScrollMode = ScrollMode.Disabled };
        Grid.SetRow(scroll, 1); page.Children.Add(scroll);
        var footer = new StackPanel { Spacing = t.Px(12) };
        footer.Children.Add(ui.P("Save defaults for new installs, or apply these settings to configured games after review.", .72));
        var configured = shell.Games.Where(g => g.Installed && !g.Blocked).ToList();
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(12), HorizontalAlignment = HorizontalAlignment.Right };
        actions.Children.Add(ui.Button("Save defaults", () => { SavePresets(); refreshFooter?.Invoke(); Toast("Defaults saved for new installs"); }, GmKind.Primary, .85));
        actions.Children.Add(ui.Button("Apply to games…", () =>
        {
            var targets = new UIElement[]
            {
                ui.RowButton("All installed games", configured.Count.ToString(), () => { CloseModal(); ApplyPresets(configured); },
                    description: "Review changes for every configured game."),
                ui.RowButton("Choose games", null, () => { CloseModal(); ChoosePresetGames(configured); },
                    description: "Pick which games to update."),
            };
            ShowModal("Apply to games", ui.Group(targets, t.Card), [ui.Button("Cancel", CloseModal, GmKind.Card, .85)], CloseModal, 860);
        }, GmKind.Card, .85, enabled: configured.Count > 0).With(b => Key(b, "presets-apply")));
        var reset = ui.Button("Discard changes", () => Render(), GmKind.Transparent, .76,
            radius: 10, minHeight: 40, padding: new Thickness(t.Px(8)));
        ToolTipService.SetToolTip(reset, "Discard unsaved preset changes.");
        reset.HorizontalAlignment = HorizontalAlignment.Left;
        reset.VerticalAlignment = VerticalAlignment.Center;
        Key(reset, "presets-discard");
        refreshFooter = () => reset.Visibility = System.Text.Json.Nodes.JsonNode.DeepEquals(
            FeatureControlSchema.Resolve(value()), FeatureControlSchema.Resolve(shell.Settings.Presets)) ? Visibility.Collapsed : Visibility.Visible;
        refreshFooter();
        foreach (var action in actions.Children.OfType<Button>())
        {
            action.Width = t.Px(260);
            action.CornerRadius = new CornerRadius(t.Px(10));
            action.MinHeight = t.Px(48);
            GmUi.NoLift(action);
        }
        var actionRow = new Grid { ColumnSpacing = t.Px(12) };
        actionRow.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        actionRow.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        actionRow.Children.Add(reset); Grid.SetColumn(actions, 1); actionRow.Children.Add(actions);
        footer.Children.Add(actionRow);
        Grid.SetRow(footer, 2); page.Children.Add(footer);
        return page;
    }

    void SavePresets()
    {
        if (presetValue is null) return;
        var v = presetValue();
        shell.Settings.NrStrength = v.NrStrength;
        shell.Settings.SharpeningStrength = v.SharpeningStrength;
        shell.Settings.MfgMultiplier = v.MfgMultiplier;
        shell.Settings.NrOnLaunch = v.NrOnLaunch == true;
        shell.Settings.FeatureControls = v.FeatureControls;
        shell.Settings.Save();
    }

    void ApplyPresets(List<Game> games)
    {
        if (presetValue is { } value) _ = RunOperationAsync("apply", games, value());
    }

    void ChoosePresetGames(List<Game> games)
    {
        var choices = new StackPanel { Spacing = t.Px(8) };
        choices.Children.Add(ui.P("Select games, then review the changes before applying.", .8));
        var selected = new HashSet<Game>();
        var review = ui.Button("Review changes", () => { CloseModal(); ApplyPresets(games.Where(selected.Contains).ToList()); },
            GmKind.Primary, .85, enabled: false, radius: 10, minHeight: 48);
        void UpdateReview()
        {
            review.IsEnabled = selected.Count > 0;
            review.Background = GmTheme.B(review.IsEnabled ? GmTheme.Accent : t.Disabled);
            review.Foreground = GmTheme.B(review.IsEnabled ? GmTheme.AccentInk : t.DisabledFg);
        }
        foreach (var game in games)
        {
            var check = new CheckBox { Content = game.Name, FontSize = t.Em(.85), Foreground = GmTheme.B(t.Fg),
                MinHeight = t.Px(48), Padding = new Thickness(t.Px(10)) };
            ui.Focusable(check);
            check.Checked += (_, _) => { selected.Add(game); UpdateReview(); };
            check.Unchecked += (_, _) => { selected.Remove(game); UpdateReview(); };
            choices.Children.Add(check);
        }
        ShowModal("Choose games", choices, [ui.Button("Cancel", CloseModal, GmKind.Card, .85), review], CloseModal, 920);
    }

    // ---------- Settings (the same preferences, sized for the couch) ----------

    static readonly string[] SettingsSections = ["Graphics", "Overlay", "Appearance", "Library", "Gaming Mode", "System", "Recovery", "About"];
    sealed record SettingsGroup(string Title, string? Description, IReadOnlyList<UIElement> Rows);

    UIElement BuildSettings()
    {
        var grid = new Grid { ColumnSpacing = t.Px(40), Padding = new Thickness(t.Px(56), t.Px(32), t.Px(56), t.Px(8)), RowSpacing = t.Px(22) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(t.Px(ActualWidth <= 1050 ? 180 : ActualWidth <= 1500 ? 220 : 270)) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        var head = new StackPanel { Spacing = t.Px(10) };
        head.Children.Add(ui.H1("Settings"));
        head.Children.Add(ui.P("The same rtxForge preferences, sized for the couch."));
        Grid.SetColumnSpan(head, 2);
        grid.Children.Add(head);

        var nav = new StackPanel { Spacing = t.Px(12) };
        foreach (var section in SettingsSections)
        {
            var active = section == settingsSection;
            var button = ui.Button(section, () => { settingsSection = section; Render(); pendingFocusKey = "gm_set-" + section; },
                active ? GmKind.Card : GmKind.Transparent, 0.92, radius: 12, padding: new Thickness(t.Px(24), t.Px(18), t.Px(24), t.Px(18)),
                minHeight: t.Compact ? 56 : 70);
            button.HorizontalAlignment = HorizontalAlignment.Stretch;
            button.HorizontalContentAlignment = HorizontalAlignment.Left;
            ui.MenuFocus(button);
            Key(button, "set-" + section);
            if (active && initialFocus is null) initialFocus = button;
            nav.Children.Add(button);
        }
        var navigation = new ScrollViewer { Content = nav, HorizontalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Grid.SetRow(navigation, 1);
        grid.Children.Add(navigation);

        var content = new StackPanel { Spacing = t.Px(24) };
        if (settingsSection == "Overlay") shell.Settings.CopyOverlayFrom(ForgeSettings.Load());
        var title = new StackPanel { Spacing = t.Px(10) };
        title.Children.Add(ui.H2(settingsSection));
        content.Children.Add(title);
        var groups = new Controls.PresetColumns(t.Px(620), 2) { ColumnSpacing = t.Px(24), RowSpacing = t.Px(28) };
        foreach (var group in SettingsGroups(settingsSection))
        {
            var section = new StackPanel { Spacing = t.Px(12) };
            section.Children.Add(ui.H2(group.Title, .96));
            if (group.Description is not null) section.Children.Add(ui.P(group.Description, .75));
            section.Children.Add(ui.Group(group.Rows)); groups.Children.Add(section);
        }
        content.Children.Add(groups);
        var scroll = new ScrollViewer { Content = content, HorizontalScrollMode = ScrollMode.Disabled, Padding = new Thickness(0, 0, t.Px(12), 0) };
        Grid.SetRow(scroll, 1);
        Grid.SetColumn(scroll, 1);
        grid.Children.Add(scroll);
        return grid;
    }

    /// <summary>A choice row opens its options; opening or dismissing never changes the setting.</summary>
    Button Choice(string title, string? description, string[] keys, string[] captions, Func<string> get, Action<string> set)
    {
        string Caption() => captions[Math.Max(0, Array.IndexOf(keys, get()))];
        Button? row = null;
        void Choose(int index)
        {
            if (keys[index] == get()) return;
            set(keys[index]);
            shell.SaveSettings();
            Render(keepFocus: true);
        }
        row = ui.RowButton(title, Caption(), () => OpenChoiceMenu(row!, title, captions, Math.Max(0, Array.IndexOf(keys, get())), Choose), description: description);
        Key(row, "choice-" + title);
        return row;
    }

    /// <summary>
    /// The controls guide (replaces on-screen navigation sentences): each action
    /// with the button for the connected controller family and the keyboard key.
    /// Rows are focusable so the D-pad can scroll through the whole guide.
    /// </summary>
    /// <summary>The controls guide rows for one input: controller (family glyphs) or keyboard.</summary>
    List<UIElement> GuideRows(string view)
    {
        var (accept, back, library, menu) = GamepadInput.Glyphs(family);
        var (select, settingsKey, bumpers) = family switch
        {
            "playstation" => ("□", "Create", "L1 / R1"),
            "nintendo" => ("Y", "−", "L / R"),
            "generic" => ("West", "Back", "Left / Right shoulder"),
            _ => ("X", "View", "LB / RB"),
        };
        (string Action, string Key)[] entries = view == "controller"
            ?
            [
                ("Move between items", "D-pad / Left stick"), ("Select", accept), ("Back, or close a dialog", back),
                ("Library", library), ("Select games", select), ("Switch pages", bumpers),
                ("Adjust a value", "D-pad left / right"), ("Settings", settingsKey), ("Main menu", menu),
            ]
            :
            [
                ("Move between items", "Arrow keys"), ("Select", "Enter"), ("Back, or close a dialog", "Esc"),
                ("Library", "Ctrl+L"), ("Select games", "X"), ("Switch pages", "Page Up / Page Down"),
                ("Adjust a value", "Left / Right"), ("Settings", "Ctrl+,"), ("Main menu", "F10"),
                ("Move focus in order", "Tab / Shift+Tab"),
            ];
        var rows = new List<UIElement>();
        foreach (var (action, key) in entries)
        {
            var row = ui.Button(ui.PreferenceRow(action, null, ui.Key(key, 0.8), minHeight: 80), null, GmKind.Transparent, 1, radius: 0,
                padding: new Thickness(0), minHeight: 0);
            row.HorizontalAlignment = HorizontalAlignment.Stretch;
            row.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            ui.RowFocus(row);
            rows.Add(row);
        }
        return rows;
    }
    Button SettingToggle(string title, string description, Func<bool> get, Action<bool> set) =>
        Choice(title, description, ["on", "off"], ["On", "Off"], () => get() ? "on" : "off", value => set(value == "on"));

    void OpenInputGuide(string input)
    {
        ShowModal(input == "controller" ? "Controller buttons" : "Keyboard shortcuts", ui.Group(GuideRows(input)),
            [ui.Button("Close", CloseModal, GmKind.Card, .85)], CloseModal, 1000);
    }

    IReadOnlyList<SettingsGroup> SettingsGroups(string section)
    {
        if (section == "Overlay") return OverlayGroups();
        var modes = shell.Settings.RuntimeProvider == "feeder" ? new[] { "nr-only" }
            : shell.NrOnlyAvailable ? new[] { "nr-only", "mfg-only", "nr-mfg" } : new[] { "mfg-only", "nr-mfg" };
        return section switch
        {
            "Graphics" =>
            [
                new("Package", "Feature provider and default selection.",
                [
                    ui.RowButton("Provider", ProviderName(), () => _ = ShowPackagesAsync(), description: "Review curated packages. Restore original files before switching providers."),
                ]),
                new("Install defaults", "Applied to new installs; game changes are reviewed first.",
                [
                    Choice("Default mode", "Features selected when rtxForge starts.", modes, modes.Select(mode => mode switch { "nr-only" => "NR Only", "nr-mfg" => "NR + MFG", _ => "MFG Only" }).ToArray(),
                        () => shell.Settings.DefaultProfile, value => { shell.Settings.DefaultProfile = value; shell.Mode = value; }),
                    SettingToggle("Enable NR on launch", "Leave off to enable NR later from the overlay.", () => shell.Settings.NrOnLaunch, value => shell.Settings.NrOnLaunch = value),
                    SettingToggle("Update DLSS files", "Keep backups when updating older DLSS files.", () => shell.Settings.ManageDlssFiles, value => shell.Settings.ManageDlssFiles = value),
                    SettingToggle("4K borderless on install", "Use 3840 × 2160 borderless in supported games.", () => shell.Settings.Borderless4K, value => shell.Settings.Borderless4K = value),
                ]),
                new("Existing features", "Register compatible feature packages already installed.",
                [SettingToggle("Recognize existing features", "Allow updates to compatible installations from other tools.", () => shell.Settings.RecognizePrevious, value => shell.Settings.RecognizePrevious = value)]),
            ],
            "Appearance" =>
            [
                new("Theme and scale", null,
                [
                    Choice("Theme", "Night is the Game Mode default.", ["night", "dark", "light"], ["Night", "Dark", "Light"],
                        () => shell.Settings.Theme is "light" or "dark" ? shell.Settings.Theme : "night",
                        value => { shell.Settings.Theme = value; DispatcherQueue.TryEnqueue(ApplySettings); }),
                    Choice("UI scale", "Automatic uses a 130% reference at 4K and adapts to the window.", ["auto", "100", "125", "130", "150", "175", "200"],
                        ["Automatic", "100%", "125%", "130%", "150%", "175%", "200%"], () => shell.Settings.UiScaleKey,
                        value => { shell.Settings.UiScaleKey = value; DispatcherQueue.TryEnqueue(ApplySettings); }),
                ]),
                new("Navigation and labels", null,
                [
                    Choice("Navigation placement", null, ["top", "bottom"], ["Top", "Bottom"], () => shell.Settings.NavigationPosition, value => shell.Settings.NavigationPosition = value),
                    SettingToggle("Button glyphs", "Show icons beside action labels.", () => shell.Settings.ButtonGlyphs, value => shell.Settings.ButtonGlyphs = value),
                ]),
            ],
            "Library" =>
            [
                new("Library view", null,
                [
                    Choice("Library layout", null, ["posters", "capsules", "list"], ["Posters", "Wide Capsule", "List"], () => shell.Settings.LibraryView, value => shell.Settings.LibraryView = value),
                ]),
                new("Artwork and game information", null,
                [
                    SettingToggle("Download missing artwork", "Cached images stay available offline.", () => shell.Settings.OnlineArt, value => shell.Settings.OnlineArt = value),
                    SettingToggle("Download game information", "Descriptions, developers, and release dates from Steam.", () => shell.Settings.SteamMetadata, value => shell.Settings.SteamMetadata = value),
                    RefreshArtworkRow(),
                ]),
                new("Steam integration", null,
                [
                    .. SteamArtworkRows(),
                    ui.RowButton(SteamRowTitle(), null, () => _ = ToggleSteamAsync(), glyph: "").With(row => { Key(row, "steam-shortcut"); if (steamAdded is null) LoadSteamStatus(); }),
                ]),
            ],
            "Gaming Mode" =>
            [
                new("Interface", "Mouse, keyboard, and controller input keep your chosen interface.",
                [
                    Choice("Interface", null, ["game", "desktop"], ["Gaming Mode", "Desktop"], () => "game", value =>
                    { if (value == "desktop") DispatcherQueue.TryEnqueue(() => ExitRequested?.Invoke()); }),
                ]),
                new("Controller", null,
                [
                    Choice("Controller labels", "Match your controller family.", ["auto", "xbox", "playstation", "nintendo", "generic"],
                        ["Automatic", "Xbox", "PlayStation", "Nintendo", "Generic"], () => shell.Settings.ControllerGlyphs,
                        value => { shell.Settings.ControllerGlyphs = value; family = value == "auto" ? family : value; }),
                    Choice("Controller hints", null, ["always", "auto"], ["Always visible", "Hide when idle"], () => shell.Settings.ControllerHints, value => shell.Settings.ControllerHints = value),
                    ui.RowButton("Controller buttons", null, () => OpenInputGuide("controller")),
                    ui.RowButton("Keyboard shortcuts", null, () => OpenInputGuide("keyboard")),
                ]),
            ],
            "Recovery" => RecoveryGroups(),
            "System" =>
            [
                new("Hardware", null, shell.Hardware is { } hardware
                    ? [ui.PreferenceRow("Graphics card", null, ui.Text(hardware.Gpu, .8, t.Muted)), ui.PreferenceRow("Driver", null, ui.Text(hardware.Driver, .8, t.Muted))]
                    : [ui.P("Hardware information is unavailable.", .8)]),
            ],
            _ =>
            [
                new("App and updates", null,
                [
                    ui.RowButton("Check for updates", null, () => _ = CheckForUpdatesAsync(), description: $"rtxForge {MainWindow.AppVersion} · download, verify and install the newest build.", glyph: ""),
                ]),
            ],
        };
    }
}
