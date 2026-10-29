using Microsoft.UI.Dispatching;
using Microsoft.UI.Input;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using RtxForge.Windows.Views;

namespace RtxForge.Windows;

/// <summary>
/// Shell window. Owns the library state and the install/restore/update
/// operations shared by every page (Window in rtxforge_gtk.py).
/// </summary>
public sealed partial class MainWindow : Window
{
    readonly List<string> log = [];
    DispatcherQueueTimer? toastTimer;
    bool syncingNav;

    public IForgeService Service { get; }
    public ForgeSettings Settings => Service.Settings;
    public IReadOnlyList<Game> Games { get; private set; } = [];
    public HardwareInfo? Hardware { get; private set; }
    public IReadOnlyList<string> Log => log;
    /// <summary>Library search text; kept here so it survives page navigation.</summary>
    public string Query
    {
        get => query;
        set { if (query == value) return; query = value; QueryChanged?.Invoke(); }
    }
    string query = "";
    public string Mode { get; set; } = "mfg-only";
    public bool Busy { get; private set; }
    public bool LibraryRefreshing { get; private set; } = true;
    public string? LibraryLoadError { get; private set; }

    public event Action? GamesChanged;
    public event Action? QueryChanged;
    public event Action? SettingsChanged;

    public MainWindow(IForgeService service)
    {
        Service = service;
        if (service is EngineForgeService engine) Games = engine.CachedLibrary();
        App.Main = this;
        InitializeComponent();
        Nav.RegisterPropertyChangedCallback(NavigationView.IsPaneOpenProperty, (_, _) => UpdateNavigationCommands());
        Nav.DisplayModeChanged += (_, _) => UpdateNavigationCommands();
        Nav.Loaded += (_, _) => UpdateNavigationCommands();
        UpdateNavigationCommands();

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);
        SizeCaptionButtons();
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "rtxforge.ico"));
        SizeLikeABrowser();
        RootGrid.ActualThemeChanged += (_, _) => ThemeController.Apply(this, RootGrid, Settings.Theme);

        PreviewBadge.Visibility = service.IsPreview ? Visibility.Visible : Visibility.Collapsed;
        Mode = NrOnlyAvailable || Settings.DefaultProfile != "nr-only" ? Settings.DefaultProfile : "mfg-only";
        if (Settings.RuntimeProvider == "feeder") Mode = "nr-only";
        ThemeController.Apply(this, RootGrid, Settings.Theme);

        if (SettingsPage.OpenOverlaySection)
        {
            // NavigationView creates its Settings item when the template loads.
            void OpenOverlaySettings(object sender, RoutedEventArgs e)
            {
                RootGrid.Loaded -= OpenOverlaySettings;
                Navigate("Settings");
            }
            RootGrid.Loaded += OpenOverlaySettings;
        }
        else Nav.SelectedItem = Nav.MenuItems[0];
        Closed += (_, _) => (Service as IDisposable)?.Dispose();
        InitializeGameMode();
        InitializeCompanion();
        RootGrid.KeyDown += (_, e) =>
        {
            if (e.Key == global::Windows.System.VirtualKey.F5) { e.Handled = true; _ = RescanLibraryAsync(); }
        };
        _ = LoadAsync();
        if (App.EngineProblem is { } problem)
            DispatcherQueue.TryEnqueue(() => ShowToast("Preview mode · " + problem));
    }

    /// <summary>Open at a 16:9 window filling most of the work area, centered.</summary>
    void SizeLikeABrowser()
    {
        const double ratio = 16.0 / 9;
        var area = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Primary).WorkArea;
        var height = (int)(area.Height * 0.80);
        var width = (int)(height * ratio);
        if (width > area.Width * 0.90) { width = (int)(area.Width * 0.90); height = (int)(width / ratio); }
        AppWindow.MoveAndResize(new global::Windows.Graphics.RectInt32(
            area.X + (area.Width - width) / 2, area.Y + (area.Height - height) / 2, width, height));
    }

    /// <summary>NR Only requires DLSS-Unlocked or a custom package (provider rule).</summary>
    public bool NrOnlyAvailable => Settings.RuntimeProvider is "dlss-unlocked" or "custom" or "skynizz" or "feeder";

    public void SaveSettings()
    {
        Settings.Save(preserveOverlay: true);
        ThemeController.Apply(this, RootGrid, Settings.Theme);
        SettingsChanged?.Invoke();
    }

    async Task LoadAsync()
    {
        // Neither hardware probing nor a full folder walk should delay a cached library.
        async Task ReadHardwareAsync()
        {
            try { Hardware = await Service.DetectHardwareAsync(); }
            catch (InvalidOperationException error) { AddLog("Hardware check: " + error.Message); }
        }
        var hardware = ReadHardwareAsync();
        try
        {
            await ScanAsync();
        }
        catch (InvalidOperationException error)
        {
            AddLog("Library scan stopped: " + error.Message);
            ShowToast("Could not read your library: " + error.Message);
        }
        await hardware;
#if DEBUG
        StartCrossOsReview();
#endif
    }

    /// <summary>Re-render pages after per-game changes (for example a custom accent).</summary>
    public void NotifyGamesChanged() => GamesChanged?.Invoke();

    public async Task ScanAsync()
    {
        string CurrentKey() => LibrarySnapshot.Key(Settings.RuntimeProvider, Settings.GameFolders, Settings.LibraryFolders);
        while (true)
        {
            if (libraryScan is not { IsCompleted: false })
            {
                libraryScanKey = CurrentKey();
                libraryScan = ScanLibraryCoreAsync();
            }
            var active = libraryScan;
            var activeKey = libraryScanKey;
            await active;
            // Adding a folder during startup must not reuse the older inventory.
            // UI-thread callers share an in-flight scan for the same settings.
            if (activeKey == CurrentKey()) return;
        }
    }

    Task? libraryScan;
    string? libraryScanKey;

    async Task ScanLibraryCoreAsync()
    {
        LibraryRefreshing = true; LibraryLoadError = null; GamesChanged?.Invoke();
        try
        {
            Games = await Service.ScanAsync();
        }
        catch (InvalidOperationException error) { LibraryLoadError = error.Message; throw; }
        finally { LibraryRefreshing = false; GamesChanged?.Invoke(); }
        if (!Service.IsPreview)
        {
            _ = OverlayHelper.CacheGameIdentitiesAsync(Games.ToArray());
            _ = OverlayHelper.CommandAsync("refresh-targets", start: false);
        }
        // Linux fetch_media: cached artwork and store details, downloaded when missing.
        _ = RefreshArtworkAsync(false);
    }

    // ---------- Navigation ----------

    void OnNavSelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (syncingNav) return;
        if (args.IsSettingsSelected) Navigate("Settings");
        else if (args.SelectedItem is NavigationViewItem item) Navigate((string)item.Tag);
    }

    public void Navigate(string tag, object? parameter = null)
    {
        var page = tag switch
        {
            "Settings" => typeof(SettingsPage),
            "Activity" => typeof(ActivityPage),
            "Presets" => typeof(PresetsPage),
            "Packages" => typeof(PackagesPage),
            "Extras" => typeof(ExtrasPage),
            "Game" => typeof(GamePage),
            _ => typeof(LibraryPage),
        };
        if (page == ContentFrame.SourcePageType && parameter is null) return;
        ContentFrame.Navigate(page, parameter ?? tag);
    }

    public void OpenGame(Game game, string section = "Overview")
    {
        if (Settings.SeparateGameDetails && !InGameMode) OpenGameWindow(game, section);
        else Navigate("Game", new GameRequest(game, section));
    }

    void OnNavigationBackClick(object sender, RoutedEventArgs e)
    {
        if (ContentFrame.CanGoBack) ContentFrame.GoBack();
    }

    void OnNavigationMenuClick(object sender, RoutedEventArgs e) => Nav.IsPaneOpen = !Nav.IsPaneOpen;

    CornerRadius? paneRadius;

    /// <summary>An overlay pane (phone and tablet) meets the content with square inner corners.</summary>
    void SquarePane(bool square)
    {
        static SplitView? Find(DependencyObject parent)
        {
            for (var i = 0; i < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(parent); i++)
            {
                var child = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(parent, i);
                if (child is SplitView { Name: "RootSplitView" } split) return split;
                if (Find(child) is { } found) return found;
            }
            return null;
        }
        if (Find(Nav) is not { } split) return;
        paneRadius ??= split.CornerRadius;
        split.CornerRadius = square ? new CornerRadius(0) : paneRadius.Value;
    }

    /// <summary>Back and the phone menu sit just before the mark, as in TitleBar, instead of pushing it across.</summary>
    void UpdateBrandSpacing()
    {
        var back = TitleBack.Visibility == Visibility.Visible;
        var menu = TitlePaneToggle.Visibility == Visibility.Visible;
        TitlePaneToggle.Margin = new Thickness(back ? 4 : 12, 0, 6, 0);
        CompactBrand.Margin = new Thickness(back || menu ? 6 : 12, 0, 12, 0);
        UpdateTitleBarRegions();
    }

    void UpdateNavigationCommands()
    {
        // NavigationView hides PaneHeader in compact mode. Its native toggle
        // remains reachable there so the pane can always be expanded again.
        // In Minimal (phone) mode the titlebar's toggle replaces it.
        var minimal = Nav.DisplayMode == NavigationViewDisplayMode.Minimal;
        Nav.IsPaneToggleButtonVisible = !Nav.IsPaneOpen && !minimal;
        TitlePaneToggle.Visibility = minimal ? Visibility.Visible : Visibility.Collapsed;
        // The titlebar toggle opens and closes it, so the pane's own header toggle would repeat it.
        NavigationCommands.Visibility = minimal ? Visibility.Collapsed : Visibility.Visible;
        // Phone and tablet panes open over the content: square their inner corners.
        SquarePane(Nav.DisplayMode != NavigationViewDisplayMode.Expanded);
        UpdateBrandSpacing();
        var padding = Nav.IsPaneOpen ? 12 : 4;
        NavigationCommands.Width = Math.Max(40, (Nav.IsPaneOpen ? Nav.OpenPaneLength : Nav.CompactPaneLength) - padding * 2);
        NavigationCommands.Margin = new Thickness(padding, 6, padding, 6);
        // The brand lines up with the open pane; beside the compact rail it only needs its own width.
        BrandColumn.MinWidth = Nav.IsPaneOpen ? Nav.OpenPaneLength : 0;
        UpdateTitleBarRegions();
    }

    void OnFrameNavigated(object sender, NavigationEventArgs e)
    {
        TitleBack.Visibility = ContentFrame.CanGoBack ? Visibility.Visible : Visibility.Collapsed;
        UpdateBrandSpacing();
        var tag = e.SourcePageType == typeof(SettingsPage) ? "Settings"
            : e.SourcePageType == typeof(ActivityPage) ? "Activity"
            : e.SourcePageType == typeof(PresetsPage) ? "Presets"
            : e.SourcePageType == typeof(PackagesPage) ? "Packages"
            : e.SourcePageType == typeof(ExtrasPage) ? "Extras"
            : "Library";
        syncingNav = true;
        Nav.SelectedItem = tag == "Settings"
            ? Nav.SettingsItem
            : Nav.MenuItems.Concat(Nav.FooterMenuItems).OfType<NavigationViewItem>().First(i => (string)i.Tag == tag);
        syncingNav = false;
    }

    // ---------- Operations ----------

    /// <summary>
    /// Install / uninstall / update-dlss / reset / apply through the Linux
    /// modal flow: presets (install) → review → progress → done. True when the reviewed run completed.
    /// </summary>
    public async Task<bool> LaunchAction(string operation, IReadOnlyList<Game> targets, Tuning? values = null)
    {
        if (Busy) { ShowToast("Another operation is running."); return false; }
        ArgumentNullException.ThrowIfNull(targets);
        if (targets.Count == 0) { ShowToast("No eligible games selected."); return false; }
        // Another tool's setup: installing only such games offers Adoption's choices; in a group install
        // the engine adopts them in the same review. Restore has nothing of rtxForge's to undo.
        if (targets.Any(g => g.AdoptionAvailable) && (operation != "install" || targets.All(g => g.AdoptionAvailable)))
        {
            var adoptable = targets.Where(g => g.AdoptionAvailable).ToArray();
            if (operation == "install") await ReviewAdoptionAsync(adoptable);
            else if (operation == "uninstall") ShowToast(AdoptionSkipped(adoptable.Length));
            if (operation is "install" or "uninstall") targets = targets.Where(g => !g.AdoptionAvailable).ToArray();
            if (targets.Count == 0) return false;
        }

        if (operation == "install" && values is null)
        {
            values = await OperationDialog.AskPresetsAsync(this, targets.Count == 1 ? GameTuning(targets[0]) : Settings.Presets, AccentResources.Single(targets), targets);
            if (values is null) return false;
        }
        return await OperationDialog.ShowAsync(this, operation, targets, values ?? Settings.Presets);
    }

    /// <summary>Runs one reviewed operation against the engine; used by the progress stage of the modal.</summary>
    public async Task<int> ExecuteAsync(OperationReview review, IProgress<OperationStep> progress, CancellationToken cancel)
    {
        Busy = true;
        AddLog($"{review.Operation} · {review.Ready.Count} game(s)");
        try
        {
            var logged = new Progress<OperationStep>(step =>
            {
                AddLog($"{step.Caption} {step.Game.Name}");
                progress.Report(step);
            });
            var count = await Service.ExecuteAsync(review, logged, cancel);
            AddLog($"{count} game(s) updated");
            return count;
        }
        catch (Exception error)
        {
            AddLog("Stopped: " + error.Message);
            throw;
        }
        finally
        {
            Busy = false;
            // The engine wrote real files: read the library back rather than assume.
            if (!Service.IsPreview) await ScanAsync();
            else GamesChanged?.Invoke();
        }
    }

    public Tuning GameTuning(Game game) => new(
        game.NrStrength ?? Settings.NrStrength,
        game.SharpeningStrength ?? Settings.SharpeningStrength,
        game.MfgMultiplier ?? Settings.MfgMultiplier, null, game.FeatureControls);

    void AddLog(string text) => log.Add($"{DateTime.Now:HH:mm:ss}  {text}");

    /// <summary>Adw.Toast: a short opaque notice at the bottom of the window.</summary>
    public void ShowToast(string text)
    {
        if (detailsDialogRoot is Frame { Content: GamePage gamePage }) { gamePage.ShowNotice(text); return; }
        Toast.Message = text;
        ToastHost.Visibility = Visibility.Visible;
        Toast.IsOpen = true;
        toastTimer?.Stop();
        toastTimer = DispatcherQueue.CreateTimer();
        toastTimer.Interval = TimeSpan.FromSeconds(5);
        toastTimer.IsRepeating = false;
        toastTimer.Tick += (_, _) => Toast.IsOpen = false;
        toastTimer.Start();
    }

    void OnToastClosed(InfoBar sender, InfoBarClosedEventArgs args) => ToastHost.Visibility = Visibility.Collapsed;

    /// <summary>A ContentDialog themed to match the window.</summary>
    public ContentDialog NewDialog()
    {
        var dialog = new ContentDialog
        {
            XamlRoot = detailsDialogRoot?.XamlRoot ?? RootGrid.XamlRoot,
            Style = (Style)Application.Current.Resources["DefaultContentDialogStyle"],
            RequestedTheme = RootGrid.ActualTheme,
        };
        // WinUI caps dialogs at 548 px, narrower than rtxForge's review lists: their row actions were cut off.
        dialog.Resources["ContentDialogMaxWidth"] = 760.0;
        return dialog;
    }

    public static string AppVersion
    {
        get
        {
            try { return File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "VERSION")).Trim(); }
            catch (IOException) { return "dev"; }
        }
    }

    public async Task Message(string title, object content)
    {
        var dialog = NewDialog();
        dialog.Title = title;
        dialog.Content = content is string text ? Prefs.Label(text) : content;
        dialog.CloseButtonText = "Close";
        await dialog.ShowAsync();
    }

    public nint Handle => WinRT.Interop.WindowNative.GetWindowHandle(this);
}

public sealed record GameRequest(Game Game, string Section, bool SeparateWindow = false);
