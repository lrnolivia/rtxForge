using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace RtxForge.Windows.Services;

/// <summary>Display-only library snapshot. All write reviews still inspect current game files.</summary>
internal static class LibrarySnapshot
{
    const int Limit = 4 * 1024 * 1024;
    public static string Key(string provider, IEnumerable<string> folders, IEnumerable<string> libraries) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        { provider, folders = folders.Order(StringComparer.OrdinalIgnoreCase), libraries = libraries.Order(StringComparer.OrdinalIgnoreCase) }))));

    public static JsonArray Read(string path, string key)
    {
        try
        {
            var file = new FileInfo(path);
            if (!file.Exists || file.Length > Limit) return [];
            var saved = JsonNode.Parse(File.ReadAllText(path), documentOptions: new() { MaxDepth = 32 }) as JsonObject;
            if (saved?["schema"]?.GetValue<int>() != 1 || saved["key"]?.GetValue<string>() != key
                || saved["rows"] is not JsonArray rows || rows.Count > 2000
                || rows.Any(row => row is not JsonObject || string.IsNullOrWhiteSpace(row["game"]?.GetValue<string>()))) return [];
            return rows;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException or FormatException)
        { return []; }
    }

    public static void Write(string path, string key, JsonArray rows)
    {
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            var text = new JsonObject { ["schema"] = 1, ["key"] = key, ["rows"] = rows.DeepClone() }.ToJsonString();
            if (Encoding.UTF8.GetByteCount(text) > Limit || rows.Count > 2000) return;
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(temporary, text, new UTF8Encoding(false)); File.Move(temporary, path, true);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }
        finally { try { File.Delete(temporary); } catch (Exception error) when (error is IOException or UnauthorizedAccessException) { } }
    }
}
