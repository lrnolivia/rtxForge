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

    // Add rtxForge to Steam (steam_self_install): review, then add or remove by token.
    Task<SteamShortcutStatus> SteamStatusAsync();
    Task<SteamShortcutReview> SteamReviewAsync();
    Task<SteamShortcutResult> SteamAddAsync(SteamShortcutReview review);
    Task SteamRemoveAsync(SteamShortcutStatus status);
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
        SteamGame("292030", "The Witcher 3: Wild Hunt", "The Witcher 3", installed: true, tested: true, developer: "CD PROJEKT RED", release: "2015", dlss: "310.1.0"),
        SteamGame("3321460", "Crimson Desert", "Crimson Desert", tested: true, developer: "Pearl Abyss", release: "2026"),
        SteamGame("1449110", "The Outer Worlds 2", "The Outer Worlds 2", tested: true, developer: "Obsidian Entertainment", release: "2025"),
        SteamGame("1681430", "RoboCop: Rogue City", "RoboCop Rogue City", developer: "Teyon", release: "2023"),
        new() { Id = "alanwake2", Name = "Alan Wake 2", Library = "Epic Games", Location = $@"{Epic}\AlanWake2", Developer = "Remedy Entertainment", Release = "2023", MetadataSource = "Epic" },
        SteamGame("3606480", "Call of Duty: Black Ops 7", "Call of Duty", release: "2025",
            blocked: "Online anti-cheat. rtxForge does not modify this game."),
    ];

    static Game SteamGame(string appid, string name, string folder, bool installed = false, bool tested = false,
        string? developer = null, string? release = null, string? dlss = null, string? summary = null, string? blocked = null)
    {
        const string cdn = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/";
        return new Game
        {
            Id = appid, AppId = appid, Name = name, Library = "Steam", Location = $@"{Steam}\{folder}",
            Installed = installed, Tested = tested, Developer = developer, Release = release, DlssVersion = dlss,
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
        return games;
    }

    public Task<HardwareInfo> DetectHardwareAsync(CancellationToken cancel = default) =>
        Task.FromResult(new HardwareInfo("NVIDIA GeForce RTX 4070", "Preview", "12 GB", "Preview CPU",
            "Ada Lovelace", true, "Preview mode · no game writes"));

    readonly Dictionary<string, Tuning> reviewed = [];

    public async Task<OperationReview> PrepareAsync(string operation, IReadOnlyList<Game> targets, Tuning tuning, string mode,
        IProgress<PrepareProgress>? progress = null, CancellationToken cancel = default)
    {
        progress?.Report(new PrepareProgress("Checking game files", targets.FirstOrDefault()?.Name, 0, targets.Count));
        await Task.Delay(400, cancel);
        var ready = targets.Where(g => !g.Blocked && (operation is not ("uninstall" or "reset") || g.Installed))
            .Select(g => (g, $"Ready to {Verb(operation)}")).ToList();
        var blocked = targets.Where(g => g.Blocked).Select(g => new ReviewBlock(g, g.Name, g.BlockedReason ?? "Not supported")).ToList();
        var token = operation + ":" + Guid.NewGuid().ToString("N");
        reviewed[token] = tuning;
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
            switch (operation)
            {
                case "install":
                    game.Installed = true;
                    game.NrStrength = tuning.NrStrength;
                    game.SharpeningStrength = tuning.SharpeningStrength;
                    game.MfgMultiplier = tuning.MfgMultiplier;
                    break;
                case "uninstall":
                    if (!game.Installed) continue;
                    game.Installed = false;
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

    static string StepCaption(string operation) => operation switch
    {
        "install" => "Installing features…",
        "uninstall" => "Restoring original files…",
        "update-dlss" => "Updating DLSS files…",
        "reset" => "Resetting presets…",
        _ => "Applying presets…",
    };
}
