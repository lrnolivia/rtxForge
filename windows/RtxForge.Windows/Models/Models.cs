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
    public string? PosterPath { get; init; }
    public string? CapsulePath { get; init; }
    public string? HeroPath { get; init; }
    public string? DlssVersion { get; set; }
    public string Notes { get; set; } = "";
    /// <summary>Steam app id when known (artwork, store metadata).</summary>
    public string? AppId { get; init; }
    /// <summary>Feature profile the engine recorded: NR + MFG, MFG Only, NR Only.</summary>
    public string? Profile { get; init; }
    /// <summary>The engine's scan row, passed back unchanged for review and execution.</summary>
    public System.Text.Json.Nodes.JsonObject? EngineRow { get; init; }

    // Per-game tuning; null inherits the library presets.
    public double? NrStrength { get; set; }
    public double? SharpeningStrength { get; set; }
    public string? MfgMultiplier { get; set; }
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
public sealed record OperationReview(string Operation, string Token, IReadOnlyList<(Game Game, string Detail)> Ready, IReadOnlyList<ReviewBlock> Blocked);

/// <summary>Whether this rtxForge installation is in Steam; Token carries the checked state into Remove.</summary>
public sealed record SteamShortcutStatus(bool Added, string Token);

/// <summary>One artwork slot in the Add to Steam review: poster, capsule, hero or logo; add / replace / unchanged.</summary>
public sealed record SteamArtworkSlot(string Role, string Status);

/// <summary>steam_self_install.review: what Add to Steam will change, executed by token.</summary>
public sealed record SteamShortcutReview(string Token, bool Created, string Profile, IReadOnlyList<SteamArtworkSlot> Slots, bool CentersLogo);

public sealed record SteamShortcutResult(IReadOnlyList<string> Errors, bool Preserved);

public sealed record HardwareInfo(string Gpu, string Driver, string Vram, string Cpu, string Architecture, bool Ready, string Reason);

/// <summary>
/// Desktop settings. Keys and defaults match library_media.DEFAULTS so the
/// two shells can later share one settings file.
/// </summary>
public sealed class ForgeSettings
{
    [JsonPropertyName("runtime_provider")] public string RuntimeProvider { get; set; } = "y4my";
    [JsonPropertyName("nr_runtime")] public string NrRuntime { get; set; } = "";
    [JsonPropertyName("manage_dlss_files")] public bool ManageDlssFiles { get; set; } = true;
    [JsonPropertyName("default_profile")] public string DefaultProfile { get; set; } = "mfg-only";
    [JsonPropertyName("recognize_previous")] public bool RecognizePrevious { get; set; } = true;
    [JsonPropertyName("library_view")] public string LibraryView { get; set; } = "posters";
    [JsonPropertyName("library_filter")] public string LibraryFilter { get; set; } = "all";
    [JsonPropertyName("theme")] public string Theme { get; set; } = "system";
    [JsonPropertyName("compact_header")] public bool CompactHeader { get; set; }
    [JsonPropertyName("button_glyphs")] public bool ButtonGlyphs { get; set; } = true;
    [JsonPropertyName("online_art")] public bool OnlineArt { get; set; } = true;
    [JsonPropertyName("steam_metadata")] public bool SteamMetadata { get; set; } = true;
    [JsonPropertyName("network_timeout")] public int NetworkTimeout { get; set; } = 10;
    [JsonPropertyName("art_scale")] public int ArtScale { get; set; } = 100;
    [JsonPropertyName("nr_strength")] public double NrStrength { get; set; } = 2.0;
    [JsonPropertyName("sharpening_strength")] public double SharpeningStrength { get; set; } = 0.5;
    [JsonPropertyName("mfg_multiplier")] public string MfgMultiplier { get; set; } = "auto";
    [JsonPropertyName("game_folders")] public List<string> GameFolders { get; set; } = [];
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
