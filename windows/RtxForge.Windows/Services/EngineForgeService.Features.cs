using System.Text.Json.Nodes;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>
/// The engine features beyond install / restore / update, over windows/engine-host/win_features.py:
/// artwork and Steam sync, SteamGridDB, recovery, notes and reports, tools, DLSS restore,
/// packages and application updates. Writes come back as an EngineReview first.
/// </summary>
public sealed partial class EngineForgeService
{
    static string? S(JsonNode? node, string key) => node?[key] is JsonValue v && v.TryGetValue<string>(out var s) && s.Length > 0 ? s : null;
    static bool B(JsonNode? node, string key) => node?[key] is JsonValue v && v.TryGetValue<bool>(out var b) && b;
    static int I(JsonNode? node, string key) => node?[key] is JsonValue v && v.TryGetValue<int>(out var n) ? n : 0;
    static long L(JsonNode? node, string key) => node?[key] is JsonValue v && v.TryGetValue<long>(out var n) ? n : 0;
    static IEnumerable<JsonObject> Objects(JsonNode? node) => (node as JsonArray ?? []).OfType<JsonObject>();
    static string[] Strings(JsonNode? node) => (node as JsonArray ?? []).Select(n => n?.ToString() ?? "").ToArray();

    /// <summary>The scan row for the engine, plus the artwork rtxForge currently shows (local files only).</summary>
    static JsonObject Row(Game game)
    {
        var row = (JsonObject?)game.EngineRow?.DeepClone() ?? new JsonObject { ["name"] = game.Name, ["game"] = game.Id };
        var shown = new JsonObject();
        foreach (var (role, path) in new[] { ("poster", game.PosterPath), ("capsule", game.CapsulePath), ("hero", game.HeroPath) })
            if (path is not null && File.Exists(path)) shown[role] = path;
        row["displayed"] = shown;
        return row;
    }

    static JsonArray Rows(IEnumerable<Game> games) => new(games.Where(g => g.EngineRow is not null).Select(g => (JsonNode)Row(g)).ToArray());

    static EngineReview ToReview(JsonNode? r)
    {
        static ReviewItem Item(JsonObject i) => new(S(i, "title") ?? "", S(i, "detail") ?? "", S(i, "badge") ?? "", S(i, "game"), S(i, "details"));
        return new EngineReview(S(r, "token") ?? "", S(r, "kind") ?? "", S(r, "title") ?? "", S(r, "summary") ?? "", S(r, "action") ?? "Apply",
            Objects(r?["items"]).Select(Item).ToList(), Objects(r?["blocked"]).Select(Item).ToList(), S(r, "trust"), S(r, "note"))
            { Skipped = Objects(r?["skipped"]).Select(Item).ToList() };
    }

    static PrepareProgress Phase(JsonObject message) => new(message["label"]?.ToString() ?? "", message["game"]?.ToString(),
        I(message, "current"), I(message, "total"));

    // ---------- reviews ----------

    public async Task<EngineResult> RunReviewAsync(EngineReview review, IProgress<PrepareProgress>? progress = null)
    {
        var result = await CallAsync("run", new { token = review.Token }, m => progress?.Report(Phase(m)));
        return new EngineResult(S(result, "message") ?? "Done.", S(result, "path"), Strings(result?["errors"]));
    }

    public void DiscardReview(EngineReview review) => _ = CallAsync("discard", new { token = review.Token });

    // ---------- media ----------

    public async Task<IReadOnlyList<GameMedia>> LoadMediaAsync(IReadOnlyList<Game> games, bool refresh, IProgress<PrepareProgress>? progress = null)
    {
        var settings = new JsonObject
        {
            ["online_art"] = Settings.OnlineArt, ["steam_metadata"] = Settings.SteamMetadata, ["network_timeout"] = Settings.NetworkTimeout,
        };
        var result = await CallAsync("media", new JsonObject { ["rows"] = Rows(games), ["refresh"] = refresh, ["settings"] = settings },
            m => progress?.Report(Phase(m)));
        return Objects(result).Select(m =>
        {
            string? Local(string key) => S(m, key) is { } p && File.Exists(p) ? p : null;
            var credits = new Dictionary<string, string>();
            foreach (var (role, key) in new[] { ("poster", "art_credit"), ("capsule", "capsule_credit"), ("hero", "hero_credit") })
                if (S(m, key) is { } credit) credits[role] = credit;
            return new GameMedia(S(m, "game") ?? "", Local("poster"), Local("capsule"), Local("hero"), credits,
                S(m, "description"), S(m, "developers"), S(m, "release"));
        }).ToList();
    }

