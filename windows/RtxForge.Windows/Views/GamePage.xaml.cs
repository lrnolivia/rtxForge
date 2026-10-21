using System.Diagnostics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Navigation;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using Windows.ApplicationModel.DataTransfer;

namespace RtxForge.Windows.Views;

public sealed partial class GamePage : Page
{
    readonly MainWindow shell = App.Main!;
    Game game = null!;
    string section = "Overview";
    bool narrow;
    Services.AccentPalette? gamePalette;

    public GamePage()
    {
        InitializeComponent();
        ActualThemeChanged += (_, _) => ApplyAccentText();
        shell.GamesChanged += Refresh;
        Unloaded += (_, _) => shell.GamesChanged -= Refresh;
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        var request = (GameRequest)e.Parameter;
        game = request.Game;
        TitleText.Text = game.Name;
        ShowIdentity();
        _ = LoadSteamInfoAsync(game);
        HeroImage.SetSource(game.HeroPath ?? game.CapsulePath);
        PosterImage.Source = ViewModels.GameItem.Image(game.PosterPath);
        PosterFrame.Visibility = game.PosterPath is null ? Visibility.Collapsed : Visibility.Visible;
        ApplyLayout(ActualWidth);
        _ = ApplyAccentAsync();
        Sections.SelectedItem = Sections.Items.First(i => (string)i.Tag == request.Section);
        Refresh();
    }

    /// <summary>
    /// The game's artwork accent (Linux .art-* classes): banner title, poster
    /// ring, and this page's accent surfaces (primary buttons, sliders, tabs, toggles).
    /// </summary>
    async Task ApplyAccentAsync()
    {
        var current = game;
        var palette = await Services.ArtAccent.ForGameAsync(current);
        if (palette is null || current != game) return;

        // .{art} .game-banner-title / .progress-poster-frame
        gamePalette = palette;
        ApplyAccentText();
        PosterFrame.BorderBrush = palette.AccentBrush;
        PosterFrame.BorderThickness = new Thickness(2);

        // .{art} button.suggested-action, toggle:checked, scale highlight, progressbar,
        // .game-detail-nav row:selected (alpha 0.10 fill, nav_accent label)
        var accent = palette.AccentBrush;
        var hover = palette.Brush(palette.Color, 0.9);
        var pressed = palette.Brush(palette.Color, 0.8);
        var accentFg = palette.Brush(palette.AccentFg);
        foreach (var (key, brush) in new (string, Microsoft.UI.Xaml.Media.Brush)[]
        {
            ("AccentFillColorDefaultBrush", accent),
            ("AccentButtonBackground", accent), ("AccentButtonBackgroundPointerOver", hover), ("AccentButtonBackgroundPressed", pressed),
            ("AccentButtonForeground", accentFg), ("AccentButtonForegroundPointerOver", accentFg), ("AccentButtonForegroundPressed", accentFg),
            ("SliderTrackValueFill", accent), ("SliderTrackValueFillPointerOver", hover), ("SliderTrackValueFillPressed", pressed),
            ("SliderThumbBackground", accent), ("SliderThumbBackgroundPointerOver", hover), ("SliderThumbBackgroundPressed", pressed),
            ("ToggleSwitchFillOn", accent), ("ToggleSwitchFillOnPointerOver", hover), ("ToggleSwitchFillOnPressed", pressed),
            ("ToggleSwitchKnobFillOn", accentFg), ("ProgressBarForeground", accent),
            ("SelectorBarItemPillFill", accent),
            ("SelectorBarItemBackgroundSelected", palette.Brush(palette.Color, 0.10)),
        })
            Resources[key] = brush;

        // Re-resolve ThemeResource lookups against the new page-level overrides.
        RequestedTheme = ActualTheme == ElementTheme.Dark ? ElementTheme.Light : ElementTheme.Dark;
        RequestedTheme = ElementTheme.Default;
        ApplyAccentText();
    }

    void ApplyAccentText()
    {
        if (gamePalette is not { } palette) return;
        var light = ActualTheme == ElementTheme.Light;
        var ink = light ? Services.ArtAccent.Readable(palette.Color, global::Windows.UI.Color.FromArgb(255, 243, 243, 243)) : palette.HeroAccent;
        TitleText.Foreground = palette.Brush(ink);
        Resources["SelectorBarItemForegroundSelected"] = palette.Brush(light ? ink : palette.NavAccent);
    }

