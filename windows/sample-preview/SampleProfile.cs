using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using RtxForge.Windows.Models;

namespace RtxForge.Windows;

public static class SampleProfile
{
    public static string Root { get; private set; } = "";
    public static string LocalAppData => Root.Length > 0 ? Root : throw new InvalidOperationException("A sample library is required.");
    public static string SettingsMutex => "Local\\rtxForge.Sample." + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(LocalAppData)))[..16];
    static JsonArray rows = [];
    public static SampleSelection Selection { get; } = new();
    public static int CatalogCount => rows.Count;
    public static string SettingsPath => Path.Combine(LocalAppData, "rtxForge", "settings.json");
    static readonly JsonSerializerOptions json = new() { WriteIndented = true };

    public static void Configure(string[] arguments)
    {
        Root = ""; rows = [];
        var index = Array.IndexOf(arguments, "--sample-library");
        if (index < 0 || index + 1 >= arguments.Length || arguments.Length != index + 2)
            throw new InvalidDataException("Launch this private build with --sample-library and its catalog file.");
        var path = Path.GetFullPath(arguments[index + 1]);
        var allowed = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "rtxForge-samples") + Path.DirectorySeparatorChar;
        if (!path.StartsWith(allowed, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Sample data must be in the dedicated samples folder.");
        var info = new FileInfo(path);
        if (!info.Exists || info.Length > 4 * 1024 * 1024 || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("The sample manifest is missing or invalid.");
        var document = JsonNode.Parse(File.ReadAllText(path), documentOptions: new() { MaxDepth = 24 }) as JsonObject;
        if (document?["schema"]?.GetValue<int>() != 1 || document["kind"]?.GetValue<string>() != "rtxforge-private-sample"
            || document["games"] is not JsonArray games || games.Count is < 1 or > 2000)
            throw new InvalidDataException("Invalid sample catalog.");
        var candidate = Path.GetDirectoryName(path)!;
        for (var directory = new DirectoryInfo(candidate); directory.FullName.StartsWith(allowed, StringComparison.OrdinalIgnoreCase); directory = directory.Parent!)
            if ((directory.Attributes & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("A sample profile cannot use linked folders.");
        foreach (var relative in new[] { "rtxForge", "rtxForge/settings.json", "game-state.json", "art" })
        {
            var item = Path.Combine(candidate, relative);
            if (Path.Exists(item) && (File.GetAttributes(item) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Sample state cannot use linked files or folders.");
        }
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (var node in games)
        {
            if (node is not JsonObject game) throw new InvalidDataException("Invalid sample row.");
            var id = game["id"]?.GetValue<string>() ?? "";
            var title = game["name"]?.GetValue<string>() ?? "";
            if (!System.Text.RegularExpressions.Regex.IsMatch(id, "^sample_[a-f0-9]{24}$") || !ids.Add(id)
                || string.IsNullOrWhiteSpace(title) || title.Length > 1024) throw new InvalidDataException("Invalid sample identity.");
            foreach (var key in new[] { "poster", "capsule", "hero" }) ValidateArtwork(candidate, game[key]?.GetValue<string>());
        }
        Root = candidate; rows = (JsonArray)games.DeepClone();
        Selection.Restore(Path.Combine(Root, "selection.json"), ids);
        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        if (!File.Exists(SettingsPath))
            Atomic(SettingsPath, new JsonObject { ["theme"] = "dark", ["library_view"] = "posters", ["library_filter"] = "all",
                ["runtime_provider"] = "skynizz", ["default_profile"] = "nr-mfg", ["overlay_helper"] = false,
                ["overlay_start_with_windows"] = false, ["panel_hotkey"] = "Disabled", ["online_art"] = false,
                ["steam_metadata"] = false, ["removed_games"] = new JsonArray() }.ToJsonString(json));
    }

    static void ValidateArtwork(string root, string? value)
    {
        if (string.IsNullOrEmpty(value)) return;
        if (Uri.TryCreate(value, UriKind.Absolute, out var url) && url.Scheme == "https")
        {
            if (url.Host is not ("shared.akamai.steamstatic.com" or "cdn.akamai.steamstatic.com" or "shared.fastly.steamstatic.com"))
                throw new InvalidDataException("Unrecognized artwork fallback.");
            return;
        }
        var full = Path.GetFullPath(Path.Combine(root, value));
        if (Path.IsPathRooted(value) || !full.StartsWith(Path.Combine(root, "art") + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
            || !File.Exists(full) || new FileInfo(full).Length > 20 * 1024 * 1024)
            throw new InvalidDataException("Sample artwork must be a copied local asset.");
    }

    public static List<Game> LoadGames()
    {
        _ = LocalAppData;
        var statePath = Path.Combine(Root, "game-state.json");
        var state = File.Exists(statePath) && new FileInfo(statePath).Length <= 4 * 1024 * 1024
            ? JsonNode.Parse(File.ReadAllText(statePath), documentOptions: new() { MaxDepth = 24 }) as JsonObject : null;
        string? Art(JsonObject row, string key) => row[key]?.GetValue<string>() is { Length: > 0 } value
            ? value.StartsWith("https://", StringComparison.OrdinalIgnoreCase) ? value : Path.GetFullPath(Path.Combine(Root, value)) : null;
        return rows.Cast<JsonObject>().Select(row =>
        {
            var id = row["id"]!.GetValue<string>(); var saved = state?[id] as JsonObject;
            return new Game { Id = id, Name = row["name"]!.GetValue<string>(), Library = row["source"]?.GetValue<string>() ?? "Folder",
                Location = Path.Combine(Root, "catalog", id), AppId = row["appid"]?.GetValue<string>(),
                Developer = row["developer"]?.GetValue<string>(), Release = row["release"]?.GetValue<string>(),
                Summary = row["summary"]?.GetValue<string>(), MetadataSource = row["metadata_source"]?.GetValue<string>(),
                PosterPath = Art(row, "poster"), CapsulePath = Art(row, "capsule"), HeroPath = Art(row, "hero"),
                Blocked = !string.IsNullOrWhiteSpace(row["blocked"]?.GetValue<string>()), BlockedReason = row["blocked"]?.GetValue<string>(),
                Tested = false, TestStatus = "Untested", Notes = "", EngineRow = null, RuntimeProvider = null, Profile = null,
                Installed = saved?["installed"]?.GetValue<bool>() == true,
                InstalledOn = saved?["installed"]?.GetValue<bool>() == true ? "windows" : null,
                NrStrength = saved?["nr"]?.GetValue<double>(), SharpeningStrength = saved?["sharp"]?.GetValue<double>(),
                MfgMultiplier = saved?["mfg"]?.GetValue<string>() };
        }).ToList();
    }

    public static void SaveGameState(IEnumerable<Game> games)
    {
        var state = new JsonObject();
        foreach (var game in games)
            state[game.Id] = new JsonObject { ["installed"] = game.Installed, ["nr"] = game.NrStrength,
                ["sharp"] = game.SharpeningStrength, ["mfg"] = game.MfgMultiplier };
        Atomic(Path.Combine(LocalAppData, "game-state.json"), state.ToJsonString(json));
    }

    internal static void SaveSelection() => Atomic(Path.Combine(LocalAppData, "selection.json"), JsonSerializer.Serialize(Selection.ToArray()));

    static void Atomic(string path, string content)
    {
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.WriteAllText(temporary, content); File.Move(temporary, path, true); }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}

public sealed class SampleSelection : HashSet<string>
{
    internal void Restore(string path, HashSet<string> allowed)
    {
        base.Clear();
        if (!File.Exists(path) || new FileInfo(path).Length > 256 * 1024) return;
        foreach (var id in JsonSerializer.Deserialize<string[]>(File.ReadAllText(path)) ?? [])
            if (allowed.Contains(id)) base.Add(id);
    }
    public new bool Add(string value) { var result = base.Add(value); SampleProfile.SaveSelection(); return result; }
    public new bool Remove(string value) { var result = base.Remove(value); SampleProfile.SaveSelection(); return result; }
    public new void Clear() { base.Clear(); SampleProfile.SaveSelection(); }
    public new void UnionWith(IEnumerable<string> values) { base.UnionWith(values); SampleProfile.SaveSelection(); }
    public new void ExceptWith(IEnumerable<string> values) { base.ExceptWith(values); SampleProfile.SaveSelection(); }
    public new void IntersectWith(IEnumerable<string> values) { base.IntersectWith(values); SampleProfile.SaveSelection(); }
    public new int RemoveWhere(Predicate<string> match) { var result = base.RemoveWhere(match); SampleProfile.SaveSelection(); return result; }
}
