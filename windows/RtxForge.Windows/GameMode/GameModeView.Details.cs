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
        var heroHeight = t.Px(t.Compact ? 240 : ActualWidth <= 1500 ? 280 : 320);
        var navWidth = t.Px(ActualWidth <= 1050 ? 184 : ActualWidth <= 1500 ? 246 : 254);
        var side = t.Px(ActualWidth <= 1050 ? 24 : ActualWidth <= 1500 ? 36 : 56);
        var grid = new Grid { ColumnSpacing = t.Px(26), RowSpacing = t.Px(t.Compact ? 12 : 22), Padding = new Thickness(0, 0, 0, t.Px(8)) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(navWidth + side) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(heroHeight) });
        grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });

        // ----- Hero: full width; art fades into the workspace (--view) -----
        var hero = new Grid { Background = GmTheme.B(t.View) };
        Grid.SetColumnSpan(hero, 2);
        if ((g.HeroPath ?? g.CapsulePath) is { } heroSource)
        {
            var art = new FadedImage { FadeStart = 0.3f };
            art.SetSource(heroSource);
            hero.Children.Add(art);
            // Legibility scrim behind the identity (left), so accent titles read over bright art.
            var scrim = new LinearGradientBrush { StartPoint = new global::Windows.Foundation.Point(0, 0), EndPoint = new global::Windows.Foundation.Point(1, 0) };
            scrim.GradientStops.Add(new GradientStop { Color = WithAlpha(t.View, 0.82), Offset = 0 });
            scrim.GradientStops.Add(new GradientStop { Color = WithAlpha(t.View, 0.55), Offset = 0.38 });
            scrim.GradientStops.Add(new GradientStop { Color = WithAlpha(t.View, 0), Offset = 0.72 });
            hero.Children.Add(new Border { Background = scrim, IsHitTestVisible = false });
        }
        var identity = new Grid
        {
            ColumnSpacing = t.Px(30), VerticalAlignment = VerticalAlignment.Bottom,
            Padding = new Thickness(side, t.Px(t.Compact ? 66 : 82), side, t.Px(t.Compact ? 18 : 26)),
        };
        identity.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        identity.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var posterHeight = t.Px(t.Compact ? 156 : ActualWidth <= 1500 ? 184 : 210);
        var poster = new Border
        {
            Height = posterHeight, Width = Math.Round(posterHeight * 2 / 3), CornerRadius = new CornerRadius(t.Px(10)),
            BorderThickness = new Thickness(t.Px(3)), BorderBrush = GmTheme.B(t.Line), Background = GmTheme.B(t.Card),
            VerticalAlignment = VerticalAlignment.Bottom,
        };
        if (GameItem.Image(g.PosterPath ?? g.CapsulePath) is { } posterImage)
            poster.Child = new Border { CornerRadius = new CornerRadius(t.Px(7)), Background = new ImageBrush { ImageSource = posterImage, Stretch = Stretch.UniformToFill } };
        identity.Children.Add(poster);
        var text = new StackPanel { VerticalAlignment = VerticalAlignment.Bottom, Spacing = t.Px(8) };
        if (g.Installed && g.Profile is { } profile)
            text.Children.Add(ui.Badge(profile, Microsoft.UI.Colors.Black, Microsoft.UI.Colors.White, 0.68).With(b => b.Background = GmTheme.B(Microsoft.UI.Colors.Black, 0.8)));
        var title = ui.Text(g.Name, t.Compact ? 1.35 : 1.65, t.Fg, FontWeights.Bold, wrap: true, maxLines: 2);
        title.LineHeight = t.Em(t.Compact ? 1.35 : 1.65) * 1.1;
        text.Children.Add(title);
        var badges = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(8) };
        var sourceBadge = ui.Badge(g.Library, t.Card, t.Fg, 0.62 * 1.2, g.Library == "Steam" ? "" : null);
        badges.Children.Add(sourceBadge);
        badges.Children.Add(ui.Badge(g.Tested ? "Tested" : "Untested", GmTheme.Hex("#573d18"), GmTheme.Hex("#ffe8a2"), 0.62 * 1.2, g.Tested ? "" : ""));
        text.Children.Add(badges);
        text.Children.Add(ui.Text(string.Join(" · ", new[] { g.Library, g.Installed ? "Configured" : g.Blocked ? "Unsupported" : "Available", ProviderName() }), 0.78, t.Fg));
        Grid.SetColumn(text, 1);
        identity.Children.Add(text);
        // The desktop Game Details hero actions, in the same order.
        identity.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(12), VerticalAlignment = VerticalAlignment.Bottom };
        var install = ui.Button(Glyph("", g.Installed ? "Repair Features" : "Install Features"), () => _ = RunOperationAsync("install", [g]),
            GmKind.Primary, 0.82, enabled: !g.Blocked, minHeight: t.Compact ? 46 : 54);
        Key(install, "hero-install");
        actions.Children.Add(install);
        var restore = ui.Button(Glyph("", "Restore Original Files"), () => _ = RunOperationAsync("uninstall", [g]),
            GmKind.Danger, 0.82, enabled: g.Installed, minHeight: t.Compact ? 46 : 54);
        Key(restore, "hero-restore");
        actions.Children.Add(restore);
        var update = ui.Button(Glyph("", "Update DLSS"), () => _ = RunOperationAsync("update-dlss", [g]),
            GmKind.Dlss, 0.82, enabled: !g.Blocked, minHeight: t.Compact ? 46 : 54);
        Key(update, "hero-update");
        actions.Children.Add(update);
        Grid.SetColumn(actions, 2);
        identity.Children.Add(actions);
        hero.Children.Add(identity);
        var back = ui.Button(Glyph("", "Back to Library"), CloseDetails, GmKind.Transparent, 0.78, radius: 12,
            padding: new Thickness(t.Px(18), t.Px(10), t.Px(18), t.Px(10)), minHeight: t.Compact ? 38 : 46);
        back.Background = GmTheme.B(GmTheme.Hex("#121212"), 0.86);
        back.Foreground = GmTheme.B(Microsoft.UI.Colors.White);
        back.HorizontalAlignment = HorizontalAlignment.Left;
        back.VerticalAlignment = VerticalAlignment.Top;
        back.Margin = new Thickness(side, t.Px(t.Compact ? 12 : 18), 0, 0);
        Key(back, "details-back");
        hero.Children.Add(back);
        grid.Children.Add(hero);

        // ----- Section navigation -----
        var nav = new StackPanel { Spacing = t.Px(t.Compact ? 6 : 12), Padding = new Thickness(side, t.Px(8), t.Px(18), t.Px(8)) };
        nav.Children.Add(ui.Text("Game Details", 1.06, weight: FontWeights.SemiBold).With(h => h.Margin = new Thickness(t.Px(16), t.Px(8), 0, t.Px(t.Compact ? 12 : 20))));
        var navButtons = new List<(Button Button, string Section)>();
        foreach (var section in Sections)
        {
            var active = section == detailsSection;
            var button = ui.Button(section, () => { detailsSection = section; Render(); pendingFocusKey = "gm_section-" + section; },
                GmKind.Transparent, 0.88, radius: 12, padding: new Thickness(t.Px(18), t.Px(12), t.Px(18), t.Px(12)), minHeight: t.Compact ? 46 : 60);
            button.HorizontalAlignment = HorizontalAlignment.Stretch;
            button.HorizontalContentAlignment = HorizontalAlignment.Left;
            Key(button, "section-" + section);
            navButtons.Add((button, section));
            nav.Children.Add(button);
        }
        var navScroll = new ScrollViewer { Content = nav, HorizontalScrollMode = ScrollMode.Disabled };
        Grid.SetRow(navScroll, 1);
        grid.Children.Add(navScroll);

        // ----- Section body -----
        var content = new StackPanel { Spacing = t.Px(24), Padding = new Thickness(t.Px(24), t.Px(12), t.Px(24), t.Px(12)) };
        BuildSection(g, content);
        var scroll = new ScrollViewer
        {
            Content = content, HorizontalScrollMode = ScrollMode.Disabled, Margin = new Thickness(0, 0, side, 0),
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };
        Grid.SetRow(scroll, 1);
        Grid.SetColumn(scroll, 1);
        grid.Children.Add(scroll);

        // Accent: poster stroke, title, active section (tint + readable title).
        _ = DetailsAccentAsync(g, poster, title, sourceBadge, navButtons);
        if (initialFocus is null) initialFocus = navButtons.First(b => b.Section == detailsSection).Button;
        return grid;
    }

    static global::Windows.UI.Color WithAlpha(global::Windows.UI.Color c, double alpha) =>
        global::Windows.UI.Color.FromArgb((byte)Math.Round(alpha * 255), c.R, c.G, c.B);

    async Task DetailsAccentAsync(Game g, Border poster, TextBlock title, Border sourceBadge, List<(Button Button, string Section)> nav)
    {
        var colors = t.GameColors(await ArtAccent.ForGameAsync(g));
        poster.BorderBrush = GmTheme.B(colors.Accent);
        title.Foreground = GmTheme.B(colors.Title);
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

    void SectionTitle(StackPanel content, string title, string? description = null)
    {
        var block = new StackPanel { Spacing = t.Px(10) };
        block.Children.Add(ui.H2(title));
        if (description is not null) block.Children.Add(ui.P(description));
        content.Children.Add(block);
    }

    void BuildSection(Game g, StackPanel content)
    {
        switch (detailsSection)
        {
            case "Features":
                SectionTitle(content, "Features", g.Installed
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
                    var (rows, value) = PresetRows(tuning, g.Installed && !g.Blocked);
                    content.Children.Add(ui.P("Only this game changes. Review the changes before applying."));
                    content.Children.Add(ui.Group(rows));
                    var apply = ui.Button("Apply to this game", () => _ = RunOperationAsync("apply", [g], value()), GmKind.Primary, 0.85,
                        enabled: g.Installed && !g.Blocked);
                    content.Children.Add(apply.With(b => b.HorizontalAlignment = HorizontalAlignment.Left));
                }
                SectionTitle(content, "Installation");
                content.Children.Add(ui.Group(
                [
                    ui.RowButton("Install Features", null, () => _ = RunOperationAsync("install", [g]), enabled: !g.Blocked),
                    ui.RowButton("Repair Feature Files", null, () => _ = RunOperationAsync("install", [g]), enabled: g.Installed && !g.Blocked),
                    ui.RowButton("Restore Original Files", null, () => _ = RunOperationAsync("uninstall", [g]), danger: true, enabled: g.Installed),
                ]));
                break;

            case "DLSS Files":
                SectionTitle(content, "DLSS Files", "Updater backups are previous copies, not proof of the version currently shipped by the game.");
                content.Children.Add(ui.Group(
                [
                    ui.PreferenceRow("Installed DLSS version", null, ui.Text(g.DlssVersion ?? "Checked during update", 0.85, t.Muted)),
                ]));
                SectionTitle(content, "File Management");
                var restoreDlss = ui.RowButton("Restore original DLSS files", null, () => _ = RestoreDlssAsync(g), danger: true, enabled: !g.Blocked);
                content.Children.Add(ui.Group(
                [
                    ui.RowButton("Update DLSS files", null, () => _ = RunOperationAsync("update-dlss", [g]), enabled: !g.Blocked),
                    restoreDlss,
                ]));
                var inventory = new StackPanel { Spacing = t.Px(16) };
                content.Children.Add(inventory);
                _ = FillDlssInventoryAsync(g, inventory, restoreDlss);
                break;

            case "Tools":
                SectionTitle(content, "Tools", "Check NR or add ReShade to this game. Existing graphics files are kept safe.");
                var tools = new Grid { ColumnSpacing = t.Px(20), RowSpacing = t.Px(20) };
                tools.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                tools.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                tools.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                tools.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                var index = 0;
                foreach (var (glyph, label, enabled, action) in new (string, string, bool, Action)[]
                {
                    ("", "Diagnose NR", g.Installed, () => _ = DiagnoseAsync(g)),
                    ("", "Install ReShade", !shell.Service.IsPreview && !g.Blocked, () => _ = InstallExtraAsync(g, "reshade")),
                    ("", "Install Add-on", !shell.Service.IsPreview && !g.Blocked, () => _ = InstallExtraAsync(g, "addon")),
                    ("", "ReShade Downloads", true, () => MainWindow.OpenUri("https://reshade.me/")),
                })
                {
                    var tile = new StackPanel { Spacing = t.Px(10), HorizontalAlignment = HorizontalAlignment.Center };
                    tile.Children.Add(ui.Icon(glyph, 0.8).With(i => i.HorizontalAlignment = HorizontalAlignment.Center));
                    tile.Children.Add(ui.Text(label, 1, weight: FontWeights.SemiBold).With(x => x.HorizontalAlignment = HorizontalAlignment.Center));
                    var button = ui.Button(tile, action, GmKind.Card, 1, enabled, radius: 14, minHeight: t.Compact ? 90 : 116);
                    button.HorizontalAlignment = HorizontalAlignment.Stretch;
                    Grid.SetRow(button, index / 2);
                    Grid.SetColumn(button, index % 2);
                    tools.Children.Add(button);
                    index++;
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
                content.Children.Add(notes);
                // game_notes: the test result and notes are saved with this game (shared with Desktop UI).
                notesStatus ??= g.TestStatus;
                content.Children.Add(ui.Group(
                [
                    Choice("Test Result", "Bench excludes this game from bulk installation and repair.", ["Untested", "Working", "Problem", "Bench"],
                        ["Untested", "Working", "Problem", "Bench"], () => notesStatus ?? g.TestStatus, v => notesStatus = v),
                ]));
                content.Children.Add(ui.P("Controller text entry uses the Windows touch keyboard or Steam's keyboard.", 0.83));
                var noteActions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(16) };
                noteActions.Children.Add(ui.Button("Save Notes", () => _ = SaveNotesAsync(g, notesStatus ?? g.TestStatus, notes.Text), GmKind.Primary, 0.85).With(b => Key(b, "notes-save")));
                noteActions.Children.Add(ui.Button(g.TestActive ? "Finish Test" : "Start Test", () => _ = RecordTestAsync(g), GmKind.Card, 0.85,
                    enabled: !shell.Service.IsPreview).With(b => Key(b, "notes-test")));
                content.Children.Add(noteActions);
                break;

            case "Appearance":
                SectionTitle(content, "Accent Color", "Pick a suggestion from this game's artwork. Your own picks are kept.");
                var current = shell.Settings.GameAccents.GetValueOrDefault(g.Id);
                content.Children.Add(ui.Group(
                [
                    ui.PreferenceRow("Game Accent", current is null ? "Artwork-derived" : "Custom", ui.Text(current?.ToUpperInvariant() ?? "Automatic", 0.85, t.Muted)),
                ]));
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
                SectionTitle(content, "Overview");
                // Store description and credits live here, not in the hero (Settings › Download game information).
                if (!string.IsNullOrWhiteSpace(g.Summary))
                {
                    content.Children.Add(ui.H2("About", 1.06));
                    content.Children.Add(ui.P(g.Summary).With(p => { p.MaxWidth = t.Px(980); p.HorizontalAlignment = HorizontalAlignment.Left; }));
                }
                else if (shell.Settings.SteamMetadata)
                    _ = FillStoreInfoAsync(g);
                content.Children.Add(ui.H2("Game Information", 1.06));
                var info = new List<UIElement>();
                if (!string.IsNullOrWhiteSpace(g.Developer)) info.Add(ui.PreferenceRow("Developer", null, ui.Text(g.Developer, 0.85, t.Muted)));
                if (!string.IsNullOrWhiteSpace(g.Release)) info.Add(ui.PreferenceRow("Release", null, ui.Text(g.Release, 0.85, t.Muted)));
                content.Children.Add(ui.Group(
                [
                    .. info,
                    ui.PreferenceRow("Library", null, ui.Text(g.Library, 0.85, t.Muted)),
                    ui.PreferenceRow("Location", null, ui.Text(g.Location, 0.85, t.Muted).With(x => { x.TextWrapping = TextWrapping.Wrap; x.TextAlignment = TextAlignment.Right; x.MaxWidth = t.Px(560); })),
                    ui.PreferenceRow("Compatibility", null, ui.Text(g.Blocked ? g.BlockedReason ?? "Unsupported" : "Supported", 0.85, t.Muted)),
                    ui.PreferenceRow("Metadata Source", null, ui.Text(g.MetadataSource ?? g.Library, 0.85, t.Muted)),
                ]));
                break;
        }
    }

    /// <summary>Fetches store information once, then re-renders Overview if it is still showing.</summary>
    async Task FillStoreInfoAsync(Game g)
    {
        if (await SteamStoreInfo.FillAsync(g, shell.Settings.SteamMetadata)
            && detailsGame == g && page == "details" && detailsSection == "Overview")
            Render(keepFocus: true);
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

    /// <summary>NR Strength / Sharpening / Frame generation steppers (Left/Right adjust).</summary>
    (List<UIElement> Rows, Func<Tuning> Value) PresetRows(Tuning initial, bool enabled = true)
    {
        var nr = initial.NrStrength;
        var sharp = initial.SharpeningStrength;
        var mfg = initial.MfgMultiplier;
        string[] multipliers = ["0", "2", "3", "4", "5", "6", "auto"];
        string Mfg(string v) => v switch { "auto" => "In game", "0" => "Off", _ => v + "×" };
        var nrEnabled = enabled && shell.Mode != "mfg-only";
        var mfgEnabled = enabled && shell.Mode != "nr-only";
        var rows = new List<UIElement>
        {
            ui.StepperRow("NR Strength", "0.0 turns the effect off.", () => nr.ToString("0.0"), d => nr = Math.Clamp(Math.Round(nr + d * 0.1, 1), 0, 2), nrEnabled),
            ui.StepperRow("Sharpening", "0.0 turns sharpening off.", () => sharp.ToString("0.0"), d => sharp = Math.Clamp(Math.Round(sharp + d * 0.1, 1), 0, 1), enabled),
            ui.StepperRow("Frame generation", "MFG multiplier · enable frame generation in the game.", () => Mfg(mfg),
                d => mfg = multipliers[Math.Clamp(Array.IndexOf(multipliers, mfg) + d, 0, multipliers.Length - 1)], mfgEnabled),
        };
        return (rows, () => new Tuning(nr, sharp, mfg));
    }
}
