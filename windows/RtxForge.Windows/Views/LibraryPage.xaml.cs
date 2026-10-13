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
    readonly TuningPanel tuning;
    readonly GameActions actions;
    readonly HashSet<string> selectedIds = [];
    bool syncingMode, ready, pressedOnCheck;
    GameItem? hovered;
    int density;
    bool compact;

    ForgeSettings Settings => shell.Settings;

    public LibraryPage()
    {
        InitializeComponent();

        // List view Actions column: Install / Restore, and the row's "…" menu.
        actions = new GameActions(
            game => _ = shell.LaunchAction(game.Installed ? "uninstall" : "install", [game]),
            (game, target) => GameMenu(game).ShowAt(target),
            (game, on) =>
            {
                if (on) selectedIds.Add(game.Id); else selectedIds.Remove(game.Id);
                UpdateSelectionActions();
            });

        tuning = new TuningPanel(Settings.Presets);
        tuning.Changed += (_, _) => PresetActions.Visibility = tuning.Value == Settings.Presets ? Visibility.Collapsed : Visibility.Visible;
        TuningHost.Content = tuning;

        SearchBox.Text = shell.Query;
        ArtScale.Value = Settings.ArtScale;
        (Settings.LibraryFilter switch { "available" => FilterAvailable, "installed" => FilterInstalled, _ => FilterAll }).IsChecked = true;
        ApplySettings();
        ready = true;

        // ItemContainer marks presses handled, so listen with handledEventsToo
        // to learn whether the press started on a selection check.
        Library.AddHandler(PointerPressedEvent, new PointerEventHandler((_, e) => pressedOnCheck = IsOnCheck(e.GetCurrentPoint(null).Position)), true);

        shell.GamesChanged += ShowGames;
        shell.QueryChanged += ShowGames;
        shell.SettingsChanged += ApplySettings;
        ShowGames();
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        ShowGames();
    }

    void OnSearchChanged(AutoSuggestBox sender, AutoSuggestBoxTextChangedEventArgs args) =>
        shell.Query = sender.Text?.Trim() ?? "";

    void ApplySettings()
    {
        ModeNrOnly.IsEnabled = shell.NrOnlyAvailable;
        SetMode(shell.Mode);
        (Settings.LibraryView switch { "capsules" => ViewCapsules, "list" => ViewList, _ => ViewPosters }).IsChecked = true;
        Hero.Visibility = Settings.CompactHeader ? Visibility.Collapsed : Visibility.Visible;
        tuning.Value = Settings.Presets;
        PresetActions.Visibility = Visibility.Collapsed;
    }

    // ---------- Library ----------

    void ShowGames()
    {
        var games = shell.Games;
        var libs = games.Select(g => g.Library).Distinct().Count();
        var installs = games.Count(g => g.Installed);
        StatsText.Text = games.Count == 0 && shell.Hardware is null
            ? "Finding your games…"
            : $"{games.Count} games · {libs} locations · {installs} OptiScaler installs detected";
        if (shell.Hardware is { } hardware)
            HardwareText.Text = shell.Service.IsPreview
                ? "Preview mode · no game writes"
                : hardware.Gpu + " · " + (hardware.Ready ? "Hardware check passed" : "Install unavailable — see Settings");

        var scale = Settings.ArtScale / 100.0;
        var items = games
            .Where(g => Settings.LibraryFilter switch
            {
                "available" => !g.Installed && !g.Blocked,
                "installed" => g.Installed,
                _ => true,
            })
            .Where(g => shell.Query.Length == 0 || g.Name.Contains(shell.Query, StringComparison.OrdinalIgnoreCase))
            .OrderBy(g => g.Name, StringComparer.CurrentCultureIgnoreCase)
            .Select(g => new GameItem(g, Settings, actions, selectedIds.Count > 0, selectedIds.Contains(g.Id), density))
            .ToList();
        for (var i = 0; i < items.Count; i++)
        {
            items[i].Position = i;
            items[i].IsLast = i == items.Count - 1;
        }

        var view = Settings.LibraryView;
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
        EmptyText.Visibility = items.Count == 0 && games.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
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
        const double gap = 16, footer = 68, border = 4;
        var capsules = Settings.LibraryView == "capsules";
        var preferred = (capsules ? 300 : 180) * Settings.ArtScale / 100.0;
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
        var side = Math.Round(Math.Clamp(width * 0.03, 16, 56));
        Body.Padding = new Thickness(side, 12, side, 48);

        var narrowHero = width < 1100;
        Grid.SetRow(HeroActions, narrowHero ? 1 : 0);
        Grid.SetColumn(HeroActions, narrowHero ? 1 : 2);
        HeroActions.HorizontalAlignment = narrowHero ? HorizontalAlignment.Left : HorizontalAlignment.Right;

        var nowCompact = width < 1180;
        if (nowCompact != compact)
        {
            compact = nowCompact;
            foreach (var (element, column) in new (FrameworkElement, int)[] { (ViewGroup, 0), (ArtScale, 1), (LibraryCommands, 2) })
            {
                Grid.SetRow(element, compact ? 1 : 0);
                Grid.SetColumn(element, compact ? column : column + 3);
            }
            if (compact) Grid.SetColumnSpan(LibraryCommands, 4); else Grid.SetColumnSpan(LibraryCommands, 1);
            LibraryCommands.HorizontalAlignment = compact ? HorizontalAlignment.Left : HorizontalAlignment.Stretch;
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
        Add("Install Features", "", () => _ = shell.LaunchAction("install", [game]), !game.Blocked && !shell.Busy);
        Add("Restore Original Files", "", () => _ = shell.LaunchAction("uninstall", [game]), game.Installed && !shell.Busy);
        menu.Items.Add(new MenuFlyoutSeparator());
        Add("Open Folder", "", () => Process.Start(new ProcessStartInfo("explorer.exe", $"\"{game.Location}\"") { UseShellExecute = true }),
            !shell.Service.IsPreview && Directory.Exists(game.Location));
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
        SelectAllButton.Label = count > 0 ? "Clear" : "Select all";
        SelectAllIcon.Glyph = count > 0 ? "" : "";
        ToolTipService.SetToolTip(SelectAllButton, count > 0 ? "Clear selection" : "Select every game in this view");
        // Once anything is selected, every card shows its check.
        if (Library.ItemsSource is IEnumerable<GameItem> visible)
            foreach (var item in visible) item.IsSelecting = selectedIds.Count > 0;
    }

    void OnInstallFeatures(object sender, RoutedEventArgs e) => _ = shell.LaunchAction("install", Selection());
    void OnRestoreOriginal(object sender, RoutedEventArgs e) => _ = shell.LaunchAction("uninstall", Selection()?.Where(g => g.Installed).ToList());
    void OnUpdateDlss(object sender, RoutedEventArgs e) => _ = shell.LaunchAction("update-dlss", Selection());

    List<Game>? Selection()
    {
        var selected = SelectedGames();
        return selected.Count > 0 ? selected : null;
    }

    // ---------- Features mode ----------

    void OnProfileChecked(object sender, RoutedEventArgs e)
    {
        if (!syncingMode) SetMode((string)((FrameworkElement)sender).Tag);
    }

    void SetMode(string value)
    {
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
        tuning.SetMode(value);
    }

    // ---------- Presets ----------

    void OnResetPresets(object sender, RoutedEventArgs e)
    {
        tuning.Value = Settings.Presets;
        PresetActions.Visibility = Visibility.Collapsed;
    }

    async void OnApplyPresets(object sender, RoutedEventArgs e)
    {
        var value = tuning.Value;
        Settings.NrStrength = value.NrStrength;
        Settings.SharpeningStrength = value.SharpeningStrength;
        Settings.MfgMultiplier = value.MfgMultiplier;
        Settings.Save();
        PresetActions.Visibility = Visibility.Collapsed;
        // Applying updates eligible managed INIs and saves global defaults.
        var eligible = shell.Games.Where(g => g.Installed && g.NrStrength is null).ToList();
        if (eligible.Count > 0) await shell.LaunchAction("apply", eligible, value);
        else shell.ShowToast("Presets saved.");
    }

    // ---------- Library commands ----------

    void OnRefreshLibrary(object sender, RoutedEventArgs e) => _ = shell.ScanAsync();

    async void OnAddGameFolder(object sender, RoutedEventArgs e)
    {
        var picker = new global::Windows.Storage.Pickers.FolderPicker();
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, shell.Handle);
        var folder = await picker.PickSingleFolderAsync();
        if (folder is null) return;
        if (!Settings.GameFolders.Contains(folder.Path)) Settings.GameFolders.Add(folder.Path);
        Settings.Save();
        shell.ShowToast($"Added {folder.Path}");
        await shell.ScanAsync();
    }
}
