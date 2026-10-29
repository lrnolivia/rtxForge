using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Views;

/// <summary>
/// Packages: NR packages beside the MFG packages that pair with them, unified packages
/// (NR and MFG together), then your own package (coming soon) and community projects.
/// </summary>
public sealed partial class PackagesPage : Page
{
    readonly MainWindow shell = App.Main!;
    readonly StackPanel body = new() { Spacing = 20 };
    readonly TextBlock status = Prefs.Label("Checking your system…");

    public PackagesPage()
    {
        InitializeComponent();
        var page = new StackPanel { Spacing = 8, Padding = new Thickness(36, 12, 36, 48) };
        page.Children.Add(new TextBlock { Text = "Packages", Style = Prefs.GetStyle("ForgePageTitleTextStyle") });
        page.Children.Add(Prefs.Label("rtxForge uses one package for games with DLSS and one for games without it. Every game change is reviewed before it is applied."));
        page.Children.Add(Prefs.Label(GpuSupport, "ForgeCaptionDimTextStyle"));
        page.Children.Add(status);
        page.Children.Add(body);
        Content = new ScrollViewer { Content = page, HorizontalScrollMode = ScrollMode.Disabled };
        SizeChanged += (_, e) => page.Padding = PageMargins.For(e.NewSize.Width);
        Loaded += async (_, _) => await LoadAsync();
    }

    /// <summary>Packages the engine uses automatically for the games they cover, whatever DLSS package is chosen:
    /// Feeder NR for games without DLSS, the Vulkan package for its confirmed Vulkan games.</summary>
    internal static readonly string[] Automatic = ["feeder", "vulkan-native"];
    internal const string GpuSupport = "RTX 20–50 series can install supported packages. RTX 50 uses native MFG without an unlock package. Feature availability depends on the game, package and GPU.";

    /// <summary>The NR packages heading: the DLSS choice, then the automatic packages by catalog name.</summary>
    internal static string NrDescription(PackageCatalog catalog)
    {
        var names = catalog.Packages.Where(p => Automatic.Contains(p.Id)).Select(p => p.Name).ToArray();
        return "Neural rendering. Choose one for games with DLSS" + (names.Length == 0 ? "."
            : $"; {string.Join(" and ", names)} {(names.Length == 1 ? "is" : "are")} used automatically for the games {(names.Length == 1 ? "it covers" : "they cover")}.");
    }

    /// <summary>The games a package is confirmed in, from the catalog, or null when it lists none.</summary>
    internal static string? ConfirmedGames(PackageOption item) =>
        item.Confirmed is { Count: > 0 } games ? "Confirmed games: " + string.Join(" · ", games) : null;
    /// <summary>NR packages that pair with a separate MFG package. Every other DLSS package brings its own MFG (unified).</summary>
    internal static readonly string[] PairsWithMfg = ["skynizz"];

    /// <summary>
    /// MFG packages for Skynizz NR, as Settings.MfgProvider values; all three use NVIDIA's own DLSS Frame
    /// Generation. Version reads the pinned release from the catalog (Kind follows it).
    /// </summary>
    internal static readonly (string Id, string Name, string Kind, string Summary, string[] Verified)[] MfgPackages =
    [
        ("universal", ForgeSettings.MfgName("universal"), "OptiScaler plugin",
            "Recommended. Keeps NVIDIA's DLSS Frame Generation and unlocks 3x to 6x where the driver allows 2x. The multiplier and Dynamic MFG stay in the rtxForge Overlay.", ["windows"]),
        ("integrated", ForgeSettings.MfgName("integrated"), "",
            "Patches NVIDIA's DLSS Frame Generation for 3x to 6x where the driver allows 2x, with no extra plugin.", ["windows"]),
        ("mfg-unlock", ForgeSettings.MfgName("mfg-unlock"), "ReShade add-on",
            "Raises NVIDIA's DLSS Frame Generation multiplier through ReShade. The rtxForge Overlay can't change its multiplier while you play.",["windows"]),
    ];

    /// <summary>The NR package MFG packages pair with, as the catalog names it.</summary>
    internal static string PairName(PackageCatalog catalog) => catalog.Packages.FirstOrDefault(p => PairsWithMfg.Contains(p.Id))?.Name ?? "the paired NR package";