    // ---------- Steam artwork ----------

    public async Task<IReadOnlyList<SteamArtworkProfile>> SteamArtworkProfilesAsync() =>
        Objects(await CallAsync("art_profiles")).Select(p => new SteamArtworkProfile(S(p, "root") ?? "", S(p, "userid") ?? "", B(p, "selected"))).ToList();

    public Task SelectSteamArtworkProfileAsync(SteamArtworkProfile profile) =>
        CallAsync("art_set_profile", new { root = profile.Root, userid = profile.UserId });

    public Task StoreArtworkAsync(Game game, string role, string path, string? credit = null) =>
        CallAsync("art_store", new JsonObject { ["row"] = Row(game), ["role"] = role, ["path"] = path, ["credit"] = credit ?? "Your artwork" });

    public Task ResetArtworkAsync(Game game, string role) => CallAsync("art_reset", new JsonObject { ["row"] = Row(game), ["role"] = role });

    public async Task<EngineReview> ReviewArtworkSyncAsync(IReadOnlyList<Game> games, bool single) =>
        ToReview(await CallAsync("art_sync_review", new JsonObject { ["rows"] = Rows(games), ["single"] = single, ["refresh"] = single }));

    // ---------- SteamGridDB ----------

    public async Task<SteamGridStatus> SteamGridStatusAsync()
    {
        var r = await CallAsync("sgdb_status");
        Dictionary<string, string[]> Map(string key) =>
            (r?[key] as JsonObject ?? []).ToDictionary(p => p.Key, p => Strings(p.Value));
        return new SteamGridStatus(B(r, "connected"), S(r, "problem"), Map("styles"), Map("dimensions"), Strings(r?["mimes"]));
    }

    public Task SteamGridConnectAsync(string key) => CallAsync("sgdb_connect", new { key });

    public async Task<bool> SteamGridDisconnectAsync() => B(await CallAsync("sgdb_disconnect"), "external");

    public async Task<IReadOnlyList<SteamGridGame>> SteamGridSearchAsync(string term) =>
        Objects(await CallAsync("sgdb_search", new { term })).Select(m => new SteamGridGame(L(m, "id"), S(m, "name") ?? "Unknown game")).ToList();

    public async Task<IReadOnlyList<SteamGridAsset>> SteamGridArtworkAsync(long gameId, string role, int page, string style, string dimensions, string mime, bool humor) =>
        Objects(await CallAsync("sgdb_artwork", new { game_id = gameId, role, page, style, dimensions, mime, humor }))
            .Select(a => new SteamGridAsset(L(a, "id"), S(a, "url") ?? "", S(a, "thumb"), I(a, "width"), I(a, "height"), S(a, "author") ?? "Community artist", S(a, "mime")))
            .ToList();

    public async Task<string> SteamGridDownloadAsync(SteamGridAsset asset) =>
        S(await CallAsync("sgdb_download", new { asset = new { url = asset.Url } }), "path") ?? throw new EngineException("SteamGridDB returned no image.");

    // ---------- recovery ----------

    public async Task<IReadOnlyList<RecoveryRecord>> RecoveriesAsync() =>
        Objects(await CallAsync("recoveries")).Select(r => new RecoveryRecord(S(r, "kind") ?? "", S(r, "path") ?? "", S(r, "name") ?? "", S(r, "detail") ?? "")).ToList();

    public async Task<EngineReview> ReviewRecoveryAsync(RecoveryRecord record) =>
        ToReview(await CallAsync("recovery_review", new { record = new { kind = record.Kind, path = record.Path, name = record.Name, detail = record.Detail } }));

    public async Task<EngineReview> ReviewCleanupAsync() => ToReview(await CallAsync("cleanup_review"));

    // ---------- notes, tests, reports ----------
    readonly System.Collections.Concurrent.ConcurrentDictionary<string, CancellationTokenSource> testHelperPolls = new();

