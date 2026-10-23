using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.GameMode;

/// <summary>Packages and Extras: the desktop pages of the same names, sized for the couch.</summary>
public sealed partial class GameModeView
{
    string globalNr = "leave", globalMfg = "leave";

    /// <summary>A scrolling page with the desktop title and lead.</summary>
    (Grid Page, StackPanel Body) ToolPage(string title, string lead)
    {
        var side = PageInset;
        var page = new Grid { RowSpacing = t.Px(20), Padding = new Thickness(side, t.Px(24), side, t.Px(20)) };
        page.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        page.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        var head = new StackPanel { Spacing = t.Px(10) };
        head.Children.Add(ui.H1(title, 1.4));
        head.Children.Add(ui.P(lead, .78));
        page.Children.Add(head);
        var body = new StackPanel { Spacing = t.Px(24), Padding = new Thickness(t.Px(4), t.Px(4), t.Px(4), t.Px(8)) };
        var scroll = new ScrollViewer { Content = body, HorizontalScrollMode = ScrollMode.Disabled };
        Grid.SetRow(scroll, 1); page.Children.Add(scroll);
        return (page, body);
    }

    // ---------- Packages ----------

    UIElement BuildPackages()
    {
        var (page, body) = ToolPage("Packages", "Choose what rtxForge installs. Every game change is reviewed before it is applied.");
        body.Children.Add(ui.P("Loading packages…"));
        _ = FillPackagesAsync(body);
        return page;
    }

    async Task FillPackagesAsync(StackPanel body)
    {
        PackageCatalog catalog;
        try { catalog = await shell.Service.PackagesAsync(); }
        catch (InvalidOperationException error) { body.Children.Clear(); body.Children.Add(ui.P(error.Message)); return; }
        if (page != "packages") return;
        body.Children.Clear();
        // The desktop layout: NR and MFG packages side by side, then unified packages,
        // then your own package beside the community projects.
        body.Children.Add(ui.P(catalog.Status + ".", .85));
        Border UseCard(PackageOption item)
        {
            var current = shell.Settings.RuntimeProvider == item.Id;
            var (name, version) = Views.PackagesPage.CardTitle(item, shell.Settings);
            return PackageCard(name, version, (item.Available ? item.Summary : item.Reason) + "\nGraphics API: " + string.Join(" · ", item.GraphicsApis ?? []), item.Verified,
                ui.Button(current ? "In use" : "Use for DLSS games", () =>
                {
                    shell.SelectPackage(item.Id);
                    Toast("Package selected for DLSS games. Select games, then choose Install Features.");
                    Render(keepFocus: true);
                }, GmKind.Card, .8, item.Available && !current));
        }
        var pairs = Views.PackagesPage.PairsWithMfg.Contains(shell.Settings.RuntimeProvider);
        var columns = new Controls.PresetColumns(t.Px(560), 2) { ColumnSpacing = t.Px(24), RowSpacing = t.Px(24) };
        var nr = new StackPanel { Spacing = t.Px(16) };
        var automatic = catalog.Packages.FirstOrDefault(p => Views.PackagesPage.WithoutDlss.Contains(p.Id))?.Name;
        SectionTitle(nr, "NR packages", "Neural rendering. Choose one for games with DLSS" + (automatic is null ? "." : $"; {automatic} covers games without DLSS automatically."));
        foreach (var item in catalog.Packages.Where(p => Views.PackagesPage.PairsWithMfg.Contains(p.Id))) nr.Children.Add(UseCard(item));
        foreach (var item in catalog.Packages.Where(p => Views.PackagesPage.WithoutDlss.Contains(p.Id)))
            nr.Children.Add(PackageCard(item.Name, item.Version, item.Summary + "\nGraphics API: " + string.Join(" · ", item.GraphicsApis ?? []), item.Verified,
                ui.Button(item.Available ? "Used automatically" : "Unavailable", () => { }, GmKind.Card, .8, false)));
        var mfg = new StackPanel { Spacing = t.Px(16) };
        var pairName = Views.PackagesPage.PairName(catalog);
        SectionTitle(mfg, "MFG packages", pairs ? $"Native NVIDIA frame generation for {pairName}." : $"These pair with {pairName}.");
        foreach (var package in Views.PackagesPage.MfgPackages)
        {
            var current = pairs && shell.Settings.MfgProvider == package.Id;
            mfg.Children.Add(PackageCard(package.Name, Views.PackagesPage.MfgVersion(package.Id, package.Kind, catalog), package.Summary + "\nGraphics API: DirectX 12", package.Verified,
                ui.Button(current ? "In use" : "Use with " + pairName, () =>
                {
                    shell.Settings.MfgProvider = package.Id; shell.SaveSettings();
                    Render(keepFocus: true);
                }, GmKind.Card, .8, pairs && !current)));
        }
        columns.Children.Add(nr); columns.Children.Add(mfg);
        body.Children.Add(columns);

        SectionTitle(body, "Unified packages", "NR and frame generation in one package, for games with DLSS. Choosing one replaces your NR package for those games.");
        var unified = DetailColumns();
        foreach (var item in catalog.Packages.Where(p => !Views.PackagesPage.WithoutDlss.Contains(p.Id) && !Views.PackagesPage.PairsWithMfg.Contains(p.Id)))
            unified.Children.Add(UseCard(item));
        body.Children.Add(unified);

        var more = DetailColumns();
        more.Children.Add(DetailFact("Your own package · Coming soon", "Inspect a ZIP archive and review its settings before using it. Instructions are never run.",
            ui.Button("Choose archive", () => { }, GmKind.Card, .8, false), "").With(card => card.Opacity = .55));
        if (catalog.Community.Count > 0)
        {
            var community = new StackPanel { Spacing = t.Px(16) };
            community.Children.Add(DetailHeading("Other community projects", ""));
            community.Children.Add(ui.P("Explore other projects. These sources aren't curated install options.", .8));
            community.Children.Add(ui.Group(catalog.Community.Select(source => (UIElement)ui.RowButton(source.Name, "Open",
                () => MainWindow.OpenUri(source.Url), description: source.Note)).ToList(), t.Panel));
            more.Children.Add(DetailPlate(community));
        }
        body.Children.Add(more);
    }

