using System.Diagnostics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using RtxForge.Windows.ViewModels;

namespace RtxForge.Windows.Views;

public sealed partial class LibraryPage : Page
{
    readonly MainWindow shell = App.Main!;
    readonly GameActions actions;
    readonly HashSet<string> selectedIds = [];
    bool syncingMode, ready, pressedOnCheck;
    GameItem? hovered;
    int density;
    bool compact;
    /// <summary>The library is scrolled far enough that the dashboard has collapsed (Linux collapse_header).</summary>
    bool scrolledAway;
    bool onScreen;

    ForgeSettings Settings => shell.Settings;

    public LibraryPage()
    {
        InitializeComponent();
        ActualThemeChanged += (_, _) =>
        {
            if (Library.ItemsSource is IEnumerable<GameItem> items)
                foreach (var item in items) item.RefreshTheme();
        };

        // List view Actions column: Install / Restore, and the row's "…" menu.
        actions = new GameActions(
            game => _ = shell.PresetSelecting ? ApplyPresetsAsync([game]) : shell.LaunchAction(game.Installed ? "uninstall" : "install", [game]),
            (game, target) => GameMenu(game).ShowAt(target),
            (game, on) =>
            {
                if (on) selectedIds.Add(game.Id); else selectedIds.Remove(game.Id);
                UpdateSelectionActions();
            });


        SearchBox.Text = shell.Query;
        ArtScale.Value = Settings.ArtScale;
        (Settings.LibraryFilter switch { "available" => FilterAvailable, "installed" => FilterInstalled, _ => FilterAll }).IsChecked = true;
        ApplySettings();
        ready = true;

        // ItemContainer marks presses handled, so listen with handledEventsToo
        // to learn whether the press started on a selection check.
        Library.AddHandler(PointerPressedEvent, new PointerEventHandler((_, e) => pressedOnCheck = IsOnCheck(e.GetCurrentPoint(null).Position)), true);

        ShowGames();
    }

    void OnCompactModeChosen(string mode) { if (mode != shell.Mode) SetMode(mode); }

    void OnCompactActionInvoked(string action)
    {
        if (action == "install") OnInstallFeatures(this, new RoutedEventArgs());
        else if (action == "uninstall") OnRestoreOriginal(this, new RoutedEventArgs());
        else if (action == "apply-selected") _ = ApplyPresetsAsync(SelectedGames());
        else OnUpdateDlss(this, new RoutedEventArgs());
    }

    void OnPresetModeChanged() { selectedIds.Clear(); ShowGames(); UpdateDashboard(); }

    /// <summary>Presets mode: the library presets for these games, through the usual review.</summary>
    async Task ApplyPresetsAsync(IReadOnlyList<Game> games)
    {
        var targets = games.Where(g => g.Installed && !g.Blocked).ToList();
        if (targets.Count == 0) { shell.ShowToast("Presets apply to games with features installed."); return; }
        await shell.LaunchAction("apply", targets, Settings.Presets);
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        onScreen = true;
        // Only the active page may handle titlebar actions. Old pages can have a different selection.
        shell.GamesChanged += ShowGames;
        shell.QueryChanged += ShowGames;
        shell.SettingsChanged += ApplySettings;
        shell.CompactModeChosen += OnCompactModeChosen;
        shell.CompactActionInvoked += OnCompactActionInvoked;
        shell.PresetModeChanged += OnPresetModeChanged;
        SearchBox.Text = shell.Query;
        ApplySettings();
        ShowGames();
        UpdateDashboard();
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e)
    {
        base.OnNavigatedFrom(e);
        onScreen = false;
        shell.GamesChanged -= ShowGames;
        shell.QueryChanged -= ShowGames;
        shell.SettingsChanged -= ApplySettings;
        shell.CompactModeChosen -= OnCompactModeChosen;
        shell.CompactActionInvoked -= OnCompactActionInvoked;
        shell.PresetModeChanged -= OnPresetModeChanged;
        shell.ShowCompactDashboard(false);
        shell.ShowBrand(true);
        // Presets mode belongs to this page; Edit Presets or any other page ends it.
        if (e.SourcePageType != typeof(LibraryPage)) shell.EndPresetSelection();
    }

