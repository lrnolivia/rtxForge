using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    string settingsSection = "Gaming Mode";
    Func<Tuning>? presetValue;

    // ---------- Presets (library presets) ----------

    UIElement BuildPresets()
    {
        // A wide column centered in the window: equal side margins computed from the
        // view width (alignment inside the ScrollViewer drifted right), never less
        // than the Library / Settings page margin.
        var column = Math.Min(t.Px(1600), Math.Max(0, ActualWidth - t.Px(56) * 2));
        var side = Math.Max(t.Px(56), (ActualWidth - column) / 2);
        var page = new StackPanel
        {
            Spacing = t.Px(24), HorizontalAlignment = HorizontalAlignment.Stretch,
            Padding = new Thickness(side, t.Px(32), side, t.Px(24)),
        };
        var head = new StackPanel { Spacing = t.Px(10) };
        head.Children.Add(ui.H1("Library presets"));
        head.Children.Add(ui.P("Apply to your configured games. Unmanaged games are skipped."));
        page.Children.Add(head);
        var (rows, value) = PresetRows(shell.Settings.Presets);
        presetValue = value;
        page.Children.Add(ui.Group(rows));
        page.Children.Add(new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(12) }.With(note =>
        {
            note.Children.Add(ui.Icon("", 0.8, t.Muted));
            note.Children.Add(ui.P("Saved settings take effect on the next game launch. They do not verify the rendered effect.", 0.83));
        }));
        var configured = shell.Games.Where(g => g.Installed && !g.Blocked).ToList();
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(16) };
        actions.Children.Add(ui.Button($"Apply to all configured games ({configured.Count})", () => ApplyPresets(configured), GmKind.Primary, 0.85,
            enabled: configured.Count > 0).With(b => Key(b, "presets-apply")));
        actions.Children.Add(ui.Button("Select games to apply", () =>
        {
            SavePresets();
            selecting = true;
            selectedIds.Clear();
            Open("library");
            Toast("Select games, then Install selected or use Presets › Apply.");
        }, GmKind.Card, 0.85, enabled: configured.Count > 0));
        actions.Children.Add(ui.Button("Reset Presets", () => Render(), GmKind.Card, 0.85));
        page.Children.Add(actions);
        return new ScrollViewer { Content = page, HorizontalScrollMode = ScrollMode.Disabled };
    }

    void SavePresets()
    {
        if (presetValue is null) return;
        var v = presetValue();
        shell.Settings.NrStrength = v.NrStrength;
        shell.Settings.SharpeningStrength = v.SharpeningStrength;
        shell.Settings.MfgMultiplier = v.MfgMultiplier;
        shell.Settings.Save();
    }

    void ApplyPresets(List<Game> games)
    {
        SavePresets();
        _ = RunOperationAsync("apply", games, shell.Settings.Presets);
    }

    // ---------- Settings (the same preferences, sized for the couch) ----------

    static readonly string[] SettingsSections = ["Gaming Mode", "Appearance", "Library", "Controller", "Keyboard", "System"];

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
            Key(button, "set-" + section);
            if (active && initialFocus is null) initialFocus = button;
            nav.Children.Add(button);
        }
        Grid.SetRow(nav, 1);
        grid.Children.Add(nav);

        var content = new StackPanel { Spacing = t.Px(24) };
        var (description, rows) = SettingsRows(settingsSection);
        var title = new StackPanel { Spacing = t.Px(10) };
        title.Children.Add(ui.H2(settingsSection));
        title.Children.Add(ui.P(description));
        content.Children.Add(title);
        content.Children.Add(ui.Group(rows));
        if (settingsSection == "Controller")
        {
            // Options above; the button guide in its own group.
            content.Children.Add(ui.H2("Buttons", 1.06).With(h => h.Margin = new Thickness(0, t.Px(12), 0, 0)));
            content.Children.Add(ui.Group(GuideRows("controller")));
        }
        content.Children.Add(new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(12) }.With(note =>
        {
            note.Children.Add(ui.Icon("", 0.8, t.Muted));
            note.Children.Add(ui.P("Mouse or keyboard input keeps your chosen interface.", 0.83));
        }));
        var scroll = new ScrollViewer { Content = content, HorizontalScrollMode = ScrollMode.Disabled, Padding = new Thickness(0, 0, t.Px(12), 0) };
        Grid.SetRow(scroll, 1);
        Grid.SetColumn(scroll, 1);
        grid.Children.Add(scroll);
        return grid;
    }

    /// <summary>A choice row: Select cycles forward, Left/Right step through the choices.</summary>
    Button Choice(string title, string? description, string[] keys, string[] captions, Func<string> get, Action<string> set)
    {
        string Caption() => captions[Math.Max(0, Array.IndexOf(keys, get()))];
        void Step(int d)
        {
            var i = (Math.Max(0, Array.IndexOf(keys, get())) + d + keys.Length) % keys.Length;
            set(keys[i]);
            shell.SaveSettings();
            Render(keepFocus: true);
        }
        var row = ui.RowButton(title, Caption(), () => Step(1), description: description);
        row.Tag = new Adjustable(Step);
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
    (string Description, List<UIElement> Rows) SettingsRows(string section) => section switch
    {
        "Appearance" => ("Shared desktop appearance. Gaming Mode keeps a clear focus ring.",
        [
            Choice("Theme", "Night is the Game Mode default.", ["night", "dark", "light"], ["Night", "Dark", "Light"],
                () => shell.Settings.Theme is "light" or "dark" ? shell.Settings.Theme : "night",
                v => { shell.Settings.Theme = v; DispatcherQueue.TryEnqueue(ApplySettings); }),
            Choice("Button glyphs", "Icons beside action labels; selection and package identity stay visible.", ["on", "off"], ["On", "Off"],
                () => shell.Settings.ButtonGlyphs ? "on" : "off", v => shell.Settings.ButtonGlyphs = v == "on"),
        ]),
        "Library" => ("Manage the library layout and artwork sources.",
        [
            Choice("Library layout", null, ["posters", "capsules", "list"], ["Posters", "Wide Capsule", "List"],
                () => shell.Settings.LibraryView, v => shell.Settings.LibraryView = v),
            ui.RowButton("Connect SteamGridDB", null, () => Toast("Connect SteamGridDB in Desktop UI with a keyboard.")),
            ui.RowButton("Steam artwork profile", null, () => Toast("Choose the Steam artwork profile in Desktop UI.")),
        ]),
        "Controller" => ("Keep button labels and hints consistent with your controller.",
        [
            Choice("Button labels", "Match your controller family.", ["auto", "xbox", "playstation", "nintendo", "generic"],
                ["Automatic", "Xbox", "PlayStation", "Nintendo", "Generic"], () => shell.Settings.ControllerGlyphs,
                v => { shell.Settings.ControllerGlyphs = v; family = v == "auto" ? family : v; }),
            Choice("Controller hints", null, ["always", "auto"], ["Always visible", "Hide when idle"],
                () => shell.Settings.ControllerHints, v => shell.Settings.ControllerHints = v),
        ]),
        "Keyboard" => ("Every keyboard shortcut in Gaming Mode.", GuideRows("keyboard")),
        "System" => ("Adjust display scaling and navigation placement.",
        [
            Choice("UI scale", "Automatic follows the window size (150% at 4K).", ["auto", "100", "125", "150", "175", "200"],
                ["Automatic", "100%", "125%", "150%", "175%", "200%"], () => shell.Settings.UiScaleKey,
                v => { shell.Settings.UiScaleKey = v; DispatcherQueue.TryEnqueue(ApplySettings); }),
            Choice("Navigation", null, ["top", "bottom"], ["Top", "Bottom"], () => shell.Settings.NavigationPosition, v => shell.Settings.NavigationPosition = v),
        ]),
        _ => ("Open rtxForge from your existing gaming environment.",
        [
            Choice("Interface", null, ["game", "desktop"], ["Gaming Mode", "Desktop"], () => "game", v =>
            {
                if (v == "desktop") DispatcherQueue.TryEnqueue(() => ExitRequested?.Invoke());
            }),
            ui.RowButton(SteamRowTitle(), null, () => _ = ToggleSteamAsync(), glyph: "").With(row => { Key(row, "steam-shortcut"); if (steamAdded is null) LoadSteamStatus(); }),
        ]),
    };
}