    void Refresh()
    {
        StatusBadge.Text = game.AdoptionAvailable ? "Installed · Adoption available" : game.OfflineOnly ? "Installed · Offline only" : game.Blocked ? "Unsupported"
            : game.UsesFeeder ? game.Installed ? "Feeder NR" : "Available · Feeder NR"
            : game.InstalledOnLinux ? "Installed on Linux"
            : game.Installed ? shell.Mode switch { "nr-only" => "NR Only", "nr-mfg" => "NR + MFG", _ => "MFG Only" }
            : "Ready for Features";
        // Installed with rtxForge on Linux: Set Up for Windows adapts that install instead of reinstalling it.
        InstallText.Text = game.InstallLabel;
        // Metadata pill beside STEAM / TESTED: which rtxForge installed the features.
        var os = game.Installed && game.InstalledOn is "linux" or "windows" ? game.InstalledOn : null;
        OsBadge.Visibility = os is null ? Visibility.Collapsed : Visibility.Visible;
        if (os is not null)
        {
            OsBadgeIcon.Data = OsMark.Data(os);
            OsBadgeText.Text = CrossOs.Name(os).ToUpperInvariant();
            ToolTipService.SetToolTip(OsBadge, OsMark.Tooltip(os));
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(OsBadge, OsMark.Tooltip(os));
        }
        InstallButton.IsEnabled = (!game.Blocked || game.AdoptionAvailable) && !shell.Busy;
        RestoreButton.IsEnabled = game.Installed && !game.AdoptionAvailable && !shell.Busy;
        AdoptionItem.Visibility = game.AdoptionAvailable ? Visibility.Visible : Visibility.Collapsed;
        OfflineLaunchItem.Visibility = game.OfflineOnly ? Visibility.Visible : Visibility.Collapsed;
        UpdateDlssItem.IsEnabled = !game.Blocked;
        OpenFolderItem.IsEnabled = !shell.Service.IsPreview && Directory.Exists(game.Location);
        Build(section);
    }

    void OnSectionChanged(SelectorBar sender, SelectorBarSelectionChangedEventArgs args)
    {
        if (sender.SelectedItem is SelectorBarItem item && game is not null) Build((string)item.Tag);
    }

    void OnInstall(object sender, RoutedEventArgs e) => _ = shell.LaunchAction("install", [game]);
    void OnRestore(object sender, RoutedEventArgs e) => _ = shell.LaunchAction("uninstall", [game]);
    void OnUpdateDlss(object sender, RoutedEventArgs e) => _ = shell.LaunchAction("update-dlss", [game]);
    void OnCompanion(object sender, RoutedEventArgs e) => shell.OpenCompanion(game);
    void OnAdoption(object sender, RoutedEventArgs e) => _ = shell.ReviewAdoptionAsync([game]);
    void OnLaunchOffline(object sender, RoutedEventArgs e) => _ = shell.LaunchOfflineAsync(game);
    void OnRemoveFromLibrary(object sender, RoutedEventArgs e) => _ = shell.ConfirmRemoveLibraryEntriesAsync([game]);
    void OnOpenFolder(object sender, RoutedEventArgs e) => _ = shell.OpenGameFolderAsync(game);

