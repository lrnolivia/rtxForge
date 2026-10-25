using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>
/// The shell's only dependency on the engine: scan, hardware, then every
/// write as review → execute (engine_bridge.prepare / execute on Linux).
/// EngineForgeService is the real engine; PreviewForgeService is --demo.
/// </summary>
public interface IForgeService
{
    bool IsPreview { get; }
    ForgeSettings Settings { get; }
    Task<IReadOnlyList<Game>> ScanAsync(CancellationToken cancel = default);
    Task<HardwareInfo> DetectHardwareAsync(CancellationToken cancel = default);
    /// <summary>Checks every target and returns what would change; nothing is written.</summary>
    Task<OperationReview> PrepareAsync(string operation, IReadOnlyList<Game> targets, Tuning tuning, string mode,
        IProgress<PrepareProgress>? progress = null, CancellationToken cancel = default);
    /// <summary>Applies exactly the reviewed changes. Returns the number of games changed.</summary>
    Task<int> ExecuteAsync(OperationReview review, IProgress<OperationStep> progress, CancellationToken cancel = default);
    /// <summary>Releases prepared payloads when a review is dismissed or skipped.</summary>
    void DiscardOperation(OperationReview review) { }

    // Add rtxForge to Steam (steam_self_install): review, then add or remove by token.
    Task<SteamShortcutStatus> SteamStatusAsync();
    Task<SteamShortcutReview> SteamReviewAsync();
    Task<SteamShortcutResult> SteamAddAsync(SteamShortcutReview review);
    Task SteamRemoveAsync(SteamShortcutStatus status);

    // Every other write is an EngineReview: shown as-is, then run once by token.
    Task<EngineResult> RunReviewAsync(EngineReview review, IProgress<PrepareProgress>? progress = null);
    void DiscardReview(EngineReview review);

    // Library artwork and metadata (LibraryMedia.enrich; Settings › Refresh artwork).
    Task<IReadOnlyList<GameMedia>> LoadMediaAsync(IReadOnlyList<Game> games, bool refresh, IProgress<PrepareProgress>? progress = null);

    // Steam artwork (steam_artwork, artwork_overrides): the account, your images, reviewed sync.
    Task<IReadOnlyList<SteamArtworkProfile>> SteamArtworkProfilesAsync();
    Task SelectSteamArtworkProfileAsync(SteamArtworkProfile profile);
    /// <summary>Stores an image in rtxForge for one role (poster, capsule, hero, logo); Steam changes only after a sync review.</summary>
    Task StoreArtworkAsync(Game game, string role, string path, string? credit = null);
    Task ResetArtworkAsync(Game game, string role);
    /// <summary>single: exactly these games (after Choose / Browse / Reset); otherwise the library's games with artwork to sync.</summary>
    Task<EngineReview> ReviewArtworkSyncAsync(IReadOnlyList<Game> games, bool single);

    // SteamGridDB (steamgrid_client): the key lives in Windows Credential Manager.
    Task<SteamGridStatus> SteamGridStatusAsync();
    Task SteamGridConnectAsync(string key);
    /// <summary>Removes the saved key; true when an environment key is still configured.</summary>
    Task<bool> SteamGridDisconnectAsync();
    Task<IReadOnlyList<SteamGridGame>> SteamGridSearchAsync(string term);
    Task<IReadOnlyList<SteamGridAsset>> SteamGridArtworkAsync(long gameId, string role, int page, string style, string dimensions, string mime, bool humor);
    /// <summary>Downloads the full-size image to rtxForge's preview cache; returns its path.</summary>
    Task<string> SteamGridDownloadAsync(SteamGridAsset asset);

    // Recovery (desktop_service): previous changes and old NR files.
    Task<IReadOnlyList<RecoveryRecord>> RecoveriesAsync();
    Task<EngineReview> ReviewRecoveryAsync(RecoveryRecord record);
    Task<EngineReview> ReviewCleanupAsync();

    // Notes, test records and support reports (game_notes).
    Task SaveNotesAsync(Game game, string status, string notes);
    Task StartTestAsync(Game game);
    Task FinishTestAsync(Game game);
    Task<EngineReview> PreviewReportAsync(IReadOnlyList<Game> games, bool logs, bool notes);
    // Compatibility (compat_list): skip a capability check, and share a result as a prefilled issue.
    Task SetTryAnywayAsync(Game game, bool on);
    Task<CompatShare> CompatShareAsync(Game game, string package, bool notes);

