using System.Text.Json.Nodes;

namespace RtxForge.Windows.Models;

/// <summary>Overview facts shared by Desktop and Game Mode, without repeating hero metadata.</summary>
public static class GameOverview
{
    public sealed record Fact(string Title, string Value, string Glyph);
    public const string AdoptionNote = "This package is installed. Adopt its current setup or back it up and clean install from rtxForge.";
    public const string OfflineNote = "Launch here to use the reviewed offline route. The normal Steam launch is unchanged. Online play requires removing these feature files. Adoption restore returns the previous modded setup.";
    public const string LinuxNote = "These features were installed with rtxForge on Linux and already load on Windows. Set Up for Windows hands them to rtxForge here, so you can repair, retune or restore them from Windows.";

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
        if (!string.IsNullOrWhiteSpace(game.DlssVersion))
            facts.Add(new("DLSS file version", game.DlssVersion, "\uE8A5"));
        if (game.IsFeeder)
        {
            var version = game.EngineRow?["nr_runtime"]?["version"]?.ToString();
            var state = game.EngineRow?["nr_enabled"] is JsonValue value && value.TryGetValue<bool>(out var enabled)
                ? enabled ? "Enabled in saved settings" : "Disabled in saved settings" : "Saved state unavailable";
            facts.Add(new("Neural rendering", (version is null ? "" : "Model " + version + "\n") + state + " · NR only", "\uE9E9"));
        }
        else if (game.UsesFeeder)
            facts.Add(new("Available features", "Feeder NR · NR only", "\uE9E9"));
        return facts;
    }
}
