using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>Local presentation lookup for companions whose install records predate Steam IDs.</summary>
static class OverlayArtwork
{
    public static bool Owns(Game game, string root)
    {
        try
        {
            var parent = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            var target = Path.GetFullPath(game.Id).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            return target.Equals(parent, StringComparison.OrdinalIgnoreCase)
                || target.StartsWith(parent + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
        }
        catch (Exception error) when (error is ArgumentException or NotSupportedException) { return false; }
    }

    public static string? Local(string? path)
    {
        try { return path is not null && File.Exists(path) && new FileInfo(path).Length <= 20 * 1024 * 1024 ? path : null; }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException) { return null; }
    }

    public static (string Id, string Title)? SteamIdentity(Game game)
    {
        try
        {
            // Match the enclosing installation, never a title guess or another game's cache.
            var folder = new DirectoryInfo(Path.GetFullPath(game.Location));
            for (var depth = 0; folder is not null && depth < 16; depth++, folder = folder.Parent)
            {
                var common = folder.Parent; var steamapps = common?.Parent;
                if (common is null || steamapps is null || !common.Name.Equals("common", StringComparison.OrdinalIgnoreCase)
                    || !steamapps.Name.Equals("steamapps", StringComparison.OrdinalIgnoreCase)) continue;
                var manifests = steamapps.EnumerateFiles("appmanifest_*.acf").Take(1001).ToArray();
                if (manifests.Length > 1000) return null;
                (string Id, string Title)? match = null;
                foreach (var manifest in manifests)
                {
                    if (manifest.Length > 1024 * 1024) continue;
                    var text = File.ReadAllText(manifest.FullName);
                    string Value(string key) => Regex.Match(text, "\"" + key + "\"\\s+\"([^\"]*)\"", RegexOptions.IgnoreCase).Groups[1].Value;
                    var id = Value("appid"); var install = Value("installdir");
                    if (id.Length == 0 || !id.All(char.IsAsciiDigit) || manifest.Name != "appmanifest_" + id + ".acf"
                        || install is "" or "." or ".." || install.IndexOfAny(['/', '\\']) >= 0
                        || !folder.Name.Equals(install, StringComparison.OrdinalIgnoreCase)) continue;
                    if (match is not null) return null;
                    match = (id, Value("name"));
                }
                return match;
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException) { }
        return null;
    }

    public static string? Find(Game game, ForgeSettings settings, string mediaRoot)
    {
        if (settings.AdditionalSettings.TryGetValue("game_artwork", out var overrides) && overrides.ValueKind == JsonValueKind.Object)
        {
            var selected = overrides.EnumerateObject().Where(item => Owns(game, item.Name))
                .OrderByDescending(item => item.Name.Length).FirstOrDefault();
            foreach (var role in new[] { "poster", "capsule", "hero" })
                if (selected.Value.ValueKind == JsonValueKind.Object && selected.Value.TryGetProperty(role, out var image)
                    && image.ValueKind == JsonValueKind.Object && image.TryGetProperty("path", out var path)
                    && path.ValueKind == JsonValueKind.String && Local(path.GetString()) is { } chosen) return chosen;
        }
        foreach (var path in new[] { game.PosterPath, game.CapsulePath, game.HeroPath })
            if (Local(path) is { } found) return found;
        var steam = SteamIdentity(game);
        var id = game.AppId ?? steam?.Id ?? "";
        // Collections have both per-subgame and parent artwork records. Prefer the subgame.
        foreach (var title in new[] { game.Name, steam?.Title }.OfType<string>().Distinct())
        {
            var key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(id + title))).ToLowerInvariant()[..24];
            var cache = Path.Combine(mediaRoot, key + ".json");
            try
            {
                if (!File.Exists(cache) || new FileInfo(cache).Length > 2 * 1024 * 1024) continue;
                var data = JsonNode.Parse(File.ReadAllText(cache))?["data"];
                foreach (var role in new[] { "poster", "capsule", "hero" })
                    if (data?[role] is JsonValue value && value.TryGetValue<string>(out var path) && Local(path) is { } found) return found;
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException) { }
        }
        return null;
    }
}
