using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using RtxForge.Windows.Models;
using RtxForge.Windows.ViewModels;

namespace RtxForge.Windows.GameMode;

/// <summary>
/// Game Mode versions of the desktop feature flows: the same IForgeService reviews and
/// actions (artwork and Steam sync, SteamGridDB, NR diagnosis, tools, DLSS restore, notes,
/// recovery, packages, updates) as controller-friendly modals.
/// </summary>
public sealed partial class GameModeView
{
    // ---------- reviewed writes: Checking → Review → Working → Done ----------

    async Task<EngineResult?> RunReviewAsync(string title, Func<Task<EngineReview>> prepare, string? empty = null)
    {
        var step = new GmStep(this);
        var cancelChecking = ui.Button("Cancel", CloseModal, GmKind.Card, 0.92);
        ShowModal(title, step.Root, [cancelChecking], CloseModal, 1100, cancelChecking);
        var checking = modals.Peek();
        step.Show("Checking", null, 0, null, "Checking");
        EngineReview review;
        try { review = await prepare(); }
        catch (Exception error) when (error is InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            if (modals.Count > 0 && ReferenceEquals(modals.Peek(), checking)) CloseModal();
            ShowDone(false, title, error.Message);
            return null;
        }
        if (modals.Count == 0 || !ReferenceEquals(modals.Peek(), checking)) { shell.Service.DiscardReview(review); return null; }
        CloseModal();

        var done = new TaskCompletionSource<EngineResult?>();
        var content = new StackPanel { Spacing = t.Px(20) };
        if (!review.Ready)
        {
            content.Children.Add(ui.P(empty ?? (review.Summary.Length > 0 ? review.Summary : "Nothing to change."), 0.95));
            if (review.Blocked.Count > 0)
                content.Children.Add(ui.Group(review.Blocked.Select(b => (UIElement)ReviewRow(Find(b), b.Title, b.Detail, false)), t.Card));
            var close = ui.Button("Done", () => { CloseModal(); done.TrySetResult(null); }, GmKind.Card, 0.92);
            ShowModal(review.Title, content, [close], () => { CloseModal(); done.TrySetResult(null); }, 1100, close);
            return await done.Task;
        }
        if (review.Summary.Length > 0) content.Children.Add(ui.P(review.Summary));
        var list = new StackPanel { Spacing = t.Px(18) };
        list.Children.Add(ui.Group(review.Items.Select(i => (UIElement)ReviewRow(Find(i), i.Title,
            review.Kind == "overlay-ui" ? i.Detail : i.Details is { } d ? Shorten(d) : i.Detail, true)), t.Card));
        if (review.Blocked.Count > 0)
        {
            list.Children.Add(ui.Text($"Skipped · {review.Blocked.Count}", 0.88, weight: FontWeights.SemiBold));
            list.Children.Add(ui.Group(review.Blocked.Select(b => (UIElement)ReviewRow(Find(b), b.Title, b.Detail, false)), t.Card));
        }
        content.Children.Add(new ScrollViewer { Content = list, MaxHeight = t.Px(t.Compact ? 260 : 380), HorizontalScrollMode = ScrollMode.Disabled });
        if (review.Note is { } note) content.Children.Add(ui.P(note, 0.8));
        var trusted = review.Trust is null;
        Button go = null!;
        if (review.Trust is { } statement)
        {
            Button toggle = null!;
            toggle = ui.RowButton(statement, "No", () =>
            {
                trusted = !trusted;
                SetPrimaryEnabled(go, trusted);
                if (toggle.Content is Grid g && g.Children.OfType<TextBlock>().FirstOrDefault() is { } value) value.Text = trusted ? "Yes" : "No";
            });
            content.Children.Add(ui.Group([toggle], t.Card));
        }
        else content.Children.Add(ui.P("Your files only change after you confirm.", 0.8));
        void Cancel() { CloseModal(); shell.Service.DiscardReview(review); done.TrySetResult(null); }
        var cancel = ui.Button("Cancel", Cancel, GmKind.Card, 0.92);
        go = ui.Button(review.Action, () => { CloseModal(); _ = RunReviewedAsync(review, done); }, GmKind.Primary, 0.92, enabled: trusted);
        // Enabled later by the trust toggle; a disabled-looking but focusable button keeps the D-pad path stable.
        ShowModal(review.Title, content, [cancel, go], Cancel, 1100, cancel);
        return await done.Task;
    }

