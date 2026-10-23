using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using RtxForge.Windows.ViewModels;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    bool selecting;
    readonly HashSet<string> selectedIds = [];
    double libraryScroll;
    ScrollViewer? libraryScroller;
    bool libraryFilterHidden;

    IEnumerable<Game> FilteredGames() => LibraryScope.Filter(shell.Games, shell.Settings.LibraryFilter);

    static string FilterLabel(string key) => key switch { "installed" => "Installed", "all" => "All", _ => "Available" };

    UIElement BuildLibrary()
    {
        var main = new Grid { Padding = new Thickness(PageInset, t.Px(t.Compact ? 16 : 24), PageInset, 0), RowSpacing = t.Px(t.Compact ? 12 : 14) };
        for (var i = 0; i < 4; i++) main.RowDefinitions.Add(new RowDefinition { Height = i == 3 ? new GridLength(1, GridUnitType.Star) : GridLength.Auto });
        var games = FilteredGames().ToList();

        // Heading: Library · counts · package identity.
        var heading = new Grid();
        heading.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        heading.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var titles = new StackPanel { Spacing = t.Px(10) };
        titles.Children.Add(ui.H1(selecting ? "Select games" : "Library", t.Compact ? 1.18 : 1.62));
        var configured = shell.Games.Count(g => g.Installed);
        if ((!t.Compact || shell.LibraryRefreshing || shell.LibraryLoadError is not null)
            && (shell.Games.Count > 0 || !shell.LibraryRefreshing || shell.LibraryLoadError is not null))
            titles.Children.Add(ui.P(selecting ? $"{selectedIds.Count} selected · {FilterLabel(shell.Settings.LibraryFilter)}"
                : shell.LibraryLoadError is not null ? "Could not refresh your library. Rescan to try again."
                : shell.LibraryRefreshing ? shell.Games.Count == 0 ? "Finding your games…" : $"{shell.Games.Count} games · Refreshing library…"
                : $"{shell.Games.Count} games · {configured} configured"));
        heading.Children.Add(titles);
        var provider = GmUi.Capsule(new Border
        {
            Background = GmTheme.B(t.Panel), CornerRadius = new CornerRadius(t.Px(24)), VerticalAlignment = VerticalAlignment.Center,
            Padding = new Thickness(t.Px(20), t.Px(t.Compact ? 7 : 10), t.Px(20), t.Px(t.Compact ? 7 : 10)),
            Child = ui.IconLabel("", ProviderName()).With(p => { foreach (var c in p.Children) if (c is TextBlock tb) tb.FontSize = t.Em(0.85); }),
        });
        Grid.SetColumn(provider, 1);
        heading.Children.Add(provider);
        main.Children.Add(heading);

        // Toolbar: Features + operations.
        var toolbar = new Grid { ColumnSpacing = t.Px(20) };
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var mode = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(28), VerticalAlignment = VerticalAlignment.Center };
        mode.Children.Add(ui.Heading("Features", 0.92).With(x => x.VerticalAlignment = VerticalAlignment.Center));
        mode.Children.Add(ui.Segments(
            [("nr-only", "NR Only", shell.NrOnlyAvailable), ("mfg-only", "MFG Only", shell.Settings.RuntimeProvider != "feeder"), ("nr-mfg", "NR + MFG", shell.Settings.RuntimeProvider != "feeder")],
            shell.Mode, key => { shell.Mode = key; Render(keepFocus: true); }));
        toolbar.Children.Add(mode);
        var targets = LibraryScope.Targets(shell.Games, shell.Settings.LibraryFilter, "", selectedIds, selecting);
        var installTargets = targets.Where(g => !g.Blocked).ToList();
        var restoreTargets = targets.Where(g => g.Installed).ToList();
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(12), VerticalAlignment = VerticalAlignment.Center };
        var install = ui.Button(Glyph("", selectedIds.Count > 0 ? $"Install Selected ({selectedIds.Count})" : "Install Features"),
            () => _ = RunOperationAsync("install", installTargets), GmKind.Primary, 0.85, enabled: installTargets.Count > 0, minHeight: t.Compact ? 48 : 60);
        Key(install, "lib-install");
        var restore = ui.Button(Glyph("", selectedIds.Count > 0 ? $"Restore Selected ({selectedIds.Count})" : "Restore Original Files"),
            () => _ = RunOperationAsync("uninstall", restoreTargets), GmKind.Danger, 0.85,
            enabled: restoreTargets.Count > 0, minHeight: t.Compact ? 48 : 60);
        Key(restore, "lib-restore");
        var update = ui.Button(Glyph("", "Update DLSS"), () => _ = RunOperationAsync("update-dlss", installTargets), GmKind.Dlss, 0.85,
            enabled: installTargets.Count > 0, minHeight: t.Compact ? 48 : 60);
        Key(update, "lib-update");
        actions.Children.Add(install);
        actions.Children.Add(restore);
        actions.Children.Add(update);
        Grid.SetColumn(actions, 1);
        toolbar.Children.Add(actions);
        var toolbarSurface = new Border
        {
            Background = GmTheme.B(t.Panel), CornerRadius = new CornerRadius(t.Px(16)), Child = toolbar,
            Padding = new Thickness(t.Px(24), t.Px(t.Compact ? 8 : 20), t.Px(24), t.Px(t.Compact ? 8 : 20)),
        };
        Grid.SetRow(toolbarSurface, 1);
        main.Children.Add(toolbarSurface);

        // Sub-bar: filter summary · view choices · selection.
        var subbar = new Grid { ColumnSpacing = t.Px(16) };
        subbar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        subbar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        subbar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var filter = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(16), VerticalAlignment = VerticalAlignment.Center };
        filter.Children.Add(ui.Text("Show: " + FilterLabel(shell.Settings.LibraryFilter), 0.85, t.Muted).With(x => x.VerticalAlignment = VerticalAlignment.Center));
        var filterButton = ui.Button(Glyph("", "Filter"), OpenFilter, GmKind.Quiet, 0.85, minHeight: t.Compact ? 40 : 48);
        Key(filterButton, "lib-filter");
        filter.Children.Add(filterButton);
        subbar.Children.Add(filter);
        var views = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(6) };
        foreach (var (key, label) in new[] { ("posters", "Posters"), ("capsules", "Wide Capsule"), ("list", "List") })
        {
            var on = shell.Settings.LibraryView == key;
            var labelContent = Glyph("", label);
            if (!on && labelContent is StackPanel caption && caption.Children.FirstOrDefault() is FontIcon check) check.Opacity = 0;
            var view = ui.Button(labelContent, () => SetLibraryView(key), on ? GmKind.Active : GmKind.Transparent, 0.8,
                radius: 8, padding: new Thickness(t.Px(16), t.Px(10), t.Px(16), t.Px(10)), minHeight: t.Compact ? 40 : 48);
            GmUi.Capsule(view);
            ui.Focusable(view, -6);
            Key(view, "view-" + key);
            views.Children.Add(view);
        }
        var viewSurface = GmUi.Capsule(new Border { Background = GmTheme.B(t.Panel), CornerRadius = new CornerRadius(t.Px(12)), Padding = new Thickness(t.Px(4)), Child = ui.Selection("library-layout", views, views.Children.OfType<Button>().First(b => b.Name == "gm_view-" + shell.Settings.LibraryView)) });
        Grid.SetColumn(viewSurface, 1);
        subbar.Children.Add(viewSurface);
        var selection = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(4), HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center };
        selection.Children.Add(ui.Button(Glyph("", "Rescan"), () => _ = RefreshAsync(), GmKind.Quiet, 0.78,
            enabled: !shell.Busy, minHeight: t.Compact ? 40 : 48).With(b => Key(b, "lib-rescan")));
        selection.Children.Add(ui.Button(ui.Icon("", 0.85), OpenLibraryOptions, GmKind.Quiet, 0.78,
            minHeight: t.Compact ? 40 : 48, name: "Library options").With(b => Key(b, "lib-options")));
        if (selecting)
        {
            selection.Children.Add(ui.Button("Select all", () => { foreach (var g in games.Where(g => !g.Blocked)) selectedIds.Add(g.Id); Render(keepFocus: true); }, GmKind.Quiet, 0.78).With(b => Key(b, "sel-all")));
            selection.Children.Add(ui.Button("Clear", () => { selectedIds.Clear(); Render(keepFocus: true); }, GmKind.Quiet, 0.78, enabled: selectedIds.Count > 0).With(b => Key(b, "sel-clear")));
            selection.Children.Add(ui.Button("Done", () => { selecting = false; selectedIds.Clear(); Render(); }, GmKind.Card, 0.78).With(b => Key(b, "sel-done")));
        }
        else selection.Children.Add(ui.Button(Glyph("", "Select games"), () => { selecting = true; Render(keepFocus: true); }, GmKind.Quiet, 0.85, minHeight: t.Compact ? 40 : 48).With(b => Key(b, "sel-start")));
        Grid.SetColumn(selection, 2);
        subbar.Children.Add(selection);
        var filterHost = new Border { Child = subbar };
        Grid.SetRow(filterHost, 2);
        main.Children.Add(filterHost);

        // Games.
        var scroller = new ScrollViewer { HorizontalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        PolishScroll(scroller);
        var available = Math.Max(320, ActualWidth - PageInset * 2 - t.Px(34));
        scroller.Content = games.Count == 0
            ? EmptyLibrary()
            : shell.Settings.LibraryView == "list" ? ListLayout(games) : CardLayout(games, available, shell.Settings.LibraryView == "capsules");
        var previousOffset = libraryScroll;
        var filterHeight = 0d;
        bool? renderedFilters = null;
        var changingFilterLayout = false;
        void ShowFilters(bool show)
        {
            if (filterHeight <= 0 || renderedFilters == show) return;
            renderedFilters = show; changingFilterLayout = true;
            libraryFilterHidden = !show;
            filterHost.Height = show ? double.NaN : 0;
            filterHost.Opacity = show ? 1 : 0;
            filterHost.IsHitTestVisible = show;
            filterHost.Clip = show ? null : new Microsoft.UI.Xaml.Media.RectangleGeometry { Rect = new global::Windows.Foundation.Rect(0, 0, 0, 0) };
            // A growing viewport can clamp its offset near the last row. That layout
            // adjustment is not an upward user scroll and must not reopen the bar.
            DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
            { previousOffset = scroller.VerticalOffset; changingFilterLayout = false; });
        }
        subbar.SizeChanged += (_, e) =>
        {
            if (e.NewSize.Height <= 0) return;
            filterHeight = e.NewSize.Height; ShowFilters(!libraryFilterHidden);
        };
        subbar.GotFocus += (_, _) => ShowFilters(true);
        scroller.ViewChanged += (_, _) =>
        {
            if (!ReferenceEquals(libraryScroller, scroller)) return;
            var offset = scroller.VerticalOffset;
            var delta = offset - previousOffset;
            if (changingFilterLayout) { previousOffset = offset; libraryScroll = offset; return; }
            if (offset <= t.Px(8) || delta < -t.Px(6)) ShowFilters(true);
            else if (delta > t.Px(8) && offset > filterHeight && FocusedWithin(subbar) is null) ShowFilters(false);
            previousOffset = offset; libraryScroll = offset;
        };
        libraryScroller = scroller;   // Render restores libraryScroll before focusing (see RestoreScroll)
        FrameworkElement viewport = shell.Games.Count == 0 && shell.LibraryRefreshing
            ? new Controls.LibrarySkeleton(shell.Settings.LibraryView, GmTheme.B(t.Panel), t.Px(1)) : scroller;
        Grid.SetRow(viewport, 3);
        main.Children.Add(viewport);

        // No scroll cue: navigation help is contextual tips (see Tip / TipOnFocus).
        return main;
    }

    UIElement EmptyLibrary()
    {
        var page = new StackPanel { Spacing = t.Px(24), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, t.Px(60), 0, 0) };
        page.Children.Add(ui.Icon("", 2.4, t.Muted).With(i => i.HorizontalAlignment = HorizontalAlignment.Center));
        page.Children.Add(ui.H2(shell.LibraryLoadError is not null ? "Library unavailable" : shell.Games.Count == 0 ? "No games found" : "No games match this filter").With(h => h.HorizontalAlignment = HorizontalAlignment.Center));
        page.Children.Add(ui.P(shell.Games.Count == 0 ? "Rescan your library, or add a game folder from Library options." : "Choose a different filter to see more of your library.", 0.92)
            .With(p => { p.TextAlignment = TextAlignment.Center; p.MaxWidth = t.Em(0.92) * 30; }));
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(16), HorizontalAlignment = HorizontalAlignment.Center };
        actions.Children.Add(ui.Button("Rescan library", () => _ = RefreshAsync(), GmKind.Card, 0.92));
        actions.Children.Add(ui.Button("Library options", OpenLibraryOptions, GmKind.Card, 0.92));
        actions.Children.Add(ui.Button("Filter", OpenFilter, GmKind.Card, 0.92));
        page.Children.Add(actions);
        return page;
    }

    object Glyph(string glyph, string text) => shell.Settings.ButtonGlyphs ? ui.IconLabel(glyph, text) : text;

    string ProviderName() => shell.Settings.RuntimeProvider switch
    {
        "feeder" => "Feeder NR",
        "skynizz" => "Skynizz",
        "dlss-unlocked" => "DLSS-Unlocked",
        "custom" => "Custom package",
        _ => "y4my Multipass",
    };

    List<Game> SelectedGames() => shell.Games.Where(g => selectedIds.Contains(g.Id)).ToList();

    void SetLibraryView(string key, bool persist = true)
    {
        shell.Settings.LibraryView = key;
        if (persist) shell.Settings.Save();
        libraryScroll = 0;
        pendingFocusKey = "gm_view-" + key;
        Render();
    }

    // ---------- Cards (posters / wide capsules) ----------

    UIElement CardLayout(List<Game> games, double width, bool wide)
    {
        int columns;
        if (!wide)
            columns = t.Compact ? Math.Max(3, (int)((width + t.Px(24)) / (t.Px(108) + t.Px(24))))
                    : ActualWidth <= 1050 ? 5 : 7;
        else
            columns = t.Compact ? 4 : ActualWidth <= 1050 ? 2 : ActualWidth <= 1500 ? 3 : 4;
        var gap = t.Px(t.Compact ? 18 : 24);
        var cell = Math.Floor((width - gap * (columns - 1)) / columns);
        var grid = new Grid { ColumnSpacing = gap, RowSpacing = t.Px(t.Compact ? 18 : 24), Padding = new Thickness(t.Px(12), t.Px(18), t.Px(22), t.Px(18)) };
        for (var c = 0; c < columns; c++) grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(cell) });
        for (var i = 0; i < games.Count; i++)
        {
            if (i % columns == 0) grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var card = GameCard(games[i], cell, wide);
            Grid.SetRow(card, i / columns);
            Grid.SetColumn(card, i % columns);
            grid.Children.Add(card);
        }
        return grid;
    }

    Button GameCard(Game game, double width, bool wide)
    {
        var artHeight = wide ? width * 430 / 920 : width * 1.5;
        var art = new Border
        {
            Width = width, Height = artHeight, CornerRadius = new CornerRadius(t.Px(12)), BorderThickness = new Thickness(t.Px(GmTheme.ArtworkStroke)),
            BorderBrush = GmTheme.B(t.Line), Background = GmTheme.B(t.Card),
        };
        var source = wide ? game.CapsulePath ?? game.PosterPath : game.PosterPath ?? game.CapsulePath;
        var image = GameItem.Image(source);
        art.Child = image is not null
            ? new Border { CornerRadius = new CornerRadius(t.Px(12 - GmTheme.ArtworkStroke)), Background = new ImageBrush { ImageSource = image, Stretch = Stretch.UniformToFill } }
            : ui.Text(game.Name, 0.8, t.Muted, FontWeights.SemiBold, wrap: true).With(x => { x.HorizontalAlignment = HorizontalAlignment.Center; x.VerticalAlignment = VerticalAlignment.Center; x.TextAlignment = TextAlignment.Center; x.Margin = new Thickness(t.Px(12)); });
        var overlay = new Grid();
        overlay.Children.Add(art);
        var check = SelectionCheck(game);
        if (check is not null) overlay.Children.Add(check);

        var title = ui.Text(game.Name, 0.93, t.Fg, FontWeights.SemiBold, wrap: true, maxLines: 2);
        title.MinHeight = t.Em(0.93) * 2.5;
        var column = new StackPanel { Spacing = t.Px(t.Compact ? 8 : 14) };
        column.Children.Add(overlay);
        column.Children.Add(title);
        var enabled = !selecting || !game.Blocked;
        var card = ui.Button(column, () => ActivateGame(game), GmKind.Transparent, 1, enabled: enabled, radius: 14,
            padding: new Thickness(0), minHeight: 0, name: game.Name);
        // Every card fills its cell, so art never sizes to the title text.
        card.Width = width;
        card.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        title.Width = width;
        // Keep a thin rounded focus ring separate from the artwork's accent selection stroke.
        card.Style = (Style)Application.Current.Resources["GmBareButtonStyle"];
        card.UseSystemFocusVisuals = false;
        card.FocusVisualMargin = new Thickness(-t.Px(5), -t.Px(5), -t.Px(5), title.MinHeight + column.Spacing - t.Px(5));
        card.IsTabStop = true;
        GmMotion.Card(card, t.S);
        card.Tag = art;
        if (libraryFocusKey == "gm_game-" + game.Id.GetHashCode().ToString("x")) ReceiveArtwork(art);
        if (!enabled) art.Opacity = 0.5;
        Key(card, "game-" + game.Id.GetHashCode().ToString("x"));
        _ = DecorateAsync(game, card, art, title, null, source);
        return card;
    }

    Border? SelectionCheck(Game game)
    {
        if (!selecting) return null;
        var on = selectedIds.Contains(game.Id);
        return new Border
        {
            Width = t.Px(32), Height = t.Px(32), CornerRadius = new CornerRadius(t.Px(6)), BorderThickness = new Thickness(t.Px(2)),
            BorderBrush = GmTheme.B(t.Focus), Background = GmTheme.B(t.Window), Margin = new Thickness(t.Px(14)),
            HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top,
            Child = on ? ui.Icon("", 0.7) : null, Tag = on ? "on" : "off",
        };
    }

    /// <summary>Accent only on focus / selection: art stroke and title (neutral when idle).</summary>
    async Task DecorateAsync(Game game, Control target, Border art, TextBlock title, Border? row, string? source)
    {
        var selected = selecting && selectedIds.Contains(game.Id);
        if (target is Button button) GmGlow.Selected(button, selected);
        // Hover must be wired before asynchronous palette analysis; the image light does not need its result.
        GmGlow.Artwork(target, art, t.GameColors(null).Accent, selected, t, source, ui.ArtworkLight);
        var palette = await ArtAccent.ForGameAsync(game);
        var colors = t.GameColors(palette);
        // List rows use the desktop list's accent states exactly (GameItem RowFill / RowTitle / RowText):
        // selected = accent fill with dark accent ink; focused = desktop row-hover title on the normal surface.
        if (row is not null && palette is not null && selected)
        {
            foreach (var text in Descendants(row).OfType<TextBlock>()) text.Foreground = palette.Brush(palette.AccentDark);
            // Desktop RowChipFill on a selected row: translucent dark chips, no stroke.
            foreach (var chip in Descendants(row).OfType<Border>().Where(b => b.Tag is "chip"))
            {
                chip.Background = new SolidColorBrush(global::Windows.UI.Color.FromArgb(0x29, 0, 0, 0));
                chip.BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
                if (t.IsLight) BadgeTheme.AttachLight(chip, colors.Accent);
            }
        }
        void Paint(bool focused)
        {
            var on = focused || selected;
            art.BorderBrush = GmTheme.B(on ? colors.Accent : t.Line);
            if (row is null)
            {
                title.Foreground = GmTheme.B(on ? colors.Title : t.Fg);
                return;
            }
            row.Background = selected && palette is not null ? palette.AccentBrush : GmTheme.B(t.Panel);
            title.Foreground = selected && palette is not null ? palette.Brush(palette.AccentDark)
                : focused && palette is not null ? palette.Brush(palette.RowHoverTitle)
                : GmTheme.B(t.Fg);
        }
        Paint(target.FocusState != FocusState.Unfocused);
        target.GotFocus += (_, _) => Paint(true);
        target.LostFocus += (_, _) => Paint(false);
        target.PointerEntered += (_, _) => Paint(true);
        target.PointerExited += (_, _) => Paint(target.FocusState != FocusState.Unfocused);
        if (selected && FindCheck(art.Parent as Grid) is { } check)
        {
            check.Background = GmTheme.B(colors.Accent);
            check.BorderBrush = GmTheme.B(colors.Accent);
            if (check.Child is FontIcon icon) icon.Foreground = GmTheme.B(colors.Ink);
        }
    }

    static IEnumerable<DependencyObject> Descendants(DependencyObject parent)
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
        {
            var child = VisualTreeHelper.GetChild(parent, i);
            yield return child;
            foreach (var nested in Descendants(child)) yield return nested;
        }
    }

    static Border? FindCheck(Grid? overlay) => overlay?.Children.OfType<Border>().FirstOrDefault(b => b.Tag is "on");

    void ActivateGame(Game game)
    {
        if (selecting)
        {
            if (game.Blocked) return;
            if (!selectedIds.Add(game.Id)) selectedIds.Remove(game.Id);
            Render(keepFocus: true);
            return;
        }
        OpenDetails(game);
    }

    void ToggleSelectFocused(DependencyObject? focused)
    {
        if (page != "library" || modals.Count > 0) return;
        var name = (focused as FrameworkElement)?.Name;
        var game = FilteredGames().FirstOrDefault(g => name == "gm_game-" + g.Id.GetHashCode().ToString("x"));
        if (game is null) return;
        if (!selecting) selecting = true;
        ActivateGame(game);
    }

    // ---------- List ----------

    UIElement ListLayout(List<Game> games)
    {
        var stack = new StackPanel { Spacing = t.Px(2), Padding = new Thickness(t.Px(12), t.Px(18), t.Px(22), t.Px(18)) };
        for (var i = 0; i < games.Count; i++) stack.Children.Add(ListRow(games[i], i == 0, i == games.Count - 1));
        return stack;
    }

    Button ListRow(Game game, bool first, bool last)
    {
        var s = t.S;
        var grid = new Grid { ColumnSpacing = t.Px(28), MinHeight = t.Px(t.Compact ? 84 : 112) };
        foreach (var w in new[] { 144.0, -1, 230, 160, 152 })
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = w < 0 ? new GridLength(1, GridUnitType.Star) : new GridLength(t.Px(w)) });
        var art = new Border
        {
            Width = t.Px(144), Height = t.Px(68), CornerRadius = new CornerRadius(t.Px(8)), BorderThickness = new Thickness(t.Px(2)),
            BorderBrush = GmTheme.B(t.Line), Background = GmTheme.B(t.Card), VerticalAlignment = VerticalAlignment.Center,
        };
        if (GameItem.Image(game.CapsulePath ?? game.PosterPath) is { } image)
            art.Child = new Border { CornerRadius = new CornerRadius(t.Px(6)), Background = new ImageBrush { ImageSource = image, Stretch = Stretch.UniformToFill } };
        // Selection: the check gets its own column before the art (desktop list layout).
        var artCell = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(16), VerticalAlignment = VerticalAlignment.Center };
        if (SelectionCheck(game) is { } check)
        {
            check.Margin = new Thickness(0);
            check.VerticalAlignment = VerticalAlignment.Center;
            artCell.Children.Add(check);
            grid.ColumnDefinitions[0].Width = new GridLength(t.Px(144 + 48));
        }
        var artLight = new Grid { Width = art.Width, Height = art.Height, VerticalAlignment = VerticalAlignment.Center };
        artLight.Children.Add(art);
        artCell.Children.Add(artLight);
        grid.Children.Add(artCell);

        var title = ui.Text(game.Name, 1.04, t.Fg, FontWeights.SemiBold);
        var names = new StackPanel { Spacing = t.Px(4), VerticalAlignment = VerticalAlignment.Center };
        names.Children.Add(title);
        names.Children.Add(ui.Text(game.Library, 0.77, t.Muted));
        Grid.SetColumn(names, 1);
        grid.Children.Add(names);

        var feature = GmUi.Capsule(new Border
        {
            Background = GmTheme.B(t.Card), BorderBrush = GmTheme.B(t.Line), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(t.Px(18)),
            Padding = new Thickness(t.Px(18), t.Px(12), t.Px(18), t.Px(12)), HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Center,
            Child = ui.Text(game.Installed ? game.Profile ?? "Configured" : "Not configured", 0.76, t.Fg, new global::Windows.UI.Text.FontWeight(650)).With(x => x.TextLineBounds = TextLineBounds.Tight),
            Tag = "chip",
        });
        Grid.SetColumn(feature, 2);
        grid.Children.Add(feature);

        var state = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(10), VerticalAlignment = VerticalAlignment.Center };
        var dot = new Microsoft.UI.Xaml.Shapes.Ellipse { Width = t.Px(8), Height = t.Px(8), VerticalAlignment = VerticalAlignment.Center };
        if (game.Installed) dot.Fill = GmTheme.B(GmTheme.Accent);
        else { dot.Stroke = GmTheme.B(t.Muted); dot.StrokeThickness = 1.5; }
        state.Children.Add(dot);
        state.Children.Add(ui.Text(game.Blocked ? game.BlockedStatus : game.Installed ? "Installed" : game.UsesFeeder ? "Available · Feeder NR" : "Available", 0.85, t.Muted));
        Grid.SetColumn(state, 3);
        grid.Children.Add(state);

        // Same height and padding as the feature chip beside it.
        var details = GmUi.Capsule(new Border
        {
            Background = GmTheme.B(t.Card), BorderBrush = GmTheme.B(t.Card), BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(t.Px(32)), Padding = new Thickness(t.Px(18), t.Px(12), t.Px(18), t.Px(12)),
            HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center,
            Child = ui.Text(selecting ? "Select" : "Details", 0.76, t.Fg, FontWeights.SemiBold).With(x => x.TextLineBounds = TextLineBounds.Tight),
            Tag = "chip",
        });
        Grid.SetColumn(details, 4);
        grid.Children.Add(details);

        var surface = new Border
        {
            Background = GmTheme.B(t.Panel), Child = grid, Padding = new Thickness(t.Px(24), t.Px(16), t.Px(24), t.Px(16)),
            CornerRadius = new CornerRadius(first ? t.Px(16) : 0, first ? t.Px(16) : 0, last ? t.Px(16) : 0, last ? t.Px(16) : 0),
        };
        var enabled = !selecting || !game.Blocked;
        var row = ui.Button(surface, () => ActivateGame(game), GmKind.Transparent, 1, enabled: enabled, radius: 0, padding: new Thickness(0), minHeight: 0, name: game.Name);
        row.HorizontalAlignment = HorizontalAlignment.Stretch;
        row.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        row.CornerRadius = surface.CornerRadius;
        ui.Focusable(row, -6);
        GmUi.NoLift(row);
        Key(row, "game-" + game.Id.GetHashCode().ToString("x"));
        _ = DecorateAsync(game, row, art, title, surface, game.CapsulePath ?? game.PosterPath);
        return row;
    }

    // ---------- Filter dialog (staged: Apply / Reset / Back) ----------

    void OpenFilter()
    {
        var current = shell.Settings.LibraryFilter is "installed" or "all" ? shell.Settings.LibraryFilter : "available";
        var pending = current;
        var options = new StackPanel { Spacing = t.Px(12) };
        var status = ui.P("", 0.8);
        var buttons = new List<(Button Button, Border Mark, string Key)>();
        void Refresh()
        {
            foreach (var (_, mark, key) in buttons)
            {
                var on = key == pending;
                mark.Background = GmTheme.B(on ? GmTheme.Accent : Microsoft.UI.Colors.Transparent);
                mark.BorderBrush = GmTheme.B(on ? GmTheme.Accent : t.Muted);
                mark.Child = on ? ui.Icon("", 0.6, GmTheme.AccentInk) : null;
            }
            status.Text = $"Current: {FilterLabel(current)} · Pending: {FilterLabel(pending)} · Up/down move · Select changes the choice.";
        }
        foreach (var (key, label, description) in new[]
        {
            ("available", "Available", "Supported games without features installed"),
            ("installed", "Installed", "Games with managed features"),
            ("all", "All", "Every discovered game"),
        })
        {
            var mark = new Border
            {
                Width = t.Px(34), Height = t.Px(34), CornerRadius = new CornerRadius(t.Px(17)), BorderThickness = new Thickness(t.Px(2)),
                VerticalAlignment = VerticalAlignment.Center,
            };
            var line = new Grid { ColumnSpacing = t.Px(22) };
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            line.Children.Add(mark);
            var name = ui.Text(label, 1, t.Fg, FontWeights.SemiBold).With(x => x.VerticalAlignment = VerticalAlignment.Center);
            Grid.SetColumn(name, 1);
            line.Children.Add(name);
            var desc = ui.Text(description, 0.8, t.Muted).With(x => x.VerticalAlignment = VerticalAlignment.Center);
            Grid.SetColumn(desc, 2);
            line.Children.Add(desc);
            var option = ui.Button(line, () => { pending = key; Refresh(); }, GmKind.Card, 1, radius: 12,
                padding: new Thickness(t.Px(24)), minHeight: t.Compact ? 66 : 96);
            option.HorizontalAlignment = HorizontalAlignment.Stretch;
            option.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            buttons.Add((option, mark, key));
            options.Children.Add(option);
        }
        Refresh();
        var content = new StackPanel { Spacing = t.Px(20) };
        content.Children.Add(ui.P("Choose which games to show, then Apply.", 0.92));
        content.Children.Add(options);
        content.Children.Add(status);
        var reset = ui.Button("Reset", () => { pending = "available"; Refresh(); }, GmKind.Card, 0.92);
        var back = ui.Button("Back", CloseModal, GmKind.Card, 0.92);
        var apply = ui.Button(Glyph("", "Apply"), () =>
        {
            shell.Settings.LibraryFilter = pending;
            shell.Settings.Save();
            CloseModal();
            libraryScroll = 0;
            Render(keepFocus: true);
        }, GmKind.Primary, 0.92);
        ShowModal("Filter library", content, [reset, back, apply], CloseModal, 900,
            buttons.First(b => b.Key == current).Button);
    }
}
