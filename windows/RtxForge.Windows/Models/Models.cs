using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace RtxForge.Windows.Models;

/// <summary>One library row; field names follow the engine's game dict.</summary>
public sealed class Game
{
    public required string Id { get; init; }
    public required string Name { get; init; }
    public string Library { get; init; } = "";
    public string Location { get; init; } = "";
    public bool Installed { get; set; }
    public bool Blocked { get; init; }
    public string? BlockedReason { get; init; }
    public bool Tested { get; init; }
    public string? Developer { get; set; }
    public string? Release { get; set; }
    public string? MetadataSource { get; init; }
    public string? Summary { get; set; }
    // Artwork: local file path or https URL. Poster 2:3, capsule 460:215, hero banner.
    public string? PosterPath { get; set; }
    public string? CapsulePath { get; set; }
    public string? HeroPath { get; set; }
    /// <summary>Artwork credits by role (poster, capsule, hero), as LibraryMedia records them.</summary>
    public Dictionary<string, string> ArtCredits { get; init; } = [];
    /// <summary>game_notes test result: Untested, Working, Problem or Bench.</summary>
    public string TestStatus { get; set; } = "Untested";
    /// <summary>A test record is open (Start Test, then Finish Test after playing).</summary>
    public bool TestActive { get; set; }
    public JsonObject? FunctionalTest => (EngineRow?["test_record"]?["sessions"] as JsonArray)?
        .OfType<JsonObject>().LastOrDefault()?["functional"] as JsonObject;
    public string? FunctionalTestText => FunctionalTest?["text"]?.ToString();
    public string? TestSuggestion => FunctionalTest?["suggestion"]?.ToString();
    public string? DlssVersion { get; set; }
    public string Notes { get; set; } = "";
    /// <summary>Steam app id when known (artwork, store metadata).</summary>
    public string? AppId { get; init; }
    /// <summary>Feature profile the engine recorded: NR + MFG, MFG Only, NR Only.</summary>
    public string? Profile { get; init; }
    public string? RuntimeProvider { get; init; }
    public bool IsFeeder => RuntimeProvider == "feeder";
    /// <summary>A detected installation or a fresh DX11 or DX12 (no DLSS) target admitted to the separate Feeder route.</summary>
    public bool UsesFeeder => IsFeeder || EngineRow?["install_provider"]?.ToString() == "feeder"
        && EngineRow?["feeder_available"] is JsonValue flag && flag.TryGetValue<bool>(out var supported) && supported;
    /// <summary>A Vulkan installation, or a confirmed Vulkan game the engine routes to the bundled Vulkan package, like Feeder.</summary>
    public bool UsesVulkan => RuntimeProvider == "vulkan-native" && Installed || EngineRow?["install_provider"]?.ToString() == "vulkan-native"
        && EngineRow?["vulkan_available"] is JsonValue flag && flag.TryGetValue<bool>(out var available) && available;
    /// <summary>Which rtxForge installed the features: "windows", "linux" (shared .rtxforge-install.json), or null.</summary>
    public string? InstalledOn { get; set; }
    IReadOnlyList<string> installedOses = [];
    /// <summary>Every OS this install supports, including shared-drive adaptations; old scans fall back to InstalledOn.</summary>
    public IReadOnlyList<string> InstalledOses
    {
        get => Installed ? CrossOs.Normalize(installedOses, InstalledOn) : [];
        set => installedOses = CrossOs.Normalize(value);
    }
    /// <summary>A Feeder setup is installed but needs attention (BlockedReason says why); not an unsupported game.</summary>
    public bool FeederNeedsAttention => Blocked && EngineRow?["feeder_detected"] is JsonValue detected
        && detected.TryGetValue<bool>(out var found) && found;
    /// <summary>The block is a capability check Try anyway can skip; anti-cheat and missing executables never are.</summary>
    public bool BlockedSoft => Blocked && EngineRow?["soft_reasons"] is JsonArray reasons && reasons.Any(r => r?.ToString() == BlockedReason);
    /// <summary>The capability check skipped with Try anyway, when it is on for this game.</summary>
    public string? TryAnyway => EngineRow?["try_anyway"] is JsonValue v && v.TryGetValue<string>(out var r) && r.Length > 0 ? r : null;
    /// <summary>Known result (Working or Problem): your own first, then the shipped compatibility list.</summary>
    public string? CompatVerdict => EngineRow?["compat"]?["verdict"]?.ToString();
    public bool CompatFromList => EngineRow?["compat"]?["source"]?.ToString() == "list";
    /// <summary>"Unsupported", or the Feeder status for an installed setup that needs attention.</summary>
    public string BlockedStatus => FeederNeedsAttention || EngineRow?["feeder_restore_first"]?.GetValue<bool>() == true ? "Needs Attention" : "Unsupported";
    /// <summary>Installed with rtxForge on Linux: Windows loads it natively; Set Up for Windows adapts it here.</summary>
    public bool InstalledOnLinux => InstalledOses.SequenceEqual(["linux"]);
    /// <summary>The library's install action: Set Up for Windows adapts a Linux install instead of reinstalling it.</summary>
    public bool AdoptionAvailable => EngineRow?["adoption_available"]?.GetValue<bool>() == true;
    public bool Managed => EngineRow?["managed"]?.GetValue<bool>() == true;
    public bool OfflineOnly => EngineRow?["offline_only"]?.GetValue<bool>() == true;
    public bool OfflineLaunchAvailable => EngineRow?["offline_launch_available"]?.GetValue<bool>() == true;
    /// <summary>The package route this game uses (or would install with), then any other compatible routes. Incompatible ones aren't listed.</summary>
    public string ProviderCandidatesText
    {
        get
        {
            var all = (EngineRow?["provider_candidates"] as JsonArray ?? []).OfType<JsonObject>().ToList();
            static bool Flag(JsonObject p, string key) => p[key] is JsonValue v && v.TryGetValue<bool>(out var on) && on;
            var switchFirst = Installed && Managed;
            var id = switchFirst ? RuntimeProvider : EngineRow?["install_provider"]?.ToString() ?? EngineRow?["recommended_provider"]?.ToString();
            var used = all.FirstOrDefault(p => p["id"]?.ToString() == id) ?? all.FirstOrDefault(p => Flag(p, "compatible") && Flag(p, "ready"));
            if (used is null) return "";
            var others = all.Where(p => p != used && Flag(p, "compatible")).Select(p => p["name"]?.ToString() ?? "").ToList();
            var text = $"{used["name"]}: {used["reason"]}";
            if (others.Count == 0) return text;
            var names = others.Count == 1 ? others[0] : string.Join(", ", others.SkipLast(1)) + " and " + others[^1];
            return text + "\nAlso compatible: " + names + (switchFirst ? ". Restore Original Files first to switch." : ".");
        }
    }
    public bool DynamicMfgAvailable => RuntimeProvider == "skynizz" && EngineRow?["dynamic_mfg_available"] is JsonValue flag
        && flag.TryGetValue<bool>(out var available) && available;
    public string DynamicMfgDetail => EngineRow?["dynamic_mfg_detail"] is JsonValue detail && detail.TryGetValue<string>(out var text) ? text : "";
    public string InstallLabel => AdoptionAvailable ? "Adopt with rtxForge" : InstalledOnLinux ? "Set Up for Windows"
        : UsesFeeder ? Installed ? "Update Feeder NR" : "Install Feeder NR" : "Install Features";
    /// <summary>The engine's scan row, passed back unchanged for review and execution.</summary>
    public System.Text.Json.Nodes.JsonObject? EngineRow { get; init; }
    public bool AntiCheatDetected
    {
        get
        {
            var node = EngineRow?["anti_cheat"];
            return node is not null && (node is not System.Text.Json.Nodes.JsonValue value
                || !value.TryGetValue<bool>(out var detected) || detected);
        }
    }