    /// <summary>A primary action enabled after a trust confirmation, with the primary colors restored.</summary>
    void SetPrimaryEnabled(Button button, bool on)
    {
        button.IsEnabled = on;
        button.Background = GmTheme.B(on ? GmTheme.Accent : t.Disabled);
        button.Foreground = GmTheme.B(on ? GmTheme.AccentInk : t.DisabledFg);
    }

    static string Shorten(string text) => text.Length > 240 ? text[..240].TrimEnd() + "…" : text;

    Game? Find(ReviewItem item) => item.GameId is null ? null
        : shell.Games.FirstOrDefault(g => g.Id == item.GameId) ?? shell.Games.FirstOrDefault(g => g.Name == item.Title);

    async Task RunReviewedAsync(EngineReview review, TaskCompletionSource<EngineResult?> done)
    {
        var step = new GmStep(this);
        ShowModal(null, step.Root, [], () => { }, 1100);
        var working = modals.Peek();
        step.Show(review.Action, null, 0, null, review.Action);
        var progress = new Progress<PrepareProgress>(p => step.Show(review.Action, null, 0, null, p.Label));
        EngineResult result;
        try { result = await shell.Service.RunReviewAsync(review, progress); }
        catch (Exception error) when (error is InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            result = new EngineResult(error.Message, null, [error.Message]);
        }
        if (modals.Count > 0 && ReferenceEquals(modals.Peek(), working)) CloseModal();
        var ok = result.Errors.Count == 0;
        ShowDone(ok, ok ? "Done" : "Could not finish", ok ? result.Message : result.Message + " " + string.Join(" ", result.Errors.Where(e => e != result.Message)));
        done.TrySetResult(result);
    }

    // ---------- Settings › Library: artwork ----------

    List<UIElement> LibraryArtworkRows() =>
    [
        ui.RowButton("Refresh artwork", "Refresh", () => { Toast("Refreshing artwork…"); _ = shell.RefreshArtworkAsync(true); },
            description: "Cached images remain available offline.", glyph: "").With(r => Key(r, "art-refresh")),
        ui.RowButton("Sync artwork to Steam", null, () => _ = SyncArtworkAsync(null), description: "Review and sync artwork for your library.",
            glyph: "").With(r => Key(r, "art-sync")),
        ui.RowButton("Steam artwork profile", null, () => _ = ChooseProfileAsync(), description: "Choose which local Steam account receives artwork.",
            glyph: "").With(r => Key(r, "art-profile")),
        ui.RowButton("Connect SteamGridDB", null, () => _ = ConnectSteamGridAsync(null), description: "Connect your account to browse custom artwork.",
            glyph: "").With(r => Key(r, "sgdb-connect")),
    ];

    async Task SyncArtworkAsync(Game? game)
    {
        if (shell.Service.IsPreview) { Toast("Steam artwork sync is disabled in preview mode."); return; }
        await RunReviewAsync("Sync artwork to Steam",
            () => shell.Service.ReviewArtworkSyncAsync(game is null ? shell.Games : [game], single: game is not null),
            game is null ? "No custom artwork to sync yet." : "Steam already shows this artwork.");
    }

    async Task ChooseProfileAsync()
    {
        IReadOnlyList<SteamArtworkProfile> accounts;
        try { accounts = await shell.Service.SteamArtworkProfilesAsync(); }
        catch (InvalidOperationException error) { ShowDone(false, "Steam artwork profile", error.Message); return; }
        var content = new StackPanel { Spacing = t.Px(18) };
        content.Children.Add(ui.P("Choose the local Steam account whose artwork rtxForge should update."));
        if (accounts.Count == 0) content.Children.Add(ui.P("No Steam profile found. Open Steam once, then try again."));
        else
            content.Children.Add(ui.Group(accounts.Select(account => (UIElement)ui.RowButton("Steam account " + account.UserId, account.Selected ? "Selected" : null, async () =>
            {
                CloseModal();
                try { await shell.Service.SelectSteamArtworkProfileAsync(account); Toast("Steam artwork profile selected"); }
                catch (InvalidOperationException error) { ShowDone(false, "Steam artwork profile", error.Message); }
            }, description: account.Root)), t.Card));
        var back = ui.Button("Back", CloseModal, GmKind.Card, 0.92);
        ShowModal("Steam artwork profile", content, [back], CloseModal, 1000);
    }

