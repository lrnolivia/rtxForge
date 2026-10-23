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
    }
}