    /// <summary>
    /// Linux collapse_header: compact mode, or a long library scrolled past 120 px, hides the
    /// dashboard (hero, Features, Presets) and shows the compact one in the titlebar. Near the
    /// top again (under 10 px) the full dashboard returns, unless compact mode is on.
    /// </summary>
    void OnLibraryScrolled(object? sender, ScrollViewerViewChangedEventArgs e)
    {
        var offset = LibraryScroll.VerticalOffset;
        var canCollapse = LibraryScroll.ScrollableHeight + (Dashboard.Visibility == Visibility.Visible ? 0 : Dashboard.ActualHeight) > 300;
        if (offset > 120 && canCollapse && !scrolledAway) { scrolledAway = true; UpdateDashboard(); }
        else if (offset < 10 && scrolledAway) { scrolledAway = false; UpdateDashboard(); }
    }

    void UpdateDashboard()
    {
        // Presets mode always uses the compact titlebar: its options replace the Features selector and install actions.
        var collapsed = Settings.CompactHeader || scrolledAway || shell.PresetSelecting;
        Dashboard.Visibility = collapsed ? Visibility.Collapsed : Visibility.Visible;
        // Compact: the toolbar meets the titlebar with ordinary spacing (Linux top margin 0).
        Toolbar.Padding = new Thickness(Toolbar.Padding.Left, collapsed ? 12 : 32, Toolbar.Padding.Right, 0);
        shell.SyncCompactDashboard(shell.Mode, ModeNrOnly.IsEnabled, InstallText.Text);
        shell.ShowCompactDashboard(collapsed && onScreen);
        // The full hero carries the mark and wordmark, so the titlebar brand waits until it collapses.
        shell.ShowBrand(collapsed || !onScreen);
    }

    void OnSearchChanged(AutoSuggestBox sender, AutoSuggestBoxTextChangedEventArgs args) =>
        shell.Query = sender.Text?.Trim() ?? "";

    void ApplySettings()
    {
        (Settings.LibraryFilter switch { "available" => FilterAvailable, "installed" => FilterInstalled, _ => FilterAll }).IsChecked = true;
        ModeNrOnly.IsEnabled = shell.NrOnlyAvailable;
        ModeMfgOnly.IsEnabled = ModeNrMfg.IsEnabled = Settings.RuntimeProvider != "feeder";
        SetMode(shell.Mode);
        (Settings.LibraryView switch { "capsules" => ViewCapsules, "list" => ViewList, _ => ViewPosters }).IsChecked = true;
        UpdateDashboard();

    }

    // ---------- Library ----------

    void ShowGames()
    {
        var games = shell.Games;
        var libs = games.Select(g => g.Library).Distinct().Count();
        var installs = games.Count(g => g.Installed);
        StatsText.Text = games.Count == 0 && shell.LibraryRefreshing
            ? ""
            : $"{games.Count} games · {libs} locations · {installs} OptiScaler installs detected";
        if (shell.Hardware is { } hardware)
            HardwareText.Text = shell.Service.IsPreview
                ? "Preview mode · no game writes"
                : hardware.Gpu + " · " + (hardware.Ready ? "Hardware check passed" : "Install unavailable — see Settings");

        var scale = Settings.ArtScale / 100.0;
        var items = LibraryScope.Filter(games, Settings.LibraryFilter, shell.Query)
            .Select(g => new GameItem(g, Settings, actions, selectedIds.Count > 0, selectedIds.Contains(g.Id), density, this) { PresetMode = shell.PresetSelecting })
            .ToList();
        for (var i = 0; i < items.Count; i++)
        {
            items[i].Position = i;
            items[i].IsLast = i == items.Count - 1;
        }

        var view = Settings.LibraryView;
        var loading = shell.LibraryRefreshing && games.Count == 0;
        StatsText.Visibility = loading ? Visibility.Collapsed : Visibility.Visible;
        LoadingCards.Configure(view, Settings.ArtScale / 100.0);
        LoadingCards.Visibility = loading ? Visibility.Visible : Visibility.Collapsed;
        RefreshStatus.Visibility = !loading && (shell.LibraryRefreshing || shell.LibraryLoadError is not null) ? Visibility.Visible : Visibility.Collapsed;
        RefreshStatus.Text = shell.LibraryLoadError is not null ? "Could not refresh your library. Rescan to try again."
            : games.Count > 0 ? "Refreshing library…" : "Finding your games…";
        Library.ItemTemplate = (DataTemplate)Resources[view switch
        {
            "capsules" => "CapsuleTemplate",
            "list" => "ListTemplate",
            _ => "PosterTemplate",
        }];
        if (view == "list")
            Library.Layout = (Layout)Resources["ListLayout"];
        else
        {
            ApplyGridMetrics();
            Library.Layout = (Layout)Resources["GridLayout"];
        }
        Library.ItemsSource = items;
        ListHeader.Visibility = view == "list" && items.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
        EmptyText.Visibility = items.Count == 0 && !shell.LibraryRefreshing ? Visibility.Visible : Visibility.Collapsed;
        EmptyText.Text = shell.LibraryLoadError is not null ? "Your library could not be loaded."
            : games.Count == 0 ? "No games found. Add a folder or rescan your library." : "No games match this view.";
        ArtScale.IsEnabled = view != "list";
        UpdateSelectionActions();
    }