    /// <summary>An MFG package's pinned version, from the paired NR package's catalog entry.</summary>
    internal static string MfgVersion(string id, string kind, PackageCatalog catalog)
    {
        var pair = catalog.Packages.FirstOrDefault(p => PairsWithMfg.Contains(p.Id));
        var version = pair?.MfgVersions?.GetValueOrDefault(id);
        if (id == "integrated") return pair is null ? "Built into the bridge" : $"Built into the {pair.Name} {version} bridge".Replace("  ", " ");
        return string.IsNullOrEmpty(version) ? kind : $"{version} · {kind}";
    }

    /// <summary>A package card's name and version: an NR package that pairs with MFG is named with the selected MFG package.</summary>
    internal static (string Name, string Version) CardTitle(PackageOption item, ForgeSettings settings)
    {
        if (!PairsWithMfg.Contains(item.Id)) return (item.Name, item.Version);
        var mfg = MfgPackages.FirstOrDefault(p => p.Id == settings.MfgProvider);
        if (mfg.Id is null) return (item.Name, item.Version);
        var version = mfg.Id == "integrated" ? "" : item.MfgVersions?.GetValueOrDefault(mfg.Id) ?? "";
        return ($"{item.Name} + {mfg.Name}", $"{item.Version} · {mfg.Name} {version}".TrimEnd());
    }

    async Task LoadAsync()
    {
        PackageCatalog catalog;
        try { catalog = await shell.Service.PackagesAsync(); }
        catch (InvalidOperationException error) { status.Text = error.Message; return; }
        status.Text = catalog.Status;
        body.Children.Clear();
        var pairs = PairsWithMfg.Contains(shell.Settings.RuntimeProvider);

        // NR packages beside the MFG packages that pair with them.
        var columns = new PresetColumns(420, 2) { ColumnSpacing = 16, RowSpacing = 20, Margin = new Thickness(0, 12, 0, 0) };
        var nr = new StackPanel { Spacing = 12 };
        nr.Children.Add(Heading("NR packages", NrDescription(catalog)));
        foreach (var item in catalog.Packages.Where(p => PairsWithMfg.Contains(p.Id)))
        {
            nr.Children.Add(PackageCard(item));
            if (shell.Settings.RuntimeProvider == item.Id) nr.Children.Add(new Expander
            {
                Header = item.Name + " settings", Content = SkynizzSettings(catalog), HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
            });
        }
        foreach (var item in catalog.Packages.Where(p => Automatic.Contains(p.Id))) nr.Children.Add(AutomaticCard(item));
        if (catalog.Packages.Any(p => p.Id == "feeder")) nr.Children.Add(FeederSetup());
        columns.Children.Add(nr);

        var mfg = new StackPanel { Spacing = 12 };
        var pairName = PairName(catalog);
        mfg.Children.Add(Heading("MFG packages", pairs
            ? $"Native NVIDIA frame generation for {pairName}, in games with DLSS Frame Generation. Applies to new installs; restore a game before switching its MFG package."
            : $"These pair with {pairName}. Your package for DLSS games brings its own frame generation."));
        foreach (var package in MfgPackages) mfg.Children.Add(MfgCard(package, pairs, catalog));
        columns.Children.Add(mfg);
        body.Children.Add(columns);

        // Whole packages: NR and MFG together.
        var unified = new StackPanel { Spacing = 12, Margin = new Thickness(0, 12, 0, 0) };
        unified.Children.Add(Heading("Unified packages", "NR and frame generation in one package, for games with DLSS. Choosing one replaces your NR package for those games."));
        var unifiedCards = new PresetColumns(360, 2) { ColumnSpacing = 16, RowSpacing = 16 };
        foreach (var item in catalog.Packages.Where(p => !Automatic.Contains(p.Id) && !PairsWithMfg.Contains(p.Id))
                     .OrderByDescending(p => p.Id == shell.Settings.RuntimeProvider))
            unifiedCards.Children.Add(PackageCard(item));
        unified.Children.Add(unifiedCards);
        unified.Children.Add(new Expander { Header = "NR model", Content = SkynizzSettings(catalog),
            HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch });
        body.Children.Add(unified);

        // Your own package (not supported yet) beside community projects.
        var sources = new PresetColumns(400, 2) { ColumnSpacing = 16, RowSpacing = 16, Margin = new Thickness(0, 12, 0, 0) };
        var custom = Section("Your own package · Coming soon", "Inspect a ZIP archive and review its settings before using it. Instructions are never run.");
        var pick = Prefs.ActionButton("Choose archive", (_, _) => { }, glyph: "");
        pick.IsEnabled = false;
        pick.HorizontalAlignment = HorizontalAlignment.Right;
        custom.Children.Add(pick);
        var customCard = Card(custom); customCard.Opacity = .55; customCard.IsHitTestVisible = false;
        sources.Children.Add(customCard);
        if (catalog.Community.Count > 0)
        {
            var community = Section("Other community projects", "Explore other projects. These sources aren't curated install options.");
            foreach (var source in catalog.Community)
            {
                var entry = new StackPanel { Spacing = 4 };
                entry.Children.Add(new HyperlinkButton { Content = source.Name, NavigateUri = new Uri(source.Url), Padding = new Thickness(0) });
                entry.Children.Add(Prefs.Label(source.Note, "ForgeCaptionDimTextStyle"));
                community.Children.Add(entry);
            }
            sources.Children.Add(Card(community));
        }
        body.Children.Add(sources);
    }

