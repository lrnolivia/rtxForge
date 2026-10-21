using System.Text.Json;
using System.Text.Json.Nodes;
using RtxForge.Windows;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

static class Program
{
    static int checks;
    static void Check(bool result, string message) { if (!result) throw new Exception(message); checks++; }
    static void Reject(Action action, string message) { try { action(); } catch (Exception) { checks++; return; } throw new Exception(message); }
    static async Task Main()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var live = Path.Combine(local, "rtxForge", "settings.json");
        var before = File.ReadAllBytes(live);
        var root = Path.Combine(local, "rtxForge-samples", "tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var path = Path.Combine(root, "library.json");
        var games = new JsonArray();
        foreach (var index in Enumerable.Range(0, 3)) games.Add(new JsonObject { ["id"] = "sample_" + index.ToString("x24"), ["name"] = "Sample " + index, ["source"] = "Steam" });
        void Manifest(JsonArray rows) => File.WriteAllText(path, new JsonObject { ["schema"] = 1, ["kind"] = "rtxforge-private-sample", ["games"] = rows }.ToJsonString());
        Manifest(games);
        SampleProfile.Configure(["sample.exe", "--sample-library", path]);
        Check(SampleProfile.CatalogCount == 3, "Catalog count");
        var service = new PreviewForgeService();
        Check(service.IsPreview && service.Settings.LibraryView == "posters", "Sample service/layout");
        var initial = await service.ScanAsync();
        SampleProfile.Selection.Add(initial[1].Id);
        SampleProfile.Configure(["sample.exe", "--sample-library", path]);
        Check(SampleProfile.Selection.Contains(initial[1].Id), "Selection/relaunch");
        Check(initial.Count == 3 && initial.All(x => !x.Installed && !x.Managed && !x.Tested && x.EngineRow is null), "Fresh display-only state");
        Check(initial.All(x => x.Location.StartsWith(root + Path.DirectorySeparatorChar)), "Private locations");
        LibraryLocations.Remove(service.Settings, [initial[0]]); service.Settings.Save();
        Check(File.Exists(SampleProfile.SettingsPath), "Saved isolated settings");
        var restarted = new PreviewForgeService();
        var visible = await restarted.ScanAsync();
        Check(visible.Count == 2 && visible.All(x => x.Id != initial[0].Id), "Remove/relaunch");
        var edited = ForgeSettings.EditOverlay(x => x.PanelHotkey = "F10");
        Check(ForgeSettings.Load().PanelHotkey == "F10", "Static overlay edit isolation");
        service.Settings.Theme = "light"; service.Settings.Save(preserveOverlay: true);
        Check(ForgeSettings.Load().PanelHotkey == "F10" && ForgeSettings.Load().Theme == "light", "preserveOverlay uses sample");
        Check(service.Settings.Clone().RemovedGames.Count == 1, "Clone keeps sample removal");
        OverlayHelper.ConfigureStartup(edited);
        Check((await OverlayHelper.CommandAsync("exit"))!.Contains("sample"), "No live helper command");
        var engine = await EngineForgeService.TryStartAsync();
        Check(engine.Service is null && engine.Problem!.Contains("disabled"), "Real engine fail closed");
        var review = await restarted.PrepareAsync("install", visible, restarted.Settings.Presets, "nr-mfg");
        var steps = new CaptureProgress();
        var timer = System.Diagnostics.Stopwatch.StartNew();
        Check(await restarted.ExecuteAsync(review, steps) == 2, "Simulated batch install");
        Check(timer.Elapsed.TotalSeconds is >= 9.9 and < 14, "Batch takes ten seconds, not ten per game");
        Console.WriteLine($"Batch duration: {timer.Elapsed.TotalSeconds:F2}s");
        var fractions = steps.Values.Where(step => step.Fraction.HasValue).Select(step => step.Fraction!.Value).ToArray();
        Check(fractions.Length > 100 && fractions.First() < .05 && fractions.Last() == 1,
            "Determinate progress spans the full duration");
        Check(fractions.Zip(fractions.Skip(1)).All(pair => pair.First <= pair.Second), "Monotonic progress");
        Check((await new PreviewForgeService().ScanAsync()).Count(x => x.Installed) == 2, "Simulation persists separately");
        timer.Restart();
        await SampleInstallProgress.WaitAsync(0, 1, visible[0], new CaptureProgress(), default);
        Check(timer.Elapsed.TotalSeconds is >= 9.9 and < 14, "Single-game duration");
        Console.WriteLine($"Single-game duration: {timer.Elapsed.TotalSeconds:F2}s");
        var cancellation = new CancellationTokenSource(120);
        var cancelled = await restarted.PrepareAsync("install", [initial[0]], restarted.Settings.Presets, "nr-mfg");
        try { await restarted.ExecuteAsync(cancelled, new CaptureProgress(), cancellation.Token); throw new Exception("Cancellation ignored"); }
        catch (OperationCanceledException) { checks++; }
        Check(!initial[0].Installed && (await new PreviewForgeService().ScanAsync()).Count(x => x.Installed) == 2, "Cancellation preserves saved state");
        Check(!Directory.Exists(Path.Combine(root, "catalog")), "Simulation never visits target folders");
        Check(before.SequenceEqual(File.ReadAllBytes(live)), "Live settings bytes unchanged");
        Reject(() => SampleProfile.Configure(["sample.exe"]), "Missing manifest accepted");
        Reject(() => SampleProfile.Configure(["sample.exe", "--sample-library", live]), "Real settings path accepted");
        File.WriteAllText(path, "{invalid");
        Reject(() => SampleProfile.Configure(["sample.exe", "--sample-library", path]), "Malformed manifest accepted");
        Check(SampleProfile.Root == "", "Invalid manifest leaves profile unconfigured");
        Console.WriteLine($"PASS {checks} sample isolation checks; live settings bytes unchanged; no real engine, helper, game paths.");
    }

    sealed class CaptureProgress : IProgress<OperationStep>
    {
        public List<OperationStep> Values { get; } = [];
        public void Report(OperationStep value) => Values.Add(value);
    }
}