    /// <summary>
    /// Sizes poster/capsule cells exactly: as many columns as fit at the
    /// slider's size, widened so the row ends flush with the edge, and the art
    /// kept at its true ratio (2:3 posters, 460:215 capsules) so nothing crops.
    /// </summary>
    void ApplyGridMetrics()
    {
        const double gap = 16, border = 4;
        var capsules = Settings.LibraryView == "capsules";
        var footer = capsules ? 68 : 88;
        var preferred = (capsules ? 300 : 212) * Settings.ArtScale / 100.0;
        var available = Library.ActualWidth;
        if (available <= 0) available = Math.Max(preferred, ActualWidth - 72);
        var columns = Math.Max(1, (int)Math.Floor((available + gap) / (preferred + gap)));
        var width = Math.Floor((available - gap * (columns - 1)) / columns);
        var inner = width - border; // art sits inside the 2px ring on each side
        var art = capsules ? inner * 215 / 460 : inner * 1.5;

        var grid = (UniformGridLayout)Resources["GridLayout"];
        grid.MinItemWidth = width;
        grid.MinItemHeight = Math.Round(art + footer + border);
        grid.MaximumRowsOrColumns = columns;
    }

    // ---------- Responsive layout ----------

    /// <summary>
    /// Margins scale with the window; hero actions and library tools wrap
    /// onto their own row when narrow; list columns drop Location, then
    /// Features, as the list narrows (Game, Status and Actions always stay).
    /// </summary>
    void OnPageSizeChanged(object sender, SizeChangedEventArgs e)
    {
        var width = e.NewSize.Width;
        var side = PageMargins.Side(width);
        Dashboard.Padding = new Thickness(side, 12, side, 0);
        Toolbar.Padding = new Thickness(side, Toolbar.Padding.Top, side, 0);
        Body.Padding = new Thickness(side, 16, side, 48);
        LoadingCards.Margin = new Thickness(side, 16, side, 48);

        var narrowHero = width < 1100;
        Grid.SetRow(HeroActions, narrowHero ? 1 : 0);
        Grid.SetColumn(HeroActions, narrowHero ? 1 : 2);
        HeroActions.HorizontalAlignment = narrowHero ? HorizontalAlignment.Left : HorizontalAlignment.Right;

        var nowCompact = width < 1180;
        if (nowCompact != compact)
        {
            compact = nowCompact;
            // Narrow: title and a full-width search on top; filters, view, size and commands
            // flow together beneath instead of sitting under unrelated columns.
            FrameworkElement[] tools = [FilterGroup, ViewGroup, ArtScale, LibraryCommands];
            foreach (var element in tools)
            {
                ((Panel)element.Parent).Children.Remove(element);
                (compact ? LibraryTools.Children : LibraryHeader.Children).Add(element);
            }
            FilterGroup.Margin = new Thickness(compact ? 0 : 12, 0, 0, 0);
            LibraryTools.Visibility = compact ? Visibility.Visible : Visibility.Collapsed;
            Grid.SetColumn(SearchBox, compact ? 1 : 2);
            Grid.SetColumnSpan(SearchBox, compact ? 5 : 1);
            SearchBox.MaxWidth = compact ? double.PositiveInfinity : 360;
            LibraryCommands.HorizontalAlignment = compact ? HorizontalAlignment.Left : HorizontalAlignment.Stretch;
            // Icon-width commands and a slimmer size slider keep the tools on one row beneath.
            foreach (var command in LibraryCommands.PrimaryCommands.OfType<AppBarButton>()) command.Width = compact ? 44 : double.NaN;
            ArtScale.Width = compact ? 100 : 120;
        }
        LibraryCommands.DefaultLabelPosition = width < 820 ? CommandBarDefaultLabelPosition.Collapsed : CommandBarDefaultLabelPosition.Right;

        var listWidth = width - side * 2;
        var nowDensity = listWidth < 860 ? 2 : listWidth < 1060 ? 1 : 0;
        if (nowDensity != density)
        {
            density = nowDensity;
            HeaderLocation.Width = new GridLength(density >= 1 ? 0 : 240);
            HeaderFeatures.Width = new GridLength(density >= 2 ? 0 : 150);
            HeaderLocationText.Visibility = density >= 1 ? Visibility.Collapsed : Visibility.Visible;
            HeaderFeaturesText.Visibility = density >= 2 ? Visibility.Collapsed : Visibility.Visible;
            if (ready && Settings.LibraryView == "list") ShowGames();
        }
    }

