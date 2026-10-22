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
        var side = PageInset;
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
        head.Children.Add(ui.P("Your defaults for new installs. Review games to apply them to existing packages.", .78));
        page.Children.Add(head);
        var fields = new StackPanel { Spacing = t.Px(24), Padding = new Thickness(t.Px(4), t.Px(4), t.Px(4), t.Px(8)) };
        Action? refreshFooter = null;
        var (rows, value) = PresetRows(shell.Settings.Presets, legacy: shell.Settings.RuntimeProvider != "skynizz", changed: () => refreshFooter?.Invoke(),
            dynamicSupported: shell.Settings.DynamicMfgSupported);
        presetValue = value;
        foreach (var row in rows) fields.Children.Add(row);
        var scroll = new ScrollViewer { Content = fields, HorizontalScrollMode = ScrollMode.Disabled };
        Grid.SetRow(scroll, 1); page.Children.Add(scroll);
        // The desktop footer: Reset · Select games · Apply to all.
        var configured = shell.Games.Where(g => g.Installed && !g.Blocked).ToList();
        var caption = ui.P("", .72);
        caption.VerticalAlignment = VerticalAlignment.Center;
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(12), HorizontalAlignment = HorizontalAlignment.Right };
        var reset = ui.Button("Reset", () => Render(), GmKind.Card, .85).With(b => Key(b, "presets-discard"));
        ToolTipService.SetToolTip(reset, "Discard unsaved preset changes.");
        actions.Children.Add(reset);
        actions.Children.Add(ui.Button("Select games", () => ChoosePresetGames(configured), GmKind.Card, .85, enabled: configured.Count > 0)
            .With(b => Key(b, "presets-select")));
        actions.Children.Add(ui.Button("Apply to all", () =>
        {
            if (configured.Count == 0) { SavePresets(); Render(); Toast("Saved as your defaults for new installs"); return; }
            ApplyPresets(configured, () => { SavePresets(); Render(); });
        }, GmKind.Primary, .85).With(b => Key(b, "presets-apply")));
        refreshFooter = () =>
        {
            var dirty = !System.Text.Json.Nodes.JsonNode.DeepEquals(FeatureControlSchema.Resolve(value()), FeatureControlSchema.Resolve(shell.Settings.Presets));
            reset.IsEnabled = dirty;
            caption.Text = (dirty ? "Unsaved changes. " : "") + (configured.Count > 0
                ? $"Apply to all reviews {configured.Count} configured game{(configured.Count == 1 ? "" : "s")} and keeps these as your defaults."
                : "No games have features installed yet. Apply to all saves these as your defaults for new installs.");
        };
        refreshFooter();
        foreach (var action in actions.Children.OfType<Button>())
        {
            action.Width = t.Px(220);
            action.CornerRadius = new CornerRadius(t.Px(10));
            action.MinHeight = t.Px(48);
            GmUi.NoLift(action);
        }
        var footer = new Grid { ColumnSpacing = t.Px(12) };
        footer.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        footer.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        footer.Children.Add(caption); Grid.SetColumn(actions, 1); footer.Children.Add(actions);
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

    void ApplyPresets(List<Game> games, Action? completed = null)
    {
        if (presetValue is { } value) _ = RunOperationAsync("apply", games, value(), completed);
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
            review.Background = GmTheme.B(review.IsEnabled ? ui.Accent : t.Disabled);
            review.Foreground = GmTheme.B(review.IsEnabled ? ui.AccentInk : t.DisabledFg);
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

    Control? FocusedWithin(DependencyObject container)
    {
        if (XamlRoot is null) return null;
        var focused = Microsoft.UI.Xaml.Input.FocusManager.GetFocusedElement(XamlRoot) as Control;
        for (DependencyObject? node = focused; node is not null; node = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(node))
            if (ReferenceEquals(node, container)) return focused;
        return null;
    }

    void RestoreLayoutFocus(Control? control)
    {
        if (control is null) return;
        DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
        { if (control.XamlRoot is not null) control.Focus(FocusState.Keyboard); });
    }

    UIElement BuildSettings()
    {
        var side = PageInset;
        var grid = new Grid { ColumnSpacing = t.Px(24), Padding = new Thickness(side, t.Px(32), side, t.Px(8)), RowSpacing = t.Px(22) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(t.Px(ActualWidth <= 1050 ? 220 : 264)) });
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
            var button = ui.Button(ui.IconLabel(SettingsCategory.Glyph(section), section), () => { settingsSection = section; Render(); pendingFocusKey = "gm_set-" + section; },
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
        var definitions = SettingsGroups(settingsSection);
        var sections = new List<StackPanel>();
        foreach (var group in definitions)
        {
            var section = new StackPanel { Spacing = t.Px(12) };
            section.Children.Add(ui.H2(group.Title, .96));
            if (group.Description is not null) section.Children.Add(ui.P(group.Description, .75));
            var rows = new StackPanel { Spacing = t.Px(8) };
            foreach (var row in group.Rows)
            {
                if (row is Button button) { ui.StyleSettingsRow(button); rows.Children.Add(button); }
                else rows.Children.Add(new Border { Background = GmTheme.B(t.Panel), CornerRadius = new CornerRadius(t.Px(12)), Child = row });
            }
            section.Children.Add(rows); sections.Add(section);
        }
        var groups = new StackPanel { Spacing = t.Px(32), HorizontalAlignment = HorizontalAlignment.Stretch };
        foreach (var section in sections) groups.Children.Add(section);
        content.Children.Add(groups);
        var scroll = new ScrollViewer { Content = content, HorizontalScrollMode = ScrollMode.Disabled, Padding = new Thickness(0, 0, t.Px(12), 0) };
        Grid.SetRow(scroll, 1);
        Grid.SetColumn(scroll, 1);
        grid.Children.Add(scroll);
        return grid;
    }

    /// <summary>A choice row opens its options; opening or dismissing never changes the setting.</summary>
    Button Choice(string title, string? description, string[] keys, string[] captions, Func<string> get, Action<string> set, string? glyph = null)
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
        row = ui.RowButton(title, Caption(), () => OpenChoiceMenu(row!, title, captions, Math.Max(0, Array.IndexOf(keys, get())), Choose), description: description, glyph: glyph);
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
            var row = ui.Button(ui.PreferenceRow(action, null, view == "controller" ? ui.ControllerKey(family, GuideAction(action), .8) : ui.Key(key, .8), minHeight: 80), null, GmKind.Transparent, 1, radius: 0,
                padding: new Thickness(0), minHeight: 0);
            row.HorizontalAlignment = HorizontalAlignment.Stretch;
            row.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            ui.RowFocus(row);
            rows.Add(row);
        }
        return rows;
    }

    static string GuideAction(string label) => label switch
    {
        "Select" => "accept", "Back, or close a dialog" => "back", "Library" => "search",
        "Select games" => "select", "Switch pages" => "shoulders", "Adjust a value" => "adjust",
        "Settings" => "settings", "Main menu" => "menu", _ => "move",
    };
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
                new("Theme", null,
                [
                    Choice("Theme", "Night is the Game Mode default.", ["night", "dark", "light"], ["Night", "Dark", "Light"],
                        () => shell.Settings.Theme is "light" or "dark" ? shell.Settings.Theme : "night",
                        value => { shell.Settings.Theme = value; DispatcherQueue.TryEnqueue(ApplySettings); }),
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
                new("Layout and labels", null,
                [
                    Choice("Game Mode scale", "Automatic uses a 130% reference at 4K and adapts to the window.", ["auto", "100", "125", "130", "150", "175", "200"],
                        ["Automatic", "100%", "125%", "130%", "150%", "175%", "200%"], () => shell.Settings.UiScaleKey,
                        value => { shell.Settings.UiScaleKey = value; DispatcherQueue.TryEnqueue(ApplySettings); }),
                    Choice("Navigation placement", null, ["top", "bottom"], ["Top", "Bottom"], () => shell.Settings.NavigationPosition, value => shell.Settings.NavigationPosition = value),
                    SettingToggle("Button glyphs", "Show icons beside action labels.", () => shell.Settings.ButtonGlyphs, value => shell.Settings.ButtonGlyphs = value),
                ]),
                new("Controller", null,
                [
                    Choice("Controller labels", "Match your controller family.", ["auto", "xbox", "playstation", "nintendo", "steam", "generic"],
                        ["Automatic", "Xbox", "PlayStation", "Nintendo", "Steam Controller", "Generic"], () => shell.Settings.ControllerGlyphs,
                        value => { shell.Settings.ControllerGlyphs = value; family = value == "auto" ? detectedFamily : value; RenderFooter(); }),
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
