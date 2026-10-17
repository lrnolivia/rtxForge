using System.Diagnostics;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using Windows.Graphics.Imaging;

namespace RtxForge.Windows;

/// <summary>
/// Desktop actions shared by Settings, Game Details, Packages and Extras: library media,
/// custom artwork and Steam sync, SteamGridDB, recovery, reports, NR diagnosis and updates
/// (Window methods of the same names in gui/rtxforge_gtk.py).
/// </summary>
public sealed partial class MainWindow
{
    int mediaGeneration;

    public static readonly Dictionary<string, string> ArtworkRoles = new()
    {
        ["poster"] = "Poster", ["capsule"] = "Wide Capsule", ["hero"] = "Hero", ["logo"] = "Logo",
    };

    // ---------- library media (fetch_media) ----------

    /// <summary>LibraryMedia.enrich for the library (cached; refresh downloads again). Applies results as they arrive.</summary>
    public async Task RefreshArtworkAsync(bool refresh, IReadOnlyList<Game>? games = null)
    {
        var generation = ++mediaGeneration;
        var targets = games ?? Games;
        if (targets.Count == 0) return;
        try
        {
            var media = await Service.LoadMediaAsync(targets, refresh);
            if (generation != mediaGeneration && games is null) return;
            ApplyMedia(media);
            if (refresh) ShowToast("Artwork refreshed. Cached images remain available offline.");
        }
        catch (InvalidOperationException error)
        {
            if (refresh) ShowToast("Could not refresh artwork: " + error.Message);
        }
    }

    void ApplyMedia(IEnumerable<GameMedia> media)
    {
        var changed = false;
        foreach (var item in media)
        {
            if (Games.FirstOrDefault(g => g.Id == item.GameId) is not { } game) continue;
            if (item.Poster is { } poster && poster != game.PosterPath) { game.PosterPath = poster; changed = true; }
            if (item.Capsule is { } capsule && capsule != game.CapsulePath) { game.CapsulePath = capsule; changed = true; }
            if (item.Hero is { } hero && hero != game.HeroPath) { game.HeroPath = hero; changed = true; }
            foreach (var (role, credit) in item.Credits) game.ArtCredits[role] = credit;
            if (string.IsNullOrEmpty(game.Summary) && item.Description is { } description) game.Summary = description;
            if (string.IsNullOrEmpty(game.Developer) && item.Developers is { } developers) game.Developer = developers;
            if (string.IsNullOrEmpty(game.Release) && item.Release is { } release) game.Release = release;
        }
        if (changed) GamesChanged?.Invoke();
    }

    // ---------- custom artwork (choose_game_artwork / reset_game_artwork / sync_steam_artwork) ----------