    Expander FeederSetup()
    {
        var feeder = Section("Feeder setup", "Import your local stack once. New installs use the verified copy kept by rtxForge. The paths below are saved import locations on this PC.");
        var paths = new PresetColumns(360, 2) { ColumnSpacing = 16, RowSpacing = 12 };
        paths.Children.Add(PathField("Stack import folder", "Your ReShade, Feeder, RenoDX and shader files. A game folder here is an import source, not the installation destination.",
            shell.Settings.FeederSource, path => shell.Settings.FeederSource = path));
        paths.Children.Add(PathField("Manual-install backups (optional)", "Needed to adopt an existing manual Feeder setup. Fresh installations create their own restore backups.",
            shell.Settings.FeederBackups, path => shell.Settings.FeederBackups = path));
        feeder.Children.Add(paths);
        var kept = Prefs.Label("Checking stored Feeder files…", "ForgeCaptionDimTextStyle");
        var keep = new Button { Content = "Keep a copy in rtxForge", HorizontalAlignment = HorizontalAlignment.Left };
        var legacy = new Button { Content = "Get DX9/DX10 support", HorizontalAlignment = HorizontalAlignment.Left, IsEnabled = !shell.Service.IsPreview };
        ToolTipService.SetToolTip(keep, "Verify both folders and store their files with rtxForge. Game files are not changed.");
        async Task ShowKeptAsync(bool import, bool downloadLegacy = false)
        {
            keep.IsEnabled = legacy.IsEnabled = false;
            try
            {
                var storage = await shell.Service.FeederStorageAsync(import ? NonEmpty(shell.Settings.FeederSource) : null,
                    import ? NonEmpty(shell.Settings.FeederBackups) : null, legacy: downloadLegacy);
                kept.Text = (storage.Recipe is null ? "No stack stored yet" : "Stored stack · " + storage.Recipe
                    + (storage.NrVersion is null ? "" : " · NR model " + storage.NrVersion))
                    + $" · {storage.Backups} original backup{(storage.Backups == 1 ? "" : "s")} kept"
                    + (storage.LegacyReady ? " · DX9/DX10 support ready" : "")
                    + (storage.Recipe is null ? "" : ". Ready for new installs; the old import location is not required.");
            }
            catch (InvalidOperationException error) { kept.Text = error.Message; }
            finally { keep.IsEnabled = true; legacy.IsEnabled = !shell.Service.IsPreview; }
        }
        static string? NonEmpty(string value) => string.IsNullOrWhiteSpace(value) ? null : value;
        keep.Click += async (_, _) => await ShowKeptAsync(true);
        feeder.Children.Add(kept);
        feeder.Children.Add(keep);
        feeder.Children.Add(Prefs.Label("For DirectX 9, DirectX 10 and 32-bit games, get the verified Feeder helper, ReShade and dgVoodoo2 files. This downloads support files only; game changes still go through installation review.", "ForgeCaptionDimTextStyle"));
        legacy.Click += async (_, _) => await ShowKeptAsync(false, downloadLegacy: true);
        feeder.Children.Add(legacy);
        _ = ShowKeptAsync(false);
        return new Expander
        {
            Header = "Feeder setup", Content = feeder, HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
        };
    }

