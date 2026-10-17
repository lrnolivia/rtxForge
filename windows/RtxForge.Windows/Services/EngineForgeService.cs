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

    sealed record Request(TaskCompletionSource<JsonNode?> Done, Action<JsonObject>? Progress);

    public bool IsPreview => false;
    public ForgeSettings Settings { get; } = ForgeSettings.Load();
    public string EngineRoot { get; }

    EngineForgeService(Process process, string root)
    {
        this.process = process;
        EngineRoot = root;
    }

    // ---------- startup ----------

    /// <summary>Starts the host, or returns null (with the reason) when Python or the engine is unavailable.</summary>
    public static async Task<(EngineForgeService? Service, string? Problem)> TryStartAsync()
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

        Process process;
        try { process = Process.Start(info)!; }
        catch (Exception error) when (error is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            return (null, "Python could not start: " + error.Message);
        }

        var service = new EngineForgeService(process, root);
        var ready = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        _ = Task.Run(() => service.ReadLoop(ready));
        _ = Task.Run(() => service.DrainErrors());
        var first = await Task.WhenAny(ready.Task, Task.Delay(TimeSpan.FromSeconds(30)));
        if (first != ready.Task)
        {
            service.Dispose();
            return (null, "The rtxForge engine did not start in time.");
        }
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

    async Task DrainErrors()
    {
        // Engine diagnostics go to %LOCALAPPDATA%\rtxForge\engine.log for support reports.
        var log = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "engine.log");
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
        // The library serves every mode; the installation review checks native FG for NR + MFG.
        var rows = await CallAsync("scan", new { folders = Settings.GameFolders, library_folders = Settings.LibraryFolders, runtime_provider = Settings.RuntimeProvider }, cancel: cancel) as JsonArray ?? [];
        var art = new SteamArtwork(Settings.OnlineArt);
        return LibraryLocations.Visible(rows.OfType<JsonObject>().Select(row => ToGame(row, art)), Settings.RemovedGames);
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
            NrStrength = D("nr_strength"),
            SharpeningStrength = D("sharpening_strength"),
            MfgMultiplier = multiplier,
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
        var rows = new JsonArray(targets.Where(g => g.EngineRow is not null).Select(g => (JsonNode)g.EngineRow!.DeepClone()).ToArray());
        if (operation == "update-dlss")
        {
            var checkedFiles = await CallAsync("prepare_dlss", new JsonObject { ["rows"] = rows },
                message => progress?.Report(new PrepareProgress(message["label"]?.ToString() ?? "",
                    message["game"]?.ToString(), I(message, "checked"), I(message, "total"))), cancel);
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
        var engineOperation = operation switch { "install" => "install", "uninstall" => "uninstall", _ => "reset" };
        var settings = new JsonObject
        {
            ["runtime_provider"] = Settings.RuntimeProvider,
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
        };
        var result = await CallAsync("prepare", new JsonObject
        {
            ["rows"] = rows,
            ["mode"] = mode,
            ["operation"] = engineOperation,
            ["settings"] = settings,
            ["save_defaults"] = false,
        }, message => progress?.Report(new PrepareProgress(
            message["label"]?.ToString() ?? "",
            message["game"]?.ToString(),
            message["checked"] is JsonValue c && c.TryGetValue<int>(out var done) ? done : 0,
            message["total"] is JsonValue n && n.TryGetValue<int>(out var all) ? all : 0)), cancel);

        Game? Match(string? name, string? path = null) => path is not null
            ? targets.FirstOrDefault(g => string.Equals(g.Location, path, StringComparison.OrdinalIgnoreCase))
            : targets.FirstOrDefault(g => g.Name == name);
        var readyRows = (result?["rows"] as JsonArray ?? []).OfType<JsonObject>()
            .Select(r => (Game: Match(r["name"]?.ToString(), r["game"]?.ToString()), Detail: r["detail"]?.ToString() ?? "", Summary: r["summary"]?.ToString()))
            .Where(r => r.Game is not null).Select(r => new OperationGameReview(r.Game!, r.Detail,
                r.Summary ?? "Review the technical details before continuing.")).ToList();
        var blocked = (result?["blocked"] as JsonArray ?? []).OfType<JsonObject>()
            .Select(b => new ReviewBlock(Match(b["name"]?.ToString()), b["name"]?.ToString() ?? "", b["reason"]?.ToString() ?? "", b["summary"]?.ToString())).ToList();
        var warnings = (result?["warnings"] as JsonArray ?? []).OfType<JsonObject>()
            .Select(w => new ReviewBlock(Match(w["name"]?.ToString()), w["name"]?.ToString() ?? "", w["reason"]?.ToString() ?? "")).ToList();
        return new OperationReview(operation, result?["token"]?.ToString() ?? "", readyRows, blocked, warnings);
    }

    public async Task<int> ExecuteAsync(OperationReview review, IProgress<OperationStep> progress, CancellationToken cancel = default)
    {
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
            await CallAsync("execute", new { token = review.Token }, Report);
        }
        catch (EngineException error) when (error.Message.Contains("Changes undone", StringComparison.Ordinal))
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
        try { process.StandardInput.Close(); } catch (IOException) { }
        try { if (!process.WaitForExit(3000)) process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
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