    void MonitorTestHelper(Game game)
    {
        if (game.EngineRow?["test_record"]?["active"]?["id"]?.ToString() is not { } session) return;
        var cancellation = new CancellationTokenSource();
        if (!testHelperPolls.TryAdd(game.Id, cancellation)) { cancellation.Dispose(); return; }
        _ = PollTestHelperAsync(game, session, cancellation);
    }

    async Task PollTestHelperAsync(Game game, string session, CancellationTokenSource cancellation)
    {
        try
        {
            while (!cancellation.IsCancellationRequested)
            {
                var helper = await TestHelperAsync();
                await CallAsync("test_helper", new JsonObject { ["row"] = Row(game), ["session"] = session, ["helper"] = helper }, cancel: cancellation.Token);
                await Task.Delay(1000, cancellation.Token);
            }
        }
        catch (Exception error) when (error is OperationCanceledException or InvalidOperationException or IOException or ObjectDisposedException) { }
        finally { testHelperPolls.TryRemove(game.Id, out _); cancellation.Dispose(); }
    }

    void Apply(Game game, JsonNode? record)
    {
        game.TestStatus = S(record, "status") ?? "Untested";
        game.Notes = record?["notes"]?.ToString() ?? "";
        game.TestActive = record?["active"] is JsonObject;
        if (game.EngineRow is not null) game.EngineRow["test_record"] = record?.DeepClone();
    }

    public async Task SaveNotesAsync(Game game, string status, string notes) =>
        Apply(game, await CallAsync("notes_save", new { game = game.Id, status, notes }));

    async Task<JsonObject> TestHelperAsync()
    {
        try
        {
            var text = await OverlayHelper.CommandAsync("status", start: false);
            var helper = text is null ? new JsonObject() : JsonNode.Parse(text) as JsonObject ?? new JsonObject();
            helper["running"] = helper["helper_pid"]?.GetValue<int>() > 0;
            return helper;
        }
        catch (Exception error) when (error is IOException or System.Text.Json.JsonException or InvalidOperationException)
        { return new JsonObject { ["running"] = false, ["problem"] = error.Message }; }
    }

    public async Task StartTestAsync(Game game)
    {
        var valid = OverlayShortcut.TryParse(Settings.PanelHotkey, out _, out var binding, out _) && binding.Key != 0;
        Apply(game, await CallAsync("test_start", new JsonObject { ["row"] = Row(game), ["helper"] = await TestHelperAsync(),
            ["shortcut_ok"] = valid, ["shortcut"] = Settings.PanelHotkey }));
        MonitorTestHelper(game);
    }

    public async Task FinishTestAsync(Game game)
    {
        Apply(game, await CallAsync("test_finish", new JsonObject { ["row"] = Row(game), ["helper"] = await TestHelperAsync() }));
        if (testHelperPolls.TryGetValue(game.Id, out var cancellation)) cancellation.Cancel();
    }

    public async Task<BetaReportDraft> DraftReportsAsync(IReadOnlyList<Game> games, string? format, string channel)
    {
        var r = await CallAsync("report_draft", new JsonObject { ["rows"] = Rows(games), ["format"] = format, ["channel"] = channel });
        static IReadOnlyDictionary<string, string> Map(JsonNode? node) =>
            (node as JsonObject)?.ToDictionary(p => p.Key, p => p.Value?.ToString() ?? "") ?? new Dictionary<string, string>();
        var reports = Objects(r?["reports"]).Select(o => new BetaReport(S(o, "id") ?? "", S(o, "name") ?? "",
            Map(o["fields"]), Map(o["sources"]), Strings(o["problems"]))).ToList();
        var fields = Objects(r?["fields"]).Select(o => new ReportField(S(o, "id") ?? "", S(o, "label") ?? "",
            Strings(o["choices"]), B(o, "required"), I(o, "max"))).ToList();
        return new BetaReportDraft(reports, fields);
    }