    void Build(string name)
    {
        section = name;
        PageHost.Children.Clear();
        var g = game;

        switch (name)
        {
            case "Overview":
                if (g.OfflineOnly)
                {
                    var offline = new PreferencesGroup("Offline-only features", "Launch here to use the reviewed offline route. The normal Steam launch is unchanged. Online play requires removing these feature files. Adoption restore returns the previous modded setup.");
                    offline.Add(Prefs.ActionButton("Launch offline", (_, _) => _ = shell.LaunchOfflineAsync(g), accent: true));
                    PageHost.Children.Add(offline);
                }
                if (g.AdoptionAvailable)
                    PageHost.Children.Add(Prefs.Row("Adoption available", "This package is installed. Adopt its current setup or back it up and clean install from rtxForge.", Prefs.ActionButton("Review Adoption", (_, _) => _ = shell.ReviewAdoptionAsync([g]))));
                if (g.Blocked)
                    PageHost.Children.Add(new InfoBar
                    {
                        IsOpen = true, IsClosable = false, Severity = InfoBarSeverity.Warning, Margin = new Thickness(0, 24, 0, 0),
                        Title = "rtxForge will not modify this game", Message = g.BlockedReason ?? "",
                    });
                else if (g.InstalledOnLinux)
                    PageHost.Children.Add(new InfoBar
                    {
                        IsOpen = true, IsClosable = false, Severity = InfoBarSeverity.Informational, Margin = new Thickness(0, 24, 0, 0),
                        Title = "Installed on Linux",
                        Message = "These features were installed with rtxForge on Linux and already load on Windows. "
                            + "Set Up for Windows hands them to rtxForge here, so you can repair, retune or restore them from Windows.",
                    });
                var info = new PreferencesGroup("Game Information");
                if (g.IsFeeder)
                    info.Add(Prefs.Row("NR route", "Feeder NR · " + (g.EngineRow?["nr_runtime"]?["version"]?.ToString() ?? "Version unavailable")
                        + (g.EngineRow?["nr_enabled"]?.GetValue<bool>() == true ? ". Enabled in saved settings." : ". Disabled in saved settings.")
                        + " Check the running game with Diagnose NR.", glyph: ""));
                foreach (var (title, value, glyph) in new (string, string?, string)[]
                {
                    ("Library", g.Library, ""), ("Location", g.Location, ""),
                    ("Compatibility", g.Blocked ? null : "Supported", ""), ("Metadata Source", g.MetadataSource, ""),
                    ("Developer", g.Developer, ""), ("Release", g.Release, ""),
                })
                    if (!string.IsNullOrEmpty(value)) info.Add(Prefs.Row(title, value, glyph: glyph));
                if (g.Installed && g.InstalledOn is "linux" or "windows")
                {
                    // The OS mark sits where the other rows have their glyph.
                    var installedWith = Prefs.Row("Installed with", "rtxForge on " + CrossOs.Name(g.InstalledOn));
                    ((Grid)installedWith.Child).Children.Insert(0,
                        OsMark.Create(g.InstalledOn, 20, (Brush)Application.Current.Resources["TextFillColorPrimaryBrush"]));
                    info.Add(installedWith);
                }
                PageHost.Children.Add(info);
                break;

            case "Presets":
                if (g.IsFeeder)
                {
                    PageHost.Children.Add(Prefs.Row("Feeder NR settings", "Your existing tuning is preserved. Use ReShade's NR panel in the running game to adjust passes, resolution, tone and structure.", glyph: ""));
                    break;
                }
                var features = new PreferencesGroup(null,
                    "Tuning values for this game. Reset restores your library presets. Apply saves them for this game.");
                var tuning = new PresetControlsView(shell.GameTuning(g), shell.Settings.OverlayControls == "classic");
                tuning.SetMode(g.Profile?.Contains("Only", StringComparison.OrdinalIgnoreCase) == true
                    ? g.Profile.StartsWith("NR", StringComparison.OrdinalIgnoreCase) ? "nr-only" : "mfg-only" : shell.Mode,
                    g.Installed, g.RuntimeProvider != "skynizz");
                // 16px gaps (the pods' own spacing): group spacing 4 + margin 12.
                if (g.Installed) tuning.Margin = new Thickness(0, 12, 0, 0);
                features.Add(tuning);
                var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 12, 0, 0) };
                var reset = Prefs.ActionButton("Reset", (_, _) => _ = shell.LaunchAction("reset", [g]));
                var apply = Prefs.ActionButton("Apply", (_, _) => _ = shell.LaunchAction("apply", [g], tuning.Value), accent: true);
                reset.IsEnabled = apply.IsEnabled = g.Installed && !shell.Busy;
                actions.Children.Add(reset);
                actions.Children.Add(apply);
                features.Add(actions);
                PageHost.Children.Add(features);
                break;

            case "DLSS Files":
                var files = new PreferencesGroup("Installed DLSS Files");
                files.Add(Prefs.Row("nvngx_dlss.dll", g.DlssVersion is null ? "Not detected" : "Version " + g.DlssVersion, glyph: ""));
                PageHost.Children.Add(files);
                var manage = new PreferencesGroup("File Management");
                var update = Prefs.ActionButton("Update", (_, _) => _ = shell.LaunchAction("update-dlss", [g]));
                update.IsEnabled = !g.Blocked && !shell.Busy;
                manage.Add(Prefs.Row("Update DLSS", "Update older DLSS files. Backups are kept for restoration.", update, ""));
                var restoreDlss = Prefs.ActionButton("Restore", async (_, _) => await shell.RestoreDlssFilesAsync(g));
                restoreDlss.IsEnabled = false;
                var backupRow = Prefs.Row("Restore original DLSS files", "Checking for backups…", restoreDlss, "");
                manage.Add(backupRow);
                PageHost.Children.Add(manage);
                _ = FillDlssInventoryAsync(g, files, backupRow, restoreDlss);
                break;