    // Per-game tuning; null inherits the library presets.
    public double? NrStrength { get; set; }
    public double? SharpeningStrength { get; set; }
    public string? MfgMultiplier { get; set; }
    public JsonObject? FeatureControls { get; set; }
}

/// <summary>Cross-OS installs (scripts/cross_os.py): whichever OS runs the game adapts the install.</summary>
public static class CrossOs
{
    public static string Name(string? os) => os switch { "linux" => "Linux", "windows" => "Windows", _ => "" };
    public static IReadOnlyList<string> Normalize(IEnumerable<string>? oses, string? fallback = null)
    {
        var known = (oses ?? []).Where(os => os is "windows" or "linux").Distinct().ToArray();
        return known.Length > 0 ? known : fallback is "windows" or "linux" ? [fallback] : [];
    }
    public static IReadOnlyList<string> Read(JsonNode? value) => Normalize(
        (value as JsonArray ?? []).OfType<JsonValue>().Select(v => v.TryGetValue<string>(out var os) ? os : ""));
    public static string Names(IEnumerable<string> oses) => string.Join(" and ", oses.Select(Name));
    public static string Tooltip(IEnumerable<string> oses) => "Installed with rtxForge on " + Names(oses);
}

/// <summary>NR Strength / Sharpening / MFG, as written to OptiScaler.ini.</summary>
public sealed record Tuning(double NrStrength, double SharpeningStrength, string MfgMultiplier, bool? NrOnLaunch = null, JsonObject? FeatureControls = null)
{
    public static readonly string[] MultiplierValues = ["auto", "0", "2", "3", "4", "5", "6"];
    public static readonly string[] MultiplierCaptions = ["In game", "Off", "2×", "3×", "4×", "5×", "6×"];
}

/// <summary>One step of a running operation: which game, how far along (0–1 overall when known).</summary>
public sealed record OperationStep(int Index, int Total, Game Game, string Caption, double? Fraction = null);

/// <summary>Review progress: the current phase, and per game when the engine is checking targets.</summary>
public sealed record PrepareProgress(string Label, string? Game = null, int Checked = 0, int Total = 0);

/// <summary>A game the engine refused for this operation, with its reason.</summary>
public sealed record ReviewBlock(Game? Game, string Name, string Reason, string? Summary = null);