    public async Task<string?> PickFileAsync(params string[] extensions)
    {
        var picker = new global::Windows.Storage.Pickers.FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, Handle);
        foreach (var extension in extensions) picker.FileTypeFilter.Add(extension);
        var file = await picker.PickSingleFileAsync();
        return file?.Path;
    }

    /// <summary>Steam sync needs PNG or JPEG; WebP is converted with the Windows image codecs (artwork_overrides does this with GdkPixbuf).</summary>
    public static async Task<string> PngIfWebpAsync(string path)
    {
        var head = new byte[12];
        await using (var stream = File.OpenRead(path)) _ = await stream.ReadAsync(head);
        if (!(head[0] == 'R' && head[1] == 'I' && head[2] == 'F' && head[3] == 'F' && head[8] == 'W' && head[9] == 'E' && head[10] == 'B' && head[11] == 'P'))
            return path;
        var folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "state", "desktop", "converted");
        Directory.CreateDirectory(folder);
        var target = Path.Combine(folder, Guid.NewGuid().ToString("N") + ".png");
        try
        {
            using var input = await global::Windows.Storage.Streams.FileRandomAccessStream.OpenAsync(path, global::Windows.Storage.FileAccessMode.Read);
            var decoder = await BitmapDecoder.CreateAsync(input);
            using var pixels = await decoder.GetSoftwareBitmapAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied);
            using var output = await global::Windows.Storage.Streams.FileRandomAccessStream.OpenAsync(target, global::Windows.Storage.FileAccessMode.ReadWrite);
            var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, output);
            encoder.SetSoftwareBitmap(pixels);
            await encoder.FlushAsync();
        }
        catch (Exception error) when (error is System.Runtime.InteropServices.COMException or IOException or ArgumentException)
        {
            throw new InvalidOperationException("Windows could not read this WebP image. Export it as PNG, then choose it again.");
        }
        return target;
    }

    public async Task ChooseArtworkAsync(Game game, string role)
    {
        if (Service.IsPreview) { ShowToast("Custom artwork is disabled in preview mode."); return; }
        var path = await PickFileAsync(".png", ".jpg", ".jpeg", ".webp");
        if (path is null) return;
        try
        {
            await Service.StoreArtworkAsync(game, role, await PngIfWebpAsync(path));
        }
        catch (InvalidOperationException error) { await Message("Choose " + ArtworkRoles[role].ToLowerInvariant() + " artwork", error.Message); return; }
        await RefreshArtworkAsync(false, [game]);
        await SyncGameArtworkAsync(game);
    }

    public async Task ResetArtworkAsync(Game game, string role)
    {
        if (Service.IsPreview) { ShowToast("Custom artwork is disabled in preview mode."); return; }
        try { await Service.ResetArtworkAsync(game, role); }
        catch (InvalidOperationException error) { await Message("Reset artwork", error.Message); return; }
        await SyncGameArtworkAsync(game);
        // The scan reads Steam's artwork again without the custom image.
        await ScanAsync();
    }

    /// <summary>Uses an image already stored (SteamGridDB pick), then reviews its Steam sync.</summary>
    public async Task UseArtworkAsync(Game game, string role, string path, string credit)
    {
        try { await Service.StoreArtworkAsync(game, role, await PngIfWebpAsync(path), credit); }
        catch (InvalidOperationException error) { await Message("Use artwork", error.Message); return; }
        await RefreshArtworkAsync(false, [game]);
        await SyncGameArtworkAsync(game);
    }

    public async Task SyncGameArtworkAsync(Game game)
    {
        if (Service.IsPreview) { ShowToast("Steam artwork sync is disabled in preview mode."); return; }
        await ReviewDialog.ShowAsync(this, "Sync artwork to Steam", () => Service.ReviewArtworkSyncAsync([game], single: true),
            "Steam already shows this artwork.");
    }

    public async Task SyncLibraryArtworkAsync()
    {
        if (Service.IsPreview) { ShowToast("Steam artwork sync is disabled in preview mode."); return; }
        await ReviewDialog.ShowAsync(this, "Sync artwork to Steam", () => Service.ReviewArtworkSyncAsync(Games, single: false),
            "No custom artwork to sync yet.");
    }

    // ---------- Steam artwork profile (choose_steam_artwork_profile) ----------

    public async Task ChooseSteamArtworkProfileAsync()
    {
        if (Service.IsPreview) { ShowToast("Steam artwork is disabled in preview mode."); return; }
        IReadOnlyList<SteamArtworkProfile> accounts;
        try { accounts = await Service.SteamArtworkProfilesAsync(); }
        catch (InvalidOperationException error) { await Message("Steam artwork profile", error.Message); return; }
        var dialog = NewDialog();
        dialog.Title = "Steam artwork profile";
        dialog.CloseButtonText = "Close";
        var body = new StackPanel { Spacing = 8, MinWidth = 480 };
        body.Children.Add(Prefs.Label("Choose the local Steam account whose artwork rtxForge should update."));
        if (accounts.Count == 0) body.Children.Add(Prefs.Label("No Steam profile found. Open Steam once, then try again."));
        SteamArtworkProfile? chosen = null;
        foreach (var account in accounts)
        {
            var choose = Prefs.ActionButton(account.Selected ? "Selected" : "Choose", (_, _) => { chosen = account; dialog.Hide(); }, accent: !account.Selected);
            choose.IsEnabled = !account.Selected;
            body.Children.Add(Prefs.Row("Steam account " + account.UserId, account.Root, choose, ""));
        }
        dialog.Content = body;
        await dialog.ShowAsync();
        if (chosen is null) return;
        try
        {
            await Service.SelectSteamArtworkProfileAsync(chosen);
            ShowToast("Steam artwork profile selected");
        }
        catch (InvalidOperationException error) { await Message("Steam artwork profile", error.Message); }
    }

    // ---------- SteamGridDB connection (show_steamgrid_connection) ----------

    /// <summary>Returns true when a key is saved after the dialog closes.</summary>
    public async Task<bool> ConnectSteamGridAsync()
    {
        var status = await Service.SteamGridStatusAsync();
        var connected = status.Connected;
        var dialog = NewDialog();
        dialog.Title = "Connect SteamGridDB";
        var body = new StackPanel { Spacing = 12, MinWidth = 480 };
        body.Children.Add(Prefs.Label("Choose artwork from SteamGridDB in Desktop or Game Mode. Connect once with your own API key."));
        body.Children.Add(new HyperlinkButton { Content = "Get my key", NavigateUri = new Uri("https://www.steamgriddb.com/profile/preferences/api") });
        var entry = new PasswordBox { PlaceholderText = "Paste your SteamGridDB API key", IsEnabled = !Service.IsPreview };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(entry, "SteamGridDB API key");
        ToolTipService.SetToolTip(entry, "Stored only in Windows Credential Manager");
        body.Children.Add(entry);
        var line = Prefs.Label(Service.IsPreview ? "Preview only. No credentials are read or saved."
            : status.Problem ?? (connected ? "Connected. Desktop and Game Mode share this connection." : "Get your key, paste it above, then choose Connect."));
        body.Children.Add(line);
        body.Children.Add(Prefs.Label("Your key is saved in Windows Credential Manager, never in app settings or your game files.", "ForgeCaptionDimTextStyle"));
        dialog.Content = body;
        dialog.PrimaryButtonText = connected ? "Replace key" : "Connect";
        dialog.SecondaryButtonText = "Disconnect";
        dialog.CloseButtonText = "Close";
        dialog.IsPrimaryButtonEnabled = !Service.IsPreview;
        dialog.IsSecondaryButtonEnabled = connected && !Service.IsPreview;
        dialog.DefaultButton = ContentDialogButton.Primary;
        dialog.PrimaryButtonClick += async (_, args) =>
        {
            args.Cancel = true;
            var deferral = args.GetDeferral();
            line.Text = "Checking key and saving securely…";
            dialog.IsPrimaryButtonEnabled = dialog.IsSecondaryButtonEnabled = false;
            try
            {
                await Service.SteamGridConnectAsync(entry.Password);
                connected = true;
                line.Text = "Connected. Desktop and Game Mode share this connection.";
                dialog.PrimaryButtonText = "Replace key";
            }
            catch (InvalidOperationException error) { line.Text = error.Message; }
            finally
            {
                entry.Password = "";
                dialog.IsPrimaryButtonEnabled = true;
                dialog.IsSecondaryButtonEnabled = connected;
                deferral.Complete();
            }
        };
        dialog.SecondaryButtonClick += async (_, args) =>
        {
            args.Cancel = true;
            var deferral = args.GetDeferral();
            line.Text = "Removing saved connection…";
            try
            {
                var external = await Service.SteamGridDisconnectAsync();
                connected = external;
                dialog.PrimaryButtonText = "Connect";
                line.Text = external ? "Saved key removed. An external environment key is still configured." : "Disconnected. Your downloaded artwork stays in place.";
            }
            catch (InvalidOperationException error) { line.Text = error.Message; }
            finally { dialog.IsSecondaryButtonEnabled = connected; deferral.Complete(); }
        };
        await dialog.ShowAsync();
        entry.Password = "";
        return connected;
    }

    // ---------- SteamGridDB browser (open_steamgrid_search) ----------

    public async Task BrowseArtworkAsync(Game game, string role)
    {
        if (Service.IsPreview) { ShowToast("SteamGridDB is disabled in preview mode."); return; }
        SteamGridStatus status;
        try { status = await Service.SteamGridStatusAsync(); }
        catch (InvalidOperationException error) { await Message("SteamGridDB", error.Message); return; }
        if (!status.Connected && !await ConnectSteamGridAsync()) return;
        if (!status.Connected) status = await Service.SteamGridStatusAsync();
        await new SteamGridBrowser(this, game, role, status).ShowAsync();
    }

    // ---------- NR diagnosis (show_diagnostics) ----------

    public async Task DiagnoseAsync(Game game)
    {
        while (true)
        {
            NrDiagnosis report;
            try { report = await Service.DiagnoseAsync(game); }
            catch (InvalidOperationException error) { await Message(game.Name + " · NR Diagnosis", error.Message); return; }
            var body = new StackPanel { Spacing = 10, MinWidth = 560 };
            foreach (var warning in report.Warnings)
                body.Children.Add(new InfoBar { IsOpen = true, IsClosable = false, Severity = InfoBarSeverity.Warning, Title = "DLSS Override", Message = warning });
            foreach (var observation in report.Observations) body.Children.Add(Prefs.Label(observation));
            body.Children.Add(Prefs.Label("Visible result: " + report.VisualResult, "ForgeHeadingTextStyle"));
            if (report.Report.Length > 0)
                body.Children.Add(new TextBox
                {
                    Text = report.Report, IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MaxHeight = 300,
                    FontFamily = new FontFamily("Cascadia Mono, Consolas"), FontSize = 12,
                });
            var dialog = NewDialog();
            dialog.Title = game.Name + " · NR Diagnosis";
            dialog.Content = new ScrollViewer { Content = body, MaxHeight = 560 };
            dialog.PrimaryButtonText = "Refresh";
            dialog.CloseButtonText = "Close";
            if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
        }
    }

    // ---------- Recovery (show_undo / show_cleanup / show_reports) ----------

    public async Task ShowPreviousChangesAsync()
    {
        IReadOnlyList<RecoveryRecord> records;
        try { records = await Service.RecoveriesAsync(); }
        catch (InvalidOperationException error) { await Message("Undo previous changes", error.Message); return; }
        var dialog = NewDialog();
        dialog.Title = "Undo previous changes";
        dialog.CloseButtonText = "Close";
        var list = new StackPanel { Spacing = 4, MinWidth = 520 };
        if (records.Count == 0)
            list.Children.Add(Prefs.Label(Service.IsPreview ? "Your install and uninstall backups will appear here." : "No recorded changes yet."));
        RecoveryRecord? chosen = null;
        foreach (var record in records)
            list.Children.Add(Prefs.Row(record.Name, record.Detail, Prefs.ActionButton("Review", (_, _) => { chosen = record; dialog.Hide(); }), ""));
        dialog.Content = new ScrollViewer { Content = list, MaxHeight = 480 };
        await dialog.ShowAsync();
        if (chosen is null) return;
        var result = await ReviewDialog.ShowAsync(this, "Restore recorded changes", () => Service.ReviewRecoveryAsync(chosen));
        if (result is not null) await ScanAsync();
    }

    public async Task ReviewOldNrFilesAsync()
    {
        if (Service.IsPreview) { ShowToast("Old NR file cleanup is disabled in preview mode."); return; }
        var result = await ReviewDialog.ShowAsync(this, "Remove old NR files", Service.ReviewCleanupAsync, "No old NR files were found in your libraries.");
        if (result is not null) await ScanAsync();
    }

    public async Task ShowReportsAsync()
    {
        var dialog = NewDialog();
        dialog.Title = "Library status & reports";
        var body = new StackPanel { Spacing = 10, MinWidth = 560 };
        var totals = Games.GroupBy(g => g.TestStatus).ToDictionary(g => g.Key, g => g.Count());
        body.Children.Add(Prefs.Label(string.Join(" · ", new[] { "Untested", "Working", "Problem", "Bench" }
            .Select(s => $"{totals.GetValueOrDefault(s)} {s.ToLowerInvariant()}")), "ForgeHeadingTextStyle"));
        body.Children.Add(Prefs.Label("Diagnostics separate saved settings from captured runtime evidence. Nothing is uploaded."));
        var list = new StackPanel { Spacing = 4 };
        Game? diagnose = null;
        foreach (var game in Games)
            list.Children.Add(Prefs.Row(game.Name, game.TestStatus + (game.TestActive ? " · test in progress" : ""),
                Prefs.ActionButton("Diagnose", (_, _) => { diagnose = game; dialog.Hide(); })));
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 320 });
        var logs = new CheckBox { Content = "Include redacted logs from the latest captured test" };
        var notes = new CheckBox { Content = "Include my notes" };
        body.Children.Add(logs);
        body.Children.Add(notes);
        dialog.Content = body;
        dialog.PrimaryButtonText = "Preview Support Report";
        dialog.IsPrimaryButtonEnabled = !Service.IsPreview && Games.Count > 0;
        dialog.CloseButtonText = "Close";
        dialog.DefaultButton = ContentDialogButton.Primary;
        var choice = await dialog.ShowAsync();
        if (diagnose is not null) { await DiagnoseAsync(diagnose); return; }
        if (choice != ContentDialogResult.Primary) return;
        bool withLogs = logs.IsChecked == true, withNotes = notes.IsChecked == true;
        var result = await ReviewDialog.ShowAsync(this, "Review Support Report", () => Service.PreviewReportAsync(Games, withLogs, withNotes));
        if (result?.Path is { } path) ShowToast("Saved " + path);
    }

    // ---------- Application updates (check_app_update) ----------

    public async Task CheckForUpdatesAsync()
    {
        if (Service.IsPreview) { ShowToast("Checking for updates is disabled in preview mode."); return; }
        var result = await ReviewDialog.ShowAsync(this, "rtxForge Update", Service.CheckForUpdateAsync);
        if (result?.Path is not { } installer || result.Errors.Count > 0) return;
        // The verified installer replaces this build in place; rtxForge closes so its files can be updated.
        Process.Start(new ProcessStartInfo(installer) { UseShellExecute = true });
        Close();
    }

    // ---------- Tools: ReShade and add-ons (choose_extra / review_extra_restore) ----------

    public async Task InstallExtraAsync(Game game, string kind)
    {
        if (Service.IsPreview) { ShowToast("Installing tools is disabled in preview mode."); return; }
        var path = kind == "reshade" ? await PickFileAsync(".dll") : await PickFileAsync(".addon64");
        if (path is null) return;
        await ReviewDialog.ShowAsync(this, kind == "reshade" ? "Install ReShade" : "Install Add-on", () => Service.ReviewExtraAsync(game, path, kind));
    }

    public Task RestoreExtraAsync(ExtraRecord record) =>
        ReviewDialog.ShowAsync(this, "Restore Tool", () => Service.ReviewExtraRestoreAsync(record));

    public static void OpenUri(string uri) => Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });

    // ---------- DLSS files ----------

    public async Task RestoreDlssFilesAsync(Game game)
    {
        if (Service.IsPreview) { ShowToast("Preview mode · game writes disabled"); return; }
        var result = await ReviewDialog.ShowAsync(this, "Restore original DLSS files", () => Service.ReviewDlssRestoreAsync(game));
        if (result is not null && result.Errors.Count == 0) await ScanAsync();
    }

    // ---------- Notes and test records ----------

    public async Task SaveNotesAsync(Game game, string status, string notes)
    {
        try
        {
            await Service.SaveNotesAsync(game, status, notes);
            ShowToast("Notes saved");
        }
        catch (InvalidOperationException error) { await Message("Save notes", error.Message); }
    }

    public async Task RecordTestAsync(Game game)
    {
        var finish = game.TestActive;
        try
        {
            if (finish) await Service.FinishTestAsync(game);
            else await Service.StartTestAsync(game);
        }
        catch (InvalidOperationException error) { await Message(finish ? "Finish Test" : "Start Test", error.Message); return; }
        if (!finish && game.Library == "Steam" && game.AppId is { } appid && appid.All(char.IsDigit)) OpenUri("steam://rungameid/" + appid);
        ShowToast(finish ? "Logs captured. Record your result and save notes." : "Test started. Launch your game normally, then return here to finish.");
        NotifyGamesChanged();
    }

    // ---------- Packages (select_package) ----------

    /// <summary>Saves the chosen provider; then installs on the selected games or asks for a selection.</summary>
    public void SelectPackage(string provider, Tuning? presets = null)
    {
        if (Busy) { ShowToast("Wait for the current operation to finish."); return; }
        Settings.RuntimeProvider = provider;
        if (presets is not null)
        {
            Settings.NrStrength = presets.NrStrength;
            Settings.SharpeningStrength = presets.SharpeningStrength;
            Settings.MfgMultiplier = presets.MfgMultiplier;
        }
        if (!NrOnlyAvailable && Mode == "nr-only") Mode = "mfg-only";
        if (provider == "skynizz") Settings.DefaultProfile = Mode = "nr-mfg";
        SaveSettings();
        _ = ScanAsync();
        ShowToast("Package selected. Select games, then choose Install Features.");
    }
}