    void OnLibrarySizeChanged(object sender, SizeChangedEventArgs e)
    {
        if (Settings.LibraryView != "list" && Math.Abs(e.NewSize.Width - e.PreviousSize.Width) > 0.5) ApplyGridMetrics();
    }

    void OnItemInvoked(ItemsView sender, ItemsViewItemInvokedEventArgs args)
    {
        if (args.InvokedItem is not GameItem item) return;
        // The check selects; anywhere else on the card opens the game.
        var onCheck = pressedOnCheck;
        pressedOnCheck = false;
        if (onCheck) { if (!item.Game.Blocked) item.IsSelected = !item.IsSelected; }
        else if (shell.PresetSelecting) _ = ApplyPresetsAsync([item.Game]);
        else shell.OpenGame(item.Game);
    }

    // Hit-test by position: the ItemContainer's own chrome sits over the
    // template, so the press's OriginalSource is never the check itself.
    bool IsOnCheck(global::Windows.Foundation.Point point) =>
        VisualTreeHelper.FindElementsInHostCoordinates(point, Library, includeAllElements: true)
            .Any(e => e is FrameworkElement { Tag: "check", Visibility: Visibility.Visible, Opacity: > 0 });

    void OnLibraryRightTapped(object sender, RightTappedRoutedEventArgs e)
    {
        if ((e.OriginalSource as FrameworkElement)?.DataContext is not GameItem item) return;
        GameMenu(item.Game).ShowAt((FrameworkElement)e.OriginalSource, e.GetPosition((UIElement)e.OriginalSource));
        e.Handled = true;
    }

    MenuFlyout GameMenu(Game game)
    {
        var menu = new MenuFlyout();
        void Add(string caption, string glyph, Action run, bool enabled = true)
        {
            var item = new MenuFlyoutItem { Text = caption, IsEnabled = enabled, Icon = new FontIcon { Glyph = glyph } };
            item.Click += (_, _) => run();
            menu.Items.Add(item);
        }
        Add("Game Details", "", () => shell.OpenGame(game));
        Add("DLSS Files", "", () => shell.OpenGame(game, "DLSS Files"));
        menu.Items.Add(new MenuFlyoutSeparator());
        Add(game.InstallLabel, "", () => _ = shell.LaunchAction("install", [game]), (!game.Blocked || game.AdoptionAvailable) && !shell.Busy);
        if (game.OfflineOnly) Add("Launch offline", "", () => _ = shell.LaunchOfflineAsync(game), !shell.Busy);
        Add("Restore Original Files", "", () => _ = shell.LaunchAction("uninstall", [game]), game.Installed && !shell.Busy);
        menu.Items.Add(new MenuFlyoutSeparator());
        Add("Open Folder", "", () => _ = shell.OpenGameFolderAsync(game),
            !shell.Service.IsPreview && Directory.Exists(game.Location));
        menu.Items.Add(new MenuFlyoutSeparator());
        Add("Remove from library", "", () => _ = shell.ConfirmRemoveLibraryEntriesAsync([game]), !shell.Busy);
        return menu;
    }

    void OnViewChecked(object sender, RoutedEventArgs e)
    {
        Settings.LibraryView = (string)((FrameworkElement)sender).Tag;
        if (ready) { Settings.Save(); ShowGames(); }
    }

    void OnFilterChecked(object sender, RoutedEventArgs e)
    {
        Settings.LibraryFilter = (string)((FrameworkElement)sender).Tag;
        if (ready) ShowGames();
    }

