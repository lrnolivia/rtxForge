using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>Reuse the library's palette, using only settings and cached artwork.</summary>
static class OverlayAccent
{
    public static async Task<AccentPalette> ForGameAsync(Game game)
    {
        var settings = ForgeSettings.Load();
        // Companion records use the executable's directory; library preferences
        // use the installation root. Choose the most specific matching root.
        var custom = settings.GameAccents.Where(pair => OverlayArtwork.Owns(game, pair.Key))
            .OrderByDescending(pair => pair.Key.Length).Select(pair => pair.Value).FirstOrDefault();
        if (custom is not null && ArtAccent.TryParse(custom, out var picked)) return ArtAccent.Palette(picked);
        try
        {
            var media = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "state", "desktop", "media");
            var source = OverlayArtwork.Find(game, settings, media)
                ?? OverlayArtwork.Local(new SteamArtwork(false).Poster(game.AppId ?? OverlayArtwork.SteamIdentity(game)?.Id));
            if (source is not null)
            {
                var accent = await ArtAccent.SignatureColorAsync(await ArtAccent.LoadAsync(source));
                return ArtAccent.Palette(accent ?? ArtAccent.NoArtwork);
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Text.Json.JsonException
                                      or InvalidOperationException or System.Runtime.InteropServices.COMException) { }
        return ArtAccent.Palette(ArtAccent.NoArtwork);
    }
}
