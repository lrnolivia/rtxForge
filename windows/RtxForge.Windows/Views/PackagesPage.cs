using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Views;

/// <summary>
/// Packages: one package for games with DLSS, chosen here, and one for games without
/// DLSS, used automatically (Feeder NR today). Custom packages are coming soon.
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
    static readonly string[] WithoutDlss = ["feeder"];
    bool DlssPackageChosen(PackageCatalog catalog) => catalog.Packages.Any(p => p.Id == shell.Settings.RuntimeProvider && !WithoutDlss.Contains(p.Id));

    async Task LoadAsync()
    {
        PackageCatalog catalog;
        try { catalog = await shell.Service.PackagesAsync(); }
        catch (InvalidOperationException error) { status.Text = error.Message; return; }
        status.Text = catalog.Status;
        body.Children.Clear();

        var dlss = new StackPanel { Spacing = 12, Margin = new Thickness(0, 12, 0, 0) };
        dlss.Children.Add(Heading("Games with DLSS", DlssPackageChosen(catalog)
            ? "Installs neural rendering and frame generation in games with native DLSS. Restore a game's original files before switching its package."
            : "Choose the package rtxForge installs in games with native DLSS."));
        var packages = new PresetColumns(360, 2) { ColumnSpacing = 12, RowSpacing = 12 };
        foreach (var item in catalog.Packages.Where(p => !WithoutDlss.Contains(p.Id))
                     .OrderByDescending(p => p.Id == shell.Settings.RuntimeProvider).ThenByDescending(p => p.Recommended))
            packages.Children.Add(PackageCard(item));
        dlss.Children.Add(packages);
        body.Children.Add(dlss);
        if (shell.Settings.RuntimeProvider == "skynizz") body.Children.Add(SkynizzComponents(catalog));

        var other = new StackPanel { Spacing = 12, Margin = new Thickness(0, 12, 0, 0) };
        other.Children.Add(Heading("Games without DLSS", "Used automatically for supported games without native DLSS, alongside your DLSS package. More packages are planned."));
        foreach (var item in catalog.Packages.Where(p => WithoutDlss.Contains(p.Id))) other.Children.Add(AutomaticCard(item));
        body.Children.Add(other);
        if (catalog.Packages.Any(p => p.Id == "feeder"))
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
            other.Children.Add(new Expander
            {
                Header = "Feeder setup", Content = feeder, HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
            });
        }

        // Custom packages are not supported yet: shown, greyed out.
        var sources = new PresetColumns(400, catalog.Community.Count > 0 ? 2 : 1) { ColumnSpacing = 12, RowSpacing = 12 };
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

    UIElement SkynizzComponents(PackageCatalog catalog)
    {
            var components = new PresetColumns(400, 2) { ColumnSpacing = 12, RowSpacing = 12 };
            var nr = Section("NR package", "Skynizz for DirectX 12 games with DLSS. A compatible local NR model is required.");
            var release = catalog.Packages.FirstOrDefault(p => p.Id == "skynizz")?.Version.Split(' ', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault();
            var releases = new List<string> { "latest" };
            var captions = new List<string> { "Latest supported (recommended)" };
            if (release is not null && release.StartsWith('v') && Version.TryParse(release[1..], out _))
            {
                releases.Add(release); captions.Add(release + " · keep this release");
            }
            var saved = shell.Settings.SkynizzVersion;
            var savedOnly = !releases.Contains(saved);
            if (savedOnly) { releases.Add(saved); captions.Add("Saved release · " + saved); }
            nr.Children.Add(Choice("Release", "Repairs keep each game's installed release. New installs use this selection.", captions,
                releases.IndexOf(saved), index => shell.Settings.SkynizzVersion = releases[index], savedOnly ? captions.Count - 1 : -1));
            nr.Children.Add(Choice("NR model preset", "Performance (B) uses preset 2 with compatible 310.9.16 models.",
                ["Automatic", "Legacy (A)", "Performance (B)"], Math.Clamp(shell.Settings.NrPreset ?? 0, 0, 2),
                index => shell.Settings.NrPreset = index));
            components.Children.Add(Card(nr));
            var mfg = Section("MFG package", "For NR + MFG installs in games with native DLSS Frame Generation.");
            string[] mfgComponents = ["universal", "integrated", "mfg-unlock"];
            mfg.Children.Add(Choice("MFG component", "Applies to new installs. Restore an existing package before switching components.",
                ["Universal MFG 1.6.1 (recommended)", "Integrated Ada bridge", "MFG Unlock 1.4.4 (preview)"],
                Math.Max(0, Array.IndexOf(mfgComponents, shell.Settings.MfgProvider)),
                index => shell.Settings.MfgProvider = mfgComponents[index]));
            mfg.Children.Add(Prefs.Label("Universal loads as an OptiScaler plugin and replaces the integrated unlock; OptiScaler keeps the multiplier and Dynamic controls. Upstream lists RTX 30 and 40 support (RTX 20 experimental); rtxForge has not yet validated it in games. MFG Unlock uses ReShade and remains a preview.", "ForgeCaptionDimTextStyle"));
            components.Children.Add(Card(mfg));
            return components;
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
        use.HorizontalAlignment = HorizontalAlignment.Right;
        ToolTipService.SetToolTip(use, item.Reason);
        Grid.SetRow(use, 2); content.Children.Add(use);
        return Card(content);
    }

    /// <summary>A package for games without DLSS: always on, so it has no Use button.</summary>
    static Border AutomaticCard(PackageOption item)
    {
        var content = Section(item.Name, item.Version);
        content.Children.Add(Prefs.Label(item.Summary));
        content.Children.Add(Prefs.Label(item.Available ? "Used automatically" : item.Reason, "ForgeCaptionDimTextStyle"));
        return Card(content);
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