    void OnArtScaleChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        Settings.ArtScale = (int)e.NewValue;
        if (ready) ShowGames();
    }

    // ---------- Selection (Linux "Install Selected") ----------

    /// <summary>Selects every supported game in the current view (filter + search); Clear while anything is selected.</summary>
    void OnSelectAll(object sender, RoutedEventArgs e)
    {
        var visible = Library.ItemsSource as IEnumerable<GameItem> ?? [];
        var clear = selectedIds.Count > 0;
        // Item setters report back through actions.Select, keeping selectedIds in step.
        foreach (var item in visible.Where(i => !i.Game.Blocked)) item.IsSelected = !clear;
        if (clear) selectedIds.Clear();
        UpdateSelectionActions();
    }

    List<Game> SelectedGames() => shell.Games.Where(g => selectedIds.Contains(g.Id)).ToList();

    // ---------- Artwork accent ring on hover (Linux .gallery-artwork-ring) ----------

    // Hover drives GameItem.IsHovered; the templates bind the ring and title
    // tint to it, so nothing is resized or restyled in code.
    void OnLibraryPointerMoved(object sender, PointerRoutedEventArgs e)
    {
        var item = (e.OriginalSource as FrameworkElement)?.DataContext as GameItem;
        if (item == hovered) return;
        if (hovered is not null) hovered.IsHovered = false;
        hovered = item;
        if (item is not null) item.IsHovered = true;
    }

    void OnLibraryPointerExited(object sender, PointerRoutedEventArgs e)
    {
        if (hovered is not null) hovered.IsHovered = false;
        hovered = null;
    }

    void UpdateSelectionActions()
    {
        var count = SelectedGames().Count;
        InstallText.Text = count > 0 ? $"Install Selected ({count})" : "Install Features";
        shell.SyncCompactDashboard(shell.Mode, ModeNrOnly.IsEnabled, InstallText.Text);
        shell.SyncCompactPresets(count);
        SelectAllButton.Label = count > 0 ? "Clear" : "Select all";
        RemoveSelectedButton.IsEnabled = count > 0 && !shell.Busy;
        SelectAllIcon.Glyph = count > 0 ? "" : "";
        ToolTipService.SetToolTip(SelectAllButton, count > 0 ? "Clear selection" : "Select every game in this view");
        // Once anything is selected, every card shows its check.
        if (Library.ItemsSource is IEnumerable<GameItem> visible)
            foreach (var item in visible) item.IsSelecting = selectedIds.Count > 0;
    }

    void OnInstallFeatures(object sender, RoutedEventArgs e) => _ = shell.LaunchAction("install", Selection().Where(g => !g.Blocked).ToList());
    void OnRestoreOriginal(object sender, RoutedEventArgs e) => _ = shell.LaunchAction("uninstall", Selection().Where(g => g.Installed).ToList());
    void OnUpdateDlss(object sender, RoutedEventArgs e) => _ = shell.LaunchAction("update-dlss", Selection().Where(g => !g.Blocked).ToList());

    List<Game> Selection() => LibraryScope.Targets(shell.Games, Settings.LibraryFilter, shell.Query, selectedIds);

    // ---------- Features mode ----------

    void OnProfileChecked(object sender, RoutedEventArgs e)
    {
        if (!syncingMode) SetMode((string)((FrameworkElement)sender).Tag);
    }

    void SetMode(string value)
    {
        if (Settings.RuntimeProvider == "feeder") value = "nr-only";
        shell.Mode = value;
        syncingMode = true;
        foreach (var toggle in new[] { ModeNrOnly, ModeMfgOnly, ModeNrMfg })
            toggle.IsChecked = (string)toggle.Tag == value;
        syncingMode = false;
        ProfileNote.Text = value switch
        {
            "nr-only" => "Neural Rendering",
            "nr-mfg" => "Neural Rendering and frame generation",
            _ => "Native frame generation",
        };
        shell.SyncCompactDashboard(value, ModeNrOnly.IsEnabled, InstallText.Text);
    }


    // ---------- Library commands ----------

    void OnRefreshLibrary(object sender, RoutedEventArgs e) => _ = shell.RescanLibraryAsync();
    void OnAddLibraryFolder(object sender, RoutedEventArgs e) => _ = shell.AddLibraryFolderAsync(collection: true);
    void OnRemoveSelected(object sender, RoutedEventArgs e) => _ = shell.ConfirmRemoveLibraryEntriesAsync(SelectedGames());
    void OnRemovedGames(object sender, RoutedEventArgs e) => _ = shell.ShowRemovedLibraryEntriesAsync();

    void OnAddGameFolder(object sender, RoutedEventArgs e) => _ = shell.AddLibraryFolderAsync();
}
