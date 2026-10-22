using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using RtxForge.Windows.ViewModels;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    Game? detailsGame;
    string detailsSection = "Overview";
    string? libraryFocusKey;
    bool presetsExpanded;
    /// <summary>Unsaved Test Result choice on the Notes section (Choice re-renders the page).</summary>
    string? notesStatus;
    string? notesDraft;
    static readonly string[] Sections = ["Overview", "Features", "DLSS Files", "Tools", "Appearance", "Notes"];

    void OpenDetails(Game game)
    {
        libraryFocusKey = FocusKey(FocusManager.GetFocusedElement(XamlRoot) as DependencyObject);
        detailsGame = game;
        detailsSection = "Overview";
        presetsExpanded = false;
        notesStatus = null;
        notesDraft = null;

        page = "details";
        Render();
    }

    /// <summary>Back from Details restores the Library view, scroll and the card that opened it.</summary>
    void CloseDetails()
    {
        page = "library";
        Render();
        if (libraryFocusKey is { } key)
            DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
                FindByKey(body, key)?.Focus(FocusState.Keyboard));
    }

    UIElement BuildDetails(Game g)
    {
        var navWidth = t.Px(ActualWidth <= 1050 ? 220 : ActualWidth <= 1500 ? 254 : 268);
        var side = PageInset;
        var heroWidth = Math.Max(t.Px(420), ActualWidth - navWidth - side);
        var heroHeight = Math.Clamp(heroWidth * .38, t.Px(360), t.Px(620));
        var grid = new Grid { RowSpacing = t.Px(t.Compact ? 12 : 22), Padding = new Thickness(0, 0, 0, t.Px(8)) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(navWidth + side) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });

        // The section rail spans the workspace; the hero belongs to the content column.
        var hero = new Grid { Background = GmTheme.B(t.View), Height = heroHeight };
        Grid.SetColumn(hero, 1);
        if ((g.HeroPath ?? g.CapsulePath) is { } heroSource)
        {
            var art = new FadedImage { ChosenFocus = FadedImage.Stored(shell.Settings.GameHeroFocus, g.Id) };
            art.SetSource(heroSource);
            hero.Children.Add(art);
        }
        var identity = new Grid
        {
            ColumnSpacing = t.Px(20), VerticalAlignment = VerticalAlignment.Bottom,
            Padding = new Thickness(t.Px(36), t.Px(24), side, t.Px(t.Compact ? 20 : 28)),
        };
        identity.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        identity.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var posterHeight = Math.Clamp(heroHeight * .48, t.Px(120), t.Px(260));
        var poster = new Border
        {
            Height = posterHeight, Width = Math.Round(posterHeight * 2 / 3), CornerRadius = new CornerRadius(t.Px(10)),
            BorderThickness = new Thickness(t.Px(2)), BorderBrush = GmTheme.B(t.Line), Background = GmTheme.B(t.Card),
            VerticalAlignment = VerticalAlignment.Bottom,
            Visibility = g.PosterPath is null ? Visibility.Collapsed : Visibility.Visible,
        };
        if (GameItem.Image(g.PosterPath) is { } posterImage)
            poster.Child = new Border { CornerRadius = new CornerRadius(t.Px(7)), Background = new ImageBrush { ImageSource = posterImage, Stretch = Stretch.UniformToFill } };
        identity.Children.Add(poster);
        var heroBody = new Grid { ColumnSpacing = t.Px(24), RowSpacing = t.Px(10), VerticalAlignment = VerticalAlignment.Bottom };
        heroBody.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        heroBody.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        for (var row = 0; row < 3; row++) heroBody.RowDefinitions.Add(new() { Height = GridLength.Auto });
        var head = new StackPanel { Spacing = t.Px(6) };
        var status = g.AdoptionAvailable ? "Installed · Adoption available" : g.OfflineOnly ? "Installed · Offline only"
            : g.Blocked ? g.BlockedStatus : g.UsesFeeder ? g.Installed ? "Feeder NR" : "Available · Feeder NR"
            : g.InstalledOnLinux ? "Installed on Linux" : g.Installed ? g.Profile ?? "Configured" : "Ready for Features";
        head.Children.Add(ui.Badge(status, t.Card, t.Fg, .62));
        var title = ui.Text(g.Name, color: t.Fg, wrap: true, maxLines: 2);
        title.FontFamily = (FontFamily)Application.Current.Resources["ForgeHeroFontFamily"];
        title.FontSize = Math.Clamp(heroWidth / t.S / 26, 32, 64) * t.S * (g.Name.Length > 28 ? .78 : 1);
        title.LineHeight = title.FontSize * 1.1;
        head.Children.Add(title);
        Grid.SetColumnSpan(head, 2); heroBody.Children.Add(head);
        var text = new StackPanel { Spacing = t.Px(8), VerticalAlignment = VerticalAlignment.Bottom };
        // Credits, then the badges inline after them, wrapping as the hero narrows.
        var badges = new WrapRow { Spacing = t.Px(10), LineSpacing = t.Px(6) };
        var creditsText = ui.Text(GameCredits.Line(g), .72, t.Muted);
        creditsText.TextTrimming = TextTrimming.CharacterEllipsis;
        creditsText.VerticalAlignment = VerticalAlignment.Center;
        creditsText.Visibility = creditsText.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
        ToolTipService.SetToolTip(creditsText, GameCredits.Tooltip(g));
        badges.Children.Add(creditsText);
        var sourceBadge = ui.Badge(g.Library == "Steam" ? "STEAM" : "NON-STEAM", t.Card, t.Fg, .58, g.Library == "Steam" ? "" : null);
        badges.Children.Add(sourceBadge);
        // Which rtxForge installed it (Linux game_mode: "Installed on Linux" with the rtx-os mark).
        if (g.Installed && g.InstalledOn is "linux" or "windows")
        {
            var osBadge = ui.Badge(CrossOs.Name(g.InstalledOn).ToUpperInvariant(), t.Card, t.Fg, .58);
            ((StackPanel)osBadge.Child).Children.Insert(0, OsMark.Create(g.InstalledOn, t.Em(.58), GmTheme.B(t.Fg)));
            badges.Children.Add(osBadge);
        }
        badges.Children.Add(ui.Badge(g.Tested ? "TESTED" : "UNTESTED", t.Card, t.Muted, .58, g.Tested ? "" : ""));
        text.Children.Add(badges);
        var summaryText = ui.Text(g.Summary ?? "", .70, t.Muted, wrap: true, maxLines: 2);
        summaryText.MaxWidth = t.Px(640); summaryText.HorizontalAlignment = HorizontalAlignment.Left;
        ToolTipService.SetToolTip(summaryText, g.Summary);
        summaryText.Visibility = string.IsNullOrWhiteSpace(g.Summary) ? Visibility.Collapsed : Visibility.Visible;
        text.Children.Add(summaryText);
        if (shell.Settings.SteamMetadata && (g.Summary is null || g.Developer is null || g.Release is null))
            _ = FillStoreInfoAsync(g, creditsText, summaryText);
        Grid.SetRow(text, 1); heroBody.Children.Add(text);
        // The same action hierarchy as Desktop: primary, restore, then More.
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(10), VerticalAlignment = VerticalAlignment.Bottom };
        var install = ui.Button(Glyph("", g.InstallLabel), () => _ = RunOperationAsync("install", [g]),
            GmKind.Primary, 0.76, enabled: !g.Blocked || g.AdoptionAvailable, radius: 10, minHeight: 46);
        Key(install, "hero-install");
        actions.Children.Add(install);
        var restore = ui.Button(Glyph("", "Restore Original Files"), () => _ = RunOperationAsync("uninstall", [g]),
            GmKind.Card, 0.76, enabled: g.Installed && !g.AdoptionAvailable, radius: 10, minHeight: 46);
        Key(restore, "hero-restore");
        actions.Children.Add(restore);
        var more = ui.Button(ui.Icon("", .85), () => OpenDetailsActions(g), GmKind.Card,
            radius: 10, padding: new Thickness(t.Px(14)), minHeight: 46, name: "More game options");
        Key(more, "hero-more"); ToolTipService.SetToolTip(more, "More options"); actions.Children.Add(more);
        Grid.SetRow(actions, 1); Grid.SetColumn(actions, 1); heroBody.Children.Add(actions);
        heroBody.SizeChanged += (_, e) =>
        {
            foreach (var button in actions.Children) button.Measure(new global::Windows.Foundation.Size(double.PositiveInfinity, double.PositiveInfinity));
            var actionWidth = actions.Children.Cast<FrameworkElement>().Sum(button => button.DesiredSize.Width) + actions.Spacing * (actions.Children.Count - 1);
            var stack = e.NewSize.Width < actionWidth;
            actions.Orientation = stack ? Orientation.Vertical : Orientation.Horizontal;
            foreach (var button in actions.Children.OfType<Button>()) button.HorizontalAlignment = stack ? HorizontalAlignment.Stretch : HorizontalAlignment.Left;
            var narrow = e.NewSize.Width < actionWidth + t.Px(364);
            Grid.SetRow(actions, narrow ? 2 : 1); Grid.SetColumn(actions, narrow ? 0 : 1);
            Grid.SetColumnSpan(actions, narrow ? 2 : 1);
            actions.HorizontalAlignment = stack ? HorizontalAlignment.Stretch : narrow ? HorizontalAlignment.Left : HorizontalAlignment.Right;
        };
        Grid.SetColumn(heroBody, 1); identity.Children.Add(heroBody);
        hero.Children.Add(identity);
        var back = ui.Button(Glyph("", "Back to Library"), CloseDetails, GmKind.Transparent, 0.78, radius: 12,
            padding: new Thickness(t.Px(18), t.Px(10), t.Px(18), t.Px(10)), minHeight: t.Compact ? 38 : 46);
        back.HorizontalAlignment = HorizontalAlignment.Left;
        Key(back, "details-back");
        grid.Children.Add(hero);

        // ----- Section navigation -----
        var nav = new StackPanel { Spacing = t.Px(8), Padding = new Thickness(t.Px(20), t.Px(20), t.Px(20), t.Px(20)) };
        nav.Children.Add(back);
        nav.Children.Add(ui.Text("Game Details", 1.06, weight: FontWeights.SemiBold).With(h => h.Margin = new Thickness(t.Px(16), t.Px(8), 0, t.Px(t.Compact ? 12 : 20))));
        var navButtons = new List<(Button Button, string Section)>();
        foreach (var section in Sections)
        {
            var active = section == detailsSection;
            var button = ui.Button(ui.IconLabel(GameSections.Glyph(section), section), () => { detailsSection = section; Render(); pendingFocusKey = "gm_section-" + section; },
                GmKind.Transparent, 0.88, radius: 12, padding: new Thickness(t.Px(18), t.Px(12), t.Px(18), t.Px(12)), minHeight: t.Compact ? 46 : 60);
            button.HorizontalAlignment = HorizontalAlignment.Stretch;
            button.HorizontalContentAlignment = HorizontalAlignment.Left;
            ui.MenuFocus(button);
            Key(button, "section-" + section);
            navButtons.Add((button, section));
            nav.Children.Add(button);
        }
        var navScroll = new ScrollViewer { Content = nav, Background = GmTheme.B(t.Panel), HorizontalScrollMode = ScrollMode.Disabled };
        Grid.SetRowSpan(navScroll, 2);
        grid.Children.Add(navScroll);

        // ----- Section body -----
        var content = new StackPanel { Spacing = t.Px(24), Padding = new Thickness(t.Px(32), t.Px(16), side, t.Px(20)) };
        BuildSection(g, content);
        var workspace = new StackPanel();
        var heroSpacer = new Border();
        workspace.Children.Add(heroSpacer); workspace.Children.Add(content);
        var scroll = new ScrollViewer
        {
            Content = workspace, HorizontalScrollMode = ScrollMode.Disabled,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };
        Grid.SetRowSpan(scroll, 2); Grid.SetColumn(scroll, 1); grid.Children.Add(scroll);
        grid.Children.Remove(hero);
        Grid.SetRowSpan(hero, 2); hero.VerticalAlignment = VerticalAlignment.Top;
        grid.Children.Add(hero);
        var expandedWidth = heroWidth;
        var collapsing = new CollapsingHero(scroll, hero, heroSpacer, progress =>
        {
            var fullPoster = Math.Clamp(heroHeight * .48, t.Px(120), t.Px(260));
            poster.Height = fullPoster + (t.Px(100) - fullPoster) * progress;
            poster.Width = Math.Round(poster.Height * 2 / 3);
            var fullTitle = Math.Clamp(expandedWidth / t.S / 26, 32, 64) * t.S * (g.Name.Length > 28 ? .78 : 1);
            title.FontSize = fullTitle + (Math.Min(fullTitle, t.Px(32)) - fullTitle) * progress;
            title.LineHeight = title.FontSize * 1.1;
            text.Opacity = 1 - progress;
            text.Visibility = progress >= .75 ? Visibility.Collapsed : Visibility.Visible;
        });
        void ResizeHero(double width)
        {
            if (width <= 0) return;
            expandedWidth = width;
            poster.Visibility = g.PosterPath is not null && width >= t.Px(620) ? Visibility.Visible : Visibility.Collapsed;
            heroHeight = Math.Clamp(width * .38, t.Px(360), t.Px(620));
            collapsing.SetRange(heroHeight, t.Px(width < t.Px(620) ? 290 : 210));
        }
        var lastWidth = 0d;
        hero.SizeChanged += (_, e) =>
        {
            if (Math.Abs(lastWidth - e.NewSize.Width) < .5) return;
            lastWidth = e.NewSize.Width; ResizeHero(lastWidth);
        };
        ResizeHero(heroWidth);

        // Accent: poster stroke, title, active section (tint + readable title).
        _ = DetailsAccentAsync(g, poster, title, sourceBadge, install, navButtons);
        if (initialFocus is null) initialFocus = navButtons.First(b => b.Section == detailsSection).Button;
        return grid;
    }

    void OpenDetailsActions(Game g)
    {
        var rows = new List<UIElement>
        {
            ui.RowButton("Update DLSS", null, () => { CloseModal(); _ = RunOperationAsync("update-dlss", [g]); }, enabled: !g.Blocked),
        };
        if (g.AdoptionAvailable) rows.Add(ui.RowButton("Adopt with rtxForge", null, () => { CloseModal(); _ = shell.ReviewAdoptionAsync([g]); }));
        if (g.OfflineOnly) rows.Add(ui.RowButton("Launch offline", null, () => { CloseModal(); _ = shell.LaunchOfflineAsync(g); }));
        rows.Add(ui.RowButton("Open Folder", null, () => { CloseModal(); _ = shell.OpenGameFolderAsync(g); }, enabled: !shell.Service.IsPreview && Directory.Exists(g.Location)));
        rows.Add(ui.RowButton("Remove from library", null, () => { CloseModal(); ConfirmRemoveGames([g]); }, danger: true));
        ShowModal("Game options", ui.Group(rows), [ui.Button("Back", CloseModal, GmKind.Card, .85)], CloseModal, 900);
    }

    async Task DetailsAccentAsync(Game g, Border poster, TextBlock title, Border sourceBadge, Button install, List<(Button Button, string Section)> nav)
    {
        var renderedUi = ui;
        var colors = t.GameColors(await ArtAccent.ForGameAsync(g));
        if (page != "details" || detailsGame?.Id != g.Id || !ReferenceEquals(ui, renderedUi)) return;
        ui.FocusBrush.Color = colors.Title;
        poster.BorderBrush = GmTheme.B(colors.Accent);
        title.Foreground = GmTheme.B(colors.Title);
        if (install.IsEnabled) { install.Background = GmTheme.B(colors.Accent); install.Foreground = GmTheme.B(colors.Ink); }
        sourceBadge.Background = GmTheme.B(colors.Pill);
        foreach (var child in ((StackPanel)sourceBadge.Child).Children)
        {
            if (child is TextBlock tb) tb.Foreground = GmTheme.B(colors.Ink);
            if (child is FontIcon fi) fi.Foreground = GmTheme.B(colors.Ink);
        }
        foreach (var (button, section) in nav)
            if (section == detailsSection)
            {
                button.Background = GmTheme.B(colors.Tint);
                button.Foreground = GmTheme.B(colors.TintText);
            }
    }

    Grid DetailHeading(string title, string? glyph = null)
    {
        glyph ??= title switch
        {
            "Features" or "Feeder NR" or "Neural rendering" => "\uE9E9",
            "Installation" or "File Management" => "\uE896", "DLSS Files" => "\uE8A5",
            "Tools" => "\uE90F", "Notes" => "\uE70B", "Appearance" or "Custom Artwork" => "\uE790",
            "Performance" => "\uE9D9", "Sharpening" => "\uE7AD", "Multi-Frame Generation" => "\uE7F4",
            _ => "\uE713",
        };
        var row = new Grid { ColumnSpacing = t.Px(14) };
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.Children.Add(ui.Icon(glyph, 1.05).With(icon => icon.VerticalAlignment = VerticalAlignment.Center));
        var label = ui.Text(title, .96, weight: FontWeights.SemiBold, wrap: true);
        Grid.SetColumn(label, 1); row.Children.Add(label); return row;
    }

    void SectionTitle(StackPanel content, string title, string? description = null)
    {
        var block = new StackPanel { Spacing = t.Px(10) };
        block.Children.Add(DetailHeading(title));
        if (description is not null) block.Children.Add(ui.P(description));
        content.Children.Add(block);
    }

    Controls.PresetColumns DetailColumns(int maximum = 2) => new(t.Px(340), maximum)
    { ColumnSpacing = t.Px(16), RowSpacing = t.Px(16) };

    Border DetailPlate(UIElement content) => new()
    { Background = GmTheme.B(t.Card), CornerRadius = new CornerRadius(t.Px(16)), Padding = new Thickness(t.Px(28)), Child = content };

    Border DetailFact(string title, string value, Button? action = null, string? glyph = null)
    {
        var lines = new StackPanel { Spacing = t.Px(16) };
        var heading = new Grid { ColumnSpacing = t.Px(12) };
        heading.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        heading.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        if (glyph is not null) heading.Children.Add(ui.Icon(glyph, 1.05).With(icon => icon.VerticalAlignment = VerticalAlignment.Center));
        var label = ui.Text(title, .88, weight: FontWeights.SemiBold, wrap: true);
        Grid.SetColumn(label, 1); heading.Children.Add(label); lines.Children.Add(heading);
        lines.Children.Add(ui.P(value, .8));
        if (action is not null) { action.HorizontalAlignment = HorizontalAlignment.Right; lines.Children.Add(action); }
        return DetailPlate(lines).With(card => card.VerticalAlignment = VerticalAlignment.Top);
    }

    void BuildSection(Game g, StackPanel content)
    {
        switch (detailsSection)
        {
            case "Features":
                if (g.IsFeeder)
                {
                    SectionTitle(content, "Feeder NR", "Your existing tuning is preserved. Use ReShade's NR panel in the running game to adjust passes, resolution, tone and structure. Frame generation is unavailable for this route.");
                    var feederActions = DetailColumns();
                    foreach (var action in new[] {
                        ui.RowButton("Update Feeder NR", null, () => _ = RunOperationAsync("install", [g]), glyph: "\uE896", enabled: !g.Blocked || g.AdoptionAvailable),
                        ui.RowButton("Restore Original Files", null, () => _ = RunOperationAsync("uninstall", [g]), danger: true, glyph: "\uE7A7", enabled: g.Installed),
                    }) feederActions.Children.Add(ui.Group([action], t.Card));
                    content.Children.Add(feederActions);
                    break;
                }
                SectionTitle(content, "Features", g.InstalledOnLinux
                    ? $"Saved: {g.Profile ?? "Configured"}. Installed with rtxForge on Linux; it already loads on Windows. Set Up for Windows hands it to rtxForge here to repair, retune or restore."
                    : g.Installed
                    ? $"Saved: {g.Profile ?? "Configured"}. The rendered effect still needs an in-game check."
                    : g.Blocked ? g.BlockedReason ?? "This game is not supported." : "Not installed. Review every file change before installing.");
                var expander = ui.Button(new Grid().With(row =>
                {
                    row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                    row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                    row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                    row.ColumnSpacing = t.Px(16);
                    row.Children.Add(ui.Icon(presetsExpanded ? "" : "", 0.7));
                    var label = ui.Text("Presets", 1, weight: FontWeights.SemiBold);
                    Grid.SetColumn(label, 1);
                    row.Children.Add(label);
                    var state = ui.Text(presetsExpanded ? "Expanded" : "Collapsed", 0.7, t.Muted);
                    Grid.SetColumn(state, 2);
                    row.Children.Add(state);
                }), () => { presetsExpanded = !presetsExpanded; Render(keepFocus: true); }, GmKind.Transparent, 1, radius: 12,
                    padding: new Thickness(t.Px(18)), minHeight: 0);
                expander.HorizontalAlignment = HorizontalAlignment.Stretch;
                expander.HorizontalContentAlignment = HorizontalAlignment.Stretch;
                Key(expander, "presets-expander");
                content.Children.Add(expander);
                if (presetsExpanded)
                {
                    var tuning = shell.GameTuning(g);
                    var (rows, value) = PresetRows(tuning, g.Installed && !g.Blocked, g.RuntimeProvider != "skynizz", embedded: true,
                        dynamicSupported: g.DynamicMfgAvailable);
                    content.Children.Add(ui.P("Only this game changes. Review the changes before applying."));
                    foreach (var row in rows) content.Children.Add(row);
                    var apply = ui.Button("Apply to this game", () => _ = RunOperationAsync("apply", [g], value()), GmKind.Primary, 0.85,
                        enabled: g.Installed && !g.Blocked);
                    content.Children.Add(apply.With(b => b.HorizontalAlignment = HorizontalAlignment.Right));
                }
                SectionTitle(content, "Installation");
                var installActions = DetailColumns(3);
                foreach (var action in new[] {
                    ui.RowButton(g.InstallLabel, null, () => _ = RunOperationAsync("install", [g]), glyph: "\uE896", enabled: !g.Blocked),
                    ui.RowButton("Repair Feature Files", null, () => _ = RunOperationAsync("install", [g]), glyph: "\uE90F", enabled: g.Installed && !g.Blocked),
                    ui.RowButton("Restore Original Files", null, () => _ = RunOperationAsync("uninstall", [g]), danger: true, glyph: "\uE7A7", enabled: g.Installed),
                }) installActions.Children.Add(ui.Group([action], t.Card));
                content.Children.Add(installActions);
                break;

            case "DLSS Files":
                SectionTitle(content, "DLSS Files", "Updater backups are previous copies, not proof of the version currently shipped by the game.");
                content.Children.Add(DetailFact("Installed DLSS version", g.DlssVersion ?? "Checked during update", glyph: "\uE8A5"));
                SectionTitle(content, "File Management");
                var restoreDlss = ui.RowButton("Restore original DLSS files", null, () => _ = RestoreDlssAsync(g), danger: true, glyph: "\uE7A7", enabled: !g.Blocked);
                var fileActions = DetailColumns();
                foreach (var action in new[] {
                    ui.RowButton("Update DLSS files", null, () => _ = RunOperationAsync("update-dlss", [g]), glyph: "\uE8AB", enabled: !g.Blocked),
                    restoreDlss,
                }) fileActions.Children.Add(ui.Group([action], t.Card));
                content.Children.Add(fileActions);
                var inventory = new StackPanel { Spacing = t.Px(16) };
                content.Children.Add(inventory);
                _ = FillDlssInventoryAsync(g, inventory, restoreDlss);
                break;

            case "Tools":
                SectionTitle(content, "Tools", "Check NR or add ReShade to this game. Existing graphics files are kept safe.");
                var tools = DetailColumns();
                foreach (var (glyph, label, enabled, action) in new (string, string, bool, Action)[]
                {
                    ("", "Diagnose NR", g.Installed, () => _ = DiagnoseAsync(g)),
                    ("", "Install ReShade", !shell.Service.IsPreview && !g.Blocked, () => _ = InstallExtraAsync(g, "reshade")),
                    ("", "Install Add-on", !shell.Service.IsPreview && !g.Blocked, () => _ = InstallExtraAsync(g, "addon")),
                    ("", "ReShade Downloads", true, () => MainWindow.OpenUri("https://reshade.me/")),
                })
                {
                    var tile = new StackPanel { Spacing = t.Px(10), HorizontalAlignment = HorizontalAlignment.Center };
                    tile.Children.Add(ui.Icon(glyph, 1.05).With(i => i.HorizontalAlignment = HorizontalAlignment.Center));
                    tile.Children.Add(ui.Text(label, 1, weight: FontWeights.SemiBold).With(x => x.HorizontalAlignment = HorizontalAlignment.Center));
                    var button = ui.Button(tile, action, GmKind.Card, 1, enabled, radius: 14, minHeight: t.Compact ? 90 : 116);
                    button.HorizontalAlignment = HorizontalAlignment.Stretch;
                    tools.Children.Add(button);
                }
                content.Children.Add(tools);
                content.Children.Add(ui.P("Use an extracted x64 ReShade DLL or .addon64 file from a source you trust. Each install is reviewed first and can be restored.", 0.83));
                var installed = new StackPanel { Spacing = t.Px(16) };
                content.Children.Add(installed);
                _ = FillExtraRecordsAsync(g, installed);
                break;

            case "Notes":
                SectionTitle(content, "Notes", "Kept with this game in rtxForge.");
                var notes = new TextBox
                {
                    Text = notesDraft ?? g.Notes, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = t.Px(160),
                    FontSize = t.Em(0.9), PlaceholderText = "What worked, what didn't, settings you used",
                    Background = GmTheme.B(t.Panel), Foreground = GmTheme.B(t.Fg), BorderBrush = GmTheme.B(t.Line),
                    CornerRadius = new CornerRadius(t.Px(12)), Padding = new Thickness(t.Px(20)),
                };
                notes.TextChanged += (_, _) => notesDraft = notes.Text;
                ui.Focusable(notes);
                Key(notes, "notes");
                var noteCards = DetailColumns();
                noteCards.Children.Add(new StackPanel { Spacing = t.Px(16), Children = { DetailHeading("Notes", "\uE70B"), notes } });
                var testSettings = new StackPanel { Spacing = t.Px(20) };
                testSettings.Children.Add(DetailHeading("Testing", "\uE9D9"));
                // game_notes: the test result and notes are saved with this game (shared with Desktop UI).
                notesStatus ??= g.TestStatus;
                testSettings.Children.Add(ui.Group(
                [
                    Choice("Test Result", "Bench excludes this game from bulk installation and repair.", ["Untested", "Working", "Problem", "Bench"],
                        ["Untested", "Working", "Problem", "Bench"], () => notesStatus ?? g.TestStatus, v => notesStatus = v),
                ]));
                testSettings.Children.Add(ui.P("Controller text entry uses the Windows touch keyboard or Steam's keyboard.", 0.83));
                var noteActions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(12), HorizontalAlignment = HorizontalAlignment.Right };
                noteActions.Children.Add(ui.Button(g.TestActive ? "Finish Test" : "Start Test", () => _ = RecordTestAsync(g), GmKind.Card, 0.85,
                    enabled: !shell.Service.IsPreview).With(b => Key(b, "notes-test")));
                noteActions.Children.Add(ui.Button("Save Notes", () => _ = SaveNotesAsync(g, notesStatus ?? g.TestStatus, notes.Text), GmKind.Primary, 0.85).With(b => Key(b, "notes-save")));
                testSettings.Children.Add(noteActions);
                noteCards.Children.Add(DetailPlate(testSettings)); content.Children.Add(noteCards);
                break;

            case "Appearance":
                SectionTitle(content, "Accent Color", "Pick a suggestion from this game's artwork. Your own picks are kept.");
                var current = shell.Settings.GameAccents.GetValueOrDefault(g.Id);
                content.Children.Add(DetailFact("Game Accent", current?.ToUpperInvariant() ?? "Automatic · from artwork", glyph: "\uE790"));
                var swatches = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(16) };
                content.Children.Add(swatches);
                _ = FillSwatchesAsync(g, swatches, current);
                content.Children.Add(ui.Button("Use artwork color", () =>
                {
                    shell.Settings.GameAccents.Remove(g.Id);
                    shell.Settings.Save();
                    shell.NotifyGamesChanged();
                }, GmKind.Card, 0.85, enabled: current is not null).With(b => b.HorizontalAlignment = HorizontalAlignment.Left));
                CustomArtworkSection(g, content);
                break;

            default:
                if (g.AdoptionAvailable) content.Children.Add(DetailFact("Adoption available", GameOverview.AdoptionNote,
                    ui.Button("Review Adoption", () => _ = shell.ReviewAdoptionAsync([g]), GmKind.Card, .8), "\uE930"));
                if (g.OfflineOnly) content.Children.Add(DetailFact("Offline-only features", GameOverview.OfflineNote,
                    ui.Button("Launch offline", () => _ = shell.LaunchOfflineAsync(g), GmKind.Card, .8), "\uE72E"));
                if (g.Blocked) content.Children.Add(DetailFact("rtxForge will not modify this game", g.BlockedReason ?? "Unsupported", glyph: "\uE7BA"));
                else if (g.InstalledOnLinux) content.Children.Add(DetailFact("Installed on Linux", GameOverview.LinuxNote, glyph: "\uE946"));
                var overviewFacts = GameOverview.Facts(g);
                var info = DetailColumns(overviewFacts.Count > 3 ? 4 : 3);
                foreach (var fact in overviewFacts) info.Children.Add(DetailFact(fact.Title, fact.Value, glyph: fact.Glyph));
                content.Children.Add(info);
                content.Children.Add(DetailFact("Game folder", g.Location, ui.Button("Open folder", () => _ = shell.OpenGameFolderAsync(g),
                    GmKind.Card, .8, enabled: !shell.Service.IsPreview && Directory.Exists(g.Location)), "\uE838"));
                break;
        }
    }

    /// <summary>Update hero metadata in place, preserving any unsaved preset edits below it.</summary>
    async Task FillStoreInfoAsync(Game g, TextBlock credits, TextBlock summary)
    {
        if (await SteamStoreInfo.FillAsync(g, shell.Settings.SteamMetadata)
            && detailsGame == g && page == "details")
        {
            credits.Text = GameCredits.Line(g);
            credits.Visibility = credits.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
            ToolTipService.SetToolTip(credits, GameCredits.Tooltip(g));
            summary.Text = g.Summary ?? "";
            summary.Visibility = summary.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
            ToolTipService.SetToolTip(summary, g.Summary);
        }
    }

    /// <summary>The shared accent suggestions, as focusable swatches.</summary>
    async Task FillSwatchesAsync(Game g, StackPanel swatches, string? current)
    {
        var source = g.PosterPath ?? g.CapsulePath ?? g.HeroPath;
        if (source is null) { swatches.Children.Add(ui.P("No artwork to sample.")); return; }
        IReadOnlyList<ArtAccent.AccentSuggestion> suggestions;
        try { suggestions = await ArtAccent.SuggestionsAsync(await ArtAccent.LoadAsync(source)); }
        catch (Exception error) when (error is HttpRequestException or IOException or TaskCanceledException or System.Runtime.InteropServices.COMException)
        {
            swatches.Children.Add(ui.P("Artwork is unavailable right now."));
            return;
        }
        foreach (var suggestion in suggestions)
        {
            var hex = ArtAccent.Hex(suggestion.Color);
            var chosen = string.Equals(hex, current, StringComparison.OrdinalIgnoreCase);
            var dot = new Border
            {
                Width = t.Px(56), Height = t.Px(56), CornerRadius = new CornerRadius(t.Px(28)), Padding = new Thickness(t.Px(4)),
                BorderThickness = new Thickness(t.Px(3)), BorderBrush = GmTheme.B(chosen ? t.Focus : Microsoft.UI.Colors.Transparent),
                HorizontalAlignment = HorizontalAlignment.Center,
                Child = new Microsoft.UI.Xaml.Shapes.Ellipse { Fill = GmTheme.B(suggestion.Color) },
            };
            var cell = new StackPanel { Spacing = t.Px(8) };
            cell.Children.Add(dot);
            cell.Children.Add(ui.Text(suggestion.Label, 0.72, t.Muted).With(x => x.HorizontalAlignment = HorizontalAlignment.Center));
            var button = ui.Button(cell, () =>
            {
                shell.Settings.GameAccents[g.Id] = hex;
                shell.Settings.Save();
                shell.NotifyGamesChanged();
            }, GmKind.Transparent, 1, radius: 16, padding: new Thickness(t.Px(10)), minHeight: 0, name: $"{suggestion.Label} {hex}");
            Key(button, "swatch-" + suggestion.Label);
            swatches.Children.Add(button);
        }
    }

    /// <summary>Compact controller cards retain the overlay vocabulary and original values.</summary>
    (List<UIElement> Rows, Func<Tuning> Value) PresetRows(Tuning initial, bool enabled = true, bool legacy = false, Action? changed = null, bool embedded = false, bool dynamicSupported = true, bool installation = false)
    {
        var values = FeatureControlSchema.Resolve(initial);
        var advanced = shell.Settings.OverlayControls == "classic";
        var controls = FeatureControlSchema.Shared.Controls;
        FeatureControl Definition(string key) => controls.Single(f => f.Key == key);
        Controls.PresetColumns Pair(params UIElement[] children)
        {
            var columns = new Controls.PresetColumns(t.Px(270), 2) { ColumnSpacing = t.Px(24), RowSpacing = t.Px(20) };
            foreach (var child in children) columns.Children.Add(child); return columns;
        }
        Border Card(string title, params UIElement[] children)
        {
            var section = new StackPanel { Spacing = t.Px(20), Padding = new Thickness(embedded ? 0 : t.Px(28)) };
            if (title.Length > 0) section.Children.Add(DetailHeading(title));
            foreach (var child in children) section.Children.Add(child);
            return new Border { Child = section, Background = embedded ? null : GmTheme.B(t.Panel), CornerRadius = new CornerRadius(t.Px(16)), VerticalAlignment = VerticalAlignment.Top };
        }
        UIElement Field(FeatureControl field)
        {
            var available = enabled && FeatureControlSchema.Available(field, shell.Mode, legacy);
            var label = field.Key == "enabled" ? "Enable NR on launch" : field.Caption(advanced);
            var shown = ui.Text("", .78, available ? t.Fg : t.DisabledFg);
            shown.HorizontalAlignment = HorizontalAlignment.Center;
            shown.VerticalAlignment = VerticalAlignment.Center;
            var line = new Grid { ColumnSpacing = t.Px(8) };
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Button? button = null;
            void Refresh()
            {
                var current = FeatureControlSchema.Number(values, field);
                // Keep the runtime's numeric units in both control styles.
                shown.Text = field.Key == "skin" && current < 0 && !advanced ? "Follow structure" : field.Display(current, true);
                if (button is not null) Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, label + ": " + shown.Text);
            }
            void Adjust(int direction)
            {
                if (!available) return;
                var current = FeatureControlSchema.Number(values, field);
                var next = field.Kind == "toggle" ? current == 0 ? 1 : 0
                    : field.Values.Length > 0 ? field.Values[Math.Clamp(Array.IndexOf(field.Values, current) + direction, 0, field.Values.Length - 1)]
                    : Math.Clamp(Math.Round(current + direction * field.Step, 2), field.Min, field.Max);
                FeatureControlSchema.Put(values, field, next);
                Refresh();
                changed?.Invoke();
            }
            Border Step(string glyph, int direction)
            {
                var target = new Border
                {
                    MinWidth = t.Px(38), MinHeight = t.Px(42), Background = GmTheme.B(Microsoft.UI.Colors.Transparent),
                    Child = ui.Icon(glyph, .55, available ? t.Muted : t.DisabledFg),
                };
                target.Tapped += (_, e) => { Adjust(direction); e.Handled = true; };
                return target;
            }
            var discrete = field.Kind is "toggle" or "choice";
            if (discrete)
            {
                Grid.SetColumnSpan(shown, 2); line.Children.Add(shown);
                var arrow = ui.Icon("", .55); Grid.SetColumn(arrow, 2); line.Children.Add(arrow);
            }
            else
            {
                line.Children.Add(Step("", -1));
                Grid.SetColumn(shown, 1); line.Children.Add(shown);
                var right = Step("", 1); Grid.SetColumn(right, 2); line.Children.Add(right);
            }
            void Choose()
            {
                var numbers = field.Kind == "toggle" ? new double[] { 0, 1 } : field.Values;
                var captions = field.Kind == "toggle" ? new[] { "Off", "On" } : field.Choices;
                OpenChoiceMenu(button!, label, captions, Math.Max(0, Array.IndexOf(numbers, FeatureControlSchema.Number(values, field))), i =>
                {
                    FeatureControlSchema.Put(values, field, numbers[i]); Refresh(); changed?.Invoke();
                });
            }
            button = ui.Button(line, discrete ? Choose : null, GmKind.Card, .78, available,
                radius: 12, padding: new Thickness(t.Px(12), t.Px(4), t.Px(12), t.Px(4)), minHeight: 54);
            button.HorizontalAlignment = HorizontalAlignment.Stretch;
            button.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            button.BorderBrush = GmTheme.B(t.Line);
            button.BorderThickness = new Thickness(t.Px(1));
            if (!discrete) button.Tag = new Adjustable(Adjust);
            GmUi.NoLift(button);
            ui.Focusable(button, 0);
            Key(button, "preset-field-" + field.Key);
            Refresh();
            var fieldColumn = new StackPanel { Spacing = t.Px(8) };
            fieldColumn.Children.Add(ui.Text(label, .84, available ? t.Fg : t.DisabledFg, FontWeights.SemiBold, wrap: true));
            fieldColumn.Children.Add(button);
            if (!available) fieldColumn.Children.Add(ui.P("Unavailable for this package.", .66));
            else if (field.Key == "skin") fieldColumn.Children.Add(ui.P("−1 follows local structure.", .66));
            return fieldColumn;
        }
        UIElement Choices(string key)
        {
            var definition = Definition(key);
            var line = new Controls.PresetColumns(t.Px(70), definition.Values.Length) { ColumnSpacing = t.Px(4), RowSpacing = t.Px(4) };
            var buttons = new List<Button>();
            void Select(double value)
            {
                FeatureControlSchema.Put(values, definition, value);
                for (var i = 0; i < buttons.Count; i++)
                {
                    buttons[i].Background = GmTheme.B(definition.Values[i] == value ? t.SegmentSelected : t.Card);
                    buttons[i].Foreground = GmTheme.B(definition.Values[i] == value ? t.ActiveFg : t.Fg);
                    Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(buttons[i], definition.Label + " " + definition.Choices[i] + (definition.Values[i] == value ? " selected" : ""));
                }
                changed?.Invoke();
            }
            for (var i = 0; i < definition.Values.Length; i++)
            {
                var number = definition.Values[i];
                var button = ui.Button(definition.Choices[i], () => Select(number), GmKind.Card, .85,
                    enabled && FeatureControlSchema.Available(definition, shell.Mode, legacy), radius: 8,
                    padding: new Thickness(t.Px(10)), minHeight: 42);
                button.HorizontalAlignment = HorizontalAlignment.Stretch;
                Key(button, "preset-" + key + "-" + i); buttons.Add(button); line.Children.Add(button);
            }
            foreach (var button in buttons) { GmUi.NoLift(button); ui.Focusable(button, -4); }
            Select(FeatureControlSchema.Number(values, definition));
            return new Border { Child = line, Background = GmTheme.B(t.Card), BorderBrush = GmTheme.B(t.Line),
                BorderThickness = new Thickness(t.Px(1)), CornerRadius = new CornerRadius(t.Px(12)), Padding = new Thickness(t.Px(4)) };
        }
        UIElement Disclosure(string title, params UIElement[] children)
        {
            var body = new StackPanel { Spacing = t.Px(12), Visibility = Visibility.Collapsed };
            foreach (var child in children) body.Children.Add(child);
            var icon = ui.Icon("", .7);
            var heading = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(12) };
            heading.Children.Add(icon); heading.Children.Add(ui.Text(title, .9, weight: FontWeights.SemiBold));
            Button? button = null;
            button = ui.Button(heading, () =>
            {
                body.Visibility = body.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible;
                icon.Glyph = body.Visibility == Visibility.Visible ? "" : "";
                Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button!, title + (body.Visibility == Visibility.Visible ? " expanded" : " collapsed"));
            }, GmKind.Transparent, radius: 8, padding: new Thickness(t.Px(8)), minHeight: 42, name: title + " collapsed");
            Key(button, "preset-disclosure-" + title);
            var group = new StackPanel { Spacing = t.Px(12) }; group.Children.Add(button); group.Children.Add(body); return group;
        }
        UIElement MfgControls()
        {
            var state = new MfgPreset(values);
            var allowed = enabled && shell.Mode != "nr-only";
            var header = new Grid { ColumnSpacing = t.Px(20) };
            header.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            header.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
            var title = ui.Text("Multi-Frame Generation", .96, weight: FontWeights.SemiBold, wrap: true);
            title.VerticalAlignment = VerticalAlignment.Center; header.Children.Add(title);
            var toggle = new ToggleSwitch { OnContent = "On", OffContent = "Off", MinWidth = 0,
                IsOn = state.Enabled, IsEnabled = allowed, Foreground = GmTheme.B(t.Fg), FontSize = t.Em(.8) };
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(toggle, "Multi-Frame Generation");
            ui.Focusable(toggle); Key(toggle, "preset-mfg-enabled"); Grid.SetColumn(toggle, 1); header.Children.Add(toggle);
            var tabs = new List<Button>(); var ratios = new List<Button>();
            var caption = ui.P("Multiplier", .75); var description = ui.P("", .75);
            var ratioGroup = new StackPanel { Spacing = t.Px(8) };
            void Refresh()
            {
                void Selection(Button button, bool selected, bool canSelect, string label)
                {
                    button.Background = GmTheme.B(selected ? t.SegmentSelected : t.Card);
                    button.Foreground = GmTheme.B(selected ? t.ActiveFg : t.Fg);
                    button.IsEnabled = canSelect;
                    Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, "Multi-Frame Generation " + label + (selected ? " selected" : ""));
                }
                for (var i = 0; i < tabs.Count; i++)
                    Selection(tabs[i], state.Mode == i, allowed && state.Enabled && (i != 2 || !legacy && dynamicSupported), MfgPreset.Modes[i]);
                for (var i = 0; i < ratios.Count; i++)
                    Selection(ratios[i], state.Multiplier == MfgPreset.Multipliers[i], allowed && state.Enabled, MfgPreset.Multipliers[i] + "×");
                ratioGroup.Visibility = state.Enabled && state.Mode != 0 ? Visibility.Visible : Visibility.Collapsed;
                caption.Text = state.Mode == 2 ? "Maximum multiplier" : "Multiplier";
                description.Text = allowed ? state.Description : "Unavailable for this package.";
            }
            void Change(Action change) { change(); state.Store(values); Refresh(); changed?.Invoke(); }
            UIElement Segments(string[] captions, List<Button> buttons, Action<int> select, string key)
            {
                var line = new Controls.PresetColumns(t.Px(70), captions.Length) { ColumnSpacing = t.Px(4), RowSpacing = t.Px(4) };
                for (var i = 0; i < captions.Length; i++)
                {
                    var index = i;
                    var button = ui.Button(captions[i], () => Change(() => select(index)), GmKind.Card, .85,
                        radius: 8, padding: new Thickness(t.Px(10)), minHeight: 42);
                    button.HorizontalAlignment = HorizontalAlignment.Stretch;
                    Key(button, "preset-mfg-" + key + "-" + i); GmUi.NoLift(button); ui.Focusable(button, -4);
                    buttons.Add(button); line.Children.Add(button);
                }
                return new Border { Child = line, Background = GmTheme.B(t.Card), BorderBrush = GmTheme.B(t.Line),
                    BorderThickness = new Thickness(t.Px(1)), CornerRadius = new CornerRadius(t.Px(12)), Padding = new Thickness(t.Px(4)) };
            }
            var modes = Segments(MfgPreset.Modes, tabs, state.SetMode, "mode");
            ratioGroup.Children.Add(caption);
            ratioGroup.Children.Add(Segments(MfgPreset.Multipliers.Select(n => n + "×").ToArray(), ratios,
                i => state.SetMultiplier(MfgPreset.Multipliers[i]), "ratio"));
            toggle.Toggled += (_, _) => Change(() =>
            {
                if (toggle.IsOn && state.Mode == 2 && (legacy || !dynamicSupported)) state.SetMode(1);
                state.SetEnabled(toggle.IsOn);
            });
            ToolTipService.SetToolTip(tabs[2], "Requires the integrated MFG package and a compatible game and driver.");
            Refresh();
            return Card("", header, modes, ratioGroup, description);
        }
        if (installation)
        {
            var main = new Controls.PresetColumns(t.Px(420), 2) { ColumnSpacing = t.Px(24), RowSpacing = t.Px(20) };
            main.Children.Add(MfgControls());
            main.Children.Add(Card("Neural rendering", Field(Definition("enabled")), Choices("style"), Field(Definition("intensity"))));
            var performanceFields = controls.Where(f => f.Group == "Performance").Select(Field).ToArray();
            var morePerformance = new List<UIElement>();
            for (var i = 0; i < performanceFields.Length; i += 2)
                morePerformance.Add(i + 1 < performanceFields.Length ? Pair(performanceFields[i], performanceFields[i + 1]) : performanceFields[i]);
            var more = Disclosure("More settings",
                Pair(Field(Definition("preset")), Field(Definition("passes"))),
                Disclosure("DLSS presets", Pair(Field(Definition("dlss_preset")), Field(Definition("rr_preset")))),
                Disclosure("Image tuning", Pair(Field(Definition("detail")), Field(Definition("colour"))),
                    Pair(Field(Definition("structure")), Field(Definition("tone"))), Pair(Field(Definition("skin")), Field(Definition("auto_mask")))),
                Disclosure("Sharpening", Field(Definition("sharpen")),
                    Pair(Field(Definition("sharpen_shader")), Field(Definition("sharp_override"))), Field(Definition("sharpness")),
                    Pair(Field(Definition("motion_sharpen")), Field(Definition("motion_sharpness")))),
                Disclosure("Performance", morePerformance.ToArray()));
            return ([main, more], () => FeatureControlSchema.Tuning(values));
        }
        var rows = new List<UIElement> { MfgControls() };
        var primary = new Controls.PresetColumns(t.Px(560), 2) { ColumnSpacing = t.Px(28), RowSpacing = t.Px(28) };
        primary.Children.Add(Card("Neural rendering", Field(Definition("enabled")), Choices("style"), Field(Definition("intensity")),
            Pair(Field(Definition("preset")), Field(Definition("passes")))));
        var secondary = new StackPanel { Spacing = t.Px(16) };
        secondary.Children.Add(Card("Image tuning", Pair(Field(Definition("detail")), Field(Definition("colour"))),
            Disclosure("Fine tuning", Pair(Field(Definition("structure")), Field(Definition("tone"))), Pair(Field(Definition("skin")), Field(Definition("auto_mask"))))));
        secondary.Children.Add(Card("", Disclosure("Sharpening", Field(Definition("sharpen")),
            Pair(Field(Definition("sharpen_shader")), Field(Definition("sharp_override"))), Field(Definition("sharpness")),
            Disclosure("Motion sharpening", Field(Definition("motion_sharpen")), Field(Definition("motion_sharpness"))))));
        var performance = controls.Where(f => f.Group == "Performance").Select(Field).ToArray();
        var performanceRows = new List<UIElement>();
        for (var i = 0; i < performance.Length; i += 2)
            performanceRows.Add(i + 1 < performance.Length ? Pair(performance[i], performance[i + 1]) : performance[i]);
        secondary.Children.Add(Card("", Disclosure("Performance", performanceRows.ToArray())));
        primary.Children.Add(secondary); rows.Add(primary);
        rows.Add(Card("DLSS presets", ui.P("Applies when the game next starts DLSS. Game default keeps the game's own choice.", .72),
            Pair(Field(Definition("dlss_preset")), Field(Definition("rr_preset")))));
        return (rows, () => FeatureControlSchema.Tuning(values));
    }
}