    public async Task<EngineReview> PreviewReportAsync(IReadOnlyList<string> ids, IReadOnlyDictionary<string, Dictionary<string, string>> edits,
        bool logs, bool notes, string documents)
    {
        var changes = new JsonObject();
        foreach (var (id, fields) in edits)
            changes[id] = new JsonObject(fields.Select(f => KeyValuePair.Create(f.Key, (JsonNode?)f.Value)));
        return ToReview(await CallAsync("report_preview", new JsonObject { ["ids"] = new JsonArray(ids.Select(i => (JsonNode)i).ToArray()),
            ["edits"] = changes, ["logs"] = logs, ["notes"] = notes, ["documents"] = documents }));
    }

    public async Task<BetaReportLinks> ReportLinksAsync(IReadOnlyList<string> ids, string? issue, string? archive)
    {
        var r = await CallAsync("report_links", new JsonObject { ["ids"] = new JsonArray(ids.Select(i => (JsonNode)i).ToArray()),
            ["issue"] = issue, ["archive"] = archive });
        var links = Objects(r?["links"]).Select(o => new BetaReportLink(S(o, "name") ?? "", S(o, "url") ?? "", B(o, "complete"), S(o, "text") ?? "")).ToList();
        return new BetaReportLinks(links, S(r?["issue"], "url"), I(r?["issue"], "number"), S(r, "comment") ?? "");
    }

    static JsonObject ReportEdits(IReadOnlyDictionary<string, string> edits) =>
        new(edits.Select(f => KeyValuePair.Create(f.Key, (JsonNode?)f.Value)));

    public async Task<ReportOutline> OutlineReportAsync(string id, IReadOnlyDictionary<string, string> edits, bool logs)
    {
        var r = await CallAsync("report_outline", new JsonObject { ["id"] = id, ["edits"] = ReportEdits(edits), ["logs"] = logs });
        return new ReportOutline(S(r, "title") ?? "", S(r, "text") ?? "",
            Objects(r?["logs"]).Select(o => new ReportLog(S(o, "name") ?? "", S(o, "detail") ?? "", S(o, "text") ?? "")).ToList(),
            Objects(r?["skipped"]).Select(o => $"{S(o, "name")} · {S(o, "reason")}").ToList());
    }

    public async Task<ReportSent> SendReportAsync(string id, IReadOnlyDictionary<string, string> edits, bool logs, string documents)
    {
        var r = await CallAsync("report_send", new JsonObject { ["id"] = id, ["edits"] = ReportEdits(edits), ["logs"] = logs, ["documents"] = documents });
        return new ReportSent(B(r, "sent"), I(r, "number"), S(r, "url"), S(r, "path") ?? "", S(r, "error"));
    }

    public async Task SetTryAnywayAsync(Game game, bool on) =>
        Apply(game, await CallAsync("try_anyway", new { game = game.Id, on, reason = game.BlockedReason ?? "" }));

    public async Task<CompatShare> CompatShareAsync(Game game, string package, bool notes)
    {
        var r = await CallAsync("compat_share", new JsonObject { ["row"] = Row(game), ["package"] = package, ["notes"] = notes });
        return new CompatShare(S(r, "title") ?? "", S(r, "body") ?? "", S(r, "url") ?? "");
    }

    // ---------- tools ----------

    public async Task<NrDiagnosis> DiagnoseAsync(Game game)
    {
        var report = await CallAsync("diagnose", new JsonObject { ["row"] = Row(game) });
        return new NrDiagnosis(Strings(report?["observations"]), S(report, "visual_result") ?? "Not established",
            report?.ToJsonString(new System.Text.Json.JsonSerializerOptions { WriteIndented = true }) ?? "", Strings(report?["warnings"]));
    }

    public async Task<IReadOnlyList<ExtraRecord>> ExtraRecordsAsync(Game game) =>
        Objects(await CallAsync("extras_list", new JsonObject { ["row"] = Row(game) }))
            .Select(r => new ExtraRecord(S(r, "path") ?? "", S(r, "name") ?? "", S(r, "kind") ?? "", S(r, "title") ?? "", S(r, "date") ?? "")).ToList();

    public async Task<EngineReview> ReviewExtraAsync(Game game, string path, string kind) =>
        ToReview(await CallAsync("extra_review", new JsonObject { ["row"] = Row(game), ["path"] = path, ["kind"] = kind }));

    public async Task<EngineReview> ReviewExtraRestoreAsync(ExtraRecord record) =>
        ToReview(await CallAsync("extra_restore_review", new { path = record.Path }));

