using System.Runtime.CompilerServices;
using System.Text.Json;
using RtxForge.Windows.Models;

static class GameModeThemes
{
    [ModuleInitializer]
    public static void Verify()
    {
        var themes = new ForgeSettings { Theme = "dark" };
        themes.LinkGameModeTheme(false);
        if (themes.GameModeTheme != "dark") throw new Exception("Unlink must preserve the current color theme.");
        themes.SetGameModeTheme("night");
        if (themes.Theme != "dark" || themes.ResolvedGameModeTheme != "night") throw new Exception("Game Mode must not recolor Desktop while unlinked.");
        themes.Theme = "light";
        if (themes.ResolvedGameModeTheme != "night") throw new Exception("Desktop must not recolor unlinked Game Mode.");
        var themeRoundTrip = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(themes))!;
        if (themeRoundTrip.GameModeThemeLinked || themeRoundTrip.GameModeTheme != "night") throw new Exception("Independent theme must persist.");
        themes.LinkGameModeTheme(true);
        if (themes.ResolvedGameModeTheme != "light") throw new Exception("Relink must follow Desktop.");
        themes.SetGameModeTheme("dark");
        if (themes.Theme != "dark") throw new Exception("Linked changes must update the shared theme.");
        if (!JsonSerializer.Deserialize<ForgeSettings>("{}")!.GameModeThemeLinked) throw new Exception("Existing settings must retain shared themes.");
        Console.WriteLine("PASS: independent themes, unlink continuity, relink, persistence and existing-settings migration.");
        if (new ForgeSettings().GameModeCardOpacity != 10 || new ForgeSettings().GameModeNavbarOpacity != 0)
            throw new Exception("The default card tint must be softened, with navbar tint clamped at clear.");
        foreach (var opacity in new[] { -10, 0, 15, 40, 75, 90, 100, 110 })
        {
            var settings = new ForgeSettings { GameModeCardOpacity = opacity, NrStrength = 1.25 };
            var restored = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(settings))!;
            if (restored.GameModeCardOpacity != Math.Clamp(opacity, 0, 100)
                || restored.GameModeNavbarOpacity != Math.Max(0, restored.GameModeCardOpacity - 15) || restored.NrStrength != 1.25)
                throw new Exception("Card opacity persistence/clamping changed the navbar relationship or other settings.");
        }
        Console.WriteLine("PASS: frosted card tint defaults, bounds and persistence; navbar stays 15 points lower, clamped at clear.");
    }
}
