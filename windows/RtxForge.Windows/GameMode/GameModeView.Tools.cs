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
        // As on the desktop: NR packages, the MFG packages that pair with Skynizz NR, unified packages, your own.
        body.Children.Add(ui.P(catalog.Status + ".", .85));
        static string Tested(IReadOnlyList<string>? verified) => verified is { Count: > 0 }
            ? " Tested in games on " + string.Join(" and ", verified.Select(CrossOs.Name)) + "." : " Experimental.";
        UIElement UseRow(PackageOption item)
        {
            var current = shell.Settings.RuntimeProvider == item.Id;
            return ui.RowButton(item.Name, current ? "In use" : item.Available ? "Use for DLSS games" : "Unavailable", () =>
            {
                shell.SelectPackage(item.Id);
                Toast("Package selected for DLSS games. Select games, then choose Install Features.");
                Render(keepFocus: true);
            }, description: item.Version + " · " + (item.Available ? item.Summary : item.Reason) + Tested(item.Verified), enabled: item.Available && !current);
        }
        var pairs = Views.PackagesPage.PairsWithMfg.Contains(shell.Settings.RuntimeProvider);
        var nr = catalog.Packages.Where(p => Views.PackagesPage.PairsWithMfg.Contains(p.Id)).Select(UseRow).ToList();
        nr.AddRange(catalog.Packages.Where(p => Views.PackagesPage.WithoutDlss.Contains(p.Id)).Select(item => (UIElement)ui.RowButton(item.Name,
            "Used automatically", () => { }, description: item.Version + " · Games without DLSS. " + item.Summary + Tested(item.Verified), enabled: false)));
        var mfg = Views.PackagesPage.MfgPackages.Select(package =>
        {
            var current = pairs && shell.Settings.MfgProvider == package.Id;
            return (UIElement)ui.RowButton(package.Name, current ? "In use" : pairs ? "Use with Skynizz NR" : "Needs Skynizz NR", () =>
            {
                shell.Settings.MfgProvider = package.Id; shell.SaveSettings();
                Render(keepFocus: true);
            }, description: package.Version + " · " + package.Summary + Tested(package.Verified), enabled: pairs && !current);
        }).ToList();
        var unified = catalog.Packages.Where(p => !Views.PackagesPage.WithoutDlss.Contains(p.Id) && !Views.PackagesPage.PairsWithMfg.Contains(p.Id))
            .Select(UseRow).ToList();
        unified.Add(ui.RowButton("Your own package", "Coming soon", () => { },
            description: "Inspect a ZIP archive and review its settings before using it.", enabled: false));
        foreach (var (title, lead, rows) in new (string, string, List<UIElement>)[]
        {
            ("NR packages", "Neural rendering. Choose one for games with DLSS; Feeder NR covers games without DLSS automatically.", nr),
            ("MFG packages", pairs ? "Native NVIDIA frame generation for Skynizz NR." : "These pair with Skynizz NR.", mfg),
            ("Unified packages", "NR and frame generation in one package, for games with DLSS.", unified),
        })
        {
            SectionTitle(body, title, lead);
            body.Children.Add(ui.Group(rows, t.Card));
        }
        if (catalog.Community.Count > 0)
        {
            SectionTitle(body, "Other community projects", "Explore other projects. These sources aren't curated install options.");
            body.Children.Add(ui.Group(catalog.Community.Select(source => (UIElement)ui.RowButton(source.Name, "Open",
                () => MainWindow.OpenUri(source.Url), description: source.Note)).ToList(), t.Card));
        }
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