    // ---------- DLSS files ----------

    public async Task<DlssInventory> DlssInventoryAsync(Game game)
    {
        var r = await CallAsync("dlss_inventory", new JsonObject { ["row"] = Row(game) });
        var files = Objects(r?["files"]).Select(f => new DlssFile(S(f, "title") ?? "", S(f, "path") ?? "", S(f, "current") ?? "Unknown", S(f, "provenance") ?? "")).ToList();
        return new DlssInventory(files, S(r, "blocked") ?? "", Objects(r?["backups"]).Select(b => S(b, "date")).FirstOrDefault());
    }

    public async Task<EngineReview> ReviewDlssRestoreAsync(Game game) =>
        ToReview(await CallAsync("dlss_restore_review", new JsonObject { ["row"] = Row(game) }));

    // ---------- packages ----------

    public async Task<PackageCatalog> PackagesAsync()
    {
        var r = await CallAsync("packages");
        var status = $"{S(r?["host"], "gpu") ?? "System"} · {S(r?["host"], "reason") ?? ""}";
        var packages = Objects(r?["catalog"]).Select(p => new PackageOption(S(p, "id") ?? "", S(p, "name") ?? "", S(p, "version") ?? "",
            S(p, "summary") ?? "", B(p, "available"), S(p, "reason") ?? "", B(p, "recommended"), S(p, "url") ?? "",
            (p["verified"] as JsonArray)?.Select(os => os?.ToString() ?? "").Where(os => os.Length > 0).ToArray(),
            (p["mfg_versions"] as JsonObject)?.ToDictionary(v => v.Key, v => v.Value?.ToString() ?? ""), Strings(p["graphics_apis"]),
            Strings(p["confirmed"]))).ToList();
        var community = Objects(r?["community"]).Select(c => new CommunitySource(S(c, "name") ?? "", S(c, "url") ?? "", S(c, "note") ?? "")).ToList();
        return new PackageCatalog(status, packages, community, S(r?["custom"], "name"));
    }

    public async Task<FeederStorage> FeederStorageAsync(string? source = null, string? backups = null, bool legacy = false)
    {
        var r = await CallAsync("feeder_storage", new JsonObject { ["source"] = source, ["backups"] = backups, ["legacy"] = legacy });
        var kept = r?["stack"] as JsonObject;
        return new FeederStorage(S(kept, "recipe"), S(kept, "imported_from"), S(kept, "nr_version"), I(r, "backups"), B(r, "legacy_ready"));
    }

    public async Task<PackageInspection> InspectPackageAsync(string path)
    {
        var r = await CallAsync("package_inspect", new { path });
        return new PackageInspection(S(r, "token") ?? "", S(r, "name") ?? "", S(r, "family") ?? "unknown", S(r, "confidence") ?? "",
            I(r, "file_count"), L(r, "expanded_bytes"),
            Objects(r?["parameters"]).Select(p => new PackageParameter(S(p, "key") ?? "", S(p, "label") ?? "", p["value"]?.ToString() ?? "", S(p, "origin") ?? "")).ToList(),
            Strings(r?["warnings"]), Objects(r?["instructions"]).Select(i => (S(i, "path") ?? "", S(i, "text") ?? "")).ToList(), B(r, "deployable"));
    }

    public async Task<PackageChoice> UseCustomPackageAsync(PackageInspection inspection, IReadOnlyDictionary<string, string> values, bool trusted, string notes)
    {
        var fields = new JsonObject();
        foreach (var (key, value) in values) fields[key] = value;
        var r = await CallAsync("package_use", new JsonObject { ["token"] = inspection.Token, ["values"] = fields, ["trusted"] = trusted, ["notes"] = notes });
        double D(string key, double fallback) => r?[key] is JsonValue v && v.TryGetValue<double>(out var d) ? d : fallback;
        return new PackageChoice(S(r, "name") ?? inspection.Name, new Tuning(D("nr_strength", 2.0), D("sharpening_strength", 0.5), S(r, "mfg_multiplier") ?? "auto"));
    }

    // ---------- updates ----------

    public async Task<EngineReview> CheckForUpdateAsync() =>
        ToReview(await CallAsync("update_check", new { version = MainWindow.AppVersion }));
}