    // Tools: NR diagnosis (runtime_diagnostics) and ReShade / add-ons (extra_tools).
    Task<NrDiagnosis> DiagnoseAsync(Game game);
    Task<IReadOnlyList<ExtraRecord>> ExtraRecordsAsync(Game game);
    /// <summary>kind: reshade or addon.</summary>
    Task<EngineReview> ReviewExtraAsync(Game game, string path, string kind);
    Task<EngineReview> ReviewExtraRestoreAsync(ExtraRecord record);

    // DLSS files (runtime_updates): inventory and restoring the latest update's backups.
    Task<DlssInventory> DlssInventoryAsync(Game game);
    Task<EngineReview> ReviewDlssRestoreAsync(Game game);

    // Packages (package_catalog).
    Task<PackageCatalog> PackagesAsync();
    /// <summary>Imports the given Feeder folders into app-owned storage (when set), then reports what is kept.</summary>
    Task<FeederStorage> FeederStorageAsync(string? source = null, string? backups = null);
    Task<PackageInspection> InspectPackageAsync(string path);
    Task<PackageChoice> UseCustomPackageAsync(PackageInspection inspection, IReadOnlyDictionary<string, string> values, bool trusted, string notes);

    // Application updates: GitHub releases windows-v<VERSION>.
    Task<EngineReview> CheckForUpdateAsync();
}

/// <summary>
/// Preview mode, equivalent to `rtxforge_gtk.py --demo`: a sample library
/// with public Steam artwork (as scripts/demo_assets.py), in-memory state
/// and no game writes.
/// </summary>
public sealed class PreviewForgeService : IForgeService
{
    const string Steam = @"C:\Program Files (x86)\Steam\steamapps\common";
    const string Epic = @"D:\Epic Games";

    readonly List<Game> games =
    [
        SteamGame("1091500", "Cyberpunk 2077", "Cyberpunk 2077", installed: true, tested: true, developer: "CD PROJEKT RED", release: "2020", dlss: "310.4.0",
            summary: "An open-world, action-adventure RPG set in the megalopolis of Night City."),
        SteamGame("2840770", "Avatar: Frontiers of Pandora", "Avatar Frontiers of Pandora", installed: true, tested: true, developer: "Massive Entertainment", release: "2023", dlss: "310.2.1"),
        SteamGame("292030", "The Witcher 3: Wild Hunt", "The Witcher 3", installed: true, tested: true, developer: "CD PROJEKT RED", release: "2015", dlss: "310.1.0",
            installedOn: "linux"),
        SteamGame("3321460", "Crimson Desert", "Crimson Desert", tested: true, developer: "Pearl Abyss", release: "2026"),
        SteamGame("1449110", "The Outer Worlds 2", "The Outer Worlds 2", tested: true, developer: "Obsidian Entertainment", release: "2025"),
        SteamGame("1681430", "RoboCop: Rogue City", "RoboCop Rogue City", developer: "Teyon", release: "2023"),
        new() { Id = "alanwake2", Name = "Alan Wake 2", Library = "Epic Games", Location = $@"{Epic}\AlanWake2", Developer = "Remedy Entertainment", Release = "2023", MetadataSource = "Epic" },
        SteamGame("3606480", "Call of Duty: Black Ops 7", "Call of Duty", release: "2025",
            blocked: "Online anti-cheat. rtxForge does not modify this game."),
    ];

    static Game SteamGame(string appid, string name, string folder, bool installed = false, bool tested = false,
        string? developer = null, string? release = null, string? dlss = null, string? summary = null, string? blocked = null,
        string installedOn = "windows")
    {
        const string cdn = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/";
        return new Game
        {
            Id = appid, AppId = appid, Name = name, Library = "Steam", Location = $@"{Steam}\{folder}",
            Installed = installed, InstalledOn = installed ? installedOn : null, Tested = tested, Developer = developer, Release = release, DlssVersion = dlss,
            Summary = summary, MetadataSource = "Steam", Blocked = blocked is not null, BlockedReason = blocked,
            PosterPath = $"{cdn}{appid}/library_600x900.jpg",
            CapsulePath = $"{cdn}{appid}/header.jpg",
            HeroPath = $"{cdn}{appid}/library_hero.jpg",
        };
    }

