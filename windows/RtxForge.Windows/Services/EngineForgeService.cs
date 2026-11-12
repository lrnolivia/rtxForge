using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Win32;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>
/// The real engine: the shared Python engine (scripts/desktop_service.py over
/// engine/rtxengine.py) hosted by windows/engine-host/rtxforge_win_host.py.
/// One long-lived process; JSON lines in both directions. A prepared review
/// lives in the host and is executed by token, exactly as the Linux desktop
/// executes the in-memory review it showed.
/// </summary>
public sealed partial class EngineForgeService : IForgeService, IDisposable
{
    readonly Process process;
    readonly ConcurrentDictionary<int, Request> pending = new();
    readonly SemaphoreSlim writeLock = new(1, 1);
    int nextId;
    bool appUpdateHandedOff;

    sealed record Request(TaskCompletionSource<JsonNode?> Done, Action<JsonObject>? Progress);

    readonly bool readOnly;
    public bool IsPreview => readOnly;
    public ForgeSettings Settings { get; } = ForgeSettings.Load();
    public JsonObject? OverlayRefreshResult { get; private set; }
    public event Action<JsonObject>? OverlayRefreshChanged;
    /// <summary>What rtxForge is doing in the background (scripts/activity.py), "" when idle.</summary>
    public string Activity { get; private set; } = "";
    public event Action<string>? ActivityChanged;
    public string EngineRoot { get; }
    public bool SplitRenderEnabled { get; private set; }
    static string SnapshotPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "state", "library-snapshot.json");
    // Each build keys its own snapshot, so an update never shows the previous build's verdicts.
    static readonly string Build = typeof(EngineForgeService).Assembly.ManifestModule.ModuleVersionId.ToString("N");
    string SnapshotKey() => LibrarySnapshot.Key(Settings.RuntimeProvider + "|" + Build + "|" + Settings.ExecutableSelectionKey, Settings.GameFolders, Settings.LibraryFolders);
    public IReadOnlyList<Game> CachedLibrary()
    {
        try { return LibraryGames(LibrarySnapshot.Read(SnapshotPath, SnapshotKey())); }
        catch (Exception error) when (error is InvalidOperationException or FormatException or JsonException or ArgumentException) { return []; }
    }

    EngineForgeService(Process process, string root, bool readOnly = false)
    {
        this.process = process;
        EngineRoot = root;
        this.readOnly = readOnly;
    }

    // ---------- startup ----------

    /// <summary>Starts the host, or returns null (with the reason) when Python or the engine is unavailable.</summary>
    public static async Task<(EngineForgeService? Service, string? Problem)> TryStartAsync(string logName = "engine.log", bool readOnly = false)
    {
        var root = FindEngineRoot();
        if (root is null) return (null, "The rtxForge engine files were not found next to the app.");
        var python = FindPython();
        if (python is null) return (null, "Python 3 was not found. The packaged build includes it; for a dev build install Python 3.11 or newer.");

        var info = new ProcessStartInfo(python.Value.Exe)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            StandardInputEncoding = new UTF8Encoding(false),
        };
        foreach (var arg in python.Value.Args) info.ArgumentList.Add(arg);
        foreach (var arg in new[] { "-I", "-B", "-u", Path.Combine(root, "windows", "engine-host", "rtxforge_win_host.py") })
            info.ArgumentList.Add(arg);
        info.Environment["RTXFORGE_ROOT"] = root;
        // Add rtxForge to Steam points the shortcut at this executable.
        info.Environment["RTXFORGE_APP_EXE"] = Environment.ProcessPath ?? Path.Combine(AppContext.BaseDirectory, "rtxForge.exe");
        info.Environment["PYTHONIOENCODING"] = "utf-8";
        info.Environment["RTXFORGE_OVERLAY_HOST"] = logName == "overlay-engine.log" ? "1" : "0";
        info.Environment["RTXFORGE_READ_ONLY"] = readOnly ? "1" : "0";

        Process process;
        try { process = Process.Start(info)!; }
        catch (Exception error) when (error is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            return (null, "Python could not start: " + error.Message);
        }

        var service = new EngineForgeService(process, root, readOnly);
        var ready = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        _ = Task.Run(() => service.ReadLoop(ready));
        _ = Task.Run(() => service.DrainErrors(logName));
        var first = await Task.WhenAny(ready.Task, Task.Delay(TimeSpan.FromSeconds(30)));
        if (first != ready.Task)
        {
            service.Dispose();
            return (null, "The rtxForge engine did not start in time.");
        }
        if (ready.Task.IsCompletedSuccessfully)
            service.SplitRenderEnabled = ready.Task.Result["split_render_enabled"]?.GetValue<bool>() == true;
        return (service, null);
    }

    static string? FindEngineRoot()
    {
        // Packaged: the publish step copies the engine to <app>\engine.
        var bundled = Path.Combine(AppContext.BaseDirectory, "engine");
        if (IsEngineRoot(bundled)) return bundled;
        // Dev build: the repository this binary was built from.
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
            if (IsEngineRoot(dir.FullName)) return dir.FullName;
        return null;
    }

    static bool IsEngineRoot(string path) =>
        File.Exists(Path.Combine(path, "windows", "engine-host", "rtxforge_win_host.py")) &&
        File.Exists(Path.Combine(path, "engine", "rtxengine.py")) &&
        File.Exists(Path.Combine(path, "provider.json"));

    static (string Exe, string[] Args)? FindPython()
    {
        var bundled = Path.Combine(AppContext.BaseDirectory, "python", "python.exe");
        if (File.Exists(bundled)) return (bundled, []);
        foreach (var (exe, args) in new (string, string[])[] { ("py.exe", ["-3"]), ("python.exe", []) })
            foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
            {
                var candidate = Path.Combine(dir.Trim(), exe);
                if (File.Exists(candidate)) return (candidate, args);
            }
        return null;
    }

    // ---------- protocol ----------

    async Task ReadLoop(TaskCompletionSource<JsonObject> ready)
    {
        try
        {
            while (await process.StandardOutput.ReadLineAsync() is { } line)
            {
                if (JsonNode.Parse(line) is not JsonObject message) continue;
                if (message["event"]?.GetValue<string>() is { } kind)
                {
                    if (kind == "ready") ready.TrySetResult(message);
                    else if (kind == "overlay-refresh")
                    {
                        OverlayRefreshResult = (JsonObject)(message["result"]?.DeepClone() ?? new JsonObject { ["status"] = "pending", ["error"] = message["error"]?.DeepClone() });
                        OverlayRefreshChanged?.Invoke((JsonObject)OverlayRefreshResult.DeepClone());
                    }
                    else if (kind == "activity")
                    {
                        Activity = message["text"]?.ToString() ?? "";
                        ActivityChanged?.Invoke(Activity);
                    }
                    else if (kind == "progress" && message["id"]?.GetValue<int>() is { } pid && pending.TryGetValue(pid, out var running))
                        running.Progress?.Invoke(message);
                    continue;
                }
                if (message["id"]?.GetValue<int>() is not { } id || !pending.TryRemove(id, out var request)) continue;
                if (message["error"]?.GetValue<string>() is { } error) request.Done.TrySetException(new EngineException(error));
                else request.Done.TrySetResult(message["result"]?.DeepClone());
            }
        }
        catch (Exception error) when (error is IOException or JsonException or ObjectDisposedException) { }
        foreach (var request in pending.Values) request.Done.TrySetException(new EngineException("The rtxForge engine stopped."));
        pending.Clear();
        ready.TrySetCanceled();
    }

    async Task DrainErrors(string logName)
    {
        // Engine diagnostics go to %LOCALAPPDATA%\rtxForge\engine.log for support reports.
        var log = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", logName);
        Directory.CreateDirectory(Path.GetDirectoryName(log)!);
        try
        {
            await using var writer = new StreamWriter(log, append: false, Encoding.UTF8) { AutoFlush = true };
            while (await process.StandardError.ReadLineAsync() is { } line) await writer.WriteLineAsync(line);
        }
        catch (Exception error) when (error is IOException or ObjectDisposedException or UnauthorizedAccessException) { }
    }

    async Task<JsonNode?> CallAsync(string method, object? parameters = null, Action<JsonObject>? progress = null, CancellationToken cancel = default)
    {
        var id = Interlocked.Increment(ref nextId);
        var request = new Request(new TaskCompletionSource<JsonNode?>(TaskCreationOptions.RunContinuationsAsynchronously), progress);
        pending[id] = request;
        var line = JsonSerializer.Serialize(new { id, method, @params = parameters ?? new { } });
        await writeLock.WaitAsync(cancel);
        try
        {
            await process.StandardInput.WriteLineAsync(line);
            await process.StandardInput.FlushAsync();
        }
        finally { writeLock.Release(); }
        return await request.Done.Task;
    }

    // ---------- IForgeService ----------

    public async Task<HardwareInfo> DetectHardwareAsync(CancellationToken cancel = default)
    {
        var h = await CallAsync("hardware", cancel: cancel);
        string S(string key) => h?[key]?.ToString() ?? "";
        return new HardwareInfo(S("gpu"), S("driver"), S("vram"), S("cpu"), S("architecture"),
            h?["ready"]?.GetValue<bool>() == true, S("reason"));
    }

    public async Task<IReadOnlyList<Game>> ScanAsync(CancellationToken cancel = default)
    {
        var key = SnapshotKey();
        // The library serves every mode; the installation review checks native FG for NR + MFG.
        var rows = await CallAsync("scan", new { folders = Settings.GameFolders, library_folders = Settings.LibraryFolders, runtime_provider = Settings.RuntimeProvider, game_executables = Settings.GameExecutables }, cancel: cancel) as JsonArray ?? [];
        LibrarySnapshot.Write(SnapshotPath, key, rows);
        var games = LibraryGames(rows);
        if (!readOnly) foreach (var game in games.Where(g => g.TestActive)) MonitorTestHelper(game);
        return games;
    }

    public async Task<string> ValidateExecutableAsync(Game game, string? path)
    {
        var result = await CallAsync("validate_executable", new { row = Row(game), path });
        return result?["exe"]?.GetValue<string>() ?? throw new EngineException("The game EXE could not be verified.");
    }

    IReadOnlyList<Game> LibraryGames(JsonArray rows)
    {
        var art = new SteamArtwork(Settings.OnlineArt);
        return LibraryLocations.Visible(rows.OfType<JsonObject>().Select(row => ToGame(OwnPackage(row), art)), Settings.RemovedGames);
    }

    /// <summary>A game with its own package shows that package's verdict (the scan keeps both).</summary>
    JsonObject OwnPackage(JsonObject row)
    {
        if (row["game"]?.ToString() is not { } id || !Settings.GamePackages.TryGetValue(id, out var package) || package == Settings.RuntimeProvider
            || row[package == "skynizz" ? "skynizz_blocked" : "package_blocked"] is not JsonValue verdict) return row;
        row["blocked"] = verdict.DeepClone();
        return row;
    }

    static Game ToGame(JsonObject row, SteamArtwork art)
    {
        string? S(string key) => row[key] is JsonValue v && v.TryGetValue<string>(out var s) && s.Length > 0 ? s : null;
        double? D(string key) => row[key] is JsonValue v && v.TryGetValue<double>(out var d) ? d : null;
        string? Art(string role) => row["art"] is JsonObject found && found[role] is JsonValue v && v.TryGetValue<string>(out var p) && File.Exists(p) ? p : null;
        var source = S("source") ?? "Folder";
        var appid = S("appid") ?? S("metadata_appid");
        var multiplier = row["mfg_multiplier"] switch
        {
            JsonValue v when v.TryGetValue<int>(out var n) => n.ToString(),
            JsonValue v when v.TryGetValue<string>(out var s) => s,
            _ => null,
        };
        return new Game
        {
            Id = S("game")!,
            Name = S("name") ?? Path.GetFileName(S("game")) ?? "",
            Library = source,
            Location = S("game") ?? "",
            Installed = row["installed"]?.GetValue<bool>() == true,
            Blocked = S("blocked") is not null,
            BlockedReason = S("blocked"),
            MetadataSource = appid is null ? null : "Steam",
            AppId = appid,
            Profile = S("profile"),
            RuntimeProvider = S("runtime_provider"),
            InstalledOn = S("installed_on") is "linux" or "windows" ? S("installed_on") : null,
            InstalledOses = CrossOs.Read(row["installed_oses"]),
            NrStrength = D("nr_strength"),
            SharpeningStrength = D("sharpening_strength"),
            MfgMultiplier = multiplier,
            FeatureControls = row["feature_controls"] is JsonObject controls ? (JsonObject)controls.DeepClone() : null,
            // Your Steam grid picks (Steam and Non-Steam) and Steam's cache, as Linux; then the store CDN.
            PosterPath = Art("poster") ?? art.Poster(appid),
            CapsulePath = Art("capsule") ?? art.Capsule(appid),
            HeroPath = Art("hero") ?? art.Hero(appid),
            ArtCredits = Credits(row["art"] as JsonObject),
            Notes = row["test_record"]?["notes"]?.ToString() ?? "",
            TestStatus = row["test_record"]?["status"]?.ToString() ?? "Untested",
            TestActive = row["test_record"]?["active"] is JsonObject,
            EngineRow = row,
        };
    }

    /// <summary>LibraryMedia credit keys (art_credit, capsule_credit, hero_credit) by role.</summary>
    static Dictionary<string, string> Credits(JsonObject? art)
    {
        var credits = new Dictionary<string, string>();
        if (art is null) return credits;
        foreach (var (role, key) in new[] { ("poster", "art_credit"), ("capsule", "capsule_credit"), ("hero", "hero_credit") })
            if (art[key]?.ToString() is { Length: > 0 } credit) credits[role] = credit;
        return credits;
    }

    public async Task<OperationReview> PrepareAsync(string operation, IReadOnlyList<Game> targets, Tuning tuning, string mode,
        IProgress<PrepareProgress>? progress = null, CancellationToken cancel = default)
    {
        var ordered = targets.OrderBy(g => g.Name, StringComparer.CurrentCultureIgnoreCase).ToArray();
        var counted = progress is null ? null : new OneCount(progress, targets.Count);
        return operation is "install" or "update" or "repair" or "uninstall" or "reset" or "apply"
            ? await PlanAsync(operation, ordered, tuning, mode, counted, cancel)
            : await PrepareOneAsync(operation, ordered, tuning, mode, counted, cancel);
    }

    /// <summary>
    /// Checking progress as one pass over the selection: each package's route and each
    /// supported-features check report into one count, and every game counts once.
    /// </summary>
    sealed class OneCount(IProgress<PrepareProgress> target, int total) : IProgress<PrepareProgress>
    {
        readonly HashSet<string> seen = new(StringComparer.OrdinalIgnoreCase);
        public void Report(PrepareProgress step)
        {
            if (step.Game is null && step.Total == 0) { target.Report(step); return; }
            int count;
            lock (seen) { if (step.Game is { Length: > 0 } game && step.Checked > 0) seen.Add(game); count = seen.Count; }
            target.Report(new PrepareProgress(string.IsNullOrWhiteSpace(step.Label) ? "Preparing game files" : step.Label, step.Game, count, total));
        }
    }

    JsonObject PrepareSettings(string provider, Tuning tuning, string mode, bool supportedSubset)
    {
        var settings = new JsonObject
        {
            ["runtime_provider"] = provider,
            ["nr_on_launch"] = tuning.NrOnLaunch ?? Settings.NrOnLaunch,
            ["prefer_bundled_nr_only"] = supportedSubset && mode == "nr-only",
            ["manage_dlss_files"] = Settings.ManageDlssFiles,
            ["nr_runtime"] = Settings.NrRuntime,
            ["skynizz_version"] = Settings.SkynizzVersion,
            ["mfg_provider"] = Settings.MfgProvider,
            ["nr_preset"] = Settings.NrPreset,
            ["feeder_source"] = Settings.FeederSource,
            ["feeder_backups"] = Settings.FeederBackups,
            ["borderless_4k"] = Settings.Borderless4K,
            ["nr_strength"] = Math.Round(tuning.NrStrength, 1),
            ["sharpening_strength"] = Math.Round(tuning.SharpeningStrength, 1),
            ["mfg_multiplier"] = tuning.MfgMultiplier == "auto" ? "auto" : int.Parse(tuning.MfgMultiplier),
            ["feature_controls"] = tuning.FeatureControls?.DeepClone(),
        };
        settings["game_executables"] = JsonSerializer.SerializeToNode(Settings.GameExecutables);
        foreach (var item in ForgeSettings.Load().OverlayReviewOptions()) settings[item.Key] = item.Value?.DeepClone();
        var overlay = ForgeSettings.Load();
        settings["overlay_helper"] = overlay.OverlayHelper;
        settings["overlay_renderer"] = overlay.OverlayRenderer;
        return settings;
    }

    static JsonArray Rows(IReadOnlyList<Game> targets) =>
        new(targets.Where(g => g.EngineRow is not null).Select(g => (JsonNode)g.EngineRow!.DeepClone()).ToArray());

    static Action<JsonObject> Reporter(IProgress<PrepareProgress>? progress) => message => progress?.Report(new PrepareProgress(
        message["label"]?.ToString() ?? "", message["game"]?.ToString(), I(message, "checked"), I(message, "total")));

    /// <summary>
    /// One review planned by the shared planner (scripts/review_plan.py), as Game Mode on
    /// both systems: each game takes its route (Adoption, Vulkan, Feeder NR or its own DLSS
    /// package), consecutive games on one route share a check, packages download first, and
    /// games that support only NR or only MFG get opt-in offers. Every step runs in turn, by name.
    /// </summary>
    async Task<OperationReview> PlanAsync(string operation, IReadOnlyList<Game> targets, Tuning tuning, string mode,
        IProgress<PrepareProgress>? progress, CancellationToken cancel)
    {
        var settings = PrepareSettings(Settings.RuntimeProvider, tuning, mode, false);
        settings["game_packages"] = JsonSerializer.SerializeToNode(Settings.GamePackages);
        var result = await CallAsync("review_prepare", new JsonObject
        {
            ["rows"] = Rows(targets),
            ["operation"] = operation,
            ["mode"] = mode,
            ["settings"] = settings,
        }, Reporter(progress), cancel);
        OperationReview Step(JsonObject entry) => Reviewed(entry["operation"]?.ToString() ?? operation,
            entry["provider"]?.ToString() ?? Settings.RuntimeProvider, entry["review"] as JsonObject, targets) with { Blocked = [], Warnings = [] };
        var steps = Objects(result?["steps"]).Select(Step).ToArray();
        var supported = Objects(result?["supported"]).Select(offer => new SupportedOperationReview(Step(offer),
            offer["nr"]?.GetValue<bool>() == true, offer["mfg"]?.GetValue<bool>() == true, offer["reason"]?.ToString() ?? "")).ToArray();
        var blocked = Blocks(result?["blocked"], targets, true);
        var warnings = Blocks(result?["warnings"], targets, false);
        if (steps.Length == 1) return steps[0] with { Blocked = blocked, Warnings = warnings, Supported = supported };
        var byName = StringComparer.CurrentCultureIgnoreCase;
        return new OperationReview(operation, "", steps.SelectMany(s => s.Ready).OrderBy(r => r.Game.Name, byName).ToArray(), blocked, warnings)
        {
            Steps = steps,
            Supported = supported,
        };
    }

    /// <summary>One prepare call: DLSS file updates and the operations the planner does not route.</summary>
    async Task<OperationReview> PrepareOneAsync(string operation, IReadOnlyList<Game> targets, Tuning tuning, string mode,
        IProgress<PrepareProgress>? progress, CancellationToken cancel)
    {
        var rows = Rows(targets);
        if (operation == "update-dlss")
        {
            var checkedFiles = await CallAsync("prepare_dlss", new JsonObject { ["rows"] = rows }, Reporter(progress), cancel);
            // Paths identify installations even when Steam and Non-Steam names match.
            Game? Installation(JsonObject row) => targets.FirstOrDefault(g =>
                string.Equals(g.Location, row["game"]?.ToString(), StringComparison.OrdinalIgnoreCase));
            var ready = Objects(checkedFiles?["rows"]).Select(r =>
                (Game: Installation(r), Detail: r["detail"]?.ToString() ?? "", Summary: r["summary"]?.ToString()))
                .Where(r => r.Game is not null).Select(r => new OperationGameReview(r.Game!, r.Detail,
                    r.Summary ?? "Update this game's DLSS files. Originals will be backed up.")).ToList();
            var skipped = Objects(checkedFiles?["blocked"]).Select(r =>
                new ReviewBlock(Installation(r), r["name"]?.ToString() ?? "", r["reason"]?.ToString() ?? "", r["summary"]?.ToString())).ToList();
            return new OperationReview(operation, checkedFiles?["token"]?.ToString() ?? "", ready, skipped);
        }
        var engineOperation = operation switch { "adopt" => "adopt", "adopt-clean" => "adopt-clean", _ => "reset" };
        var result = await CallAsync("prepare", new JsonObject
        {
            ["rows"] = rows,
            ["mode"] = mode,
            ["operation"] = engineOperation,
            ["settings"] = PrepareSettings(Settings.RuntimeProvider, tuning, mode, false),
            ["save_defaults"] = false,
        }, Reporter(progress), cancel);
        return Reviewed(operation, Settings.RuntimeProvider, result as JsonObject, targets);
    }

    static Game? Match(IReadOnlyList<Game> targets, string? name, string? path = null) => path is not null
        ? targets.FirstOrDefault(g => string.Equals(g.Location, path, StringComparison.OrdinalIgnoreCase))
        : targets.FirstOrDefault(g => g.Name == name);

    static IReadOnlyList<ReviewBlock> Blocks(JsonNode? items, IReadOnlyList<Game> targets, bool summary) =>
        Objects(items).Select(b => new ReviewBlock(Match(targets, b["name"]?.ToString(), b["game"]?.ToString()), b["name"]?.ToString() ?? "",
            b["reason"]?.ToString() ?? "", summary ? b["summary"]?.ToString() : null)).ToArray();

    /// <summary>A host review (token, rows, blocked, warnings, trust) as the dialog shows it.</summary>
    OperationReview Reviewed(string operation, string provider, JsonObject? result, IReadOnlyList<Game> targets)
    {
        var ready = Objects(result?["rows"])
            .Select(r => (Game: Match(targets, r["name"]?.ToString(), r["game"]?.ToString()), Detail: r["detail"]?.ToString() ?? "", Summary: r["summary"]?.ToString()))
            .Where(r => r.Game is not null).Select(r => new OperationGameReview(r.Game!, r.Detail,
                (r.Summary ?? "Review the changes before continuing.")
                // Games can use different packages in one review, so each says which.
                + (operation is "install" or "repair"
                    ? "\nPackage: " + (r.Game!.UsesFeeder ? "Feeder NR" : Settings.PackageName(provider)) : ""))).ToArray();
        return new OperationReview(operation, result?["token"]?.ToString() ?? "", ready, Blocks(result?["blocked"], targets, true),
            Blocks(result?["warnings"], targets, false)) { OfflineNotice = result?["trust"]?.ToString() };
    }

    public void DiscardOperation(OperationReview review)
    {
        static IEnumerable<string> Tokens(OperationReview item) => new[] { item.Token }
            .Concat(item.Steps.SelectMany(Tokens)).Concat(item.Supported.SelectMany(s => Tokens(s.Review)));
        _ = DiscardOperationAsync(Tokens(review).Where(t => !string.IsNullOrWhiteSpace(t)).Distinct().ToArray());
    }
    async Task DiscardOperationAsync(string[] tokens)
    {
        try { await CallAsync("discard_operation", new { tokens }); }
        catch (Exception error) when (error is IOException or InvalidOperationException) { System.Diagnostics.Debug.WriteLine(error); }
    }

    public async Task<int> ExecuteAsync(OperationReview review, IProgress<OperationStep> progress, CancellationToken cancel = default)
    {
        if (review.Steps.Count > 0)
        {
            var completed = 0;
            foreach (var step in review.Steps)
            {
                cancel.ThrowIfCancellationRequested();
                var offset = completed;
                var partProgress = new Progress<OperationStep>(p => progress.Report(p with { Index = p.Index + offset, Total = review.Ready.Count }));
                try { completed += await ExecuteAsync(step, partProgress, cancel); }
                catch (EngineException error) { throw new EngineException($"{completed} games updated before the operation stopped. {error.Message}"); }
            }
            return completed;
        }
        var games = review.Ready.Select(r => r.Game).ToList();
        if (review.Operation == "update-dlss")
        {
            if (games.Count > 0) progress.Report(new OperationStep(0, games.Count, games[0], "Updating DLSS files…", 0.1));
            var result = await CallAsync("update_dlss", new { token = review.Token }, message =>
            {
                var game = games.FirstOrDefault(g => g.Name == message["game"]?.ToString()) ?? games.FirstOrDefault();
                if (game is not null) progress.Report(new OperationStep(Math.Max(0, I(message, "current") - 1),
                    games.Count, game, message["label"]?.ToString() ?? "Updating DLSS files…"));
            }, cancel);
            var count = I(result, "updated_games");
            if (count == 0) throw new EngineException("No native DLSS files changed. Review the update again to check the file versions.");
            return count;
        }

        void Report(JsonObject message)
        {
            var total = message["total"]?.GetValue<int>() ?? games.Count;
            var current = message["current"]?.GetValue<int>() ?? 1;
            var game = games.FirstOrDefault(g => g.Name == message["game"]?.ToString()) ?? games.ElementAtOrDefault(current - 1);
            if (game is null) return;
            double? fraction = message["fraction"] is JsonValue f && f.TryGetValue<double>(out var value) ? value : null;
            progress.Report(new OperationStep(current - 1, total, game, message["label"]?.ToString() ?? "", fraction));
        }

        using var registration = cancel.Register(() => _ = CallAsync("cancel", new { token = review.Token }));
        try
        {
            await CallAsync("execute", new { token = review.Token, offline_acknowledged = review.OfflineAcknowledged }, Report);
        }
        catch (EngineException error) when (error.Message.Contains("Changes undone", StringComparison.Ordinal) || error.Message.StartsWith("Update cancelled.", StringComparison.Ordinal))
        {
            throw new OperationCanceledException(error.Message, error);
        }
        return games.Count;
    }

    // ---------- Add rtxForge to Steam ----------

    public async Task<SteamShortcutStatus> SteamStatusAsync()
    {
        var result = await CallAsync("steam_status");
        return new SteamShortcutStatus(result?["added"]?.GetValue<bool>() == true, result?["token"]?.ToString() ?? "");
    }

    public async Task<SteamShortcutReview> SteamReviewAsync()
    {
        var result = await CallAsync("steam_review");
        var slots = (result?["roles"] as JsonArray ?? []).OfType<JsonObject>()
            .Select(r => new SteamArtworkSlot(r["role"]?.ToString() ?? "", r["status"]?.ToString() ?? "")).ToList();
        return new SteamShortcutReview(result?["token"]?.ToString() ?? "", result?["created"]?.GetValue<bool>() == true,
            result?["profile"]?.ToString() ?? "", slots, result?["logo_position"]?.ToString() == "add");
    }

    public async Task<SteamShortcutResult> SteamAddAsync(SteamShortcutReview review)
    {
        var result = await CallAsync("steam_install", new { token = review.Token });
        var errors = (result?["errors"] as JsonArray ?? []).Select(e => e?.ToString() ?? "").ToList();
        return new SteamShortcutResult(errors, (result?["preserved"] as JsonArray)?.Count > 0);
    }

    public Task SteamRemoveAsync(SteamShortcutStatus status) => CallAsync("steam_remove", new { token = status.Token });

    public void Dispose()
    {
        foreach (var cancellation in testHelperPolls.Values) cancellation.Cancel();
        try { process.StandardInput.Close(); } catch (IOException) { }
        // A verified application updater must survive a slow engine shutdown.
        // Ordinary shutdown still cleans up the whole engine process tree.
        try { if (!process.WaitForExit(3000)) process.Kill(entireProcessTree: !appUpdateHandedOff); } catch (InvalidOperationException) { }
        process.Dispose();
    }
}