    /// <summary>SteamGridDB key entry: the Windows touch keyboard or Steam's keyboard types into the field.</summary>
    async Task ConnectSteamGridAsync(Action? connected)
    {
        SteamGridStatus status;
        try { status = await shell.Service.SteamGridStatusAsync(); }
        catch (InvalidOperationException error) { ShowDone(false, "SteamGridDB", error.Message); return; }
        var content = new StackPanel { Spacing = t.Px(18) };
        content.Children.Add(ui.P("Choose artwork from SteamGridDB in Desktop or Game Mode. Connect once with your own API key from steamgriddb.com › Preferences › API."));
        var entry = new PasswordBox
        {
            PlaceholderText = "Paste your SteamGridDB API key", FontSize = t.Em(0.9), IsEnabled = !shell.Service.IsPreview,
            Background = GmTheme.B(t.Card), Foreground = GmTheme.B(t.Fg), BorderBrush = GmTheme.B(t.Line), CornerRadius = new CornerRadius(t.Px(12)),
            Padding = new Thickness(t.Px(18)),
        };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(entry, "SteamGridDB API key");
        ui.Focusable(entry);
        Key(entry, "sgdb-key");
        content.Children.Add(entry);
        var line = ui.P(shell.Service.IsPreview ? "Preview only. No credentials are read or saved." :
            status.Problem ?? (status.Connected ? "Connected. Desktop and Game Mode share this connection." : "Paste your key, then choose Connect."));
        content.Children.Add(line);
        content.Children.Add(ui.P("Your key is saved in Windows Credential Manager, never in app settings or your game files.", 0.8));
        Button connect = null!, disconnect = null!;
        var isConnected = status.Connected;
        connect = ui.Button(isConnected ? "Replace key" : "Connect", async () =>
        {
            line.Text = "Checking key and saving securely…";
            connect.IsEnabled = false;
            try
            {
                await shell.Service.SteamGridConnectAsync(entry.Password);
                isConnected = true;
                line.Text = "Connected. Desktop and Game Mode share this connection.";
                if (connected is not null) { CloseModal(); connected(); return; }
            }
            catch (InvalidOperationException error) { line.Text = error.Message; }
            finally { entry.Password = ""; connect.IsEnabled = true; disconnect.IsEnabled = isConnected; }
        }, GmKind.Primary, 0.92, enabled: !shell.Service.IsPreview);
        disconnect = ui.Button("Disconnect", async () =>
        {
            try
            {
                var external = await shell.Service.SteamGridDisconnectAsync();
                isConnected = external;
                line.Text = external ? "Saved key removed. An external environment key is still configured." : "Disconnected. Your downloaded artwork stays in place.";
            }
            catch (InvalidOperationException error) { line.Text = error.Message; }
            disconnect.IsEnabled = isConnected;
        }, GmKind.Card, 0.92, enabled: isConnected && !shell.Service.IsPreview);
        var close = ui.Button("Close", () => { entry.Password = ""; CloseModal(); }, GmKind.Card, 0.92);
        ShowModal("Connect SteamGridDB", content, [close, disconnect, connect], () => { entry.Password = ""; CloseModal(); }, 1000, entry);
    }

    // ---------- Details › Appearance: custom artwork ----------

