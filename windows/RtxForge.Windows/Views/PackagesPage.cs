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
        page.Children.Add(status);
        page.Children.Add(body);
        Content = new ScrollViewer { Content = page, HorizontalScrollMode = ScrollMode.Disabled };
        SizeChanged += (_, e) => page.Padding = PageMargins.For(e.NewSize.Width);
        Loaded += async (_, _) => await LoadAsync();
    }

    /// <summary>Packages for games without DLSS; the engine uses them automatically, whatever DLSS package is chosen.</summary>
    internal static readonly string[] WithoutDlss = ["feeder"];
    /// <summary>NR packages that pair with a separate MFG package. Every other DLSS package brings its own MFG (unified).</summary>
    internal static readonly string[] PairsWithMfg = ["skynizz"];

    /// <summary>
    /// MFG packages for Skynizz NR, as Settings.MfgProvider values. All three use NVIDIA's own DLSS Frame
    /// Generation; each presented 4 generated frames in Halo on an RTX 4070 (Forge Lab, 2026-10-22).
    /// </summary>
    internal static readonly (string Id, string Name, string Version, string Summary, string[] Verified)[] MfgPackages =
    [
        ("universal", "Universal MFG", "1.6.1 · OptiScaler plugin",
            "Recommended. Keeps NVIDIA's DLSS Frame Generation and unlocks 3x to 6x on RTX 40. The multiplier and Dynamic MFG stay in the rtxForge Overlay.", ["windows"]),
        ("integrated", "Integrated Ada unlock", "Built into the Skynizz bridge",
            "Patches NVIDIA's DLSS Frame Generation for 3x to 6x on RTX 40, with no extra plugin.", ["windows"]),
        ("mfg-unlock", "MFG Unlock", "1.4.5 · ReShade add-on",
            "Raises NVIDIA's DLSS Frame Generation multiplier through ReShade. The rtxForge Overlay can't change its multiplier while you play, and it isn't offered for inZOI yet.",["windows"]),
    ];

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
        nr.Children.Add(Heading("NR packages", "Neural rendering. Choose one for games with DLSS; Feeder NR covers games without DLSS automatically."));
        foreach (var item in catalog.Packages.Where(p => PairsWithMfg.Contains(p.Id)))
        {
            nr.Children.Add(PackageCard(item));
            if (shell.Settings.RuntimeProvider == item.Id) nr.Children.Add(new Expander
            {
                Header = "Skynizz settings", Content = SkynizzSettings(catalog), HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
            });
        }
        foreach (var item in catalog.Packages.Where(p => WithoutDlss.Contains(p.Id))) nr.Children.Add(AutomaticCard(item));
        if (catalog.Packages.Any(p => p.Id == "feeder")) nr.Children.Add(FeederSetup());
        columns.Children.Add(nr);

        var mfg = new StackPanel { Spacing = 12 };
        mfg.Children.Add(Heading("MFG packages", pairs
            ? "Native NVIDIA frame generation for Skynizz NR, in games with DLSS Frame Generation. Applies to new installs; restore a game before switching its MFG package."
            : "These pair with Skynizz NR. Your package for DLSS games brings its own frame generation."));
        foreach (var package in MfgPackages) mfg.Children.Add(MfgCard(package, pairs));
        columns.Children.Add(mfg);
        body.Children.Add(columns);

        // Whole packages: NR and MFG together.
        var unified = new StackPanel { Spacing = 12, Margin = new Thickness(0, 12, 0, 0) };
        unified.Children.Add(Heading("Unified packages", "NR and frame generation in one package, for games with DLSS. Choosing one replaces Skynizz NR for those games."));
        var unifiedCards = new PresetColumns(360, 2) { ColumnSpacing = 16, RowSpacing = 16 };
        foreach (var item in catalog.Packages.Where(p => !WithoutDlss.Contains(p.Id) && !PairsWithMfg.Contains(p.Id))
                     .OrderByDescending(p => p.Id == shell.Settings.RuntimeProvider))
            unifiedCards.Children.Add(PackageCard(item));
        unified.Children.Add(unifiedCards);
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
        var feeder = Section("Feeder setup", "Choose your local stack once; rtxForge keeps a verified copy, and installation copies ReShade, Feeder, RenoDX and shaders for you.");
        var paths = new PresetColumns(360, 2) { ColumnSpacing = 16, RowSpacing = 12 };
        paths.Children.Add(FolderField("Local stack folder", "Your ReShade, Feeder, RenoDX and shader files. Only needed until rtxForge keeps a copy.",
            shell.Settings.FeederSource, path => shell.Settings.FeederSource = path));
        paths.Children.Add(FolderField("Original backups folder", "Original manifests and backups used to recognize existing setups. rtxForge keeps verified copies.",
            shell.Settings.FeederBackups, path => shell.Settings.FeederBackups = path));
        feeder.Children.Add(paths);
        var kept = Prefs.Label("Checking stored Feeder files…", "ForgeCaptionDimTextStyle");
        var keep = new Button { Content = "Keep a copy in rtxForge", HorizontalAlignment = HorizontalAlignment.Left };
        ToolTipService.SetToolTip(keep, "Verify both folders and store their files with rtxForge. Game files are not changed.");
        async Task ShowKeptAsync(bool import)
        {
            keep.IsEnabled = false;
            try
            {
                var storage = await shell.Service.FeederStorageAsync(import ? NonEmpty(shell.Settings.FeederSource) : null,
                    import ? NonEmpty(shell.Settings.FeederBackups) : null);
                kept.Text = (storage.Recipe is null ? "No stack stored yet" : "Stored stack · " + storage.Recipe
                    + (storage.NrVersion is null ? "" : " · NR model " + storage.NrVersion))
                    + $" · {storage.Backups} original backup{(storage.Backups == 1 ? "" : "s")} kept";
            }
            catch (InvalidOperationException error) { kept.Text = error.Message; }
            finally { keep.IsEnabled = true; }
        }
        static string? NonEmpty(string value) => string.IsNullOrWhiteSpace(value) ? null : value;
        keep.Click += async (_, _) => await ShowKeptAsync(true);
        feeder.Children.Add(kept);
        feeder.Children.Add(keep);
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
        settings.Children.Add(Choice("NR model preset", "Performance (B) uses preset 2 with compatible 310.9.16 models.",
            ["Automatic", "Legacy (A)", "Performance (B)"], Math.Clamp(shell.Settings.NrPreset ?? 0, 0, 2),
            index => shell.Settings.NrPreset = index));
        return settings;
    }

    Border PackageCard(PackageOption item)
    {
        var current = shell.Settings.RuntimeProvider == item.Id;
        var content = new Grid { RowSpacing = 12 };
        content.RowDefinitions.Add(new() { Height = GridLength.Auto });
        content.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        content.RowDefinitions.Add(new() { Height = GridLength.Auto });
        content.Children.Add(Section(item.Name, item.Version));
        var description = new StackPanel { Spacing = 8 };
        description.Children.Add(Prefs.Label(item.Summary));
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

    Border MfgCard((string Id, string Name, string Version, string Summary, string[] Verified) package, bool pairs)
    {
        var current = pairs && shell.Settings.MfgProvider == package.Id;
        var content = Section(package.Name, package.Version);
        content.Children.Add(Prefs.Label(package.Summary));
        var use = Prefs.ActionButton(current ? "In use" : "Use with Skynizz NR", (_, _) =>
        {
            shell.Settings.MfgProvider = package.Id; shell.SaveSettings(); _ = LoadAsync();
        }, accent: package.Id == "universal" && pairs && !current);
        use.IsEnabled = pairs && !current && !shell.Busy;
        content.Children.Add(Footer(package.Verified, use));
        var card = Card(content);
        if (!pairs) card.Opacity = .55;
        return card;
    }

    /// <summary>A package for games without DLSS: always on, so it has no Use button.</summary>
    Border AutomaticCard(PackageOption item)
    {
        var content = Section(item.Name, item.Version);
        content.Children.Add(Prefs.Label(item.Summary));
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
        var brush = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"];
        foreach (var os in verified ?? [])
        {
            var pill = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
            pill.Children.Add(OsMark.Create(os, 12, brush));
            pill.Children.Add(Prefs.Label(CrossOs.Name(os), "ForgeCaptionDimTextStyle"));
            var tip = "Tested in games on " + CrossOs.Name(os);
            ToolTipService.SetToolTip(pill, tip); Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(pill, tip);
            marks.Children.Add(pill);
        }
        if (marks.Children.Count == 0) marks.Children.Add(Prefs.Label("Not yet tested in games", "ForgeCaptionDimTextStyle"));
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

    UIElement FolderField(string title, string description, string value, Action<string> save)
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