/// <summary>A readable change summary plus the engine's complete diagnostic text.</summary>
public sealed record OperationGameReview(Game Game, string Detail, string Summary);

/// <summary>
/// The engine's prepared review (engine_bridge.prepare). Execution runs this
/// exact review by token, so only what the user saw is written.
/// </summary>
public sealed record OperationReview(string Operation, string Token, IReadOnlyList<OperationGameReview> Ready, IReadOnlyList<ReviewBlock> Blocked,
    IReadOnlyList<ReviewBlock>? Warnings = null)
{
    /// <summary>Heads-ups for ready games (e.g. NVIDIA App's DLSS Override); they never block the install.</summary>
    public IReadOnlyList<ReviewBlock> Warnings { get; init; } = Warnings ?? [];
    public IReadOnlyList<SupportedOperationReview> Supported { get; init; } = [];
    public IReadOnlyList<OperationReview> Steps { get; init; } = [];
    public string? OfflineNotice { get; init; }
    public bool OfflineAcknowledged { get; init; }
    public string? RequiredTrust => OfflineNotice ?? Steps.Select(p => p.RequiredTrust).FirstOrDefault(t => t is not null)
        ?? Supported.Select(p => p.Review.RequiredTrust).FirstOrDefault(t => t is not null);
    public OperationReview AcknowledgeOffline(bool acknowledged) => this with
    {
        OfflineAcknowledged = acknowledged,
        Steps = Steps.Select(p => p.AcknowledgeOffline(acknowledged)).ToArray(),
        Supported = Supported.Select(p => p with { Review = p.Review.AcknowledgeOffline(acknowledged) }).ToArray(),
    };
    public OperationReview IncludeSupported()
    {
        // A combined review contributes its own package steps, so every package's run can be ordered by name.
        var byName = StringComparer.CurrentCultureIgnoreCase;
        var own = Steps.Count > 0 ? Steps : new[] { this with { Supported = [] } }.Where(r => r.Ready.Count > 0);
        var steps = own.Concat(Supported.Select(p => p.Review))
            .OrderBy(r => r.Ready.Select(item => item.Game.Name).Min(byName), byName).ToArray();
        return this with { Ready = steps.SelectMany(r => r.Ready).OrderBy(r => r.Game.Name, byName).ToArray(), Steps = steps, Supported = [] };
    }
    /// <summary>Every game the review changes, whatever its package: the full selection and partly supported games in one list, by name.</summary>
    public IReadOnlyList<(OperationGameReview Item, SupportedOperationReview? Part)> AllGames =>
        Ready.Select(item => (item, (SupportedOperationReview?)null))
            .Concat(Supported.SelectMany(part => part.Review.Ready.Select(item => (item, (SupportedOperationReview?)part))))
            .OrderBy(entry => entry.item.Game.Name, StringComparer.CurrentCultureIgnoreCase).ToArray();
}

public sealed record SupportedOperationReview(OperationReview Review, bool Nr, bool Mfg, string Reason)
{
    /// <summary>The review badge for a partly supported game.</summary>
    public string Badge => Nr && !Mfg ? "NR Only" : Mfg && !Nr ? "MFG Only" : "Ready";
}

/// <summary>Whether this rtxForge installation is in Steam; Token carries the checked state into Remove.</summary>
public sealed record SteamShortcutStatus(bool Added, string Token);

/// <summary>One artwork slot in the Add to Steam review: poster, capsule, hero or logo; add / replace / unchanged.</summary>
public sealed record SteamArtworkSlot(string Role, string Status);

/// <summary>steam_self_install.review: what Add to Steam will change, executed by token.</summary>
public sealed record SteamShortcutReview(string Token, bool Created, string Profile, IReadOnlyList<SteamArtworkSlot> Slots, bool CentersLogo);

public sealed record SteamShortcutResult(IReadOnlyList<string> Errors, bool Preserved);

/// <summary>One line of an engine review: a game, file or record, what changes, and an optional full text (report files, hashes).</summary>
public sealed record ReviewItem(string Title, string Detail, string Badge, string? GameId = null, string? Details = null);

/// <summary>
/// A reviewed write other than install/restore (artwork sync, recovery, cleanup, tools, DLSS restore,
/// support report, app update). The host keeps the exact payload; RunReviewAsync executes it once by token.
/// Trust, when set, is a statement the user must confirm before the action is enabled.
/// </summary>
public sealed record EngineReview(string Token, string Kind, string Title, string Summary, string Action,
    IReadOnlyList<ReviewItem> Items, IReadOnlyList<ReviewItem> Blocked, string? Trust = null, string? Note = null)
{
    public IReadOnlyList<ReviewItem> Skipped { get; init; } = [];
    public bool Ready => Items.Count > 0;
}

/// <summary>What a reviewed write did: a message, an optional file (report, installer) and remaining errors.</summary>
public sealed record EngineResult(string Message, string? Path, IReadOnlyList<string> Errors);

public sealed record SteamArtworkProfile(string Root, string UserId, bool Selected);