    void CustomArtworkSection(Game g, StackPanel content)
    {
        SectionTitle(content, "Custom Artwork", "Artwork changes also sync to your local Steam library. Reset restores your original Steam artwork.");
        var preview = shell.Service.IsPreview;
        var cards = new Controls.PresetColumns(t.Px(260), 3) { ColumnSpacing = t.Px(16), RowSpacing = t.Px(16) };
        foreach (var (role, title, path) in new[] { ("poster", "Poster", g.PosterPath), ("capsule", "Wide Capsule", g.CapsulePath), ("hero", "Hero", g.HeroPath) })
        {
            var thumb = new Border
            {
                Width = t.Px(role == "poster" ? 60 : 128), Height = t.Px(role == "poster" ? 90 : 60), CornerRadius = new CornerRadius(t.Px(8)),
                Background = GmTheme.B(t.Card),
            };
            if (GameItem.Image(path) is { } image) thumb.Child = new Border { CornerRadius = new CornerRadius(t.Px(8)), Background = new ImageBrush { ImageSource = image, Stretch = Stretch.UniformToFill } };
            thumb.HorizontalAlignment = HorizontalAlignment.Center;
            var card = new StackPanel { Spacing = t.Px(12) };
            card.Children.Add(ui.Text(title, .9, weight: FontWeights.SemiBold));
            card.Children.Add(new Grid { Height = t.Px(110), Children = { thumb } });
            card.Children.Add(ui.P(g.ArtCredits.GetValueOrDefault(role) ?? (path is null ? "No artwork yet" : g.MetadataSource ?? g.Library), .72));
            var choose = ui.Button("Choose image", () => _ = ChooseArtworkAsync(g, role), GmKind.Card, .78, !preview, radius: 10, minHeight: 48);
            choose.HorizontalAlignment = HorizontalAlignment.Stretch; Key(choose, "art-choose-" + role); card.Children.Add(choose);
            var actions = new Controls.PresetColumns(t.Px(100), 2) { ColumnSpacing = t.Px(8), RowSpacing = t.Px(8) };
            actions.Children.Add(ui.Button("Browse", () => _ = BrowseArtworkAsync(g, role), GmKind.Card, .72, !preview, radius: 10, minHeight: 48,
                padding: new Thickness(t.Px(10))).With(b => { b.HorizontalAlignment = HorizontalAlignment.Stretch; Key(b, "art-browse-" + role); }));
            actions.Children.Add(ui.Button("Reset", () => _ = ResetArtworkAsync(g, role), GmKind.Card, .72, !preview, radius: 10, minHeight: 48,
                padding: new Thickness(t.Px(10))).With(b => { b.HorizontalAlignment = HorizontalAlignment.Stretch; Key(b, "art-reset-" + role); }));
            card.Children.Add(actions); cards.Children.Add(DetailPlate(card));
        }
        content.Children.Add(cards);
        content.Children.Add(ui.Button(IconText("", "Sync artwork to Steam"), () => _ = SyncArtworkAsync(g), GmKind.Primary, 0.85, !preview)
            .With(b => { b.HorizontalAlignment = HorizontalAlignment.Right; Key(b, "art-sync-game"); }));
    }

    object IconText(string glyph, string text) => shell.Settings.ButtonGlyphs ? ui.IconLabel(glyph, text) : text;

    async Task ChooseArtworkAsync(Game g, string role)
    {
        var path = await shell.PickFileAsync(".png", ".jpg", ".jpeg", ".webp");
        if (path is null) return;
        try { await shell.Service.StoreArtworkAsync(g, role, await MainWindow.PngIfWebpAsync(path)); }
        catch (InvalidOperationException error) { ShowDone(false, "Choose artwork", error.Message); return; }
        await shell.RefreshArtworkAsync(false, [g]);
        await SyncArtworkAsync(g);
    }

    async Task ResetArtworkAsync(Game g, string role)
    {
        try { await shell.Service.ResetArtworkAsync(g, role); }
        catch (InvalidOperationException error) { ShowDone(false, "Reset artwork", error.Message); return; }
        await SyncArtworkAsync(g);
        await shell.ScanAsync();
    }

    // ---------- SteamGridDB browser ----------