    StackPanel SkynizzSettings(PackageCatalog catalog)
    {
        var settings = new StackPanel { Spacing = 12 };
        settings.Children.Add(Choice("NR model preset", "Performance (B) uses preset 2 with compatible NR models.",
            ["Automatic", "Legacy (A)", "Performance (B)"], Math.Clamp(shell.Settings.NrPreset ?? 0, 0, 2),
            index => shell.Settings.NrPreset = index));
        settings.Children.Add(PathField("Use your own NR DLL (optional)", "Leave blank to use the bundled NR model. A local override is validated and identified in the install review.",
            shell.Settings.NrRuntime, value => shell.Settings.NrRuntime = value));
        return settings;
    }

    Border PackageCard(PackageOption item)
    {
        var current = shell.Settings.RuntimeProvider == item.Id;
        var content = new Grid { RowSpacing = 12 };
        content.RowDefinitions.Add(new() { Height = GridLength.Auto });
        content.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        content.RowDefinitions.Add(new() { Height = GridLength.Auto });
        var (name, version) = CardTitle(item, shell.Settings);
        content.Children.Add(Section(name, version));
        var description = new StackPanel { Spacing = 8 };
        description.Children.Add(Prefs.Label(item.Summary));
        description.Children.Add(Prefs.Label("Graphics API: " + string.Join(" · ", item.GraphicsApis ?? []), "ForgeCaptionDimTextStyle"));
        if (!item.Available) description.Children.Add(Prefs.Label(item.Reason, "ForgeCaptionDimTextStyle"));
        Grid.SetRow(description, 1); content.Children.Add(description);
        var use = Prefs.ActionButton(current ? "In use" : "Use for DLSS games", (_, _) => { shell.SelectPackage(item.Id); _ = LoadAsync(); },
            accent: item.Recommended && !current);
        use.IsEnabled = item.Available && !current && !shell.Busy;
        ToolTipService.SetToolTip(use, item.Reason);
        var footer = Footer(item.Verified, use);
        Grid.SetRow(footer, 2); content.Children.Add(footer);
        return Card(content);
    }

    Border MfgCard((string Id, string Name, string Kind, string Summary, string[] Verified) package, bool pairs, PackageCatalog catalog)
    {
        var current = pairs && shell.Settings.MfgProvider == package.Id;
        var content = Section(package.Name, MfgVersion(package.Id, package.Kind, catalog));
        content.Children.Add(Prefs.Label(package.Summary));
        content.Children.Add(Prefs.Label("Graphics API: DirectX 12", "ForgeCaptionDimTextStyle"));
        var use = Prefs.ActionButton(current ? "In use" : "Use with " + PairName(catalog), (_, _) =>
        {
            shell.Settings.MfgProvider = package.Id; shell.SaveSettings(); _ = LoadAsync();
        }, accent: package.Id == "universal" && pairs && !current);
        use.IsEnabled = pairs && !current && !shell.Busy;
        content.Children.Add(Footer(package.Verified, use));
        var card = Card(content);
        if (!pairs) card.Opacity = .55;
        return card;
    }

    /// <summary>An automatic package: always on for the games it covers, so it has no Use button.</summary>
    Border AutomaticCard(PackageOption item)
    {
        var content = Section(item.Name, item.Version);
        content.Children.Add(Prefs.Label(item.Summary));
        content.Children.Add(Prefs.Label("Graphics API: " + string.Join(" · ", item.GraphicsApis ?? []), "ForgeCaptionDimTextStyle"));
        if (ConfirmedGames(item) is { } confirmed) content.Children.Add(Prefs.Label(confirmed, "ForgeCaptionDimTextStyle"));
        content.Children.Add(Footer(item.Verified, Prefs.Label(item.Available ? "Used automatically" : item.Reason, "ForgeCaptionDimTextStyle")));
        return Card(content);
    }