/// <summary>LibraryMedia.enrich for one game: local artwork paths, credits and store metadata.</summary>
public sealed record GameMedia(string GameId, string? Poster, string? Capsule, string? Hero,
    IReadOnlyDictionary<string, string> Credits, string? Description, string? Developers, string? Release);

public sealed record SteamGridGame(long Id, string Name);

public sealed record SteamGridAsset(long Id, string Url, string? Thumb, int Width, int Height, string Author, string? Mime);

/// <summary>SteamGridDB filter vocabulary per role (steamgrid_client STYLES / DIMENSIONS / MIMES).</summary>
public sealed record SteamGridStatus(bool Connected, string? Problem,
    IReadOnlyDictionary<string, string[]> Styles, IReadOnlyDictionary<string, string[]> Dimensions, string[] Mimes);

/// <summary>desktop_service.recoveries: a batch rollback or a cleanup recovery record.</summary>
public sealed record RecoveryRecord(string Kind, string Path, string Name, string Detail);

/// <summary>extra_tools.recoveries: an installed ReShade or add-on that can be restored.</summary>
public sealed record ExtraRecord(string Path, string Name, string Kind, string Title, string Date);

/// <summary>runtime_diagnostics.inspect: warnings (NVIDIA App DLSS Override), observations, the visible-result statement and the full report.</summary>
public sealed record NrDiagnosis(IReadOnlyList<string> Observations, string VisualResult, string Report, IReadOnlyList<string>? Warnings = null)
{
    public IReadOnlyList<string> Warnings { get; init; } = Warnings ?? [];
}

public sealed record DlssFile(string Title, string Path, string Current, string Provenance);

/// <summary>runtime_updates.inspect + game_recoveries for one game.</summary>
public sealed record DlssInventory(IReadOnlyList<DlssFile> Files, string Blocked, string? LatestBackup);

/// <summary>A package. Verified lists the OSes ("windows", "linux") where it has been tested in a game.</summary>
public sealed record PackageOption(string Id, string Name, string Version, string Summary, bool Available, string Reason, bool Recommended, string Url,
    IReadOnlyList<string>? Verified = null, IReadOnlyDictionary<string, string>? MfgVersions = null, IReadOnlyList<string>? GraphicsApis = null,
    IReadOnlyList<string>? Confirmed = null);

public sealed record CommunitySource(string Name, string Url, string Note);

/// <summary>A game's result as a prefilled issue: the exact text, and the URL the browser opens.</summary>
public sealed record CompatShare(string Title, string Body, string Url);

/// <summary>One field of the shared beta-report form (scripts/beta_report.py FIELDS): website, GitHub form and both apps alike.</summary>
public sealed record ReportField(string Id, string Label, IReadOnlyList<string> Choices, bool Required, int Max);

/// <summary>A drafted report for one game. Sources say where each value came from; the host keeps the draft itself.</summary>
public sealed record BetaReport(string Id, string Name, IReadOnlyDictionary<string, string> Fields,
    IReadOnlyDictionary<string, string> Sources, IReadOnlyList<string> Problems);

public sealed record BetaReportDraft(IReadOnlyList<BetaReport> Reports, IReadOnlyList<ReportField> Fields);

/// <summary>After saving: one prefilled GitHub form per game (Complete is false when the link had to be cut short).</summary>
public sealed record BetaReportLink(string Name, string Url, bool Complete, string Text);

/// <summary>Links for new reports, or the existing issue and the note to paste beside the attached ZIP.</summary>
public sealed record BetaReportLinks(IReadOnlyList<BetaReportLink> Links, string? IssueUrl, int IssueNumber, string Comment);

/// <summary>One private log as it will be sent: redacted, newest part only when long.</summary>
public sealed record ReportLog(string Name, string Detail, string Text);

/// <summary>"See what's sent": the public issue as it will read, and the logs that go privately.</summary>
public sealed record ReportOutline(string Title, string Text, IReadOnlyList<ReportLog> Logs, IReadOnlyList<string> Skipped);

/// <summary>The issue a report became, or why it couldn't be sent. A copy stays in Documents/rtxForge Reports either way.</summary>
public sealed record ReportSent(bool Sent, int Number, string? Url, string Path, string? Error);

public sealed record PackageCatalog(string Status, IReadOnlyList<PackageOption> Packages, IReadOnlyList<CommunitySource> Community, string? CustomName);

/// <summary>Feeder NR files rtxForge keeps itself: the verified stack (null when none) and original backups.</summary>
public sealed record FeederStorage(string? Recipe, string? ImportedFrom, string? NrVersion, int Backups, bool LegacyReady = false);

public sealed record PackageParameter(string Key, string Label, string Value, string Origin);

/// <summary>package_catalog.inspect_archive, held by the host under Token until it is used or discarded.</summary>
public sealed record PackageInspection(string Token, string Name, string Family, string Confidence, int FileCount, long ExpandedBytes,
    IReadOnlyList<PackageParameter> Parameters, IReadOnlyList<string> Warnings, IReadOnlyList<(string Path, string Text)> Instructions, bool Deployable);

/// <summary>The reviewed custom package's suggested presets.</summary>
public sealed record PackageChoice(string Name, Tuning Presets);