    /// <summary>A package card as on the desktop: name, version, summary, then tested-OS badges and its action.</summary>
    Border PackageCard(string name, string version, string summary, IReadOnlyList<string>? verified, Button action)
    {
        var card = new Grid { RowSpacing = t.Px(12) };
        card.RowDefinitions.Add(new() { Height = GridLength.Auto });
        card.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        card.RowDefinitions.Add(new() { Height = GridLength.Auto });
        var heading = new StackPanel { Spacing = t.Px(4) };
        heading.Children.Add(ui.Heading(name, .92, wrap: true));
        heading.Children.Add(ui.Text(version, .74, t.Muted, wrap: true));
        card.Children.Add(heading);
        var text = ui.P(summary, .8); Grid.SetRow(text, 1); card.Children.Add(text);
        var footer = new Grid { ColumnSpacing = t.Px(12) };
        footer.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        footer.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var badges = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(8), VerticalAlignment = VerticalAlignment.Center };
        if (verified is { Count: > 0 })
            foreach (var os in verified)
            {
                // The OS this PC runs is filled with the accent, as on the desktop.
                var here = os == "windows";
                var badge = ui.Badge(CrossOs.Name(os).ToUpperInvariant(), here ? GmTheme.Accent : t.Card, here ? GmTheme.AccentInk : t.Fg, .58);
                ((StackPanel)badge.Child).Children.Insert(0, Controls.OsMark.Create(os, t.Em(.58), GmTheme.B(here ? GmTheme.AccentInk : t.Fg)));
                badges.Children.Add(badge);
            }
        else badges.Children.Add(ui.Badge("EXPERIMENTAL", t.Card, t.Muted, .58));
        footer.Children.Add(badges);
        action.HorizontalAlignment = HorizontalAlignment.Right; action.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(action, 1); footer.Children.Add(action);
        Grid.SetRow(footer, 2); card.Children.Add(footer);
        return DetailPlate(card);
    }

    // ---------- Extras ----------

    UIElement BuildExtras()
    {
        var (page, body) = ToolPage("Extras", "Tools for your whole library. Every game change is reviewed before it is applied.");
        var preview = shell.Service.IsPreview;
        var engine = shell.Service as Services.EngineForgeService;
        // The desktop's layout: the one-button tools share a row, the longer tools below.
        var actions = DetailColumns(3);
        actions.Children.Add(DetailFact("Update the rtxForge Overlay", "Bring the in-game overlay in your installed games up to date. Tuning and restore backups are kept.",
            ui.Button("Review overlay updates", () => _ = ReviewOverlayPackages(), GmKind.Card, .8, enabled: engine is not null), ""));
        actions.Children.Add(DetailFact("Update DLSS files", "Replace older DLSS files across your library. Originals are backed up.",
            ui.Button("Review games", () => _ = RunOperationAsync("update-dlss", shell.Games.Where(g => !g.Blocked).ToList()), GmKind.Card, .8, enabled: !preview), ""));
        actions.Children.Add(DetailFact("Undo previous changes", "Restore the files from an earlier install, update or restore.",
            ui.Button("Show changes", () => _ = PreviousChangesAsync(), GmKind.Card, .8), ""));
        body.Children.Add(actions);

        var tools = DetailColumns();
        var once = new StackPanel { Spacing = t.Px(20) };
        once.Children.Add(DetailHeading("One-time changes", ""));
        once.Children.Add(ui.P("Turn neural rendering or frame generation on or off, or set the multiplier, in every game with a package installed.", .8));
        once.Children.Add(ui.Group(
        [
            Choice("Neural rendering", "Choose only the setting to change across installed games.", ["leave", "off", "on"],
                ["Leave as is", "Off", "On"], () => globalNr, v => globalNr = v),
            Choice("Multi-Frame Generation", "Feeder games support NR only. Leave other games as they are, or choose a new mode.",
                ["leave", "0", "2", "3", "4", "5", "6", "-1"], ["Leave as is", "Off", "2×", "3×", "4×", "5×", "6×", "Follow game"], () => globalMfg, v => globalMfg = v),
        ]));
        once.Children.Add(ui.Button("Review changes", () => _ = ReviewGlobalAsync(), GmKind.Primary, .85, enabled: engine is not null && !preview)
            .With(b => { b.HorizontalAlignment = HorizontalAlignment.Right; Key(b, "extras-global"); }));
        tools.Children.Add(DetailPlate(once));
        tools.Children.Add(DetailFact("App storage", "Downloads, backups and caches rtxForge keeps. Clean up what no game needs.",
            ui.Button("View usage", () => _ = AppStorageAsync(), GmKind.Card, .8), ""));
        body.Children.Add(tools);
        return page;
    }

    async Task ReviewGlobalAsync()
    {
        if (shell.Service is not Services.EngineForgeService engine) return;
        var changes = new JsonObject();
        if (globalNr != "leave") changes["nr"] = globalNr == "on";
        if (globalMfg != "leave") changes["mfg"] = int.Parse(globalMfg, System.Globalization.CultureInfo.InvariantCulture);
        if (changes.Count == 0) { Toast("Choose a setting to change first."); return; }
        if (await RunReviewAsync("One-time changes", () => engine.ReviewGlobalControlsAsync(changes)) is { Errors.Count: 0 })
        {
            await engine.ReloadCompanionPresetsAsync();
            await Services.OverlayHelper.CommandAsync("reload-presets", start: false);
            globalNr = globalMfg = "leave";
            Render(keepFocus: true);
        }
    }
}