    /// <summary>The OSes a package was tested on in games, left; its action, right.</summary>
    static Grid Footer(IReadOnlyList<string>? verified, FrameworkElement action)
    {
        var footer = new Grid { ColumnSpacing = 12 };
        footer.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        footer.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var marks = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, VerticalAlignment = VerticalAlignment.Center };
        Microsoft.UI.Xaml.Media.Brush Resource(string key) => (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[key];
        foreach (var os in verified ?? [])
        {
            // Badges like the Details header's; the OS this PC runs is filled with the accent.
            var current = os == "windows";
            var ink = Resource(current ? "TextOnAccentFillColorPrimaryBrush" : "TextFillColorSecondaryBrush");
            var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
            line.Children.Add(OsMark.Create(os, 12, ink));
            line.Children.Add(new TextBlock { Text = CrossOs.Name(os).ToUpperInvariant(), FontSize = 11, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                Foreground = ink, VerticalAlignment = VerticalAlignment.Center });
            var pill = new Border { Child = line, Padding = new Thickness(10, 4, 10, 4), CornerRadius = new CornerRadius(12),
                Background = Resource(current ? "AccentFillColorDefaultBrush" : "ControlFillColorSecondaryBrush") };
            var tip = "Tested in games on " + CrossOs.Name(os) + (current ? " · this PC" : "");
            ToolTipService.SetToolTip(pill, tip); Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(pill, tip);
            marks.Children.Add(pill);
        }
        if (marks.Children.Count == 0)
        {
            // Not yet tested in games: one friendly mark instead of a caveat sentence.
            var label = new TextBlock { Text = "EXPERIMENTAL", FontSize = 11, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                Foreground = Resource("SystemFillColorCautionBrush"), VerticalAlignment = VerticalAlignment.Center };
            var pill = new Border { Child = label, Padding = new Thickness(10, 4, 10, 4), CornerRadius = new CornerRadius(12),
                Background = Resource("SystemFillColorCautionBackgroundBrush") };
            ToolTipService.SetToolTip(pill, "Experimental support");
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(pill, "Experimental support");
            marks.Children.Add(pill);
        }
        footer.Children.Add(marks);
        action.HorizontalAlignment = HorizontalAlignment.Right; action.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(action, 1); footer.Children.Add(action);
        return footer;
    }

    static StackPanel Heading(string title, string description)
    {
        var heading = new StackPanel { Spacing = 4 };
        var label = Prefs.Label(title, "ForgeHeadingTextStyle"); label.FontSize = 20;
        heading.Children.Add(label);
        heading.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        return heading;
    }

    static StackPanel Section(string title, string description)
    {
        var section = new StackPanel { Spacing = 10 };
        var heading = new StackPanel { Spacing = 4 };
        heading.Children.Add(Prefs.Label(title, "ForgeHeadingTextStyle"));
        heading.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        section.Children.Add(heading);
        return section;
    }

    static Border Card(UIElement content) => new()
    {
        Style = Prefs.GetStyle("ForgeControlPodStyle"), Padding = new Thickness(20, 16, 20, 16), Child = content,
    };

    UIElement Choice(string title, string description, IReadOnlyList<string> captions, int selected, Action<int> save, int retainedOnly = -1)
    {
        var field = new StackPanel { Spacing = 6 };
        field.Children.Add(new TextBlock { Text = title, TextWrapping = TextWrapping.Wrap });
        var combo = new ComboBox { HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch };
        for (var i = 0; i < captions.Count; i++) combo.Items.Add(new ComboBoxItem { Content = captions[i], IsEnabled = i != retainedOnly });
        combo.SelectedIndex = selected;
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(combo, title);
        combo.SelectionChanged += (_, _) => { if (combo.SelectedIndex < 0 || combo.SelectedIndex == retainedOnly) return; save(combo.SelectedIndex); shell.SaveSettings(); };
        field.Children.Add(combo);
        field.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        return field;
    }

    UIElement PathField(string title, string description, string value, Action<string> save)
    {
        var field = new StackPanel { Spacing = 6 };
        field.Children.Add(new TextBlock { Text = title, TextWrapping = TextWrapping.Wrap });
        var input = new TextBox { Text = value };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(input, title);
        input.LostFocus += (_, _) => { save(input.Text.Trim()); shell.SaveSettings(); };
        field.Children.Add(input);
        field.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        return field;
    }