            case "Tools":
                var tools = new PreferencesGroup("Tools");
                var open = Prefs.ActionButton("Open", (_, _) => OnOpenFolder(this, new RoutedEventArgs()));
                open.IsEnabled = OpenFolderItem.IsEnabled;
                tools.Add(Prefs.Row("Game Folder", g.Location, open, ""));
                tools.Add(Prefs.Row("Copy Location", "Copy the install path to the clipboard.", Prefs.ActionButton("Copy", (_, _) =>
                {
                    var data = new DataPackage();
                    data.SetText(g.Location);
                    Clipboard.SetContent(data);
                    shell.ShowToast("Location copied.");
                }), ""));
                PageHost.Children.Add(tools);
                // populate_tools: NR diagnosis and ReShade / add-ons, each reviewed before it touches the game.
                var extras = new PreferencesGroup("Graphics Tools", "Check NR or add ReShade to this game. Existing graphics files are kept safe.");
                extras.Add(Prefs.Row("Diagnose NR", "Read the saved NR settings, runtime hashes and log evidence.",
                    Prefs.ActionButton("Diagnose", async (_, _) => await shell.DiagnoseAsync(g)), ""));
                foreach (var (kind, title, subtitle) in new[]
                {
                    ("reshade", "Install ReShade", "Choose an extracted x64 ReShade DLL. DirectX 10–12 games load it as dxgi.dll."),
                    ("addon", "Install Add-on", "Choose an .addon64 file (including RenoDX). Install ReShade first."),
                })
                {
                    var install = Prefs.ActionButton("Choose", async (_, _) => await shell.InstallExtraAsync(g, kind));
                    install.IsEnabled = !shell.Service.IsPreview && !g.Blocked && !shell.Busy;
                    extras.Add(Prefs.Row(title, subtitle, install, ""));
                }
                extras.Add(Prefs.Row("ReShade Downloads", "Get ReShade from its official site.",
                    Prefs.ActionButton("Open", (_, _) => MainWindow.OpenUri("https://reshade.me/")), ""));
                PageHost.Children.Add(extras);
                PageHost.Children.Add(Prefs.Label("Use an extracted x64 ReShade DLL or .addon64 file from a source you trust. Shader packs and presets remain yours to manage.", "ForgeCaptionDimTextStyle"));
                _ = FillExtraRecordsAsync(g);
                break;