    async Task BrowseArtworkAsync(Game g, string role)
    {
        SteamGridStatus status;
        try { status = await shell.Service.SteamGridStatusAsync(); }
        catch (InvalidOperationException error) { ShowDone(false, "SteamGridDB", error.Message); return; }
        if (!status.Connected) { await ConnectSteamGridAsync(() => _ = BrowseArtworkAsync(g, role)); return; }

        var titles = new Dictionary<string, string> { ["poster"] = "Posters", ["capsule"] = "Wide capsules", ["hero"] = "Heroes" };
        var line = ui.P("Searching games…");
        var results = new StackPanel { Spacing = t.Px(16) };
        var content = new StackPanel { Spacing = t.Px(18) };
        content.Children.Add(line);
        content.Children.Add(new ScrollViewer { Content = results, MaxHeight = t.Px(t.Compact ? 300 : 460), HorizontalScrollMode = ScrollMode.Disabled });
        var page = 0;
        SteamGridGame? match = null;
        var assets = new List<SteamGridAsset>();
        Button more = null!;
        var grid = new VariableSizedWrapGrid { Orientation = Orientation.Horizontal, ItemWidth = t.Px(role == "poster" ? 170 : 290), ItemHeight = t.Px(role == "poster" ? 280 : 170) };

        async Task Load(bool append)
        {
            if (match is null) return;
            page = append ? page + 1 : 0;
            line.Text = "Finding " + titles[role].ToLowerInvariant() + "…";
            IReadOnlyList<SteamGridAsset> found;
            try { found = await shell.Service.SteamGridArtworkAsync(match.Id, role, page, "", "", "", false); }
            catch (InvalidOperationException error) { line.Text = error.Message; return; }
            if (!append) { grid.Children.Clear(); assets.Clear(); }
            foreach (var asset in found.Where(a => assets.All(x => x.Id != a.Id)))
            {
                assets.Add(asset);
                var card = new StackPanel { Spacing = t.Px(6) };
                card.Children.Add(new Border
                {
                    Height = t.Px(role == "poster" ? 210 : 100), CornerRadius = new CornerRadius(t.Px(8)),
                    Background = new ImageBrush { ImageSource = new BitmapImage(new Uri(asset.Thumb ?? asset.Url)) { DecodePixelWidth = 300 }, Stretch = Stretch.UniformToFill },
                });
                card.Children.Add(ui.Text(asset.Author, 0.62, t.Muted));
                var pick = ui.Button(card, () => _ = PreviewAsync(asset), GmKind.Transparent, 1, radius: 12, padding: new Thickness(t.Px(6)), minHeight: 0,
                    name: $"{asset.Width} × {asset.Height} by {asset.Author}");
                grid.Children.Add(pick);
            }
            line.Text = assets.Count > 0 ? $"{assets.Count} {titles[role].ToLowerInvariant()} · {match.Name}" : "No artwork found for this game.";
            more.IsEnabled = found.Count > 0 && page < 100;
        }

        async Task PreviewAsync(SteamGridAsset asset)
        {
            line.Text = "Loading full-size preview…";
            string path;
            try { path = await shell.Service.SteamGridDownloadAsync(asset); }
            catch (InvalidOperationException error) { line.Text = error.Message; return; }
            line.Text = titles[role] + " · " + match?.Name;
            var body = new StackPanel { Spacing = t.Px(16) };
            body.Children.Add(new Image { Source = new BitmapImage(new Uri(path)), MaxHeight = t.Px(t.Compact ? 300 : 460), Stretch = Stretch.Uniform });
            body.Children.Add(ui.P($"{asset.Width} × {asset.Height} · {asset.Author}. Apply this image to rtxForge and your selected Steam library."));
            var back = ui.Button("Back to results", CloseModal, GmKind.Card, 0.92);
            var use = ui.Button("Use artwork", async () =>
            {
                CloseModal();
                CloseModal();
                try { await shell.Service.StoreArtworkAsync(g, role, await MainWindow.PngIfWebpAsync(path), "SteamGridDB · " + asset.Author); }
                catch (InvalidOperationException error) { ShowDone(false, "Use artwork", error.Message); return; }
                await shell.RefreshArtworkAsync(false, [g]);
                await SyncArtworkAsync(g);
            }, GmKind.Primary, 0.92);
            ShowModal("Artwork preview", body, [back, use], CloseModal, 1200, use);
        }

        more = ui.Button("Load more", () => _ = Load(true), GmKind.Card, 0.92, enabled: false);
        var close = ui.Button("Close", CloseModal, GmKind.Card, 0.92);
        ShowModal(titles[role] + " for " + g.Name, content, [close, more], CloseModal, 1400, close);
        try
        {
            var found = await shell.Service.SteamGridSearchAsync(g.Name);
            var exact = found.Where(m => string.Equals(m.Name, g.Name, StringComparison.OrdinalIgnoreCase)).ToList();
            if (exact.Count == 1) { match = exact[0]; results.Children.Add(grid); await Load(false); return; }
            line.Text = found.Count > 0 ? "Choose the matching game." : "No matching games on SteamGridDB.";
            if (found.Count > 0)
                results.Children.Add(ui.Group(found.Select(candidate => (UIElement)ui.RowButton(candidate.Name, null, () =>
                {
                    match = candidate;
                    results.Children.Clear();
                    results.Children.Add(grid);
                    _ = Load(false);
                })), t.Card));
        }
        catch (InvalidOperationException error) { line.Text = error.Message; }
    }

