using System.Text.Json;
using RtxForge.Windows.Models;

var count = 0;
foreach (var raw in new[] { "0", "2", "3", "4", "5", "6", "\"0\"", "\"2\"", "\"3\"", "\"4\"", "\"5\"", "\"6\"", "\"auto\"", "null", "1", "7", "-1", "4.5", "\"invalid\"", "{}", "[]", "true" })
{
    var input = "{\"runtime_provider\":\"skynizz\",\"default_profile\":\"nr-mfg\",\"nr_runtime\":\"model.dll\",\"game_folders\":[\"pinned\"],\"game_artwork\":{\"one\":{\"poster\":\"custom.png\"}},\"mfg_multiplier\":" + raw + "}";
    var settings = JsonSerializer.Deserialize<ForgeSettings>(input) ?? throw new Exception("Missing settings");
    var token = raw.Trim('"');
    var expected = token is "0" or "2" or "3" or "4" or "5" or "6" ? token : "auto";
    if (settings.MfgMultiplier != expected || settings.RuntimeProvider != "skynizz"
        || settings.DefaultProfile != "nr-mfg" || settings.NrRuntime != "model.dll" || settings.GameFolders.Single() != "pinned")
        throw new Exception("A multiplier reset unrelated settings: " + raw);
    using var saved = JsonDocument.Parse(JsonSerializer.Serialize(settings));
    var multiplier = saved.RootElement.GetProperty("mfg_multiplier");
    if (expected == "auto" ? multiplier.GetString() != "auto" : multiplier.GetInt32().ToString() != expected)
        throw new Exception("Not compatible with shared engine settings: " + raw);
    if (saved.RootElement.GetProperty("game_artwork").GetProperty("one").GetProperty("poster").GetString() != "custom.png")
        throw new Exception("Windows dropped shared artwork settings");
    if (settings.Clone().MfgMultiplier != expected) throw new Exception("Clone changed tuning");
    count++;
}
Console.WriteLine($"PASS: {count} numeric/text multiplier and shared-settings round trips.");
