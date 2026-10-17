using System.Text.Json;
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
    public string? DlssVersion { get; set; }
    public string Notes { get; set; } = "";
    /// <summary>Steam app id when known (artwork, store metadata).</summary>
    public string? AppId { get; init; }
    /// <summary>Feature profile the engine recorded: NR + MFG, MFG Only, NR Only.</summary>
    public string? Profile { get; init; }
    /// <summary>Which rtxForge installed the features: "windows", "linux" (shared .rtxforge-install.json), or null.</summary>
    public string? InstalledOn { get; set; }
    /// <summary>Installed with rtxForge on Linux: Windows loads it natively; Set Up for Windows adapts it here.</summary>
    public bool InstalledOnLinux => Installed && InstalledOn == "linux";
    /// <summary>The library's install action: Set Up for Windows adapts a Linux install instead of reinstalling it.</summary>
    public string InstallLabel => InstalledOnLinux ? "Set Up for Windows" : "Install Features";
    /// <summary>The engine's scan row, passed back unchanged for review and execution.</summary>
    public System.Text.Json.Nodes.JsonObject? EngineRow { get; init; }

    // Per-game tuning; null inherits the library presets.
    public double? NrStrength { get; set; }
    public double? SharpeningStrength { get; set; }
    public string? MfgMultiplier { get; set; }
}

/// <summary>Cross-OS installs (scripts/cross_os.py): whichever OS runs the game adapts the install.</summary>
public static class CrossOs
{
    public static string Name(string? os) => os switch { "linux" => "Linux", "windows" => "Windows", _ => "" };
}

/// <summary>NR Strength / Sharpening / MFG, as written to OptiScaler.ini.</summary>
public sealed record Tuning(double NrStrength, double SharpeningStrength, string MfgMultiplier)
{
    public static readonly string[] MultiplierValues = ["auto", "0", "2", "3", "4", "5", "6"];
    public static readonly string[] MultiplierCaptions = ["In game", "Off", "2×", "3×", "4×", "5×", "6×"];
}

/// <summary>One step of a running operation: which game, how far along (0–1 overall when known).</summary>
public sealed record OperationStep(int Index, int Total, Game Game, string Caption, double? Fraction = null);

/// <summary>Review progress: the current phase, and per game when the engine is checking targets.</summary>
public sealed record PrepareProgress(string Label, string? Game = null, int Checked = 0, int Total = 0);

/// <summary>A game the engine refused for this operation, with its reason.</summary>
public sealed record ReviewBlock(Game? Game, string Name, string Reason);

/// <summary>
/// The engine's prepared review (engine_bridge.prepare). Execution runs this
/// exact review by token, so only what the user saw is written.
/// </summary>
public sealed record OperationReview(string Operation, string Token, IReadOnlyList<(Game Game, string Detail)> Ready, IReadOnlyList<ReviewBlock> Blocked,
    IReadOnlyList<ReviewBlock>? Warnings = null)
{
    /// <summary>Heads-ups for ready games (e.g. NVIDIA App's DLSS Override); they never block the install.</summary>
    public IReadOnlyList<ReviewBlock> Warnings { get; init; } = Warnings ?? [];
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

public sealed record PackageOption(string Id, string Name, string Version, string Summary, bool Available, string Reason, bool Recommended, string Url);

public sealed record CommunitySource(string Name, string Url, string Note);

public sealed record PackageCatalog(string Status, IReadOnlyList<PackageOption> Packages, IReadOnlyList<CommunitySource> Community, string? CustomName);

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
    [JsonPropertyName("runtime_provider")] public string RuntimeProvider { get; set; } = "y4my";
    [JsonPropertyName("nr_runtime")] public string NrRuntime { get; set; } = "";
    [JsonPropertyName("skynizz_version")] public string SkynizzVersion { get; set; } = "latest";
    [JsonPropertyName("mfg_provider")] public string MfgProvider { get; set; } = "integrated";
    [JsonPropertyName("nr_preset")] public int? NrPreset { get; set; }
    [JsonPropertyName("manage_dlss_files")] public bool ManageDlssFiles { get; set; } = true;
    [JsonPropertyName("borderless_4k")] public bool Borderless4K { get; set; }
    [JsonPropertyName("panel_hotkey")] public string PanelHotkey { get; set; } = "Ctrl+Shift+R";
    [JsonPropertyName("companion_game")] public string CompanionGame { get; set; } = "";
    [JsonPropertyName("default_profile")] public string DefaultProfile { get; set; } = "mfg-only";
    [JsonPropertyName("recognize_previous")] public bool RecognizePrevious { get; set; } = true;
    [JsonPropertyName("library_view")] public string LibraryView { get; set; } = "posters";
    [JsonPropertyName("library_filter")] public string LibraryFilter { get; set; } = "all";
    [JsonPropertyName("theme")] public string Theme { get; set; } = "system";
    /// <summary>Compact is the default: the dashboard stays collapsed and the titlebar carries the brand, Features and actions.</summary>
    [JsonPropertyName("compact_header")] public bool CompactHeader { get; set; } = true;
    [JsonPropertyName("button_glyphs")] public bool ButtonGlyphs { get; set; } = true;
    [JsonPropertyName("online_art")] public bool OnlineArt { get; set; } = true;
    [JsonPropertyName("steam_metadata")] public bool SteamMetadata { get; set; } = true;
    [JsonPropertyName("network_timeout")] public int NetworkTimeout { get; set; } = 10;
    [JsonPropertyName("art_scale")] public int ArtScale { get; set; } = 100;
    [JsonPropertyName("nr_strength")] public double NrStrength { get; set; } = 2.0;
    [JsonPropertyName("sharpening_strength")] public double SharpeningStrength { get; set; } = 0.5;
    [JsonPropertyName("mfg_multiplier"), JsonConverter(typeof(MfgMultiplierConverter))]
    public string MfgMultiplier { get; set; } = "auto";
    [JsonPropertyName("game_folders")] public List<string> GameFolders { get; set; } = [];
    [JsonPropertyName("library_folders")] public List<string> LibraryFolders { get; set; } = [];
    [JsonPropertyName("removed_games")] public List<string> RemovedGames { get; set; } = [];
    [JsonPropertyName("game_accents")] public Dictionary<string, string> GameAccents { get; set; } = [];

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

    [JsonIgnore] public Tuning Presets => new(NrStrength, SharpeningStrength, MfgMultiplier);

    static string FilePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "settings.json");

    static readonly JsonSerializerOptions Json = new() { WriteIndented = true };

    public static ForgeSettings Load()
    {
        try
        {
            if (File.Exists(FilePath))
                return JsonSerializer.Deserialize<ForgeSettings>(File.ReadAllText(FilePath), Json) ?? new();
        }
        catch (JsonException) { }
        catch (IOException) { }
        return new();
    }

    public void Save()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
        var temp = FilePath + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(this, Json));
        File.Move(temp, FilePath, overwrite: true);
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