    async Task InspectAsync()
    {
        var path = await shell.PickFileAsync(".zip");
        if (path is null) return;
        status.Text = "Reading package files and configuration…";
        PackageInspection inspection;
        try { inspection = await shell.Service.InspectPackageAsync(path); }
        catch (InvalidOperationException error) { status.Text = error.Message; return; }
        status.Text = "Inspection complete. No game files have changed.";

        var panel = new StackPanel { Spacing = 12, MinWidth = 600 };
        panel.Children.Add(Prefs.Row(inspection.Name, inspection.Confidence + $" · Detected format: {inspection.Family} · {inspection.FileCount} files · {inspection.ExpandedBytes / 1048576.0:0.0} MiB expanded", glyph: ""));
        var fields = new Dictionary<string, Func<string>>();
        var settings = new PreferencesGroup("Package Settings");
        string[] counts = ["auto", "0", "1", "2", "3", "4", "5"];
        foreach (var parameter in inspection.Parameters)
        {
            if (parameter.Key == "OverrideInterpolationCount")
            {
                var (row, combo) = Prefs.ComboRow("MFG multiplier", parameter.Origin, ["Auto", "Off", "2×", "3×", "4×", "5×", "6×"], Math.Max(0, Array.IndexOf(counts, parameter.Value)));
                fields[parameter.Key] = () => counts[Math.Max(0, combo.SelectedIndex)];
                settings.Add(row);
            }
            else
            {
                var (row, entry) = Prefs.EntryRow(parameter.Label, parameter.Origin, parameter.Value);
                entry.MinWidth = 120;
                fields[parameter.Key] = () => entry.Text.Trim();
                settings.Add(row);
            }
        }
        panel.Children.Add(settings);
        if (inspection.Warnings.Count > 0) panel.Children.Add(Prefs.Label(string.Join("\n", inspection.Warnings), "ForgeCaptionDimTextStyle"));
        foreach (var (file, text) in inspection.Instructions)
            panel.Children.Add(new Expander
            {
                Header = file + " · original instructions · commands are never executed", HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Content = new TextBox { Text = text, IsReadOnly = true, TextWrapping = TextWrapping.Wrap, AcceptsReturn = true, MaxHeight = 220 },
            });
        panel.Children.Add(Prefs.Label("Your editable instructions / review notes (never executed)"));
        var notes = new TextBox
        {
            Text = string.Join("\n\n", inspection.Instructions.Select(i => i.Text)), AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 100, MaxHeight = 200,
        };
        panel.Children.Add(notes);
        if (!inspection.Deployable)
            panel.Children.Add(Prefs.Label("This layout has no verified deployment adapter yet. It can be inspected, but nothing will be installed.", "ForgeCaptionDimTextStyle"));
        var trust = new CheckBox { Content = "I trust the source of this package" };
        panel.Children.Add(trust);

        var dialog = shell.NewDialog();
        dialog.Title = "Review your package";
        dialog.Resources["ContentDialogMaxWidth"] = 820.0;
        dialog.Content = new ScrollViewer { Content = panel, MaxHeight = 620 };
        dialog.PrimaryButtonText = "Use reviewed package";
        dialog.IsPrimaryButtonEnabled = false;
        dialog.CloseButtonText = "Cancel";
        trust.Checked += (_, _) => dialog.IsPrimaryButtonEnabled = inspection.Deployable;
        trust.Unchecked += (_, _) => dialog.IsPrimaryButtonEnabled = false;
        PackageChoice? choice = null;
        dialog.PrimaryButtonClick += async (_, args) =>
        {
            var deferral = args.GetDeferral();
            try
            {
                choice = await shell.Service.UseCustomPackageAsync(inspection, fields.ToDictionary(f => f.Key, f => f.Value()), trust.IsChecked == true, notes.Text);
            }
            catch (InvalidOperationException error)
            {
                args.Cancel = true;
                status.Text = error.Message;
                panel.Children.Add(Prefs.Label(error.Message));
            }
            finally { deferral.Complete(); }
        };
        await dialog.ShowAsync();
        if (choice is null) { shell.Service.DiscardReview(new EngineReview(inspection.Token, "package", "", "", "", [], [])); return; }
        shell.SelectPackage("custom", choice.Presets);
        await LoadAsync();
    }
}