public sealed record HardwareInfo(string Gpu, string Driver, string Vram, string Cpu, string Architecture, bool Ready, string Reason);

/// <summary>
/// Desktop settings. Keys and defaults match library_media.DEFAULTS so the
/// two shells can later share one settings file.
/// </summary>
public sealed class ForgeSettings
{
    [JsonPropertyName("auto_update")] public bool AutoUpdate { get; set; } = true;
    // Skynizz + Universal MFG is the Windows flagship.
    string runtimeProvider = "skynizz";
    /// <summary>
    /// The package for games with DLSS. Games without DLSS use Feeder NR automatically, so the
    /// retired Feeder-only choice ("feeder") reads as Skynizz, the Feeder route's DLSS partner.
    /// y4my is no longer offered on Windows (its MFG stays at 2x on RTX 40), so it reads as Skynizz
    /// too; games already installed with y4my keep repairing and restoring from their records.
    /// The Vulkan package is automatic for its confirmed games, so a saved "vulkan-native" choice reads as Skynizz.
    /// </summary>
    [JsonPropertyName("runtime_provider")] public string RuntimeProvider
    {
        get => runtimeProvider;
        set => runtimeProvider = value is "feeder" or "y4my" or "vulkan-native" ? "skynizz" : value;
    }
    /// <summary>A game's own package for games with DLSS, by game folder; absent games use RuntimeProvider.</summary>
    [JsonPropertyName("game_packages")] public Dictionary<string, string> GamePackages { get; set; } = [];
    /// <summary>Packages a game can choose on Windows. Feeder NR stays automatic for DX11 games and DX12 games without DLSS,
    /// and confirmed Vulkan games use the Vulkan package automatically.</summary>
    public static readonly (string Key, string Name)[] GamePackageChoices = [("skynizz", "Skynizz NR"), ("dlss-unlocked", "DLSS-Unlocked")];
    /// <summary>MFG packages that pair with Skynizz NR, as MfgProvider values.</summary>
    public static readonly (string Key, string Name)[] MfgPackageNames =
        [("universal", "Universal MFG"), ("integrated", "Integrated MFG unlock"), ("mfg-unlock", "MFG Unlock")];
    public static string MfgName(string key) => MfgPackageNames.FirstOrDefault(c => c.Key == key).Name ?? key;
    /// <summary>A package's name as installed now: Skynizz NR is named with the MFG package it pairs with.</summary>
    public string PackageName(string key) => key == "skynizz" ? "Skynizz NR + " + MfgName(MfgProvider)
        : key == "vulkan-native" ? "Vulkan NR + Universal MFG" : GamePackageChoices.FirstOrDefault(c => c.Key == key).Name ?? key;
    /// <summary>A game's package choices for both UIs: "" follows the library package.</summary>
    public (string[] Keys, string[] Captions) GamePackageOptions() =>
        (["", .. GamePackageChoices.Select(c => c.Key)], ["Library package · " + PackageName(RuntimeProvider), .. GamePackageChoices.Select(c => PackageName(c.Key))]);
    public string GamePackage(Game game) => GamePackages.GetValueOrDefault(game.Id, "");
    public string GamePackageNote(Game game) => game.Installed && game.RuntimeProvider is { } installed
        ? $"Installed with {PackageName(installed)}. Another package applies after you restore this game."
        : "Used when you install features on this game. Games without DLSS get their NR package automatically.";
    /// <summary>The package a review prepares this game with: Feeder games keep their route, repairs keep the installed package.</summary>
    public string PackageFor(Game game, string operation)
    {
        static bool Known(string? key) => GamePackageChoices.Any(c => c.Key == key);
        if (game.UsesVulkan && game.Installed) return "vulkan-native";
        if (game.UsesFeeder) return RuntimeProvider;
        if (operation == "repair" && game.Installed && Known(game.RuntimeProvider)) return game.RuntimeProvider!;
        return GamePackages.TryGetValue(game.Id, out var chosen) && Known(chosen) ? chosen : RuntimeProvider;
    }
    [JsonPropertyName("nr_runtime")] public string NrRuntime { get; set; } = "";
    /// <summary>
    /// The app ships one compiled Skynizz bridge, so new installs always use it; a release saved by an
    /// earlier app reads as "latest". Repairs keep each game's recorded release.
    /// </summary>
    [JsonPropertyName("skynizz_version")] public string SkynizzVersion
    {
        get => "latest";
        set { }
    }
    [JsonPropertyName("mfg_provider")] public string MfgProvider { get; set; } = "universal";
    /// <summary>Absent in files saved before Universal MFG replaced the integrated bridge as the default (revision 1).</summary>
    [JsonPropertyName("mfg_default_revision")] public int? MfgDefaultRevision { get; set; }
    /// <summary>Dynamic MFG needs OptiScaler to own the count: the integrated bridge or the Universal plugin.</summary>
    [JsonIgnore] public bool DynamicMfgSupported => MfgProvider is "universal" or "integrated";
    [JsonPropertyName("nr_preset")] public int? NrPreset { get; set; }
    [JsonPropertyName("nr_on_launch")] public bool NrOnLaunch { get; set; } = false;
    [JsonPropertyName("feeder_source")] public string FeederSource { get; set; } = "";
    [JsonPropertyName("feeder_backups")] public string FeederBackups { get; set; } = "";
    [JsonPropertyName("manage_dlss_files")] public bool ManageDlssFiles { get; set; } = true;
    [JsonPropertyName("borderless_4k")] public bool Borderless4K { get; set; }
    string panelHotkey = Services.OverlayShortcut.Default;
    [JsonPropertyName("panel_hotkey")] public string PanelHotkey
    {
        get => panelHotkey;
        set
        {
            PanelHotkeyMigrated = Services.OverlayShortcut.IsRetiredDefault(value);
            panelHotkey = Services.OverlayShortcut.NormalizeStored(value);
        }
    }
    [JsonIgnore] public bool PanelHotkeyMigrated { get; private set; }
    [JsonPropertyName("overlay_helper")] public bool OverlayHelper { get; set; } = true;
    [JsonPropertyName("overlay_start_with_windows")] public bool OverlayStartWithWindows { get; set; } = true;
    [JsonPropertyName("overlay_material")] public string OverlayMaterial { get; set; } = "acrylic";
    [JsonPropertyName("overlay_controls")] public string OverlayControls { get; set; } = "unified";
    public static readonly string[] OverlayThemes = ["dark", "light", "app"];
    string overlayTheme = "dark";
    [JsonPropertyName("overlay_theme")] public string OverlayTheme
    {
        get => overlayTheme;
        set => overlayTheme = OverlayThemes.Contains(value) ? value : "dark";
    }
    [JsonPropertyName("overlay_live_stats")] public bool OverlayLiveStats { get; set; } = true;
    [JsonPropertyName("overlay_welcome")] public bool OverlayWelcome { get; set; } = true;
    public static readonly string[] WelcomePositions = ["top-center", "top-left", "top-right", "bottom-left", "bottom-right"];
    string overlayWelcomePosition = "top-center";
    [JsonPropertyName("overlay_welcome_position")] public string OverlayWelcomePosition
    {
        get => overlayWelcomePosition;
        set => overlayWelcomePosition = WelcomePositions.Contains(value) ? value : "top-center";
    }
    [JsonPropertyName("vulkan_mfg_native_menu")] public bool VulkanMfgNativeMenu { get; set; }
    string overlayRenderer = "game";
    /// <summary>"game" (the rtxForge in-game panel) or "optiscaler". The retired desktop window ("rtxforge") reads as "game".</summary>
    [JsonPropertyName("overlay_renderer")] public string OverlayRenderer
    {
        get => overlayRenderer;
        set => overlayRenderer = value == "optiscaler" ? "optiscaler" : "game";
    }
    [JsonPropertyName("optiscaler_hotkey")] public string OptiScalerHotkey { get; set; } = "Insert";
    [JsonPropertyName("optiscaler_ui")] public bool OptiScalerUi { get; set; } = true;
    [JsonPropertyName("optiscaler_intro")] public bool OptiScalerIntro { get; set; }
    [JsonPropertyName("reshade_ui")] public bool ReShadeUi { get; set; } = true;
    [JsonPropertyName("reshade_intro")] public bool ReShadeIntro { get; set; }
    public JsonObject GameUiOptions() => new()
    {
        ["optiscaler_ui"] = OptiScalerUi, ["optiscaler_intro"] = OptiScalerIntro,
        ["reshade_ui"] = ReShadeUi, ["reshade_intro"] = ReShadeIntro,
        ["optiscaler_hotkey"] = OptiScalerHotkey,
    };