    public bool IsPreview => true;
    public ForgeSettings Settings { get; } = ForgeSettings.Load();

    public async Task<IReadOnlyList<Game>> ScanAsync(CancellationToken cancel = default)
    {
        await Task.Delay(350, cancel);
        return LibraryLocations.Visible(games, Settings.RemovedGames);
    }

    public Task<HardwareInfo> DetectHardwareAsync(CancellationToken cancel = default) =>
        Task.FromResult(new HardwareInfo("NVIDIA GeForce RTX 4070", "Preview", "12 GB", "Preview CPU",
            "Ada Lovelace", true, "Preview mode · no game writes"));

    readonly Dictionary<string, Tuning> reviewed = [];

    public async Task<OperationReview> PrepareAsync(string operation, IReadOnlyList<Game> targets, Tuning tuning, string mode,
        IProgress<PrepareProgress>? progress = null, CancellationToken cancel = default)
    {
        // One game at a time, alphabetically, as the engine reports its checks.
        var ordered = targets.OrderBy(g => g.Name, StringComparer.CurrentCultureIgnoreCase).ToList();
        for (var index = 0; index < ordered.Count; index++)
        {
            progress?.Report(new PrepareProgress("Checking game files", ordered[index].Name, index, ordered.Count));
            await Task.Delay(250, cancel);
        }
        // As engine_bridge.adopt_plan: a Linux install is adapted for Windows, not reinstalled.
        var ready = targets.Where(g => !g.Blocked && (operation is not ("uninstall" or "reset") || g.Installed))
            .Select(g => new OperationGameReview(g, g.InstalledOnLinux
                ? operation == "uninstall" ? "Installed with rtxForge on Linux · restores the original files it backed up"
                : "Installed with rtxForge on Linux · adapts it for Windows: it already loads here, so no game files change"
                : $"Ready to {Verb(operation)}", $"Ready to {Verb(operation)}.")).ToList();
        var blocked = targets.Where(g => g.Blocked).Select(g => new ReviewBlock(g, g.Name, g.BlockedReason ?? "Not supported")).ToList();
        var token = operation + ":" + Guid.NewGuid().ToString("N");
        reviewed[token] = tuning;
        // Sample a mixed install: every third game gets NR only, as games on an NR-only route do.
        if (operation == "install" && mode == "nr-mfg" && ready.Count > 2)
        {
            var partial = ready.Where((_, index) => index % 3 == 2).ToList();
            var partToken = operation + ":" + Guid.NewGuid().ToString("N");
            reviewed[partToken] = tuning;
            return new OperationReview(operation, token, ready.Except(partial).ToList(), blocked)
            {
                Supported = [new(new OperationReview(operation, partToken, partial, []), true, false, "Frame generation is unavailable for this route.")],
            };
        }
        return new OperationReview(operation, token, ready, blocked);
    }

    static string Verb(string operation) => operation switch
    {
        "install" => "install", "uninstall" => "restore", "update-dlss" => "update", _ => "apply presets",
    };

    public async Task<int> ExecuteAsync(OperationReview review, IProgress<OperationStep> progress, CancellationToken cancel = default)
    {
        var operation = review.Operation;
        var tuning = reviewed.Remove(review.Token, out var value) ? value : Settings.Presets;
        var eligible = review.Ready.Select(r => r.Game).ToList();
        var count = 0;
        for (var index = 0; index < eligible.Count; index++)
        {
            var game = eligible[index];
            cancel.ThrowIfCancellationRequested();
            progress.Report(new OperationStep(index, eligible.Count, game, StepCaption(operation)));
            await Task.Delay(900, cancel);
            // Presets on a Linux install adapt it for Windows first (engine_bridge.adopt).
            if (operation is "reset" or "apply" && game.InstalledOnLinux) game.InstalledOn = "windows";
            switch (operation)
            {
                case "install":
                    game.Installed = true;
                    game.InstalledOn = "windows";
                    game.NrStrength = tuning.NrStrength;
                    game.SharpeningStrength = tuning.SharpeningStrength;
                    game.MfgMultiplier = tuning.MfgMultiplier;
                    break;
                case "uninstall":
                    if (!game.Installed) continue;
                    game.Installed = false;
                    game.InstalledOn = null;
                    break;
                case "reset":
                    game.NrStrength = game.SharpeningStrength = null;
                    game.MfgMultiplier = null;
                    break;
                case "apply":
                    game.NrStrength = tuning.NrStrength;
                    game.SharpeningStrength = tuning.SharpeningStrength;
                    game.MfgMultiplier = tuning.MfgMultiplier;
                    break;
                case "update-dlss":
                    game.DlssVersion = "310.5.0";
                    break;
            }
            count++;
        }
        return count;
    }

