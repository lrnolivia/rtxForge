using System.Text.Json;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

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
var defaults = new ForgeSettings();
if (defaults.PanelHotkey != "Insert" || OverlayShortcut.Decode(defaults.PanelHotkey) != (0u, 0x2Du))
    throw new Exception("Overlay must have a single-key Insert default");
foreach (var key in OverlayShortcut.Choices)
{
    var settings = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(new ForgeSettings { PanelHotkey = key, OverlayHelper = false, OverlayStartWithWindows = false, OverlayMaterial = "mica" }))!;
    if (settings.PanelHotkey != key || settings.OverlayHelper || settings.OverlayStartWithWindows || settings.OverlayMaterial != "mica")
        throw new Exception("Overlay choices were not retained");
    var (modifiers, code) = OverlayShortcut.Decode(key);
    if (key == "F8" && (modifiers != 0 || code != 0x77) || key == "Disabled" && code != 0)
        throw new Exception("Single key or disabled shortcut changed");
}
Console.WriteLine("PASS: single-key overlay default, legacy shortcuts, disabled helper/startup and material round trips.");
foreach (var controls in new[] { "unified", "classic" })
foreach (var renderer in new[] { "rtxforge", "optiscaler" })
{
    var original = new ForgeSettings { OverlayControls = controls, OverlayRenderer = renderer, OptiScalerHotkey = "F8", NrStrength = 1.25 };
    var saved = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(original))!;
    var manager = new ForgeSettings { NrStrength = .75, RuntimeProvider = "feeder" };
    manager.CopyOverlayFrom(saved);
    if (manager.OverlayControls != controls || manager.OverlayRenderer != renderer || manager.OptiScalerHotkey != "F8"
        || manager.NrStrength != .75 || manager.RuntimeProvider != "feeder") throw new Exception("Overlay preferences changed game tuning");
}
Console.WriteLine("PASS: renderer/layout/native shortcut persistence and overlay-only merge preserve tuning.");

var firstGame = new Game { Id = "full", Name = "Full" };
var otherGame = new Game { Id = "partial", Name = "Partial" };
var firstReview = new OperationReview("install", "full-token", [new(firstGame, "", "NR + MFG")], []);
var otherReview = new OperationReview("install", "nr-token", [new(otherGame, "", "NR Only")], []);
var combined = (firstReview with { Supported = [new(otherReview, true, false, "No FG")] }).IncludeSupported();
if (combined.Ready.Count != 2 || combined.Steps.Count != 2 || combined.Steps[0].Token != "full-token" || combined.Steps[1].Token != "nr-token"
    || combined.Steps[1].Ready.Single().Game.Id != "partial" || combined.Supported.Count != 0)
    throw new Exception("Supported-feature review lost the exact per-mode token or target");
Console.WriteLine("PASS: supported subsets retain distinct exact review tokens and targets.");

foreach (var raw in new[] { "false", "null", "true", "\"unknown\"" })
{
    var game = new Game { Id = "caps", Name = "Caps", EngineRow = System.Text.Json.Nodes.JsonNode.Parse("{\"anti_cheat\":" + raw + "}")!.AsObject() };
    if (game.AntiCheatDetected != (raw is not "false" and not "null")) throw new Exception("Partial-support anti-cheat filtering changed");
}
Console.WriteLine("PASS: false anti-cheat flags admit support review; true and malformed flags stay excluded.");
