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
                content.Children.Add(ui.Group(review.Blocked.Select(b => (UIElement)ReviewRow(Find(b), b.Title, b.Detail, false, b.Details)), t.Card));
            var close = ui.Button("Done", () => { CloseModal(); done.TrySetResult(null); }, GmKind.Card, 0.92);
            ShowModal(review.Title, content, [close], () => { CloseModal(); done.TrySetResult(null); }, 1100, close);
            return await done.Task;
        }
        if (review.Summary.Length > 0) content.Children.Add(ui.P(review.Summary));
        var list = new StackPanel { Spacing = t.Px(18) };
        list.Children.Add(ui.Group(review.Items.Select(i => (UIElement)ReviewRow(Find(i), i.Title, i.Detail, true, i.Details)), t.Card));
        if (review.Blocked.Count > 0)
        {
            list.Children.Add(ui.Heading($"Skipped · {review.Blocked.Count}", 0.88));
            list.Children.Add(ui.Group(review.Blocked.Select(b => (UIElement)ReviewRow(Find(b), b.Title, b.Detail, false, b.Details)), t.Card));
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
        button.Background = GmTheme.B(on ? ui.Accent : t.Disabled);
        button.Foreground = GmTheme.B(on ? ui.AccentInk : t.DisabledFg);
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

    Button RefreshArtworkRow() =>
        ui.RowButton("Refresh artwork", "Refresh", () => { Toast("Refreshing artwork…"); _ = shell.RefreshArtworkAsync(true); },
            description: "Cached images remain available offline.", glyph: "").With(r => Key(r, "art-refresh"));

    List<UIElement> SteamArtworkRows() =>
    [
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
            Background = t.Surface(t.Card), Foreground = GmTheme.B(t.Fg), BorderBrush = GmTheme.B(t.Line), CornerRadius = new CornerRadius(t.Px(12)),
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
                Background = t.Surface(t.Card),
            };
            if (GameItem.Image(path) is { } image) thumb.Child = new Border { CornerRadius = new CornerRadius(t.Px(8)), Background = new ImageBrush { ImageSource = image, Stretch = Stretch.UniformToFill } };
            thumb.HorizontalAlignment = HorizontalAlignment.Center;
            var card = new StackPanel { Spacing = t.Px(20) };
            card.Children.Add(DetailHeading(title, "\uE790"));
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

    // ---------- Bug Report (the desktop's report, with controller-sized controls) ----------

    static readonly string[] ResultChoices = ["Worked", "Didn't work", "Didn't test"];

    /// <summary>A report is about one game; with several to choose from, ask which.</summary>
    void ChooseSupportReportGames(IReadOnlyList<Game>? games = null)
    {
        games ??= shell.Games;
        if (games.Count == 1) { _ = ReportGameAsync(games[0]); return; }
        var rows = new StackPanel { Spacing = t.Px(8) };
        foreach (var game in games)
            rows.Children.Add(ui.Button(game.Name, () => { CloseModal(); _ = ReportGameAsync(game); }));
        var content = new StackPanel { Spacing = t.Px(12) };
        content.Children.Add(ui.P("Which game is it about?"));
        content.Children.Add(new ScrollViewer { Content = rows, MaxHeight = t.Px(t.Compact ? 320 : 520) }.With(s => { s.IsTabStop = true; ui.Focusable(s); }));
        ShowModal("Bug Report", content, [ui.Button("Cancel", CloseModal, GmKind.Card, .9)], CloseModal, 1000);
    }

    /// <summary>
    /// One game: "What happened?" first, NR and MFG in three words each, logs on, and Send.
    /// What rtxForge detected is folded under "Details we'll include". Choices change with A or
    /// Left/Right; text uses the on-screen keyboard. A copy is saved on this PC either way.
    /// </summary>
    async Task ReportGameAsync(Game game)
    {
        if (shell.Service.IsPreview) { Toast("Bug reports are disabled in preview mode."); return; }
        BetaReportDraft draft;
        try { draft = await shell.Service.DraftReportsAsync([game], MainWindow.InstallFormat(), ""); }
        catch (InvalidOperationException error) { ShowDone(false, "Bug Report", error.Message); return; }
        var report = draft.Reports[0];
        var values = report.Fields.ToDictionary(p => p.Key, p => p.Value);
        var edits = new Dictionary<string, string>();
        void Set(string key, string value) { values[key] = value; edits[key] = value; }
        var logs = true;
        Button? send = null;
        void Refresh() { if (send is not null) send.IsEnabled = !string.IsNullOrWhiteSpace(values.GetValueOrDefault("observations")) && !string.IsNullOrWhiteSpace(values.GetValueOrDefault("platform")); }

        var content = new StackPanel { Spacing = t.Px(16) };
        content.Children.Add(ui.P("Goes to rtxForge's issues on GitHub. What you write and the details below are public; logs stay private.", 0.8));
        var observations = draft.Fields.First(f => f.Id == "observations");
        var what = new TextBox { Header = observations.Label, Text = values.GetValueOrDefault("observations") ?? "", AcceptsReturn = true,
            TextWrapping = TextWrapping.Wrap, MinHeight = t.Px(140), MaxLength = observations.Max,
            PlaceholderText = "What you did, what you expected, and what you saw." };
        what.TextChanged += (_, _) => { Set("observations", what.Text); Refresh(); };
        ui.Focusable(what);
        content.Children.Add(what);

        Button Cycle(string label, Func<string> caption, Action step)
        {
            Button? button = null;
            button = ui.Button(label + ": " + caption(), () => { step(); button!.Content = label + ": " + caption(); Refresh(); }, GmKind.Card, .85);
            return button;
        }
        foreach (var (key, label) in new[] { ("nr-result", "NR"), ("mfg-result", "MFG") })
        {
            var original = values.GetValueOrDefault(key) ?? "";
            var index = original switch { "Working in-game" => 0, "Not working in-game" => 1, _ => 2 };
            content.Children.Add(Cycle(label, () => ResultChoices[index], () =>
            {
                index = (index + 1) % ResultChoices.Length;
                Set(key, index switch
                {
                    0 => "Working in-game",
                    1 => "Not working in-game",
                    _ => original is "Working in-game" or "Not working in-game" or "" ? "Installed, not tested" : original,
                });
            }));
        }
        content.Children.Add(Cycle("Include logs (private)", () => logs ? "On" : "Off", () => logs = !logs));

        var details = new StackPanel { Spacing = t.Px(12), Visibility = Visibility.Collapsed };
        foreach (var field in draft.Fields.Where(f => f.Id is not ("observations" or "nr-result" or "mfg-result")))
        {
            if (field.Choices.Count > 0)
            {
                var options = field.Choices.ToList();
                details.Children.Add(Cycle(field.Label, () => values.GetValueOrDefault(field.Id) is { Length: > 0 } v ? v : "Choose", () =>
                    Set(field.Id, options[(options.IndexOf(values.GetValueOrDefault(field.Id) ?? "") + 1) % options.Count])));
            }
            else
            {
                var box = new TextBox { Header = field.Label, Text = values.GetValueOrDefault(field.Id) ?? "", MaxLength = field.Max > 0 ? field.Max : 0 };
                box.TextChanged += (_, _) => { Set(field.Id, box.Text); Refresh(); };
                ui.Focusable(box);
                details.Children.Add(box);
            }
        }
        string Summary() => string.Join(" · ", new[] { "platform", "gpu", "feature-package" }
            .Select(k => values.GetValueOrDefault(k)).Where(v => !string.IsNullOrWhiteSpace(v)));
        Button? fold = null;
        fold = ui.Button("Details we'll include · " + Summary(), () =>
        {
            details.Visibility = details.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible;
        }, GmKind.Card, .8);
        content.Children.Add(fold);
        content.Children.Add(details);
        content.Children.Add(ui.P("Text entry uses the Windows touch keyboard or Steam's keyboard.", 0.75));

        var documents = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        send = ui.Button("Send Report", () => _ = SendGameReportAsync(report.Id, edits, logs, documents), GmKind.Primary, .9);
        var outline = ui.Button("See what's sent", () => _ = ShowReportOutlineAsync(report.Id, edits, logs), GmKind.Card, .9);
        Refresh();
        ShowModal("Report a problem · " + report.Name, content, [send, outline, ui.Button("Cancel", CloseModal, GmKind.Card, .9)], CloseModal, 1200, what);
    }

    async Task SendGameReportAsync(string id, IReadOnlyDictionary<string, string> edits, bool logs, string documents)
    {
        ShowModal("Sending your report…", ui.P(logs ? "Reading and redacting logs, then sending." : "Sending."), [], () => { }, 900);
        ReportSent sent;
        try { sent = await shell.Service.SendReportAsync(id, edits, logs, documents); }
        catch (InvalidOperationException error) { CloseModal(); ShowDone(false, "Bug Report", error.Message); return; }
        CloseModal();
        var content = new StackPanel { Spacing = t.Px(12) };
        if (sent.Sent)
        {
            CloseModal();
            content.Children.Add(ui.Text($"Thanks! It's issue #{sent.Number} on GitHub.", 1.0, wrap: true));
            content.Children.Add(ui.P("A copy is saved in " + Path.GetDirectoryName(sent.Path) + ".", 0.75));
            var done = ui.Button("Done", CloseModal, GmKind.Primary, .9);
            ShowModal("Report sent", content, [ui.Button("View on GitHub", () => { if (sent.Url is { } url) MainWindow.OpenUri(url); }, GmKind.Card, .9), done], CloseModal, 1000, done);
            return;
        }
        content.Children.Add(ui.Text(sent.Error ?? "The report service didn't answer.", 1.0, wrap: true));
        content.Children.Add(ui.P("Saved on this PC: " + sent.Path, 0.75));
        // Back to the form, answers kept, for another try.
        var retry = ui.Button("Try again", CloseModal, GmKind.Primary, .9);
        ShowModal("Couldn't send the report", content,
            [retry, ui.Button("Open folder", () => System.Diagnostics.Process.Start("explorer.exe", $"/select,\"{sent.Path}\""), GmKind.Card, .9)], CloseModal, 1000, retry);
    }

    async Task ShowReportOutlineAsync(string id, IReadOnlyDictionary<string, string> edits, bool logs)
    {
        ReportOutline outline;
        try { outline = await shell.Service.OutlineReportAsync(id, edits, logs); }
        catch (InvalidOperationException error) { ShowDone(false, "What's sent", error.Message); return; }
        var mono = new FontFamily("Cascadia Mono, Consolas");
        var content = new StackPanel { Spacing = t.Px(14) };
        content.Children.Add(ui.Text("Public on GitHub", 1.0, weight: FontWeights.SemiBold));
        content.Children.Add(ui.Text(outline.Title, .85, wrap: true));
        content.Children.Add(new TextBlock { Text = outline.Text, FontFamily = mono, FontSize = t.Em(0.7), Foreground = GmTheme.B(t.Muted), TextWrapping = TextWrapping.Wrap });
        content.Children.Add(ui.Text(logs ? "Private: only the rtxForge maintainers" : "Logs: not included", 1.0, weight: FontWeights.SemiBold));
        foreach (var log in outline.Logs)
        {
            content.Children.Add(ui.Text($"{log.Name} · {log.Detail}", .8, wrap: true));
            content.Children.Add(new TextBlock { Text = log.Text.Length > 8000 ? "…" + log.Text[^8000..] : log.Text, FontFamily = mono, FontSize = t.Em(0.65),
                Foreground = GmTheme.B(t.Muted), TextWrapping = TextWrapping.Wrap });
        }
        foreach (var skipped in outline.Skipped) content.Children.Add(ui.P("Not included: " + skipped, 0.75));
        var scroll = new ScrollViewer { Content = content, MaxHeight = t.Px(t.Compact ? 420 : 640) }.With(s => { s.IsTabStop = true; ui.Focusable(s); });
        var back = ui.Button("Back", CloseModal, GmKind.Primary, .9);
        ShowModal("What's sent", scroll, [back], CloseModal, 1200, back);
    }

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
        var path = kind == "reshade" ? "" : kind == "reshade-import" ? await shell.PickFileAsync(".zip", ".dll", ".addon64", ".addon32", ".ini", ".fx", ".fxh") : await shell.PickFileAsync(".addon64");
        if (path is null) return;
        await RunReviewAsync(kind == "reshade" ? "Install ReShade" : kind == "reshade-import" ? "Import ReShade package" : "Install Add-on", () => shell.Service.ReviewExtraAsync(g, path, kind));
        if (page == "details") Render(keepFocus: true);
    }

    async Task FillExtraRecordsAsync(Game g, StackPanel host)
    {
        IReadOnlyList<ExtraRecord> records;
        try { records = await shell.Service.ExtraRecordsAsync(g); }
        catch (InvalidOperationException) { return; }
        if (records.Count == 0 || detailsGame != g || detailsSection != "Tools") return;
        SectionTitle(host, "Installed Tools", "Restore puts the game's original files back.");
        host.Children.Add(ui.Group(records.Select(r => (UIElement)ui.RowButton(r.Title, "Restore", async () =>
        {
            await RunReviewAsync("Restore Tool", () => shell.Service.ReviewExtraRestoreAsync(r));
            Render(keepFocus: true);
        }, description: r.Date))));
    }

    // ---------- Details › DLSS Files ----------

    async Task FillDlssInventoryAsync(Game g, StackPanel host, Button restore, Border backupFact)
    {
        // As on the desktop: nvngx_dlss.dll first, then each file found, with the latest
        // backup shown on the Restore card.
        var rows = new List<UIElement> { ui.PreferenceRow("nvngx_dlss.dll", g.DlssVersion is null ? "Not detected" : "Version " + g.DlssVersion, null) };
        void Show()
        {
            // The rows move to a new group, so release them from the old one first.
            if (host.Children.FirstOrDefault() is Border { Child: StackPanel old }) old.Children.Clear();
            host.Children.Clear(); host.Children.Add(ui.Group(rows));
        }
        Show();
        DlssInventory inventory;
        try { inventory = await shell.Service.DlssInventoryAsync(g); }
        catch (InvalidOperationException error) { SetFactValue(backupFact, error.Message); return; }
        if (detailsGame != g || detailsSection != "DLSS Files") return;
        if (inventory.Blocked.Length > 0) rows.Add(ui.PreferenceRow("File management unavailable", inventory.Blocked, null));
        foreach (var file in inventory.Files)
            rows.Add(ui.PreferenceRow(file.Title, $"{file.Path} · {file.Current} · {file.Provenance}", null));
        Show();
        SetFactValue(backupFact, inventory.LatestBackup is { } date ? "Latest backup " + date : "No DLSS file backups for this game.");
        restore.IsEnabled = inventory.LatestBackup is not null;
    }

    /// <summary>The value line of a DetailFact card.</summary>
    static void SetFactValue(Border fact, string text)
    {
        if (fact.Child is Panel { Children.Count: > 1 } lines && lines.Children[1] is TextBlock value) value.Text = text;
    }

    async Task RestoreDlssAsync(Game g)
    {
        var result = await RunReviewAsync("Restore original DLSS files", () => shell.Service.ReviewDlssRestoreAsync(g));
        if (result is { Errors.Count: 0 }) await shell.ScanAsync();
    }

    // ---------- Details › Notes ----------

    async Task SaveNotesAsync(Game g, string status, string notes, string saved = "Notes saved.")
    {
        try { await shell.Service.SaveNotesAsync(g, status, notes); Toast(saved); }
        catch (InvalidOperationException error) { ShowDone(false, "Save notes", error.Message); }
    }

    async Task TryAnywayAsync(Game g, bool on)
    {
        try { await shell.Service.SetTryAnywayAsync(g, on); }
        catch (InvalidOperationException error) { ShowDone(false, "Try anyway", error.Message); return; }
        Toast(on ? $"{g.Name} can be installed now. Review the install before applying it." : $"{g.Name} is checked normally again.");
        await shell.ScanAsync();
    }

    /// <summary>Preview the exact issue text, then open it in the browser. Nothing is sent from rtxForge.</summary>
    async Task ShareResultAsync(Game g, bool notes = false)
    {
        CompatShare share;
        try { share = await shell.Service.CompatShareAsync(g, shell.SharePackage(g), notes); }
        catch (InvalidOperationException error) { ShowDone(false, "Share result", error.Message); return; }
        var content = new StackPanel { Spacing = t.Px(14) };
        content.Children.Add(ui.P("This opens a prefilled issue in your browser. Nothing is sent until you post it there.", 0.9));
        content.Children.Add(new ScrollViewer
        {
            MaxHeight = t.Px(t.Compact ? 220 : 340),
            Content = new TextBlock { Text = share.Body, FontFamily = new FontFamily("Cascadia Mono, Consolas"), FontSize = t.Em(0.7), Foreground = GmTheme.B(t.Muted), TextWrapping = TextWrapping.Wrap },
        }.With(s => { s.IsTabStop = true; ui.Focusable(s); }));
        var toggle = ui.Button(notes ? "Leave out my notes" : "Include my notes", () => { CloseModal(); _ = ShareResultAsync(g, !notes); }, GmKind.Card, 0.92,
            enabled: notes || g.Notes.Trim().Length > 0);
        var cancel = ui.Button("Cancel", CloseModal, GmKind.Card, 0.92);
        var open = ui.Button("Open in browser", () => { CloseModal(); if (share.Url.Length > 0) MainWindow.OpenUri(share.Url); }, GmKind.Primary, 0.92);
        ShowModal("Share result · " + g.Name, content, [toggle, cancel, open], CloseModal, 1200, open);
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
        Toast(finish ? "Functional test saved. Review the evidence and suggested fixes." : "Test started. Play for a minute, then return here to finish.");
        Render(keepFocus: true);
        if (finish) ShowFunctionalTest(g);
    }

    void ShowFunctionalTest(Game g)
    {
        if (g.FunctionalTestText is not { Length: > 0 } text) return;
        var content = new StackPanel { Spacing = t.Px(16) };
        content.Children.Add(ui.P("These checks show what ran. Check the picture yourself; you choose the final result."));
        if (g.TestSuggestion is { } suggestion) content.Children.Add(ui.P("Suggested result: " + suggestion));
        content.Children.Add(new ScrollViewer { Content = ui.P(text, .82), MaxHeight = t.Px(t.Compact ? 260 : 440),
            HorizontalScrollMode = ScrollMode.Disabled }.With(s => { s.IsTabStop = true; ui.Focusable(s); }));
        var actions = new List<Button>();
        actions.Add(ui.Button("Done", CloseModal, GmKind.Card, .9));
        actions.Add(ui.Button("Bug Report", () => { CloseModal(); ChooseSupportReportGames([g]); }, GmKind.Card, .9));
        if (g.TestSuggestion is { } chosen)
            actions.Add(ui.Button("Use " + chosen, async () => { CloseModal(); await SaveNotesAsync(g, chosen, g.Notes, "Test result saved."); Render(keepFocus: true); }, GmKind.Primary, .9));
        ShowModal("Functional test · " + g.Name, content, actions, CloseModal, 1100);
    }

    // ---------- Settings › Recovery / System ----------

    IReadOnlyList<SettingsGroup> RecoveryGroups() =>
    [
        new("Cleanup", null,
        [ui.RowButton("Old NR files", null, async () =>
        {
            if (shell.Service.IsPreview) { Toast("Old NR file cleanup is disabled in preview mode."); return; }
            if (await RunReviewAsync("Remove old NR files", shell.Service.ReviewCleanupAsync, "No old NR files were found in your libraries.") is not null)
                await shell.ScanAsync();
        }, description: "Review legacy files before removal.", glyph: "")]),
    ];

    async Task AppStorageAsync()
    {
        if (shell.Service is not Services.EngineForgeService engine) { Toast("Storage usage is available in the installed app."); return; }
        AppStorage data;
        try { data = await engine.AppStorageAsync(); }
        catch (Exception error) when (error is InvalidOperationException or IOException or UnauthorizedAccessException)
        { ShowDone(false, "App storage", error.Message); return; }
        var content = new StackPanel { Spacing = t.Px(18) };
        content.Children.Add(ui.P("Restore backups, original game files and settings are kept."));
        if (data.Warning is { } warning) content.Children.Add(ui.P(warning));
        var rows = data.Categories.Where(c => c.Bytes > 0).Select(c => (UIElement)ui.PreferenceRow(c.Title, c.Detail,
            ui.Text(AppStorage.Format(c.Bytes), .85, t.Muted)));
        content.Children.Add(new ScrollViewer { Content = ui.Group(rows, t.Card), MaxHeight = t.Px(t.Compact ? 300 : 460), HorizontalScrollMode = ScrollMode.Disabled });
        var back = ui.Button("Back", CloseModal, GmKind.Card, .92);
        var review = ui.Button("Review cleanup", async () =>
        {
            CloseModal();
            await RunReviewAsync("Clear unused downloads", engine.ReviewStorageCleanupAsync);
        }, GmKind.Primary, .92, enabled: data.Warning is null && data.DownloadBytes > 0);
        ShowModal("App storage · " + AppStorage.Format(data.Bytes), content, [back, review], CloseModal, 1100, back);
    }

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

    async Task CheckForUpdatesAsync() => await shell.CheckForUpdatesAsync();

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