    // Preview: Steam integration is disabled, as rtxforge_gtk.py --demo.
    public Task<SteamShortcutStatus> SteamStatusAsync() => Task.FromResult(new SteamShortcutStatus(false, ""));
    public Task<SteamShortcutReview> SteamReviewAsync() =>
        Task.FromException<SteamShortcutReview>(new InvalidOperationException("Steam integration is disabled in preview mode."));
    public Task<SteamShortcutResult> SteamAddAsync(SteamShortcutReview review) =>
        Task.FromException<SteamShortcutResult>(new InvalidOperationException("Steam integration is disabled in preview mode."));
    public Task SteamRemoveAsync(SteamShortcutStatus status) =>
        Task.FromException(new InvalidOperationException("Steam integration is disabled in preview mode."));

    // Preview: every write and engine read below is disabled, as rtxforge_gtk.py --demo.
    static Task<T> Disabled<T>(string feature) =>
        Task.FromException<T>(new InvalidOperationException($"{feature} is disabled in preview mode."));
    static Task Disabled(string feature) =>
        Task.FromException(new InvalidOperationException($"{feature} is disabled in preview mode."));

    public Task<EngineResult> RunReviewAsync(EngineReview review, IProgress<PrepareProgress>? progress = null) => Disabled<EngineResult>("Changing files");
    public void DiscardReview(EngineReview review) { }
    public Task<IReadOnlyList<GameMedia>> LoadMediaAsync(IReadOnlyList<Game> games, bool refresh, IProgress<PrepareProgress>? progress = null) =>
        Task.FromResult<IReadOnlyList<GameMedia>>([]);
    public Task<IReadOnlyList<SteamArtworkProfile>> SteamArtworkProfilesAsync() => Disabled<IReadOnlyList<SteamArtworkProfile>>("Steam artwork");
    public Task SelectSteamArtworkProfileAsync(SteamArtworkProfile profile) => Disabled("Steam artwork");
    public Task StoreArtworkAsync(Game game, string role, string path, string? credit = null) => Disabled("Custom artwork");
    public Task ResetArtworkAsync(Game game, string role) => Disabled("Custom artwork");
    public Task<EngineReview> ReviewArtworkSyncAsync(IReadOnlyList<Game> games, bool single) => Disabled<EngineReview>("Steam artwork sync");
    public Task<SteamGridStatus> SteamGridStatusAsync() => Task.FromResult(new SteamGridStatus(false, "Preview only. No credentials are read or saved.",
        new Dictionary<string, string[]>(), new Dictionary<string, string[]>(), []));
    public Task SteamGridConnectAsync(string key) => Disabled("SteamGridDB");
    public Task<bool> SteamGridDisconnectAsync() => Disabled<bool>("SteamGridDB");
    public Task<IReadOnlyList<SteamGridGame>> SteamGridSearchAsync(string term) => Disabled<IReadOnlyList<SteamGridGame>>("SteamGridDB");
    public Task<IReadOnlyList<SteamGridAsset>> SteamGridArtworkAsync(long gameId, string role, int page, string style, string dimensions, string mime, bool humor) =>
        Disabled<IReadOnlyList<SteamGridAsset>>("SteamGridDB");
    public Task<string> SteamGridDownloadAsync(SteamGridAsset asset) => Disabled<string>("SteamGridDB");
    public Task<IReadOnlyList<RecoveryRecord>> RecoveriesAsync() => Task.FromResult<IReadOnlyList<RecoveryRecord>>([]);
    public Task<EngineReview> ReviewRecoveryAsync(RecoveryRecord record) => Disabled<EngineReview>("Restoring changes");
    public Task<EngineReview> ReviewCleanupAsync() => Disabled<EngineReview>("Old NR file cleanup");