    [JsonPropertyName("game_overlay_settings")] public Dictionary<string, JsonObject> GameOverlaySettings { get; set; } = [];

    public JsonObject GameOverlayOptions(Game? game = null)
    {
        var values = GameUiOptions();
        values["overlay_renderer"] = OverlayRenderer;
        values["overlay_controls"] = OverlayControls;
        values["overlay_theme"] = OverlayTheme;
        values["overlay_live_stats"] = OverlayLiveStats;
        values["overlay_welcome"] = OverlayWelcome;
        values["overlay_welcome_position"] = OverlayWelcomePosition;
        values["panel_hotkey"] = PanelHotkey;
        values["vulkan_mfg_native_menu"] = VulkanMfgNativeMenu;
        if (game is not null && GameOverlaySettings.TryGetValue(game.Id, out var perGame))
            foreach (var (key, value) in perGame)
                if (key != "overlay_renderer" && values.ContainsKey(key)) values[key] = value?.DeepClone();
        return values;
    }

    public JsonObject OverlayReviewOptions(IEnumerable<string>? games = null)
    {
        var values = GameOverlayOptions();
        values["game_overlay_settings"] = JsonSerializer.SerializeToNode(GameOverlaySettings, Json);
        if (games is not null) values["target_games"] = new JsonArray(games.Select(g => (JsonNode)JsonValue.Create(g)!).ToArray());
        return values;
    }

