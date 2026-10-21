using System.Text.Json.Nodes;
using RtxForge.Windows.Services;

var folder = Path.Combine(Path.GetTempPath(), "rtxforge-library-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(folder);
var path = Path.Combine(folder, "snapshot.json");
int checks = 0;
void Check(bool valid, string message) { if (!valid) throw new Exception(message); checks++; }
try
{
    var key = LibrarySnapshot.Key("skynizz", ["B", "A"], ["Library"]);
    Check(key == LibrarySnapshot.Key("skynizz", ["A", "B"], ["Library"]), "folder order invalidates snapshot");
    Check(key != LibrarySnapshot.Key("feeder", ["A", "B"], ["Library"]), "provider change reuses old presentation");
    Check(key != LibrarySnapshot.Key("skynizz", ["A"], ["Library"]), "folder change reuses old presentation");
    Check(LibrarySnapshot.Read(path, key).Count == 0, "missing snapshot fails cold start");
    var rows = new JsonArray(new JsonObject { ["game"] = "C:/Games/One", ["name"] = "One", ["installed"] = true });
    LibrarySnapshot.Write(path, key, rows);
    Check(LibrarySnapshot.Read(path, key)[0]?["name"]?.GetValue<string>() == "One", "saved library does not round trip");
    Check(LibrarySnapshot.Read(path, "other").Count == 0, "different settings reuse snapshot");
    Check(Directory.GetFiles(folder, "*.tmp").Length == 0, "successful write retains temporary file");
    LibrarySnapshot.Write(path, key, new()); Check(LibrarySnapshot.Read(path, key).Count == 0, "empty rescan retains removed games");
    foreach (var invalid in new[] { "{", "[]", "{\"schema\":2}", "{\"schema\":1,\"key\":\"" + key + "\",\"rows\":[{}]}",
        "{\"schema\":1,\"key\":\"" + key + "\",\"rows\":[{\"game\":2}]}" })
    { File.WriteAllText(path, invalid); Check(LibrarySnapshot.Read(path, key).Count == 0, "invalid snapshot prevents fresh startup"); }
    LibrarySnapshot.Write(path, key, rows);
    var good = File.ReadAllBytes(path);
    LibrarySnapshot.Write(path, key, new JsonArray(new JsonObject { ["game"] = "Game", ["name"] = new string('x', 4 * 1024 * 1024) }));
    Check(good.SequenceEqual(File.ReadAllBytes(path)), "oversize snapshot replaces last good library");
    File.WriteAllText(path, new string('x', 4 * 1024 * 1024 + 1));
    Check(LibrarySnapshot.Read(path, key).Count == 0, "oversize input parsed");
    Console.WriteLine($"PASS: {checks} display snapshot checks: settings identity, fresh replacement, corruption and bounded atomic storage.");
}
finally { Directory.Delete(folder, true); }