    public Task SaveNotesAsync(Game game, string status, string notes)
    {
        game.TestStatus = status;
        game.Notes = notes;
        return Task.CompletedTask;
    }

    public Task StartTestAsync(Game game) => Disabled("Test records");
    public Task FinishTestAsync(Game game) => Disabled("Test records");
    public Task<EngineReview> PreviewReportAsync(IReadOnlyList<Game> games, bool logs, bool notes) => Disabled<EngineReview>("Support reports");
    public Task SetTryAnywayAsync(Game game, bool on) => Disabled("Try anyway");
    public Task<CompatShare> CompatShareAsync(Game game, string package, bool notes) => Disabled<CompatShare>("Sharing results");

    public Task<NrDiagnosis> DiagnoseAsync(Game game) => Task.FromResult(new NrDiagnosis(
        ["Preview: diagnosis reads the selected game’s settings, exact runtime hashes, and bounded log tail."], "Not tested", ""));

    public Task<IReadOnlyList<ExtraRecord>> ExtraRecordsAsync(Game game) => Task.FromResult<IReadOnlyList<ExtraRecord>>([]);
    public Task<EngineReview> ReviewExtraAsync(Game game, string path, string kind) => Disabled<EngineReview>("Installing tools");
    public Task<EngineReview> ReviewExtraRestoreAsync(ExtraRecord record) => Disabled<EngineReview>("Restoring tools");
    public Task<DlssInventory> DlssInventoryAsync(Game game) =>
        Task.FromResult(new DlssInventory([], "Preview mode · file versions appear here for your installed games.", null));
    public Task<EngineReview> ReviewDlssRestoreAsync(Game game) => Disabled<EngineReview>("Restoring DLSS files");

    public Task<FeederStorage> FeederStorageAsync(string? source = null, string? backups = null) =>
        Task.FromResult(new FeederStorage(null, null, null, 0));
    public Task<PackageCatalog> PackagesAsync() =>Task.FromResult(new PackageCatalog("Preview system · NVIDIA RTX 4070 · no game writes",
    [
        new("skynizz", "Skynizz NR + Universal MFG", "v1.3.0 bridge · Universal MFG 1.6.1", "Recommended. Neural rendering with Universal MFG 1.6.1 frame generation in DirectX 12 games with DLSS.", true,
            "Preview package · no game writes", true, "https://github.com/Skynizz/optiscaler-dlss5", ["windows"]),
        new("dlss-unlocked", "DLSS-Unlocked", "Preview", "NR and native MFG in one OptiScaler package", true, "Ready to review for your system", false, "https://github.com/ShyVortex/dlss-unlocked"),
        new("feeder", "Feeder NR", "Preview", "Neural rendering through ReShade for DirectX 11 games, and DirectX 12 games without DLSS. NR only.", true,
            "Preview package · no game writes", false, "https://github.com/jlrouzies-fr/DLSS5-Feeder", ["windows"]),
        new("vulkan-native", "Vulkan NR + Universal MFG", "Preview", "Native Vulkan NR and NVIDIA frame generation, used automatically for confirmed Vulkan games.", true,
            "Preview package · no game writes", false, "https://github.com/lrnolivia/rtxForge", GraphicsApis: ["Vulkan"],
            Confirmed: ["Sample Vulkan Game", "Another Vulkan Game"]),
    ], [], null));

    public Task<PackageInspection> InspectPackageAsync(string path) => Disabled<PackageInspection>("Custom packages");
    public Task<PackageChoice> UseCustomPackageAsync(PackageInspection inspection, IReadOnlyDictionary<string, string> values, bool trusted, string notes) =>
        Disabled<PackageChoice>("Custom packages");
    public Task<EngineReview> CheckForUpdateAsync() => Disabled<EngineReview>("Checking for updates");

    static string StepCaption(string operation) => operation switch
    {
        "install" => "Installing features…",
        "uninstall" => "Restoring original files…",
        "update-dlss" => "Updating DLSS files…",
        "reset" => "Resetting presets…",
        _ => "Applying presets…",
    };
}