    // ---------- Details › Tools ----------

    async Task DiagnoseAsync(Game g)
    {
        NrDiagnosis report;
        try { report = await shell.Service.DiagnoseAsync(g); }
        catch (InvalidOperationException error) { ShowDone(false, "NR Diagnosis", error.Message); return; }
        var content = new StackPanel { Spacing = t.Px(14) };
        foreach (var warning in report.Warnings) content.Children.Add(ui.Text(warning, 0.9, t.Danger, FontWeights.SemiBold, wrap: true));
        foreach (var observation in report.Observations) content.Children.Add(ui.P(observation, 0.88));
        content.Children.Add(ui.Text("Visible result: " + report.VisualResult, 0.95, weight: FontWeights.SemiBold, wrap: true));
        if (report.Report.Length > 0)
            content.Children.Add(new ScrollViewer
            {
                MaxHeight = t.Px(t.Compact ? 220 : 340),
                Content = new TextBlock { Text = report.Report, FontFamily = new FontFamily("Cascadia Mono, Consolas"), FontSize = t.Em(0.62), Foreground = GmTheme.B(t.Muted), TextWrapping = TextWrapping.Wrap },
            }.With(s => { s.IsTabStop = true; ui.Focusable(s); }));
        var refresh = ui.Button("Refresh", () => { CloseModal(); _ = DiagnoseAsync(g); }, GmKind.Card, 0.92);
        var close = ui.Button("Close", CloseModal, GmKind.Primary, 0.92);
        ShowModal(g.Name + " · NR Diagnosis", content, [refresh, close], CloseModal, 1200, close);
    }

    async Task InstallExtraAsync(Game g, string kind)
    {
        if (shell.Service.IsPreview) { Toast("Installing tools is disabled in preview mode."); return; }
        var path = kind == "reshade" ? await shell.PickFileAsync(".dll") : await shell.PickFileAsync(".addon64");
        if (path is null) return;
        await RunReviewAsync(kind == "reshade" ? "Install ReShade" : "Install Add-on", () => shell.Service.ReviewExtraAsync(g, path, kind));
        if (page == "details") Render(keepFocus: true);
    }

    async Task FillExtraRecordsAsync(Game g, StackPanel host)
    {
        IReadOnlyList<ExtraRecord> records;
        try { records = await shell.Service.ExtraRecordsAsync(g); }
        catch (InvalidOperationException) { return; }
        if (records.Count == 0 || detailsGame != g || detailsSection != "Tools") return;
        host.Children.Add(ui.H2("Installed Tools", 1.06));
        host.Children.Add(ui.Group(records.Select(r => (UIElement)ui.RowButton(r.Title, "Restore", async () =>
        {
            await RunReviewAsync("Restore Tool", () => shell.Service.ReviewExtraRestoreAsync(r));
            Render(keepFocus: true);
        }, description: r.Date))));
    }

    // ---------- Details › DLSS Files ----------

    async Task FillDlssInventoryAsync(Game g, StackPanel host, Button restore)
    {
        DlssInventory inventory;
        try { inventory = await shell.Service.DlssInventoryAsync(g); }
        catch (InvalidOperationException error) { host.Children.Add(ui.P(error.Message)); return; }
        if (detailsGame != g || detailsSection != "DLSS Files") return;
        var rows = new List<UIElement>();
        if (inventory.Blocked.Length > 0) rows.Add(ui.PreferenceRow("File management unavailable", inventory.Blocked, null));
        foreach (var file in inventory.Files)
            rows.Add(ui.PreferenceRow(file.Title, file.Path + " · " + file.Provenance, ui.Text(file.Current, 0.85, t.Muted)));
        rows.Add(ui.PreferenceRow("Latest backup", null, ui.Text(inventory.LatestBackup ?? "None", 0.85, t.Muted)));
        host.Children.Add(ui.Group(rows));
        restore.IsEnabled = inventory.LatestBackup is not null;
    }

