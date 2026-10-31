using System.Diagnostics;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using Windows.Graphics.Imaging;

namespace RtxForge.Windows;

/// <summary>
/// Desktop actions shared by Settings, Game Details, Packages and Extras: library media,
/// custom artwork and Steam sync, SteamGridDB, recovery, reports, NR diagnosis and updates
/// (Window methods of the same names in gui/rtxforge_gtk.py).
/// </summary>
public sealed partial class MainWindow
{
    string? overlayRefreshNotice;
    void InitializeOverlayRefresh()
    {
        if (Service is not EngineForgeService engine) return;
        void Changed(System.Text.Json.Nodes.JsonObject result) => DispatcherQueue.TryEnqueue(() => ShowOverlayRefresh(result));
        engine.OverlayRefreshChanged += Changed;
        Closed += (_, _) => engine.OverlayRefreshChanged -= Changed;
        if (engine.OverlayRefreshResult is { } result) Changed(result);
    }

    void ShowOverlayRefresh(System.Text.Json.Nodes.JsonObject result)
    {
        var updated = result["updated"]?.GetValue<int>() ?? 0;
        var blocked = (result["blocked"] as System.Text.Json.Nodes.JsonArray)?.Count ?? 0;
        var current = (result["skipped"] as System.Text.Json.Nodes.JsonArray)?.Count ?? 0;
        var error = result["error"]?.ToString();
        var identity = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(
            result["bundle"] + "|" + result["status"] + "|" + updated + "|" + current + "|" + result["blocked"]?.ToJsonString() + "|" + error)));
        if (overlayRefreshNotice == identity) return;
        overlayRefreshNotice = identity;
        var receipt = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "state", "overlay-refresh-notified.txt");
        try { if (File.Exists(receipt) && File.ReadAllText(receipt) == identity) return; }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        var message = error is not null ? "Overlay update needs attention: " + error
            : $"Overlays: {updated} updated · {current} already current" + (blocked > 0 ? $" · {blocked} need repair" : ". Ready to play.");
        AddLog(message); ShowToast(message);
        var details = new Button { Content = "Details" };
        details.Click += async (_, _) => await ShowOverlayUpdateDetailsAsync(result);
        Toast.ActionButton = details;
        if (blocked > 0 || error is not null) toastTimer?.Stop();
        try { Directory.CreateDirectory(Path.GetDirectoryName(receipt)!); File.WriteAllText(receipt, identity); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    public async Task ShowOverlayUpdateDetailsAsync(System.Text.Json.Nodes.JsonObject? result = null)
    {
        result ??= (Service as EngineForgeService)?.OverlayRefreshResult;
        if (result is null)
        {
            var path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "state", "overlay-refresh.json");
            try { if (File.Exists(path)) result = System.Text.Json.Nodes.JsonNode.Parse(File.ReadAllText(path))?.AsObject(); }
            catch (Exception e) when (e is IOException or System.Text.Json.JsonException or UnauthorizedAccessException) { }
        }
        var text = result is null ? "Checking installed overlays…" : $"{result["updated"] ?? 0} updated · {(result["skipped"] as System.Text.Json.Nodes.JsonArray)?.Count ?? 0} already current";
        if (result?["error"] is { } error) text += "\n\n" + error;
        if (result?["updated_games"] is System.Text.Json.Nodes.JsonArray updated)
            foreach (var game in updated) text += "\n\nUpdated · " + game?["title"];
        if (result?["blocked"] is System.Text.Json.Nodes.JsonArray blocked)
            foreach (var game in blocked) text += "\n\nNeeds repair · " + game?["title"] + "\n" + game?["detail"];
        var dialog = NewDialog(); dialog.Title = "Overlay update"; dialog.CloseButtonText = "Done";
        dialog.Content = new ScrollViewer { MaxHeight = 480, Content = new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, MaxWidth = 640 } };
        await dialog.ShowAsync();
    }
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

    public async Task ShowReportsAsync() => await ShowReportsAsync(null);

    /// <summary>Compatibility and bug reports. issue: from an rtxforge://support/logs?issue=N link.</summary>
    public async Task ShowReportsAsync(int? issue)
    {
        if (issue is not null) { await PrepareBetaReportsAsync(Games, issue); return; }
        var dialog = NewDialog();
        dialog.Title = "Compatibility & reports";
        var body = new StackPanel { Spacing = 10, MinWidth = 560 };
        var totals = Games.GroupBy(g => g.TestStatus).ToDictionary(g => g.Key, g => g.Count());
        body.Children.Add(Prefs.Label(string.Join(" · ", new[] { "Untested", "Working", "Problem", "Bench" }
            .Select(s => $"{totals.GetValueOrDefault(s)} {s.ToLowerInvariant()}")), "ForgeHeadingTextStyle"));
        var list = new StackPanel { Spacing = 4 };
        Func<Task>? next = null;
        foreach (var game in Games)
        {
            var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            void Add(string text, Func<Task> run, bool enabled = true)
            {
                var button = Prefs.ActionButton(text, (_, _) => { next = run; dialog.Hide(); });
                button.IsEnabled = enabled && !Service.IsPreview;
                actions.Children.Add(button);
            }
            if (game.BlockedSoft) Add("Try anyway", () => TryAnywayAsync(game, true), !Busy);
            else if (game.TryAnyway is not null) Add("Stop trying", () => TryAnywayAsync(game, false), !Busy);
            if (game.TestStatus is "Working" or "Problem") Add("Share", () => ShareResultAsync(game));
            Add("Diagnose", () => DiagnoseAsync(game), !game.Blocked);
            Add("Bug Report", () => PrepareBetaReportsAsync([game]));
            list.Children.Add(Prefs.Row(game.Name, CompatDetail(game), actions));
        }
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 360 });
        dialog.Content = body;
        dialog.CloseButtonText = "Close";
        await dialog.ShowAsync();
        if (next is not null) await next();
    }

    // ---------- Bug reports (scripts/beta_report.py, the same report as the Linux app) ----------

    /// <summary>"Windows installer" only when Setup's own uninstall entry points at this folder; otherwise the report says Not sure.</summary>
    public static string? InstallFormat()
    {
        var here = Path.TrimEndingDirectorySeparator(AppContext.BaseDirectory);
        foreach (var hive in new[] { Microsoft.Win32.Registry.CurrentUser, Microsoft.Win32.Registry.LocalMachine })
        {
            using var key = hive.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\{6E0C2B7A-3F4D-4E8B-9A51-7C2D8F1E4B90}_is1");
            if (key?.GetValue("InstallLocation") is string location
                && string.Equals(Path.TrimEndingDirectorySeparator(location), here, StringComparison.OrdinalIgnoreCase))
                return "Windows installer";
        }
        return null;
    }

    static readonly string[] ResultChoices = ["Worked", "Didn't work", "Didn't test"];

    /// <summary>A report is about one game; with several to choose from, ask which.</summary>
    async Task<Game?> PickReportGameAsync(IReadOnlyList<Game> games)
    {
        var dialog = NewDialog();
        dialog.Title = "Which game is it about?";
        Game? chosen = null;
        var search = new AutoSuggestBox { PlaceholderText = "Search your library", QueryIcon = new SymbolIcon(Symbol.Find) };
        var list = new ListView { SelectionMode = ListViewSelectionMode.None, IsItemClickEnabled = true, MaxHeight = 360,
            ItemsSource = games.Select(g => g.Name).ToList() };
        search.TextChanged += (_, _) => list.ItemsSource = games.Where(g => g.Name.Contains(search.Text.Trim(), StringComparison.OrdinalIgnoreCase)).Select(g => g.Name).ToList();
        list.ItemClick += (_, e) => { chosen = games.FirstOrDefault(g => g.Name == (string)e.ClickedItem); dialog.Hide(); };
        var body = new StackPanel { Spacing = 12, MinWidth = 480 };
        body.Children.Add(search); body.Children.Add(list);
        dialog.Content = body;
        dialog.CloseButtonText = "Cancel";
        await dialog.ShowAsync();
        return chosen;
    }

    /// <summary>
    /// Bug Report: one game, "What happened?" first, NR and MFG in three words each, and Send.
    /// What rtxForge detected sits folded underneath and can be corrected. The loew.fi report
    /// service files it on GitHub; logs go privately. A copy is saved on this PC either way.
    /// </summary>
    public async Task PrepareBetaReportsAsync(IReadOnlyList<Game> games, int? issue = null)
    {
        if (games.Count == 0) return;
        if (Service.IsPreview) { ShowToast("Bug reports are disabled in preview mode."); return; }
        var game = games.Count == 1 ? games[0] : await PickReportGameAsync(games);
        if (game is null) return;
        BetaReportDraft draft;
        try { draft = await Service.DraftReportsAsync([game], InstallFormat(), ""); }
        catch (InvalidOperationException error) { await Message("Bug Report", error.Message); return; }
        var report = draft.Reports[0];
        var values = report.Fields.ToDictionary(p => p.Key, p => p.Value);
        var edits = new Dictionary<string, string>();
        void Set(string key, string value) { values[key] = value; edits[key] = value; }
        if (issue is { } number && string.IsNullOrWhiteSpace(values.GetValueOrDefault("observations"))) Set("observations", $"Follow-up to #{number}: ");

        var dialog = NewDialog();
        dialog.Title = "Report a problem";
        var body = new StackPanel { Spacing = 18, MinWidth = 560, MaxWidth = 640 };
        var heading = new StackPanel { Spacing = 4 };
        heading.Children.Add(new TextBlock { Text = report.Name, FontSize = 18, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        heading.Children.Add(Prefs.Label("Goes to rtxForge's issues on GitHub. What you write and the details below are public; logs stay private.", "ForgeCaptionDimTextStyle"));
        body.Children.Add(heading);

        var observations = draft.Fields.First(f => f.Id == "observations");
        var what = new TextBox { Header = observations.Label, Text = values.GetValueOrDefault("observations") ?? "", AcceptsReturn = true,
            TextWrapping = TextWrapping.Wrap, MinHeight = 140, MaxLength = observations.Max,
            PlaceholderText = "What you did, what you expected, and what you saw. Include exact errors." };
        what.TextChanged += (_, _) => { Set("observations", what.Text); Refresh(); };
        body.Children.Add(what);

        var results = new Grid { ColumnSpacing = 24 };
        results.ColumnDefinitions.Add(new ColumnDefinition()); results.ColumnDefinitions.Add(new ColumnDefinition());
        foreach (var (key, label, column) in new[] { ("nr-result", "NR", 0), ("mfg-result", "MFG", 1) })
        {
            var original = values.GetValueOrDefault(key) ?? "";
            var buttons = new RadioButtons { Header = label, MaxColumns = 3, ItemsSource = ResultChoices,
                SelectedIndex = original switch { "Working in-game" => 0, "Not working in-game" => 1, _ => 2 } };
            buttons.SelectionChanged += (_, _) => Set(key, buttons.SelectedIndex switch
            {
                0 => "Working in-game",
                1 => "Not working in-game",
                _ => original is "Working in-game" or "Not working in-game" or "" ? "Installed, not tested" : original,
            });
            Grid.SetColumn(buttons, column); results.Children.Add(buttons);
        }
        body.Children.Add(results);

        var logs = new CheckBox { Content = "Include logs (sent privately to the rtxForge maintainers)", IsChecked = true };
        body.Children.Add(logs);

        // Everything rtxForge detected, folded: correct it if something's wrong.
        var details = new StackPanel { Spacing = 12 };
        foreach (var field in draft.Fields.Where(f => f.Id is not ("observations" or "nr-result" or "mfg-result")))
        {
            var value = values.GetValueOrDefault(field.Id) ?? "";
            FrameworkElement control;
            if (field.Choices.Count > 0)
            {
                var box = new ComboBox { Header = field.Label, ItemsSource = field.Choices.ToList(), HorizontalAlignment = HorizontalAlignment.Stretch,
                    SelectedItem = field.Choices.Contains(value) ? value : null, PlaceholderText = "Choose…" };
                box.SelectionChanged += (_, _) => { Set(field.Id, box.SelectedItem as string ?? ""); Refresh(); };
                control = box;
            }
            else
            {
                var box = new TextBox { Header = field.Label, Text = value, MaxLength = field.Max > 0 ? field.Max : 0 };
                box.TextChanged += (_, _) => { Set(field.Id, box.Text); Refresh(); };
                control = box;
            }
            details.Children.Add(control);
        }
        var summary = Prefs.Label(string.Join(" · ", new[] { "platform", "gpu", "feature-package" }
            .Select(k => values.GetValueOrDefault(k)).Where(v => !string.IsNullOrWhiteSpace(v))), "ForgeCaptionDimTextStyle");
        var expanderHeader = new StackPanel { Spacing = 2 };
        expanderHeader.Children.Add(new TextBlock { Text = "Details we'll include" });
        expanderHeader.Children.Add(summary);
        body.Children.Add(new Expander { Header = expanderHeader, Content = details, HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch });

        void Refresh() => dialog.IsPrimaryButtonEnabled = !string.IsNullOrWhiteSpace(values.GetValueOrDefault("observations"))
            && !string.IsNullOrWhiteSpace(values.GetValueOrDefault("platform"));
        dialog.Content = new ScrollViewer { Content = body, MaxHeight = 620 };
        dialog.PrimaryButtonText = "Send Report";
        dialog.SecondaryButtonText = "See what's sent";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        Refresh();
        var documents = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        while (true)
        {
            var choice = await dialog.ShowAsync();
            if (choice == ContentDialogResult.Secondary) { await ShowReportOutlineAsync(report.Id, edits, logs.IsChecked == true); continue; }
            if (choice != ContentDialogResult.Primary) return;
            var sent = await SendReportAsync(report.Id, edits, logs.IsChecked == true, documents);
            if (sent is null) continue;
            if (sent.Sent) { await ShowReportSentAsync(sent); return; }
            if (!await ShowReportNotSentAsync(sent)) return;
        }
    }

    async Task<ReportSent?> SendReportAsync(string id, IReadOnlyDictionary<string, string> edits, bool logs, string documents)
    {
        var progress = NewDialog();
        progress.Title = "Sending your report…";
        var ring = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 };
        ring.Children.Add(new ProgressRing { IsActive = true, Width = 24, Height = 24 });
        ring.Children.Add(Prefs.Label(logs ? "Reading and redacting logs, then sending." : "Sending."));
        progress.Content = ring;
        var showing = progress.ShowAsync();
        try { return await Service.SendReportAsync(id, edits, logs, documents); }
        catch (InvalidOperationException error) { progress.Hide(); await showing; await Message("Bug Report", error.Message); return null; }
        finally { progress.Hide(); }
    }

    async Task ShowReportOutlineAsync(string id, IReadOnlyDictionary<string, string> edits, bool logs)
    {
        ReportOutline outline;
        try { outline = await Service.OutlineReportAsync(id, edits, logs); }
        catch (InvalidOperationException error) { await Message("What's sent", error.Message); return; }
        var dialog = NewDialog();
        dialog.Title = "What's sent";
        var body = new StackPanel { Spacing = 12, MinWidth = 600 };
        body.Children.Add(Prefs.Label("Public on GitHub", "ForgeHeadingTextStyle"));
        body.Children.Add(new TextBlock { Text = outline.Title, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        body.Children.Add(new TextBox { Text = outline.Text, IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap,
            FontFamily = new FontFamily("Cascadia Mono, Consolas"), MaxHeight = 280 });
        body.Children.Add(Prefs.Label(logs ? "Private: only the rtxForge maintainers" : "Logs: not included", "ForgeHeadingTextStyle"));
        foreach (var log in outline.Logs)
            body.Children.Add(new Expander { Header = $"{log.Name} · {log.Detail}", HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Content = new TextBox { Text = log.Text.Length > 40000 ? "…" + log.Text[^40000..] : log.Text, IsReadOnly = true, AcceptsReturn = true,
                    TextWrapping = TextWrapping.Wrap, FontFamily = new FontFamily("Cascadia Mono, Consolas"), MaxHeight = 280 } });
        foreach (var skipped in outline.Skipped) body.Children.Add(Prefs.Label("Not included: " + skipped, "ForgeCaptionDimTextStyle"));
        body.Children.Add(Prefs.Label("Redaction is best effort: check for anything personal before you send.", "ForgeCaptionDimTextStyle"));
        dialog.Content = new ScrollViewer { Content = body, MaxHeight = 620 };
        dialog.CloseButtonText = "Back";
        await dialog.ShowAsync();
    }

    async Task ShowReportSentAsync(ReportSent sent)
    {
        var dialog = NewDialog();
        dialog.Title = "Report sent";
        var body = new StackPanel { Spacing = 8, MinWidth = 480 };
        body.Children.Add(new TextBlock { Text = $"Thanks! It's issue #{sent.Number} on GitHub.", FontSize = 16, TextWrapping = TextWrapping.Wrap });
        body.Children.Add(Prefs.Label("A copy is saved in " + Path.GetDirectoryName(sent.Path) + ".", "ForgeCaptionDimTextStyle"));
        dialog.Content = body;
        dialog.PrimaryButtonText = "View on GitHub";
        dialog.CloseButtonText = "Done";
        dialog.DefaultButton = ContentDialogButton.Close;
        if (await dialog.ShowAsync() == ContentDialogResult.Primary && sent.Url is { } url) OpenUri(url);
    }

    /// <summary>Why it couldn't go, where the copy is, and Try again.</summary>
    async Task<bool> ShowReportNotSentAsync(ReportSent sent)
    {
        var dialog = NewDialog();
        dialog.Title = "Couldn't send the report";
        var body = new StackPanel { Spacing = 10, MinWidth = 480 };
        body.Children.Add(new TextBlock { Text = sent.Error ?? "The report service didn't answer.", TextWrapping = TextWrapping.Wrap });
        body.Children.Add(Prefs.Row("Saved on this PC", sent.Path,
            Prefs.ActionButton("Open folder", (_, _) => Process.Start("explorer.exe", $"/select,\"{sent.Path}\""))));
        dialog.Content = body;
        dialog.PrimaryButtonText = "Try again";
        dialog.CloseButtonText = "Close";
        dialog.DefaultButton = ContentDialogButton.Primary;
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    public void CopyText(string text, string done)
    {
        try
        {
            var data = new global::Windows.ApplicationModel.DataTransfer.DataPackage(); data.SetText(text);
            global::Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(data);
            ShowToast(done);
        }
        catch (Exception) { ShowToast("Couldn't copy. The same text is in report.md inside the saved ZIP."); }
    }

    // ---------- rtxforge://support/logs ----------

    /// <summary>An issue number from a website link, set in App before this window opens; null when no link.</summary>
    public static int? PendingSupportIssue { get; set; }
    public static bool PendingSupportLink { get; set; }
    public static bool IgnoredSupportLink { get; set; }

    /// <summary>Links come from web pages: only rtxforge://support/logs, optionally ?issue=N, is accepted (scripts/beta_report.parse_link).</summary>
    public static bool TryParseSupportLink(string value, out int? issue)
    {
        issue = null;
        if (value.Length > 200 || !Uri.TryCreate(value, UriKind.Absolute, out var uri)) return false;
        if (!string.Equals(uri.Scheme, "rtxforge", StringComparison.Ordinal) || !string.Equals(uri.Host, "support", StringComparison.Ordinal)
            || uri.AbsolutePath.TrimEnd('/') != "/logs" || uri.Fragment.Length > 0 || uri.UserInfo.Length > 0 || !uri.IsDefaultPort) return false;
        var query = uri.Query.TrimStart('?');
        if (query.Length == 0) return true;
        var parts = query.Split('&');
        if (parts.Length != 1 || !parts[0].StartsWith("issue=", StringComparison.Ordinal)) return false;
        var digits = parts[0]["issue=".Length..];
        if (digits.Length is < 1 or > 7 || !digits.All(char.IsAsciiDigit) || int.Parse(digits) == 0) return false;
        issue = int.Parse(digits);
        return true;
    }

    /// <summary>After the first library scan: open beta reports for a website link, once.</summary>
    void OpenSupportLink()
    {
        if (IgnoredSupportLink) { IgnoredSupportLink = false; ShowToast("Ignored a link rtxForge doesn't recognise."); }
        if (!PendingSupportLink) return;
        PendingSupportLink = false;
        var issue = PendingSupportIssue;
        DispatcherQueue.TryEnqueue(async () => await ShowReportsAsync(issue));
    }

    /// <summary>One line per game for the compatibility list: block, Try anyway, or the known result.</summary>
    public static string CompatDetail(Game game) =>
        game.BlockedSoft ? "Not verified · " + game.BlockedReason
        : game.Blocked ? "Blocked · " + game.BlockedReason
        : game.TryAnyway is { } skipped ? "Trying anyway · " + skipped
        : game.CompatVerdict is { } verdict ? verdict + (game.CompatFromList ? " · rtxForge list" : " · your result")
        : game.TestStatus + (game.TestActive ? " · test in progress" : "");

    /// <summary>Skip (or stop skipping) a capability check. Installs still go through review, and Restore undoes them.</summary>
    public async Task TryAnywayAsync(Game game, bool on)
    {
        try { await Service.SetTryAnywayAsync(game, on); }
        catch (InvalidOperationException error) { await Message("Try anyway", error.Message); return; }
        ShowToast(on ? $"{game.Name} can be installed now. Review the install before applying it." : $"{game.Name} is checked normally again.");
        await ScanAsync();
    }

    /// <summary>The package named in a shared result: what is installed, else what an install would use.</summary>
    public string SharePackage(Game game) => game.UsesFeeder ? "Feeder NR"
        : Settings.PackageName(game.Installed && game.RuntimeProvider is { } installed ? installed : Settings.PackageFor(game, "install"));

    /// <summary>Preview the exact issue text, then open it in the browser. Nothing is sent from rtxForge.</summary>
    public async Task ShareResultAsync(Game game)
    {
        CompatShare share;
        try { share = await Service.CompatShareAsync(game, SharePackage(game), false); }
        catch (InvalidOperationException error) { await Message("Share result", error.Message); return; }
        var dialog = NewDialog();
        dialog.Title = "Share result";
        var body = new StackPanel { Spacing = 10, MinWidth = 520 };
        body.Children.Add(Prefs.Label("This opens a prefilled issue in your browser. Nothing is sent until you post it there."));
        var text = new TextBox { Text = share.Body, IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MaxHeight = 280,
            FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Cascadia Mono, Consolas") };
        var withNotes = new CheckBox { Content = "Include my notes (paths and common secrets are redacted)", IsEnabled = game.Notes.Trim().Length > 0 };
        withNotes.Click += async (_, _) =>
        {
            try { share = await Service.CompatShareAsync(game, SharePackage(game), withNotes.IsChecked == true); text.Text = share.Body; }
            catch (InvalidOperationException error) { text.Text = error.Message; }
        };
        body.Children.Add(text);
        body.Children.Add(withNotes);
        dialog.Content = body;
        dialog.PrimaryButtonText = "Open in browser";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        if (await dialog.ShowAsync() == ContentDialogResult.Primary && share.Url.Length > 0) OpenUri(share.Url);
    }

    // ---------- Application updates (check_app_update) ----------

    public async Task CheckForUpdatesAsync()
    {
        if (Service.IsPreview) { ShowToast("Checking for updates is disabled in preview mode."); return; }
        if (!InstalledApp)
        {
            ShowToast("Portable app: extract the newest ZIP into your portable folder. Settings and backups stay in your profile.");
            OpenUri("https://github.com/lrnolivia/rtxForge/releases/tag/beta");
            return;
        }
        if (updateReady) { await ApplyAppUpdateAsync(true); return; }
        await DownloadAppUpdateAsync(true);
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

    public async Task OpenGameFolderAsync(Game game)
    {
        if (Service.IsPreview) { ShowToast("Folder opening is unavailable in preview mode."); return; }
        try
        {
            var path = Path.GetFullPath(game.Location);
            if (!Directory.Exists(path)) { ShowToast("This game folder is unavailable. Reconnect its drive or rescan your library."); return; }
            var folder = await global::Windows.Storage.StorageFolder.GetFolderFromPathAsync(path);
            if (!await global::Windows.System.Launcher.LaunchFolderAsync(folder))
                ShowToast("Windows couldn't open this game folder. Try opening it from File Explorer.");
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException
            or System.Runtime.InteropServices.COMException)
        {
            ShowToast("Couldn't open the game folder: " + error.Message);
        }
    }

    // ---------- DLSS files ----------

    public async Task RestoreDlssFilesAsync(Game game)
    {
        if (Service.IsPreview) { ShowToast("Preview mode · game writes disabled"); return; }
        var result = await ReviewDialog.ShowAsync(this, "Restore original DLSS files", () => Service.ReviewDlssRestoreAsync(game));
        if (result is not null && result.Errors.Count == 0) await ScanAsync();
    }

    // ---------- Notes and test records ----------

    public async Task SaveNotesAsync(Game game, string status, string notes, string saved = "Notes saved")
    {
        try
        {
            await Service.SaveNotesAsync(game, status, notes);
            ShowToast(saved);
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
        ShowToast(finish ? "Functional test saved. Review the evidence and suggested fixes." : "Test started. Play for a minute, then return here to finish.");
        NotifyGamesChanged();
        if (finish) await ShowFunctionalTestAsync(game);
    }

    public async Task ShowFunctionalTestAsync(Game game)
    {
        if (game.FunctionalTestText is not { Length: > 0 } text) return;
        var dialog = NewDialog();
        dialog.Title = "Functional test · " + game.Name;
        var content = new StackPanel { Spacing = 14, MinWidth = 420 };
        content.Children.Add(Prefs.Label("These checks show what ran. Check the picture yourself; you choose the final result.", "ForgeCaptionDimTextStyle"));
        if (game.TestSuggestion is { } suggestion) content.Children.Add(Prefs.Label("Suggested result: " + suggestion));
        content.Children.Add(new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true });
        dialog.Content = new ScrollViewer { Content = content, MaxHeight = 560, HorizontalScrollMode = ScrollMode.Disabled };
        dialog.CloseButtonText = "Done";
        dialog.SecondaryButtonText = "Bug Report";
        if (game.TestSuggestion is { } chosen) dialog.PrimaryButtonText = "Use " + chosen;
        var choice = await dialog.ShowAsync();
        if (choice == ContentDialogResult.Primary && game.TestSuggestion is { } status)
            await SaveNotesAsync(game, status, game.Notes, "Test result saved");
        else if (choice == ContentDialogResult.Secondary) await PrepareBetaReportsAsync([game]);
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
        if (provider == "feeder") Settings.DefaultProfile = Mode = "nr-only";
        SaveSettings();
        _ = ScanAsync();
        ShowToast("Package selected. Select games, then choose Install Features.");
    }
}
