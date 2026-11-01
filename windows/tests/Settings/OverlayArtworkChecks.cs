using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

static class OverlayArtworkChecks
{
    public static void Run()
    {
        var root = Path.Combine(Path.GetTempPath(), "rtxforge-overlay-art-" + Guid.NewGuid().ToString("N"));
        var steamapps = Path.Combine(root, "steamapps"); var install = Path.Combine(steamapps, "common", "Collection");
        var nested = Path.Combine(install, "Game", "ME2", "Binaries", "Win64"); var media = Path.Combine(root, "media");
        Directory.CreateDirectory(nested); Directory.CreateDirectory(media);
        var game = new Game { Id = nested, Location = nested, Name = "Collection · Part 2" };
        var settings = new ForgeSettings(); var art = Path.Combine(root, "poster.png"); File.WriteAllBytes(art, [1, 2, 3]);
        var manifest = Path.Combine(steamapps, "appmanifest_123.acf");
        string Cache(string id, string title, object data)
        {
            var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(id + title))).ToLowerInvariant()[..24];
            var path = Path.Combine(media, hash + ".json"); File.WriteAllText(path, JsonSerializer.Serialize(new { data })); return path;
        }
        void Check(bool valid, string message) { if (!valid) throw new Exception(message); }
        try
        {
            File.WriteAllText(manifest, "\"AppState\" { \"appid\" \"123\" \"installdir\" \"Collection\" \"name\" \"Collection\" }");
            Check(OverlayArtwork.SteamIdentity(game)?.Id == "123", "Nested companion lost its enclosing Steam identity");
            var childCache = Cache("123", game.Name, new { poster = art });
            Check(OverlayArtwork.Find(game, settings, media) == art, "Legacy install without appid lost its cached subgame artwork");
            File.Delete(childCache); Cache("123", "Collection", new { poster = art });
            Check(OverlayArtwork.Find(game, settings, media) == art, "Collection artwork did not fall back to its parent title");
            var custom = Path.Combine(root, "custom.png"); File.WriteAllBytes(custom, [4, 5, 6]);
            settings.AdditionalSettings["game_artwork"] = JsonSerializer.SerializeToElement(new Dictionary<string, object>
            { [install] = new { poster = new { path = custom } }, [install + " Other"] = new { poster = new { path = art } } });
            Check(OverlayArtwork.Find(game, settings, media) == custom, "The helper ignored parent artwork overrides or matched a sibling path");
            settings.AdditionalSettings.Clear();
            File.WriteAllText(manifest, "\"appid\" \"999\" \"installdir\" \"Collection\" \"name\" \"Collection\"");
            Check(OverlayArtwork.SteamIdentity(game) is null, "A mismatched manifest filename supplied another Steam identity");
            File.WriteAllText(manifest, "\"appid\" \"123\" \"installdir\" \"../Collection\" \"name\" \"Collection\"");
            Check(OverlayArtwork.SteamIdentity(game) is null, "A traversing manifest supplied a Steam identity");
            File.WriteAllText(manifest, "\"appid\" \"123\" \"installdir\" \"Other\" \"name\" \"Collection\"");
            Check(OverlayArtwork.Find(game, settings, media) is null, "A matching title borrowed another installation's artwork");
            game.PosterPath = custom;
            Check(OverlayArtwork.Find(game, settings, media) == custom, "The manager's resolved artwork was discarded by the helper lookup");
            Console.WriteLine("PASS: nested Steam identities, subgame/collection artwork, custom artwork precedence and exact installation matching.");
        }
        finally { Directory.Delete(root, true); }
    }
}