    public static ForgeSettings EditGameOverlay(Game game, Action<JsonObject>? edit) => EditOverlay(settings =>
    {
        if (edit is null) { settings.GameOverlaySettings.Remove(game.Id); return; }
        if (!settings.GameOverlaySettings.TryGetValue(game.Id, out var values))
        {
            values = settings.GameOverlayOptions(game);
            values.Remove("overlay_renderer");
            settings.GameOverlaySettings[game.Id] = values;
        }
        edit(values);
    });

    public void CopyOverlayFrom(ForgeSettings source)
    {
        PanelHotkey = source.PanelHotkey; OverlayHelper = source.OverlayHelper;
        OverlayStartWithWindows = source.OverlayStartWithWindows; OverlayMaterial = source.OverlayMaterial;
        OverlayControls = source.OverlayControls; OverlayRenderer = source.OverlayRenderer;
        OverlayTheme = source.OverlayTheme;
        OverlayLiveStats = source.OverlayLiveStats;
        OverlayWelcome = source.OverlayWelcome; VulkanMfgNativeMenu = source.VulkanMfgNativeMenu;
        OverlayWelcomePosition = source.OverlayWelcomePosition;
        GameOverlaySettings = source.GameOverlaySettings.ToDictionary(p => p.Key, p => (JsonObject)p.Value.DeepClone());
        OptiScalerHotkey = source.OptiScalerHotkey;
        OptiScalerUi = source.OptiScalerUi; OptiScalerIntro = source.OptiScalerIntro;
        ReShadeUi = source.ReShadeUi; ReShadeIntro = source.ReShadeIntro;
    }
    [JsonPropertyName("companion_game")] public string CompanionGame { get; set; } = "";
    [JsonPropertyName("default_profile")] public string DefaultProfile { get; set; } = "mfg-only";
    [JsonPropertyName("recognize_previous")] public bool RecognizePrevious { get; set; } = true;
    [JsonPropertyName("library_view")] public string LibraryView { get; set; } = "posters";
    [JsonPropertyName("library_filter")] public string LibraryFilter { get; set; } = "all";
    [JsonPropertyName("theme")] public string Theme { get; set; } = "system";
    [JsonPropertyName("game_mode_theme_linked")] public bool GameModeThemeLinked { get; set; } = true;
    [JsonPropertyName("game_mode_theme")] public string GameModeTheme { get; set; } = "night";
    [JsonIgnore] public string ResolvedGameModeTheme => GameModeThemeLinked ? Theme : GameModeTheme;
    int gameModeCardOpacity = 10;
    [JsonPropertyName("game_mode_card_opacity")]
    public int GameModeCardOpacity { get => gameModeCardOpacity; set => gameModeCardOpacity = Math.Clamp(value, 0, 100); }
    [JsonIgnore] public int GameModeNavbarOpacity => Math.Max(0, GameModeCardOpacity - 15);
    public void LinkGameModeTheme(bool linked)
    {
        if (!linked && GameModeThemeLinked) GameModeTheme = ResolvedGameModeTheme;
        GameModeThemeLinked = linked;
    }
    public void SetGameModeTheme(string value)
    {
        if (GameModeThemeLinked) Theme = value; else GameModeTheme = value;
    }

    /// <summary>Compact is the default: the dashboard stays collapsed and the titlebar carries the brand, Features and actions.</summary>
    [JsonPropertyName("compact_header")] public bool CompactHeader { get; set; } = true;
    [JsonPropertyName("separate_game_details")] public bool SeparateGameDetails { get; set; }
    [JsonPropertyName("button_glyphs")] public bool ButtonGlyphs { get; set; } = true;
    [JsonPropertyName("reduce_motion")] public bool ReduceMotion { get; set; }
    [JsonPropertyName("online_art")] public bool OnlineArt { get; set; } = true;
    [JsonPropertyName("steam_metadata")] public bool SteamMetadata { get; set; } = true;
    [JsonPropertyName("network_timeout")] public int NetworkTimeout { get; set; } = 10;
    [JsonPropertyName("art_scale")] public int ArtScale { get; set; } = 100;
    [JsonPropertyName("nr_strength")] public double NrStrength { get; set; } = 2.0;
    [JsonPropertyName("sharpening_strength")] public double SharpeningStrength { get; set; } = 0.5;
    [JsonPropertyName("mfg_multiplier"), JsonConverter(typeof(MfgMultiplierConverter))]
    public string MfgMultiplier { get; set; } = "auto";
    [JsonPropertyName("feature_controls")] public JsonObject? FeatureControls { get; set; }
    [JsonPropertyName("game_folders")] public List<string> GameFolders { get; set; } = [];
    [JsonPropertyName("game_executables")] public Dictionary<string, string> GameExecutables { get; set; } = [];
    [JsonIgnore] public string ExecutableSelectionKey => JsonSerializer.Serialize(GameExecutables.OrderBy(item => item.Key, StringComparer.OrdinalIgnoreCase));
    [JsonPropertyName("library_folders")] public List<string> LibraryFolders { get; set; } = [];
    [JsonPropertyName("removed_games")] public List<string> RemovedGames { get; set; } = [];
    [JsonPropertyName("game_accents")] public Dictionary<string, string> GameAccents { get; set; } = [];
    /// <summary>Hero art focal points chosen per game: [x, y] as fractions of the art. Absent means automatic.</summary>
    [JsonPropertyName("game_hero_focus")] public Dictionary<string, double[]> GameHeroFocus { get; set; } = [];