    async Task RestoreDlssAsync(Game g)
    {
        var result = await RunReviewAsync("Restore original DLSS files", () => shell.Service.ReviewDlssRestoreAsync(g));
        if (result is { Errors.Count: 0 }) await shell.ScanAsync();
    }

    // ---------- Details › Notes ----------

    async Task SaveNotesAsync(Game g, string status, string notes)
    {
        try { await shell.Service.SaveNotesAsync(g, status, notes); Toast("Notes saved."); }
        catch (InvalidOperationException error) { ShowDone(false, "Save notes", error.Message); }
    }

    async Task RecordTestAsync(Game g)
    {
        var finish = g.TestActive;
        try
        {
            if (finish) await shell.Service.FinishTestAsync(g);
            else await shell.Service.StartTestAsync(g);
        }
        catch (InvalidOperationException error) { ShowDone(false, finish ? "Finish Test" : "Start Test", error.Message); return; }
        if (!finish && g.Library == "Steam" && g.AppId is { } appid && appid.All(char.IsDigit)) MainWindow.OpenUri("steam://rungameid/" + appid);
        Toast(finish ? "Logs captured. Record your result and save notes." : "Test started. Launch your game normally, then return here to finish.");
        Render(keepFocus: true);
    }

    // ---------- Settings › System: recovery and updates ----------

    List<UIElement> RecoveryRows() =>
    [
        ui.RowButton("Previous changes", null, () => _ = PreviousChangesAsync(), description: "Browse available recovery records.", glyph: ""),
        ui.RowButton("Old NR files", null, async () =>
        {
            if (shell.Service.IsPreview) { Toast("Old NR file cleanup is disabled in preview mode."); return; }
            if (await RunReviewAsync("Remove old NR files", shell.Service.ReviewCleanupAsync, "No old NR files were found in your libraries.") is not null)
                await shell.ScanAsync();
        }, description: "Review legacy files before removal.", glyph: ""),
        ui.RowButton("Check for updates", null, () => _ = CheckForUpdatesAsync(), description: $"rtxForge {MainWindow.AppVersion} · download, verify and install the newest build.", glyph: ""),
    ];

    async Task PreviousChangesAsync()
    {
        IReadOnlyList<RecoveryRecord> records;
        try { records = await shell.Service.RecoveriesAsync(); }
        catch (InvalidOperationException error) { ShowDone(false, "Undo previous changes", error.Message); return; }
        var content = new StackPanel { Spacing = t.Px(18) };
        if (records.Count == 0) content.Children.Add(ui.P(shell.Service.IsPreview ? "Your install and uninstall backups will appear here." : "No recorded changes yet."));
        else
            content.Children.Add(new ScrollViewer
            {
                MaxHeight = t.Px(t.Compact ? 300 : 460),
                Content = ui.Group(records.Select(r => (UIElement)ui.RowButton(r.Name, "Review", async () =>
                {
                    CloseModal();
                    if (await RunReviewAsync("Restore recorded changes", () => shell.Service.ReviewRecoveryAsync(r)) is not null) await shell.ScanAsync();
                }, description: r.Detail)), t.Card),
            });
        var back = ui.Button("Back", CloseModal, GmKind.Card, 0.92);
        ShowModal("Undo previous changes", content, [back], CloseModal, 1100);
    }

