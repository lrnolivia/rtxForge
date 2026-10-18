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

    public event Action? GamesChanged;
    public event Action? QueryChanged;
    public event Action? SettingsChanged;

    public MainWindow(IForgeService service)
    {
        Service = service;
        App.Main = this;
        InitializeComponent();

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);
        SizeCaptionButtons();
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "rtxforge.ico"));
        SizeLikeABrowser();
        RootGrid.ActualThemeChanged += (_, _) => ThemeController.Apply(this, RootGrid, Settings.Theme);

        PreviewBadge.Visibility = service.IsPreview ? Visibility.Visible : Visibility.Collapsed;
        Mode = Settings.RuntimeProvider == "skynizz" && Settings.DefaultProfile == "mfg-only" ? "nr-mfg" : NrOnlyAvailable || Settings.DefaultProfile != "nr-only" ? Settings.DefaultProfile : "mfg-only";
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
        try
        {
            Hardware = await Service.DetectHardwareAsync();
            await ScanAsync();
            var arguments = Environment.GetCommandLineArgs();
            if (arguments.Contains("--controls", StringComparer.OrdinalIgnoreCase))
            {
                OpenCompanion();
            }
        }
        catch (InvalidOperationException error)
        {
            AddLog("Library scan stopped: " + error.Message);
            ShowToast("Could not read your library: " + error.Message);
        }
    }

    /// <summary>Re-render pages after per-game changes (for example a custom accent).</summary>
    public void NotifyGamesChanged() => GamesChanged?.Invoke();

    public async Task ScanAsync()
    {
        if (libraryScan is { IsCompleted: false }) { await libraryScan; return; }
        libraryScan = ScanLibraryCoreAsync();
        await libraryScan;
    }

    Task? libraryScan;

    async Task ScanLibraryCoreAsync()
    {
        Games = await Service.ScanAsync();
        GamesChanged?.Invoke();
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

    public void OpenGame(Game game, string section = "Overview") => Navigate("Game", new GameRequest(game, section));

    void OnNavBackRequested(NavigationView sender, NavigationViewBackRequestedEventArgs args)
    {
        if (ContentFrame.CanGoBack) ContentFrame.GoBack();
    }

    void OnFrameNavigated(object sender, NavigationEventArgs e)
    {
        Nav.IsBackEnabled = ContentFrame.CanGoBack;
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
    /// modal flow: presets (install) → review → progress → done.
    /// </summary>
    public async Task LaunchAction(string operation, IReadOnlyList<Game> targets, Tuning? values = null)
    {
        if (Busy) { ShowToast("Another operation is running."); return; }
        ArgumentNullException.ThrowIfNull(targets);
        if (targets.Count == 0) { ShowToast("No eligible games selected."); return; }

        if (operation == "install" && values is null && Settings.RuntimeProvider != "feeder" && !targets.All(g => g.IsFeeder))
        {
            values = await OperationDialog.AskPresetsAsync(this, targets.Count == 1 ? GameTuning(targets[0]) : Settings.Presets);
            if (values is null) return;
        }
        await OperationDialog.ShowAsync(this, operation, targets, values ?? Settings.Presets);
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
        game.MfgMultiplier ?? Settings.MfgMultiplier);

    void AddLog(string text) => log.Add($"{DateTime.Now:HH:mm:ss}  {text}");

    /// <summary>Adw.Toast: a short opaque notice at the bottom of the window.</summary>
    public void ShowToast(string text)
    {
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
            XamlRoot = RootGrid.XamlRoot,
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

public sealed record GameRequest(Game Game, string Section);