            case "Notes":
                var notes = new PreferencesGroup("Your Notes", "Kept with this game in rtxForge. Included in support reports when you choose.");
                string[] states = ["Untested", "Working", "Problem", "Bench"];
                var (statusRow, status) = Prefs.ComboRow("Test Result", "Bench excludes this game from bulk installation and repair.", states,
                    Math.Max(0, Array.IndexOf(states, g.TestStatus)), "");
                notes.Add(statusRow);
                var text = new TextBox { Text = g.Notes, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 180, PlaceholderText = "What worked, what didn't, settings you used" };
                notes.Add(text);
                var noteActions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 12, 0, 0) };
                var test = Prefs.ActionButton(g.TestActive ? "Finish Test" : "Start Test", async (_, _) => await shell.RecordTestAsync(g));
                test.IsEnabled = !shell.Service.IsPreview;
                noteActions.Children.Add(test);
                noteActions.Children.Add(Prefs.ActionButton("Save Notes", async (_, _) => await shell.SaveNotesAsync(g, states[Math.Max(0, status.SelectedIndex)], text.Text), accent: true));
                notes.Add(noteActions);
                PageHost.Children.Add(notes);
                break;

            case "Appearance":
                BuildAppearance(g);
                break;
        }
    }

    /// <summary>DLSS Files: the native files found outside the feature stack, and the latest updater backup.</summary>
    async Task FillDlssInventoryAsync(Game g, PreferencesGroup files, Border backupRow, Button restore)
    {
        DlssInventory inventory;
        try { inventory = await shell.Service.DlssInventoryAsync(g); }
        catch (InvalidOperationException error) { SetSubtitle(backupRow, error.Message); return; }
        if (g != game || section != "DLSS Files") return;
        if (inventory.Blocked.Length > 0) files.Add(Prefs.Row("File management unavailable", inventory.Blocked, glyph: ""));
        foreach (var file in inventory.Files)
            files.Add(Prefs.Row(file.Title, $"{file.Path} · {file.Current} · {file.Provenance}", glyph: ""));
        SetSubtitle(backupRow, inventory.LatestBackup is { } date ? "Latest backup " + date : "No DLSS file backups for this game.");
        restore.IsEnabled = inventory.LatestBackup is not null && !shell.Busy;
    }

    async Task FillExtraRecordsAsync(Game g)
    {
        IReadOnlyList<ExtraRecord> records;
        try { records = await shell.Service.ExtraRecordsAsync(g); }
        catch (InvalidOperationException) { return; }
        if (g != game || section != "Tools" || records.Count == 0) return;
        var group = new PreferencesGroup("Installed Tools", "Restore puts the game's original files back.");
        foreach (var record in records)
            group.Add(Prefs.Row(record.Title, record.Date, Prefs.ActionButton("Restore", async (_, _) => { await shell.RestoreExtraAsync(record); Build("Tools"); }), ""));
        PageHost.Children.Add(group);
    }

    static void SetSubtitle(Border row, string text)
    {
        if ((row.Child as Grid)?.Children.OfType<StackPanel>().FirstOrDefault() is not { } lines) return;
        if (lines.Children.Count > 1 && lines.Children[1] is TextBlock subtitle) subtitle.Text = text;
        else lines.Children.Add(Prefs.Label(text, "ForgeCaptionDimTextStyle"));
    }

    // ---------- Hero identity (meta line, source/test badges, summary) ----------

    void ShowIdentity()
    {
        MetaText.Text = string.Join(" · ", new[] { game.Developer, game.Release }.Where(s => !string.IsNullOrEmpty(s)));
        MetaText.Visibility = MetaText.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
        SourceBadge.Text = game.Library == "Steam" ? "STEAM" : "NON-STEAM";
        TestBadgeText.Text = game.Tested ? "TESTED" : "UNTESTED";
        TestBadgeIcon.Glyph = game.Tested ? "" : "";
        TestBadgeIcon.Foreground = (Brush)Application.Current.Resources[game.Tested ? "ForgePillTestedBrush" : "SystemFillColorCautionBrush"];
        SummaryText.Text = game.Summary ?? "";
        SummaryText.Visibility = string.IsNullOrEmpty(game.Summary) ? Visibility.Collapsed : Visibility.Visible;
        ToolTipService.SetToolTip(SummaryText, game.Summary);
    }

    /// <summary>Settings › Download game information (shared with Game Mode): SteamStoreInfo.</summary>
    async Task LoadSteamInfoAsync(Game g)
    {
        if (await Services.SteamStoreInfo.FillAsync(g, shell.Settings.SteamMetadata) && g == game) ShowIdentity();
    }
    // ---------- Responsive layout ----------

    void OnPageSizeChanged(object sender, SizeChangedEventArgs e) => ApplyLayout(e.NewSize.Width);

    /// <summary>
    /// Scales the hero, poster, title and margins with the window, and moves
    /// the hero actions under the title when there is no room beside it.
    /// </summary>
    void ApplyLayout(double width)
    {
        if (width <= 0 || game is null) return;
        var side = PageMargins.Side(width);
        HeroBanner.Height = Math.Round(Math.Clamp(width * 0.30, 240, 560));
        var posterHeight = Math.Round(Math.Clamp(HeroBanner.Height * 0.48, 120, 260));
        PosterFrame.Height = posterHeight;
        PosterFrame.Width = Math.Round(posterHeight * 2 / 3);
        var title = Math.Clamp(width / 26, 26, 64) * (game.Name.Length > 28 ? 0.78 : 1); // detail-title step-down
        TitleText.FontSize = Math.Round(title);
        TitleText.LineHeight = Math.Round(title * 1.1);
        Identity.Padding = new Thickness(side, 0, side, Math.Round(Math.Clamp(width * 0.02, 16, 32)));
        Sections.Margin = new Thickness(side - 8, 8, side, 0);
        PageHost.Padding = new Thickness(side, 0, side, 0);

        var nowNarrow = width < 980;
        // Everything bottom-aligns with the poster; the title always spans the
        // full width. Wide: actions sit beside the meta/summary row. Narrow:
        // actions drop into their own row under it.
        Grid.SetRow(HeroActions, nowNarrow ? 2 : 1);
        Grid.SetColumn(HeroActions, nowNarrow ? 0 : 1);
        HeroActions.Margin = new Thickness(0, nowNarrow ? 12 : 0, 0, 0);
        HeroActions.HorizontalAlignment = nowNarrow ? HorizontalAlignment.Left : HorizontalAlignment.Right;
        if (nowNarrow != narrow)
        {
            narrow = nowNarrow;
            if (section == "Appearance") Build(section);
        }
    }

    // ---------- Appearance (artwork_preferences + Accent Color + Artwork Credits) ----------

    void BuildAppearance(Game g)
    {
        var preview = shell.Service.IsPreview;

        // Custom Artwork: role editors with accent-framed previews.
        var sync = Prefs.ActionButton("Sync artwork to Steam", async (_, _) => await shell.SyncGameArtworkAsync(g), glyph: "");
        sync.IsEnabled = !preview;
        var custom = new PreferencesGroup("Custom Artwork",
            "Artwork changes also sync to your local Steam library. Reset restores your original Steam artwork.", sync);
        var editors = new Grid { ColumnSpacing = 16, RowSpacing = 24 };
        var frames = new List<Border>();
        foreach (var (index, (title, hint, width, height, source)) in new[]
        {
            ("Poster", "600 × 900", 72.0, 108.0, g.PosterPath),
            ("Wide Capsule", "920 × 430", 132.0, 62.0, g.CapsulePath),
            ("Hero", "1920 × 620", 156.0, 50.0, g.HeroPath),
        }.Select((spec, i) => (i, spec)))
        {
            // Three across; one per row when the window is narrow.
            if (narrow) editors.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            else editors.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var item = new StackPanel { Spacing = 12 };
            var heading = Prefs.Label(title, "ForgeHeadingTextStyle");
            heading.HorizontalAlignment = HorizontalAlignment.Center;
            item.Children.Add(heading);
            var frame = new Border
            {
                Width = width + 4, Height = height + 4, BorderThickness = new Thickness(2),
                CornerRadius = (CornerRadius)Application.Current.Resources["ForgeArtCornerRadius"],
                BorderBrush = (Brush)Application.Current.Resources["CardStrokeColorDefaultBrush"],
                Background = (Brush)Application.Current.Resources["ControlFillColorSecondaryBrush"],
                Child = source is null
                    ? new FontIcon { Glyph = "", FontSize = 20 }
                    : new Image { Source = ViewModels.GameItem.Image(source), Stretch = Stretch.UniformToFill },
            };
            frames.Add(frame);
            item.Children.Add(new Grid { Height = 120, Children = { frame } });
            var dims = Prefs.Label(hint, "ForgeCaptionDimTextStyle");
            dims.HorizontalAlignment = HorizontalAlignment.Center;
            item.Children.Add(dims);
            foreach (var (caption, glyph) in new[] { ("Choose Image", ""), ("Browse artwork", ""), ("Reset", "") })
            {
                var role = title switch { "Poster" => "poster", "Hero" => "hero", _ => "capsule" };
                var action = Prefs.ActionButton(caption, async (_, _) =>
                {
                    if (caption == "Choose Image") await shell.ChooseArtworkAsync(g, role);
                    else if (caption == "Browse artwork") await shell.BrowseArtworkAsync(g, role);
                    else await shell.ResetArtworkAsync(g, role);
                }, glyph: glyph);
                action.HorizontalAlignment = HorizontalAlignment.Stretch;
                action.IsEnabled = !preview;
                ToolTipService.SetToolTip(action, preview ? "Preview mode" : caption);
                item.Children.Add(action);
            }
            if (narrow) Grid.SetRow(item, index); else Grid.SetColumn(item, index);
            editors.Children.Add(item);
        }
        custom.Add(new Border { Style = Prefs.GetStyle("ForgeControlPodStyle"), Child = editors });
        PageHost.Children.Add(custom);

        // Accent Color: Game Accent row with swatch and the poster picker.
        var accentGroup = new PreferencesGroup("Accent Color", "Pick any color directly from this game’s poster.");
        var swatch = new Microsoft.UI.Xaml.Shapes.Ellipse { Width = 28, Height = 28 };
        var edit = Prefs.ActionButton("Edit", (_, _) => _ = PickAccentAsync(g));
        var suffix = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12, Children = { swatch, edit } };
        var customHex = shell.Settings.GameAccents.GetValueOrDefault(g.Id);
        accentGroup.Add(Prefs.Row("Game Accent", customHex is null ? "Artwork-derived" : "Custom · " + customHex.ToUpperInvariant(), suffix, ""));
        PageHost.Children.Insert(0, accentGroup);

        // Artwork Credits pods.
        var credits = new PreferencesGroup("Artwork Credits");
        var pods = new Grid { ColumnSpacing = 16 };
        foreach (var (index, title) in new[] { "Poster", "Wide Capsule", "Hero" }.Select((t, i) => (i, t)))
        {
            pods.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var pod = new StackPanel { Spacing = 5 };
            pod.Children.Add(Prefs.Label(title, "ForgeHeadingTextStyle"));
            var creditRole = title switch { "Poster" => "poster", "Hero" => "hero", _ => "capsule" };
            var hasArt = (title switch { "Poster" => g.PosterPath, "Hero" => g.HeroPath, _ => g.CapsulePath }) is not null;
            var source = g.ArtCredits.GetValueOrDefault(creditRole) ?? (hasArt ? g.MetadataSource : null);
            pod.Children.Add(Prefs.Label(source ?? "Source information unavailable", "ForgeCaptionDimTextStyle"));
            var card = new Border { Style = Prefs.GetStyle("ForgeControlPodStyle"), Padding = new Thickness(16), Child = pod };
            Grid.SetColumn(card, index);
            pods.Children.Add(card);
        }
        credits.Add(pods);
        PageHost.Children.Add(credits);

        _ = PaintAppearanceAsync(g, frames, swatch);
    }

    /// <summary>.artwork-editor.{art} .artwork-preview border and the accent swatch.</summary>
    async Task PaintAppearanceAsync(Game g, List<Border> frames, Microsoft.UI.Xaml.Shapes.Ellipse swatch)
    {
        var palette = await Services.ArtAccent.ForGameAsync(g);
        var brush = palette?.AccentBrush ?? new SolidColorBrush(Services.ArtAccent.NoArtwork);
        swatch.Fill = brush;
        foreach (var frame in frames) frame.BorderBrush = brush;
    }

    /// <summary>"Pick Accent Color": click a pixel on the poster to preview it, Done saves it.</summary>
    async Task PickAccentAsync(Game g)
    {
        var source = g.PosterPath ?? g.CapsulePath ?? g.HeroPath;
        if (source is null) { shell.ShowToast("No poster artwork is available."); return; }
        byte[] pixels; uint sw, sh;
        IReadOnlyList<Services.ArtAccent.AccentSuggestion> suggestions;
        try
        {
            var bytes = await Services.ArtAccent.LoadAsync(source);
            (pixels, sw, sh) = await Services.ArtAccent.DecodeAsync(bytes);
            suggestions = await Services.ArtAccent.SuggestionsAsync(bytes);
        }
        catch (Exception error) when (error is HttpRequestException or IOException or TaskCanceledException or System.Runtime.InteropServices.COMException)
        {
            shell.ShowToast("Could not open this game’s artwork.");
            return;
        }

        // Fit the whole poster: as tall as the window allows beside the dialog chrome, true aspect.
        var maxH = Math.Clamp((XamlRoot?.Size.Height ?? 900) - (suggestions.Count > 0 ? 430 : 340), 220, 640);
        var scale = Math.Min(420.0 / sw, maxH / sh);
        var displayW = Math.Round(sw * scale);
        var displayH = Math.Round(sh * scale);
        var initial = shell.Settings.GameAccents.GetValueOrDefault(g.Id)
            ?? ((await Services.ArtAccent.ForGameAsync(g)) is { } p ? Services.ArtAccent.Hex(p.Color) : Services.ArtAccent.Hex(Services.ArtAccent.NoArtwork));
        var pending = initial;

        var hex = Prefs.Label(initial.ToUpperInvariant(), "ForgeDimTextStyle");
        hex.HorizontalAlignment = HorizontalAlignment.Center;
        var image = new Image { Source = ViewModels.GameItem.Image(source), Stretch = Stretch.Fill, Width = displayW, Height = displayH };
        var frame = new Border
        {
            BorderThickness = new Thickness(3), HorizontalAlignment = HorizontalAlignment.Center,
            CornerRadius = (CornerRadius)Application.Current.Resources["ForgeCardCornerRadius"], Child = image,
        };
        // Suggested swatches (shared with Game Mode): Signature, Background, Alternate, Light, Deep.
        var swatchRings = new List<(Border Ring, string Hex)>();
        var swatches = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 14, HorizontalAlignment = HorizontalAlignment.Center };
        void Preview(string color)
        {
            pending = color;
            hex.Text = color.ToUpperInvariant();
            if (Services.ArtAccent.TryParse(color, out var c)) frame.BorderBrush = new SolidColorBrush(c);
            foreach (var (ring, value) in swatchRings)
                ring.BorderBrush = string.Equals(value, color, StringComparison.OrdinalIgnoreCase)
                    ? (Brush)Application.Current.Resources["TextFillColorPrimaryBrush"]
                    : new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        }
        foreach (var suggestion in suggestions)
        {
            var value = Services.ArtAccent.Hex(suggestion.Color);
            var ring = new Border
            {
                Width = 40, Height = 40, CornerRadius = new CornerRadius(20), BorderThickness = new Thickness(2), Padding = new Thickness(3),
                HorizontalAlignment = HorizontalAlignment.Center,
                Child = new Microsoft.UI.Xaml.Shapes.Ellipse { Fill = new SolidColorBrush(suggestion.Color) },
            };
            swatchRings.Add((ring, value));
            var content = new StackPanel { Spacing = 4 };
            content.Children.Add(ring);
            content.Children.Add(new TextBlock
            {
                Text = suggestion.Label, FontSize = 11, HorizontalAlignment = HorizontalAlignment.Center,
                Foreground = (Brush)Application.Current.Resources["TextFillColorSecondaryBrush"],
            });
            var pick = new Button
            {
                Content = content, Padding = new Thickness(6, 4, 6, 4), BorderThickness = new Thickness(0),
                Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
            };
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(pick, $"{suggestion.Label} {value}");
            ToolTipService.SetToolTip(pick, $"{suggestion.Label} · {value.ToUpperInvariant()}");
            pick.Click += (_, _) => Preview(value);
            swatches.Children.Add(pick);
        }
        Preview(initial);

        // Eyedropper: a loupe of the 11×11 source pixels around the pointer, center pixel outlined.
        const int span = 11, cell = 12;
        var cells = new Microsoft.UI.Xaml.Shapes.Rectangle[span * span];
        var grid = new Grid { Width = span * cell, Height = span * cell };
        for (var i = 0; i < span; i++)
        {
            grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(cell) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(cell) });
        }
        for (var i = 0; i < cells.Length; i++)
        {
            var rect = new Microsoft.UI.Xaml.Shapes.Rectangle();
            Grid.SetRow(rect, i / span);
            Grid.SetColumn(rect, i % span);
            grid.Children.Add(rect);
            cells[i] = rect;
        }
        var center = new Border
        {
            Width = cell + 2, Height = cell + 2, BorderThickness = new Thickness(2), BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.White),
            Margin = new Thickness(span / 2 * cell - 1, span / 2 * cell - 1, 0, 0), HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top,
            Child = new Border { BorderThickness = new Thickness(1), BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Black) },
        };
        grid.Children.Add(center);
        Grid.SetRowSpan(center, span);
        Grid.SetColumnSpan(center, span);
        var swatch = new Microsoft.UI.Xaml.Shapes.Ellipse { Width = 16, Height = 16, Stroke = new SolidColorBrush(Microsoft.UI.Colors.White), StrokeThickness = 1.5 };
        var hoverHex = new TextBlock { FontSize = 12, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, VerticalAlignment = VerticalAlignment.Center };
        var readout = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Center };
        readout.Children.Add(swatch);
        readout.Children.Add(hoverHex);
        var loupeBody = new StackPanel { Spacing = 6 };
        loupeBody.Children.Add(new Border { CornerRadius = new CornerRadius(8), Child = grid });
        loupeBody.Children.Add(readout);
        var loupe = new Border
        {
            Child = loupeBody, Padding = new Thickness(6), CornerRadius = new CornerRadius(12), IsHitTestVisible = false,
            Background = (Brush)Application.Current.Resources["SolidBackgroundFillColorTertiaryBrush"],
            BorderBrush = (Brush)Application.Current.Resources["SurfaceStrokeColorDefaultBrush"], BorderThickness = new Thickness(1),
            Visibility = Visibility.Collapsed, Translation = new System.Numerics.Vector3(0, 0, 24), Shadow = new ThemeShadow(),
        };
        var canvas = new Canvas { IsHitTestVisible = false };
        canvas.Children.Add(loupe);
        var stage = new Grid { HorizontalAlignment = HorizontalAlignment.Center };
        stage.Children.Add(frame);
        stage.Children.Add(canvas);

        global::Windows.UI.Color Pixel(int x, int y)
        {
            var i = (int)(((uint)y * sw + (uint)x) * 4);
            return global::Windows.UI.Color.FromArgb(255, pixels[i + 2], pixels[i + 1], pixels[i]);
        }
        (int X, int Y) SourcePoint(global::Windows.Foundation.Point point) =>
            ((int)Math.Clamp(point.X / image.ActualWidth * sw, 0, sw - 1), (int)Math.Clamp(point.Y / image.ActualHeight * sh, 0, sh - 1));

        image.PointerMoved += (_, e) =>
        {
            var (x, y) = SourcePoint(e.GetCurrentPoint(image).Position);
            for (var i = 0; i < cells.Length; i++)
            {
                int cx = x + i % span - span / 2, cy = y + i / span - span / 2;
                cells[i].Fill = cx < 0 || cy < 0 || cx >= sw || cy >= sh
                    ? new SolidColorBrush(Microsoft.UI.Colors.Transparent)
                    : new SolidColorBrush(Pixel(cx, cy));
            }
            var color = Pixel(x, y);
            swatch.Fill = new SolidColorBrush(color);
            hoverHex.Text = Services.ArtAccent.Hex(color).ToUpperInvariant();
            loupe.Visibility = Visibility.Visible;
            // Above-right of the pointer, flipped near the edges of the stage.
            var at = e.GetCurrentPoint(stage).Position;
            loupe.Measure(new global::Windows.Foundation.Size(double.PositiveInfinity, double.PositiveInfinity));
            var (lw, lh) = (loupe.DesiredSize.Width, loupe.DesiredSize.Height);
            var left = at.X + 20 + lw > stage.ActualWidth ? at.X - 20 - lw : at.X + 20;
            var top = at.Y - 20 - lh < 0 ? at.Y + 20 : at.Y - 20 - lh;
            Canvas.SetLeft(loupe, left);
            Canvas.SetTop(loupe, top);
        };
        image.PointerExited += (_, _) => { loupe.Visibility = Visibility.Collapsed; ProtectedCursor = null; };
        image.PointerEntered += (_, _) => ProtectedCursor = Microsoft.UI.Input.InputSystemCursor.Create(Microsoft.UI.Input.InputSystemCursorShape.Cross);
        image.Tapped += (_, e) =>
        {
            var (x, y) = SourcePoint(e.GetPosition(image));
            Preview(Services.ArtAccent.Hex(Pixel(x, y)));
        };
        var body = new StackPanel { Spacing = 12 };
        var instructions = Prefs.Label("Choose a suggestion, or any pixel from the artwork.", "ForgeDimTextStyle");
        instructions.HorizontalAlignment = HorizontalAlignment.Center;
        body.Children.Add(instructions);
        if (suggestions.Count > 0) body.Children.Add(swatches);
        body.Children.Add(stage);
        body.Children.Add(hex);

        var dialog = shell.NewDialog();
        dialog.Title = "Pick Accent Color";
        dialog.Content = body;
        dialog.PrimaryButtonText = "Done";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;

        shell.Settings.GameAccents[g.Id] = pending;
        shell.Settings.Save();
        shell.NotifyGamesChanged();
        await ApplyAccentAsync();
        Build("Appearance");
    }
}