    async Task CheckForUpdatesAsync()
    {
        if (shell.Service.IsPreview) { Toast("Checking for updates is disabled in preview mode."); return; }
        var result = await RunReviewAsync("rtxForge Update", shell.Service.CheckForUpdateAsync);
        if (result?.Path is not { } installer || result.Errors.Count > 0) return;
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(installer) { UseShellExecute = true });
        shell.Close();
    }

    // ---------- Main menu › Packages ----------

    async Task ShowPackagesAsync()
    {
        CloseAllModals();
        PackageCatalog catalog;
        try { catalog = await shell.Service.PackagesAsync(); }
        catch (InvalidOperationException error) { ShowDone(false, "Packages", error.Message); return; }
        var content = new StackPanel { Spacing = t.Px(18) };
        content.Children.Add(ui.P(catalog.Status + ". Every game change is reviewed before it is applied."));
        var rows = catalog.Packages.Select(item =>
        {
            var current = shell.Settings.RuntimeProvider == item.Id;
            return (UIElement)ui.RowButton(item.Name, current ? "In use" : item.Available ? "Use" : "Unavailable", () =>
            {
                CloseModal();
                shell.SelectPackage(item.Id);
                Toast("Package selected. Select games, then choose Install Features.");
            }, description: item.Version + " · " + (item.Available ? item.Summary : item.Reason), enabled: item.Available && !current);
        }).ToList();
        rows.Add(ui.RowButton("Add custom package", catalog.CustomName, () => _ = InspectPackageAsync(),
            description: "ZIP archives. Files and instructions are inspected without running them.", enabled: !shell.Service.IsPreview));
        content.Children.Add(new ScrollViewer { Content = ui.Group(rows, t.Card), MaxHeight = t.Px(t.Compact ? 320 : 480) });
        var back = ui.Button("Back", CloseModal, GmKind.Card, 0.92);
        ShowModal("Packages", content, [back], CloseModal, 1100);
    }

    async Task InspectPackageAsync()
    {
        var path = await shell.PickFileAsync(".zip");
        if (path is null) return;
        PackageInspection inspection;
        try { inspection = await shell.Service.InspectPackageAsync(path); }
        catch (InvalidOperationException error) { ShowDone(false, "Custom package", error.Message); return; }
        var content = new StackPanel { Spacing = t.Px(16) };
        content.Children.Add(ui.P($"{inspection.Confidence} · {inspection.Family} · {inspection.FileCount} files · {inspection.ExpandedBytes / 1048576.0:0.0} MiB expanded"));
        content.Children.Add(ui.Group(inspection.Parameters.Select(p => (UIElement)ui.PreferenceRow(p.Label, p.Origin, ui.Text(p.Value, 0.85, t.Muted))), t.Card));
        foreach (var warning in inspection.Warnings) content.Children.Add(ui.P(warning, 0.8));
        if (!inspection.Deployable) content.Children.Add(ui.P("This layout has no verified deployment adapter yet. Nothing will be installed.", 0.85));
        content.Children.Add(ui.P("Package settings are taken as shown; edit them in Desktop UI if needed. Instructions are read, never executed.", 0.8));
        var trusted = false;
        Button use = null!;
        Button toggle = null!;
        toggle = ui.RowButton("I trust the source of this package", "No", () =>
        {
            trusted = !trusted;
            SetPrimaryEnabled(use, trusted && inspection.Deployable);
            if (toggle.Content is Grid g && g.Children.OfType<TextBlock>().FirstOrDefault() is { } value) value.Text = trusted ? "Yes" : "No";
        });
        content.Children.Add(ui.Group([toggle], t.Card));
        void Cancel() { CloseModal(); shell.Service.DiscardReview(new EngineReview(inspection.Token, "package", "", "", "", [], [])); }
        var cancel = ui.Button("Cancel", Cancel, GmKind.Card, 0.92);
        use = ui.Button("Use reviewed package", async () =>
        {
            try
            {
                var choice = await shell.Service.UseCustomPackageAsync(inspection, inspection.Parameters.ToDictionary(p => p.Key, p => p.Value), trusted, "");
                CloseModal();
                shell.SelectPackage("custom", choice.Presets);
                ShowDone(true, "Package selected", choice.Name + ". Select games, then choose Install Features.");
            }
            catch (InvalidOperationException error) { CloseModal(); ShowDone(false, "Custom package", error.Message); }
        }, GmKind.Primary, 0.92, enabled: false);
        ShowModal("Review " + inspection.Name, new ScrollViewer { Content = content, MaxHeight = t.Px(t.Compact ? 360 : 560) }, [cancel, use], Cancel, 1200, cancel);
    }
}
