// Windows integration smoke: the app's real service/host, temporary game files only.
// Put a usable Python 3.11+ on PATH. Requires the configured runtime catalog online.
using System.Buffers.Binary;
using System.Text.Json.Nodes;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

var root = Path.Combine(Path.GetTempPath(), "rtxforge-dlss-service-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
Environment.SetEnvironmentVariable("RTXFORGE_STATE_ROOT", Path.Combine(root, "state"));
Environment.SetEnvironmentVariable("RTXFORGE_DLSS_UNLOCKED_STATE", Path.Combine(root, "engine-state"));
var bytes = new byte[256];
bytes[0] = (byte)'M'; bytes[1] = (byte)'Z';
BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(60), 64);
new byte[] { 80, 69, 0, 0, 100, 134 }.CopyTo(bytes, 64);
BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(128), 0xFEEF04BD);
BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(132), 0x10000);
BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(136), 1 << 16);
Game Game(string folder)
{
    var path = Path.Combine(root, folder);
    Directory.CreateDirectory(path);
    File.WriteAllBytes(Path.Combine(path, "Game.exe"), bytes);
    var dll = Path.Combine(path, "Engine", "Plugins", "DLSS", "nvngx_dlss.dll");
    Directory.CreateDirectory(Path.GetDirectoryName(dll)!);
    File.WriteAllBytes(dll, bytes);
    return new Game { Id = path, Location = path, Name = "Same name",
        EngineRow = new JsonObject { ["name"] = "Same name", ["game"] = path } };
}
var untouched = Game("unselected");
var chosen = Game("selected");
var dll = Path.Combine(chosen.Location, "Engine", "Plugins", "DLSS", "nvngx_dlss.dll");
var (engine, problem) = await EngineForgeService.TryStartAsync();
var service = engine ?? throw new Exception(problem);
try
{
    var review = await service.PrepareAsync("update-dlss", [chosen], new Tuning(2, .5, "auto"), "mfg-only");
    if (review.Ready.Count != 1 || review.Ready[0].Game.Id != chosen.Id || !review.Ready[0].Detail.Contains("1.0.0.0 →"))
        throw new Exception("Review lost the installation identity or version transition");
    if (!File.ReadAllBytes(dll).SequenceEqual(bytes)) throw new Exception("Review wrote the game");
    if (await service.ExecuteAsync(review, new InlineProgress<OperationStep>(_ => { })) != 1)
        throw new Exception("Update did not report the actual changed game");
    if (File.ReadAllBytes(dll).SequenceEqual(bytes)) throw new Exception("Updater left the old DLL in place");
    var inventory = await service.DlssInventoryAsync(chosen);
    if (inventory.Files.Count != 1 || inventory.Files[0].Current == "1.0.0.0")
        throw new Exception("Inventory did not read back the replacement version");
    var current = await service.PrepareAsync("update-dlss", [chosen], new Tuning(2, .5, "auto"), "mfg-only");
    if (current.Ready.Count != 0 || current.Blocked.Count != 1)
        throw new Exception("Current DLL was still advertised as ready");
    var restore = await service.ReviewDlssRestoreAsync(chosen);
    await service.RunReviewAsync(restore);
    if (!File.ReadAllBytes(dll).SequenceEqual(bytes)) throw new Exception("Restore did not recover the exact original");
    if (!File.ReadAllBytes(Path.Combine(untouched.Location, "Engine", "Plugins", "DLSS", "nvngx_dlss.dll")).SequenceEqual(bytes))
        throw new Exception("An unselected installation changed");
    Console.WriteLine("PASS: real app service → Python host → reviewed update → version readback → no-op review → exact restore; unselected game unchanged.");
}
finally
{
    service.Dispose();
    Directory.Delete(root, recursive: true);
}

sealed class InlineProgress<T>(Action<T> report) : IProgress<T>
{
    public void Report(T value) => report(value);
}

// Application-update metadata is outside this console harness; every DLSS
// service method above is compiled directly from the shipped implementation.
namespace RtxForge.Windows
{
    static class MainWindow
    {
        public static string AppVersion => throw new NotSupportedException("Application updates are not exercised here.");
    }
}
