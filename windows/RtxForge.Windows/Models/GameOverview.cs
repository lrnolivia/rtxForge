using System.Text.Json.Nodes;

namespace RtxForge.Windows.Models;

/// <summary>Overview facts shared by Desktop and Game Mode, without repeating hero metadata.</summary>
public static class GameOverview
{
    public sealed record Fact(string Title, string Value, string Glyph);
    public const string AdoptionNote = "This package is installed. Adopt its current setup or back it up and clean install from rtxForge.";
    public const string OfflineNote = "Launch here to use the reviewed offline route. The normal Steam launch is unchanged. Online play requires removing these feature files. Adoption restore returns the previous modded setup.";
    public const string TryAnywayNote = "rtxForge hasn't verified this game with this package, so the features may not engage. Installs are still reviewed first, and Restore puts the original files back.";
    public const string LinuxNote = "These features were installed with rtxForge on Linux and already load on Windows. Set Up for Windows hands them to rtxForge here, so you can repair, retune or restore them from Windows.";

    /// <summary>What the scan already knows this game can get (engine "features"); true when the engine didn't say.</summary>
    public static bool HasNr(Game game) => Feature(game, "nr");
    public static bool HasMfg(Game game) => Feature(game, "mfg");
    static bool Feature(Game game, string key) => game.EngineRow?["features"]?[key] is not JsonValue v || !v.TryGetValue<bool>(out var on) || on;

    /// <summary>The preset mode to show for this game: the library mode, narrowed to the features it can get.</summary>
    public static string Mode(Game game, string library) => Mode([game], library);
    public static string Mode(IReadOnlyList<Game> games, string library)
    {
        bool nr = games.Any(HasNr), mfg = games.Any(HasMfg);
        if (nr && !mfg) return "nr-only";
        if (mfg && !nr) return "mfg-only";
        return library;
    }

    /// <summary>The features line for a game that isn't installed yet.</summary>
    public static string? Available(Game game) => (HasNr(game), HasMfg(game)) switch
    {
        (true, true) => "NR + MFG",
        (true, false) => "NR only",
        (false, true) => "MFG only",
        _ => null,
    };

    public static IReadOnlyList<Fact> Facts(Game game)
    {
        var package = !game.Installed && !game.AdoptionAvailable ? "Not installed" : game.RuntimeProvider switch
        {
            "skynizz" => "Skynizz", "y4my" => "y4my Multipass", "dlss-unlocked" => "DLSS-Unlocked",
            "feeder" => "Feeder NR", "custom" => "Custom package", _ => "Installed features",
        };
        var facts = new List<Fact> { new("Feature package", package, "\uE7F4") };
        if (!string.IsNullOrWhiteSpace(game.Library) && game.Library is not ("Steam" or "Folder"))
            facts.Add(new("Library", game.Library, "\uE7FC"));
        if (game.CompatVerdict is { } verdict)
            facts.Add(new("Compatibility", verdict + (game.CompatFromList ? " · rtxForge list" : " · your result"), "\uE73E"));
        if (!string.IsNullOrWhiteSpace(game.DlssVersion))
            facts.Add(new("DLSS file version", game.DlssVersion, "\uE8A5"));
        if (game.IsFeeder)
        {
            var version = game.EngineRow?["nr_runtime"]?["version"]?.ToString();
            var state = game.EngineRow?["nr_enabled"] is JsonValue value && value.TryGetValue<bool>(out var enabled)
                ? enabled ? "Enabled in saved settings" : "Disabled in saved settings" : "Saved state unavailable";
            facts.Add(new("Neural rendering", (version is null ? "" : "Model " + version + "\n") + state + " · NR only", "\uE9E9"));
        }
        else if (!game.Installed && !game.Blocked && Available(game) is { } available)
            facts.Add(new("Available features", (game.UsesFeeder ? "Feeder NR · " : "") + available, "\uE9E9"));
        return facts;
    }
}