/// <summary>An engine refusal or failure, in the engine's own user-facing words.</summary>
public sealed class EngineException(string message) : InvalidOperationException(message);

/// <summary>
/// Steam artwork for a scanned game: the local Steam library cache first
/// (new per-app folders and the older flat names), then Steam's CDN when
/// online artwork is allowed.
/// </summary>
sealed class SteamArtwork(bool online)
{
    const string Cdn = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/";
    readonly string? cache = SteamCache();

    static string? SteamCache()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
            if (key?.GetValue("SteamPath") is string steam)
            {
                var path = Path.Combine(steam.Replace('/', '\\'), "appcache", "librarycache");
                if (Directory.Exists(path)) return path;
            }
        }
        catch (System.Security.SecurityException) { }
        return null;
    }

    string? Find(string? appid, string file)
    {
        if (appid is null) return null;
        if (cache is not null)
        {
            foreach (var candidate in new[] { Path.Combine(cache, appid, file), Path.Combine(cache, $"{appid}_{file}") })
                if (File.Exists(candidate)) return candidate;
        }
        return online ? Cdn + appid + "/" + file : null;
    }

    public string? Poster(string? appid) => Find(appid, "library_600x900.jpg");
    public string? Capsule(string? appid) => Find(appid, "header.jpg");
    public string? Hero(string? appid) => Find(appid, "library_hero.jpg");
}
