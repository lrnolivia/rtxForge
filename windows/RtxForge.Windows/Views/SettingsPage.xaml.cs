using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Views;

/// <summary>
/// Settings, section for section with show_settings() in gui/rtxforge_gtk.py,
/// applied immediately as Windows settings pages do.
/// </summary>
public sealed partial class SettingsPage : Page
{
    // The package for games with DLSS; games without DLSS use Feeder automatically.
    static readonly string[] Modes = ["nr-only", "mfg-only", "nr-mfg"];
    static readonly string[] Views = ["posters", "capsules", "list"];

    readonly MainWindow shell = App.Main!;
    readonly Dictionary<string, PreferencesGroup[]> sections = [];
    static string selectedSection = "Graphics";
    public static bool OpenOverlaySection { get; set; }
    ForgeSettings Settings => shell.Settings;

    public SettingsPage()
    {
        InitializeComponent();
        if (OpenOverlaySection) { selectedSection = "Overlay"; OpenOverlaySection = false; }
        Build();
    }

    void OnPageSizeChanged(object sender, SizeChangedEventArgs e)
    {
        Body.Padding = PageMargins.For(e.NewSize.Width);
    }

    void OnSectionChanged(SelectorBar sender, SelectorBarSelectionChangedEventArgs args)
    {
        if (sender.SelectedItem?.Tag is not string name || !sections.TryGetValue(name, out var groups)) return;
        selectedSection = name;
        if (PageHost.Children.FirstOrDefault() is PresetColumns previous) previous.Children.Clear();
        PageHost.Children.Clear();
        var cards = new PresetColumns(680, 2) { ColumnSpacing = 24, RowSpacing = 24 };
        foreach (var group in groups) cards.Children.Add(group.Root);
        PageHost.Children.Add(cards);
    }

    /// <summary>The title line of a settings card built by Prefs.Row.</summary>
    static TextBlock? FindTitle(Border row) =>
        (row.Child as Grid)?.Children.OfType<StackPanel>().FirstOrDefault()?.Children.OfType<TextBlock>().FirstOrDefault();

    void Save()
    {
        Notice.IsOpen = false;
        shell.SaveSettings();
    }

