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

    void Apply(Game game, JsonNode? record)
    {
        game.TestStatus = S(record, "status") ?? "Untested";
        game.Notes = record?["notes"]?.ToString() ?? "";
        game.TestActive = record?["active"] is JsonObject;
        if (game.EngineRow is not null) game.EngineRow["test_record"] = record?.DeepClone();
    }

    public async Task SaveNotesAsync(Game game, string status, string notes) =>
        Apply(game, await CallAsync("notes_save", new { game = game.Id, status, notes }));

    public async Task StartTestAsync(Game game) => Apply(game, await CallAsync("test_start", new JsonObject { ["row"] = Row(game) }));

    public async Task FinishTestAsync(Game game) => Apply(game, await CallAsync("test_finish", new JsonObject { ["row"] = Row(game) }));

    public async Task<EngineReview> PreviewReportAsync(IReadOnlyList<Game> games, bool logs, bool notes) =>
        ToReview(await CallAsync("report_preview", new JsonObject { ["rows"] = Rows(games), ["logs"] = logs, ["notes"] = notes }));

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
            S(p, "summary") ?? "", B(p, "available"), S(p, "reason") ?? "", B(p, "recommended"), S(p, "url") ?? "")).ToList();
        var community = Objects(r?["community"]).Select(c => new CommunitySource(S(c, "name") ?? "", S(c, "url") ?? "", S(c, "note") ?? "")).ToList();
        return new PackageCatalog(status, packages, community, S(r?["custom"], "name"));
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
