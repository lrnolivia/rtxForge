using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>Reuse the library's palette, using only settings and cached artwork.</summary>
static class OverlayAccent
{
    public static async Task<AccentPalette> ForGameAsync(Game game)
    {
        var settings = ForgeSettings.Load();
        bool Owns(string root)
        {
            try
            {
                var path = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                return string.Equals(game.Id, path, StringComparison.OrdinalIgnoreCase)
                    || game.Id.StartsWith(path + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
            }
            catch (Exception error) when (error is ArgumentException or NotSupportedException) { return false; }
        }
        // Companion records use the executable's directory; library preferences
        // use the installation root. Choose the most specific matching root.
        var custom = settings.GameAccents.Where(pair => Owns(pair.Key))
            .OrderByDescending(pair => pair.Key.Length).Select(pair => pair.Value).FirstOrDefault();
        if (custom is not null && ArtAccent.TryParse(custom, out var picked)) return ArtAccent.Palette(picked);
        string? source = null;
        string? Local(string? path) => path is not null && !path.StartsWith("http", StringComparison.OrdinalIgnoreCase)
            && File.Exists(path) && new FileInfo(path).Length <= 20 * 1024 * 1024 ? path : null;
        try
        {
            if (settings.AdditionalSettings.TryGetValue("game_artwork", out var overrides)
                && overrides.ValueKind == System.Text.Json.JsonValueKind.Object)
            {
                var selected = overrides.EnumerateObject().Where(item => Owns(item.Name))
                    .OrderByDescending(item => item.Name.Length).FirstOrDefault();
                foreach (var role in new[] { "poster", "capsule", "hero" })
                    if (selected.Value.ValueKind == System.Text.Json.JsonValueKind.Object
                        && selected.Value.TryGetProperty(role, out var image) && image.TryGetProperty("path", out var path)
                        && Local(path.GetString()) is { } found) { source = found; break; }
            }
            if (source is null)
            {
                var identity = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes((game.AppId ?? "") + game.Name))).ToLowerInvariant()[..24];
                var cache = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge", "state", "desktop", "media", identity + ".json");
                if (File.Exists(cache) && new FileInfo(cache).Length < 2 * 1024 * 1024)
                {
                    var data = JsonNode.Parse(await File.ReadAllTextAsync(cache))?["data"];
                    foreach (var role in new[] { "poster", "capsule", "hero" })
                        if (Local(data?[role]?.GetValue<string>()) is { } found) { source = found; break; }
                }
            }
            source ??= Local(new SteamArtwork(false).Poster(game.AppId));
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