    void Build()
    {
        // ----- Graphics -----
        // Packages chooses the package and its files; Extras holds the library-wide tools.
        var installDefaults = new PreferencesGroup("Install defaults", "Changes to game files are reviewed before applying.");
        var (row, manageFiles) = Prefs.SwitchRow("DLSS Files", "Update older DLSS files when installing features. Backups are kept for restoration.",
            Settings.ManageDlssFiles, "");
        manageFiles.Toggled += (_, _) => { Settings.ManageDlssFiles = manageFiles.IsOn; Save(); };
        installDefaults.Add(row);
        (row, var profile) = Prefs.ComboRow("Default Mode", "Features selected when rtxForge starts.",
            ["NR Only", "MFG Only", "NR + MFG"], Math.Max(0, Array.IndexOf(Modes, Settings.DefaultProfile)), "");
        installDefaults.Add(row);
        (row, var startupNr) = Prefs.SwitchRow("Enable NR on launch", "Default for new and clean installs. Leave off to enable NR later from the overlay.", Settings.NrOnLaunch, "");
        startupNr.Toggled += (_, _) => { Settings.NrOnLaunch = startupNr.IsOn; Save(); };
        installDefaults.Add(row);
        var existingFeatures = new PreferencesGroup("Existing features", "Register compatible feature packages already installed.");
        (row, var adopt) = Prefs.SwitchRow("Recognize Existing Features", "Allow updates to compatible installations from other tools.",
            Settings.RecognizePrevious, "");
        adopt.Toggled += (_, _) => { Settings.RecognizePrevious = adopt.IsOn; Save(); };
        existingFeatures.Add(row);

        void ValidateMode()
        {
            var selectedMode = Modes[Math.Max(0, profile.SelectedIndex)];
            if (Settings.RuntimeProvider == "feeder" && selectedMode != "nr-only")
            {
                profile.SelectedIndex = Array.IndexOf(Modes, "nr-only");
                selectedMode = "nr-only";
                Notice.Title = "Feeder provides NR Only.";
                Notice.Message = "Frame generation is unavailable for this route.";
                Notice.IsOpen = true;
            }
            Settings.DefaultProfile = selectedMode;
            shell.Mode = selectedMode;
            shell.SaveSettings();
        }
        profile.SelectionChanged += (_, _) => ValidateMode();

        // ----- Appearance -----
        (row, var borderless) = Prefs.SwitchRow("4K borderless on install", "Use 3840 × 2160 borderless in supported games. Review shows each change; Restore preserves later preferences.", Settings.Borderless4K, "");
        borderless.Toggled += (_, _) => { Settings.Borderless4K = borderless.IsOn; Save(); };
        installDefaults.Add(row);

        var overlay = new OverlayPreferencesView(fresh =>
        {
            Settings.CopyOverlayFrom(fresh);
            shell.ConfigureCompanionShortcut();
        }, shell.Service as EngineForgeService, groupCards: true);

        var appearance = new PreferencesGroup("Theme");
        var navigation = new PreferencesGroup("Navigation");
        var details = new PreferencesGroup("Game Details", "Choose how Game Details opens in Desktop Mode.");
        (row, var detailsWindow) = Prefs.ComboRow("Open Game Details", "Use tabs in the app, or a sidebar in a separate window.",
            ["In the app", "In a separate window"], Settings.SeparateGameDetails ? 1 : 0, "\uE8A7");
        detailsWindow.SelectionChanged += (_, _) => { Settings.SeparateGameDetails = detailsWindow.SelectedIndex == 1; Save(); };
        details.Add(row);
        var libraryView = new PreferencesGroup("Library view");
        (row, var theme) = Prefs.ComboRow("Color theme", "Changes only rtxForge.", ThemeController.Captions,
            Math.Max(0, Array.IndexOf(ThemeController.Keys, Settings.Theme)), "");
        theme.SelectionChanged += (_, _) => { Settings.Theme = ThemeController.Keys[theme.SelectedIndex]; Save(); };
        appearance.Add(row);
        (row, var linkedTheme) = Prefs.SwitchRow("Use the same color theme in Desktop and Game Mode", "Turn off to choose each interface’s theme separately.", Settings.GameModeThemeLinked, "");
        linkedTheme.Toggled += (_, _) => { Settings.LinkGameModeTheme(linkedTheme.IsOn); Save(); };
        appearance.Add(row);
        var cardOpacity = new Slider { Minimum = 0, Maximum = 100, StepFrequency = 1, SmallChange = 1, LargeChange = 5,
            Value = Settings.GameModeCardOpacity, IsThumbToolTipEnabled = false, MinWidth = 200 };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(cardOpacity, "Game Mode card translucency");
        var opacityEnds = new Grid();
        opacityEnds.Children.Add(Prefs.Label("Clearer"));
        var moreSolid = Prefs.Label("More solid"); moreSolid.HorizontalAlignment = HorizontalAlignment.Right;
        opacityEnds.Children.Add(moreSolid);
        var opacityControls = new StackPanel { Spacing = 4 };
        opacityControls.Children.Add(cardOpacity); opacityControls.Children.Add(opacityEnds);
        appearance.Add(Prefs.Row("Game Mode card translucency", "Frosted cards with blur.", opacityControls, "\uE790"));
        cardOpacity.ValueChanged += (_, e) =>
        {
            Settings.GameModeCardOpacity = (int)Math.Round(e.NewValue);
            Save();
        };
        (row, var layout) = Prefs.ComboRow("Library layout", "Choose how your game collection is displayed.",
            ["Poster", "Wide Capsule", "List"], Math.Max(0, Array.IndexOf(Views, Settings.LibraryView)), "");
        layout.SelectionChanged += (_, _) => { Settings.LibraryView = Views[layout.SelectedIndex]; Save(); };
        libraryView.Add(row);
        (row, var compact) = Prefs.SwitchRow("Compact header", "Keep more room for your games.",
            Settings.CompactHeader, "");
        compact.Toggled += (_, _) => { Settings.CompactHeader = compact.IsOn; Save(); };
        navigation.Add(row);

        // ----- Library -----
        var library = new PreferencesGroup("Artwork and game information", "Your Steam poster, capsule, and hero images take priority.");
        var steamLibrary = new PreferencesGroup("Steam integration");
        (row, var onlineArt) = Prefs.SwitchRow("Download missing artwork", "Use SteamGridDB and Steam when local images are unavailable.",
            Settings.OnlineArt, "");
        onlineArt.Toggled += (_, _) => { Settings.OnlineArt = onlineArt.IsOn; Save(); };
        library.Add(row);
        (row, var metadata) = Prefs.SwitchRow("Download game information", "Descriptions, developers, and release dates from Steam.",
            Settings.SteamMetadata, "");
        metadata.Toggled += (_, _) => { Settings.SteamMetadata = metadata.IsOn; Save(); };
        library.Add(row);
        var timeout = new NumberBox
        {
            Minimum = 5, Maximum = 30, SmallChange = 1, Value = Settings.NetworkTimeout,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline,
        };
        timeout.ValueChanged += (_, e) => { if (!double.IsNaN(e.NewValue)) { Settings.NetworkTimeout = (int)e.NewValue; Save(); } };
        library.Add(Prefs.Row("Download timeout", "Seconds per request", timeout, ""));
        foreach (var (title, subtitle, caption, glyph, action) in new (string, string, string, string, Func<Task>)[]
        {
            ("Refresh artwork", "Cached images remain available offline.", "Refresh", "", () => shell.RefreshArtworkAsync(true)),
            ("Steam artwork profile", "Choose which local Steam account receives artwork.", "Choose", "", shell.ChooseSteamArtworkProfileAsync),
            ("Sync artwork to Steam", "Review and sync artwork for your library.", "Sync", "", shell.SyncLibraryArtworkAsync),
            ("SteamGridDB", "Connect your account to browse custom artwork.", "Connect", "", async () => await shell.ConnectSteamGridAsync()),
        })
        {
            var artworkRow = Prefs.Row(title, subtitle, Prefs.ActionButton(caption, async (_, _) => await action()), glyph);
            if (title == "Refresh artwork") library.Add(artworkRow); else steamLibrary.Add(artworkRow);
        }

        // ----- Gaming Mode (Linux: Steam Library · Interface · Controller) -----
        var steamButton = Prefs.ActionButton("Add to Steam", async (_, _) => await shell.ToggleSteamShortcutAsync());
        var steamRow = Prefs.Row("Add rtxForge to Steam", "Manage this app’s shortcut in your selected Steam profile.", steamButton, "");
        steamLibrary.Add(steamRow);
        async void RefreshSteamRow()
        {
            var added = await shell.SteamShortcutAddedAsync();
            steamButton.Content = Prefs.Content(added ? "Manage" : "Add to Steam", null);
            if (FindTitle(steamRow) is { } title) title.Text = added ? "rtxForge is in Steam" : "Add rtxForge to Steam";
        }
        shell.SteamShortcutChanged += RefreshSteamRow;
        Unloaded += (_, _) => shell.SteamShortcutChanged -= RefreshSteamRow;
        RefreshSteamRow();

        var gameModeLayout = new PreferencesGroup("Layout and labels");
        var interfaceGroup = new PreferencesGroup("Interface", "Choose the experience for Gaming Mode.");
        (row, var bigPicture) = Prefs.ComboRow("Interface", "Choose Desktop or Big Picture UI. Keyboard, mouse and controller input keep your choice.",
            ["Desktop", "Big Picture UI"], Settings.BigPictureUi ? 1 : 0, "");
        bigPicture.SelectionChanged += (_, _) =>
        {
            Settings.BigPictureUi = bigPicture.SelectedIndex == 1;
            Save();
            if (Settings.BigPictureUi) shell.ShowToast("Big Picture UI opens when you use a controller.");
        };
        interfaceGroup.Add(row);
        foreach (var (title, keys, captions, get, set, glyph) in new (string, string[], string[], Func<string>, Action<string>, string)[]
        {
            ("Game Mode scale", ["auto", "100", "125", "130", "150", "175", "200"], ["Automatic (130% at 4K)", "100%", "125%", "130%", "150%", "175%", "200%"],
                () => Settings.UiScaleKey, v => Settings.UiScaleKey = v, ""),
            ("Navigation Position", ["top", "bottom"], ["Top", "Bottom"],
                () => Settings.NavigationPosition, v => Settings.NavigationPosition = v, ""),
        })
        {
            (row, var choice) = Prefs.ComboRow(title, null, captions, Math.Max(0, Array.IndexOf(keys, get())), glyph);
            choice.SelectionChanged += (_, _) => { set(keys[choice.SelectedIndex]); Save(); };
            gameModeLayout.Add(row);
        }
        (row, var glyphs) = Prefs.SwitchRow("Button glyphs", "Show icons beside action labels.", Settings.ButtonGlyphs, "");
        glyphs.Toggled += (_, _) => { Settings.ButtonGlyphs = glyphs.IsOn; Save(); };
        gameModeLayout.Add(row);

        var controller = new PreferencesGroup("Controller", "Button labels and navigation prompts.");
        foreach (var (title, keys, captions, get, set, glyph) in new (string, string[], string[], Func<string>, Action<string>, string)[]
        {
            ("Controller Labels", ["auto", "xbox", "playstation", "nintendo", "steam", "generic"], ["Automatic", "Xbox", "PlayStation", "Nintendo", "Steam Controller", "Generic"],
                () => Settings.ControllerGlyphs, v => Settings.ControllerGlyphs = v, ""),
            ("Controller Hints", ["always", "auto"], ["Always visible", "Hide when idle"],
                () => Settings.ControllerHints, v => Settings.ControllerHints = v, ""),
        })
        {
            (row, var choice) = Prefs.ComboRow(title, null, captions, Math.Max(0, Array.IndexOf(keys, get())), glyph);
            choice.SelectionChanged += (_, _) => { set(keys[choice.SelectedIndex]); Save(); };
            controller.Add(row);
        }
        controller.Add(Prefs.Row("Controller Navigation",
            "D-pad / stick: focus · A: activate · B: back · Y: library · Menu: menu · View: settings · Bumpers: tab", glyph: ""));

        // ----- System -----
        var system = new PreferencesGroup("Hardware");
        if (shell.Hardware is { } hardware)
            foreach (var (title, value, glyph) in new[]
            {
                ("Graphics card", hardware.Gpu, ""), ("Driver", hardware.Driver, ""), ("Video memory", hardware.Vram, ""),
                ("Processor", hardware.Cpu, ""), ("Architecture", hardware.Architecture, ""),
            })
                if (!string.IsNullOrEmpty(value)) system.Add(Prefs.Row(title, value, glyph: glyph));
        system.Add(Prefs.Row("Compatibility", shell.Hardware?.Reason ?? "Not checked", glyph: ""));

        // ----- Recovery -----
        var cleanup = new PreferencesGroup("Cleanup");
        var reports = new PreferencesGroup("Reports");
        foreach (var (title, subtitle, caption, glyph, action) in new (string, string, string, string, Func<Task>)[]
        {
            ("Old NR files", "Review legacy files before removal.", "Review", "", shell.ReviewOldNrFilesAsync),
            ("Compatibility & reports", "See each game's result, try unverified games, share a result, or export a support report.", "Open", "", shell.ShowReportsAsync),
        })
        {
            var actionRow = Prefs.Row(title, subtitle, Prefs.ActionButton(caption, async (_, _) => await action()), glyph);
            (title == "Old NR files" ? cleanup : reports).Add(actionRow);
        }

        // ----- About (Linux: Application group + About dialog) -----
        var about = new PreferencesGroup("App and updates");
        about.Add(Prefs.Row("rtxForge", $"Version {MainWindow.AppVersion} · Built for Windows with WinUI 3", glyph: ""));
        about.Add(Prefs.Row("Updates", "Download, verify, and install the newest rtxForge build.",
            Prefs.ActionButton("Check for updates", async (_, _) => await shell.CheckForUpdatesAsync()), ""));

        // Linux organize_pages(): one page per section. Windows shows them as SelectorBar tabs.
        sections["Graphics"] = [installDefaults, existingFeatures];
        sections["Overlay"] = overlay.Groups.ToArray();
        sections["Appearance"] = [appearance, navigation, details];
        sections["Library"] = [libraryView, library, steamLibrary, reports];
        sections["Gaming Mode"] = [interfaceGroup, gameModeLayout, controller];
        sections["System"] = [system];
        sections["Recovery"] = [cleanup];
        sections["About"] = [about];
        foreach (var name in sections.Keys)
            Sections.Items.Add(new SelectorBarItem { Text = name, Tag = name });
        Sections.SelectedItem = Sections.Items.FirstOrDefault(i => (string)i.Tag == selectedSection) ?? Sections.Items[0];
    }
}