    // Gaming Mode (Linux couch shell; same keys and defaults as library_media.DEFAULTS).
    [JsonPropertyName("big_picture_ui")] public bool BigPictureUi { get; set; } = true;
    [JsonPropertyName("input_mode")] public string InputMode { get; set; } = "auto";
    [JsonPropertyName("ui_scale")] public JsonElement UiScale { get; set; } = JsonSerializer.SerializeToElement("auto");
    [JsonPropertyName("navigation_position")] public string NavigationPosition { get; set; } = "top";
    [JsonPropertyName("controller_glyphs")] public string ControllerGlyphs { get; set; } = "auto";
    [JsonPropertyName("controller_hints")] public string ControllerHints { get; set; } = "always";
    [JsonPropertyName("dashboard_view")] public string DashboardView { get; set; } = "capsules";
    [JsonPropertyName("dashboard_row_count")] public int DashboardRowCount { get; set; } = 5;

    /// <summary>ui_scale as Linux stores it: "auto" or a percentage.</summary>
    [JsonIgnore]
    public string UiScaleKey
    {
        get => UiScale.ValueKind == JsonValueKind.Number ? UiScale.GetInt32().ToString() : "auto";
        set => UiScale = value == "auto" ? JsonSerializer.SerializeToElement("auto") : JsonSerializer.SerializeToElement(int.Parse(value));
    }

    // The shared engine owns additional settings that this shell does not edit.
    [JsonExtensionData] public Dictionary<string, JsonElement> AdditionalSettings { get; set; } = [];

    [JsonIgnore] public Tuning Presets => new(NrStrength, SharpeningStrength, MfgMultiplier, NrOnLaunch, FeatureControls);

    static string FilePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "settings.json");

    static readonly JsonSerializerOptions Json = new() { WriteIndented = true };

    public static ForgeSettings Load()
    {
        var settings = new ForgeSettings();
        try
        {
            if (File.Exists(FilePath))
                settings = JsonSerializer.Deserialize<ForgeSettings>(File.ReadAllText(FilePath), Json) ?? new();
        }
        catch (JsonException) { }
        catch (IOException) { }
        return settings.Migrated();
    }

    /// <summary>The old default moves to Universal once; a choice made since is kept.</summary>
    public ForgeSettings Migrated()
    {
        if (MfgDefaultRevision is null && MfgProvider == "integrated") MfgProvider = "universal";
        MfgDefaultRevision = 1;
        return this;
    }

    static void WithSettingsLock(Action write)
    {
        using var mutex = new Mutex(false, @"Local\rtxForge.Settings");
        bool held;
        try { held = mutex.WaitOne(TimeSpan.FromSeconds(2)); }
        catch (AbandonedMutexException) { held = true; }
        if (!held) throw new IOException("Settings are busy. Try the change again.");
        try { write(); } finally { mutex.ReleaseMutex(); }
    }

    public static ForgeSettings EditOverlay(Action<ForgeSettings> edit)
    {
        ForgeSettings? fresh = null;
        WithSettingsLock(() => { fresh = Load(); edit(fresh); fresh.Save(); });
        return fresh!;
    }

#if DEBUG
    internal bool InMemoryReview { get; set; }
#endif
    public void Save(bool preserveOverlay = false)
    {
#if DEBUG
        if (InMemoryReview) return;
#endif
        WithSettingsLock(() =>
        {
            if (preserveOverlay) CopyOverlayFrom(Load());
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
            var temp = FilePath + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.WriteAllText(temp, JsonSerializer.Serialize(this, Json));
                File.Move(temp, FilePath, overwrite: true);
            }
            finally { if (File.Exists(temp)) File.Delete(temp); }
        });
    }

    public ForgeSettings Clone() =>
        JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(this, Json), Json)!;
}

/// <summary>The shared engine stores a numeric multiplier; older Windows builds stored text.</summary>
public sealed class MfgMultiplierConverter : JsonConverter<string>
{
    public override bool HandleNull => true;

    static string Normalize(string? value) => value is "0" or "2" or "3" or "4" or "5" or "6" ? value : "auto";

    public override string Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.String) return Normalize(reader.GetString());
        if (reader.TokenType == JsonTokenType.Number && reader.TryGetInt32(out var number))
            return Normalize(number.ToString(System.Globalization.CultureInfo.InvariantCulture));
        reader.Skip();
        return "auto";
    }

    public override void Write(Utf8JsonWriter writer, string value, JsonSerializerOptions options)
    {
        var normalized = Normalize(value);
        if (normalized == "auto") writer.WriteStringValue("auto");
        else writer.WriteNumberValue(int.Parse(normalized, System.Globalization.CultureInfo.InvariantCulture));
    }
}
