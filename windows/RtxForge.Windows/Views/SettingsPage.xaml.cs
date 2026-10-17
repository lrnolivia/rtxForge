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
    static readonly string[] ProviderKeys = ["y4my", "dlss-unlocked", "custom", "skynizz"];
    static readonly string[] Modes = ["nr-only", "mfg-only", "nr-mfg"];
    static readonly string[] Views = ["posters", "capsules", "list"];

    readonly MainWindow shell = App.Main!;
    readonly Dictionary<string, PreferencesGroup[]> sections = [];
    static string selectedSection = "Graphics";
    ForgeSettings Settings => shell.Settings;

    public SettingsPage()
    {
        InitializeComponent();
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
        PageHost.Children.Clear();
        foreach (var group in groups) PageHost.Children.Add(group.Root);
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
        var graphics = new PreferencesGroup(null, "Restore original files before switching providers.");
        var (row, provider) = Prefs.ComboRow("Provider", "Package that supplies NR and MFG.",
            ["y4my Multipass", "DLSS-Unlocked", "Custom package", "Skynizz DLSS 5 NR (NR Only)"], Math.Max(0, Array.IndexOf(ProviderKeys, Settings.RuntimeProvider)), "");
        graphics.Add(row);
        (row, var nrPath) = Prefs.EntryRow("Local NR model DLL", "Compatible nvngx_dlssnr.dll. Required for Skynizz unless a suitable model is already beside the game executable.",
            Settings.NrRuntime, @"C:\path\to\nvngx_dlssnr.dll", "");
        nrPath.LostFocus += (_, _) => { Settings.NrRuntime = nrPath.Text.Trim(); Save(); };
        graphics.Add(row);

        (row, var manageFiles) = Prefs.SwitchRow("DLSS Files", "Update older DLSS files when installing features. Backups are kept for restoration.",
            Settings.ManageDlssFiles, "");
        manageFiles.Toggled += (_, _) => { Settings.ManageDlssFiles = manageFiles.IsOn; Save(); };
        graphics.Add(row);
        (row, var profile) = Prefs.ComboRow("Default Mode", "Features selected when rtxForge starts.",
            ["NR Only", "MFG Only", "NR + MFG"], Math.Max(0, Array.IndexOf(Modes, Settings.DefaultProfile)), "");
        graphics.Add(row);
        (row, var adopt) = Prefs.SwitchRow("Recognize Existing Features", "Allow updates to compatible installations from other tools.",
            Settings.RecognizePrevious, "");
        adopt.Toggled += (_, _) => { Settings.RecognizePrevious = adopt.IsOn; Save(); };
        graphics.Add(row);

        void ValidateProvider()
        {
            var selectedProvider = ProviderKeys[Math.Max(0, provider.SelectedIndex)];
            var selectedMode = Modes[Math.Max(0, profile.SelectedIndex)];
            if (selectedProvider == "skynizz" && selectedMode != "nr-only")
            {
                profile.SelectedIndex = Array.IndexOf(Modes, "nr-only");
                Notice.Title = "Skynizz currently supports NR Only.";
                Notice.Message = "Its composition with rtxForge MFG is not verified.";
                Notice.IsOpen = true;
                selectedMode = "nr-only";
            }
            if (selectedProvider == "y4my" && selectedMode == "nr-only")
            {
                profile.SelectedIndex = Array.IndexOf(Modes, "mfg-only");
                Notice.Title = "NR Only requires DLSS-Unlocked.";
                Notice.Message = "Default Mode was changed to MFG Only.";
                Notice.IsOpen = true;
                selectedMode = "mfg-only";
            }
            var providerChanged = Settings.RuntimeProvider != selectedProvider;
            Settings.RuntimeProvider = selectedProvider;
            Settings.DefaultProfile = selectedMode;
            shell.Mode = selectedMode;
            shell.SaveSettings();
            if (providerChanged) _ = shell.ScanAsync();
        }
        provider.SelectionChanged += (_, _) => ValidateProvider();
        profile.SelectionChanged += (_, _) => ValidateProvider();

        // ----- Appearance -----
        var appearance = new PreferencesGroup(null);
        (row, var theme) = Prefs.ComboRow("App theme", "Changes only rtxForge.", ThemeController.Captions,
            Math.Max(0, Array.IndexOf(ThemeController.Keys, Settings.Theme)), "");
        theme.SelectionChanged += (_, _) => { Settings.Theme = ThemeController.Keys[theme.SelectedIndex]; Save(); };
        appearance.Add(row);
        (row, var layout) = Prefs.ComboRow("Library layout", "Choose how your game collection is displayed.",
            ["Poster", "Wide Capsule", "List"], Math.Max(0, Array.IndexOf(Views, Settings.LibraryView)), "");
        layout.SelectionChanged += (_, _) => { Settings.LibraryView = Views[layout.SelectedIndex]; Save(); };
        appearance.Add(row);
        (row, var compact) = Prefs.SwitchRow("Compact header", "Keep more room for your games.",
            Settings.CompactHeader, "");
        compact.Toggled += (_, _) => { Settings.CompactHeader = compact.IsOn; Save(); };
        appearance.Add(row);

        // ----- Library -----
        var library = new PreferencesGroup(null, "Your Steam poster, capsule, and hero images take priority.");
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
            library.Add(Prefs.Row(title, subtitle, Prefs.ActionButton(caption, async (_, _) => await action()), glyph));

        // ----- Gaming Mode (Linux: Steam Library · Interface · Controller) -----
        var gamingMode = new PreferencesGroup(null, "Use rtxForge from Steam, or switch between Desktop and Big Picture UI.");
        var steamLibrary = new PreferencesGroup("Steam Library");
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
            ("UI Scale", ["auto", "100", "125", "150", "175", "200"], ["Automatic (150% at 4K)", "100%", "125%", "150%", "175%", "200%"],
                () => Settings.UiScaleKey, v => Settings.UiScaleKey = v, ""),
            ("Navigation Position", ["top", "bottom"], ["Top", "Bottom"],
                () => Settings.NavigationPosition, v => Settings.NavigationPosition = v, ""),
        })
        {
            (row, var choice) = Prefs.ComboRow(title, null, captions, Math.Max(0, Array.IndexOf(keys, get())), glyph);
            choice.SelectionChanged += (_, _) => { set(keys[choice.SelectedIndex]); Save(); };
            interfaceGroup.Add(row);
        }

        var controller = new PreferencesGroup("Controller", "Button labels and navigation prompts.");
        foreach (var (title, keys, captions, get, set, glyph) in new (string, string[], string[], Func<string>, Action<string>, string)[]
        {
            ("Controller Labels", ["auto", "xbox", "playstation", "nintendo", "generic"], ["Automatic", "Xbox", "PlayStation", "Nintendo", "Generic"],
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
        var system = new PreferencesGroup(null);
        if (shell.Hardware is { } hardware)
            foreach (var (title, value, glyph) in new[]
            {
                ("Graphics card", hardware.Gpu, ""), ("Driver", hardware.Driver, ""), ("Video memory", hardware.Vram, ""),
                ("Processor", hardware.Cpu, ""), ("Architecture", hardware.Architecture, ""),
            })
                if (!string.IsNullOrEmpty(value)) system.Add(Prefs.Row(title, value, glyph: glyph));
        system.Add(Prefs.Row("Compatibility", shell.Hardware?.Reason ?? "Not checked", glyph: ""));

        // ----- Recovery -----
        var recovery = new PreferencesGroup(null);
        foreach (var (title, subtitle, caption, glyph, action) in new (string, string, string, string, Func<Task>)[]
        {
            ("Previous changes", "Browse available recovery records.", "Browse", "", shell.ShowPreviousChangesAsync),
            ("Old NR files", "Review legacy files before removal.", "Review", "", shell.ReviewOldNrFilesAsync),
            ("Library reports", "View test notes and export a support report.", "Open", "", shell.ShowReportsAsync),
        })
            recovery.Add(Prefs.Row(title, subtitle, Prefs.ActionButton(caption, async (_, _) => await action()), glyph));

        // ----- About (Linux: Application group + About dialog) -----
        var about = new PreferencesGroup(null);
        about.Add(Prefs.Row("rtxForge", $"Version {MainWindow.AppVersion} · Built for Windows with WinUI 3", glyph: ""));
        about.Add(Prefs.Row("Updates", "Download, verify, and install the newest rtxForge build.",
            Prefs.ActionButton("Check for updates", async (_, _) => await shell.CheckForUpdatesAsync()), ""));

        // Linux organize_pages(): one page per section. Windows shows them as SelectorBar tabs.
        sections["Graphics"] = [graphics];
        sections["Appearance"] = [appearance];
        sections["Library"] = [library];
        sections["Gaming Mode"] = [gamingMode, steamLibrary, interfaceGroup, controller];
        sections["System"] = [system];
        sections["Recovery"] = [recovery];
        sections["About"] = [about];
        foreach (var name in sections.Keys)
            Sections.Items.Add(new SelectorBarItem { Text = name, Tag = name });
        Sections.SelectedItem = Sections.Items.FirstOrDefault(i => (string)i.Tag == selectedSection) ?? Sections.Items[0];
    }
}
