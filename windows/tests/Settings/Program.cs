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
var allControls = FeatureControlSchema.Resolve(new ForgeSettings().Presets);
foreach (var control in FeatureControlSchema.Shared.Controls)
{
    var value = control.Values.Length > 0 ? control.Values[^1] : control.Max;
    FeatureControlSchema.Put(allControls, control, value);
}
var complete = FeatureControlSchema.Tuning(allControls);
var presetSettings = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(new ForgeSettings { FeatureControls = complete.FeatureControls }))!;
if (!System.Text.Json.Nodes.JsonNode.DeepEquals(allControls, FeatureControlSchema.Resolve(presetSettings.Presets)))
    throw new Exception("The full preset lost control values or units during persistence.");
if (FeatureControlSchema.Shared.Controls.Length != 24 || FeatureControlSchema.Shared.Controls.Single(c => c.Key == "colour").Max != 4)
    throw new Exception("The app lost the shared control vocabulary or colour range.");
Console.WriteLine("PASS: all 24 ordered feature controls round trip with native units, including extended colour and exact MFG choices.");
var defaults = new ForgeSettings();
if (!defaults.OptiScalerUi || !defaults.ReShadeUi || defaults.OptiScalerIntro || defaults.ReShadeIntro)
    throw new Exception("Game menus must be independent of the default-hidden welcome messages");
for (int mask = 0; mask < 16; mask++)
{
    var original = new ForgeSettings { OptiScalerUi = (mask & 1) != 0, OptiScalerIntro = (mask & 2) != 0,
        ReShadeUi = (mask & 4) != 0, ReShadeIntro = (mask & 8) != 0, NrStrength = 1.25 };
    var saved = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(original))!;
    var other = new ForgeSettings { NrStrength = .75, RuntimeProvider = "feeder" };
    other.CopyOverlayFrom(saved);
    if (other.OptiScalerUi != original.OptiScalerUi || other.OptiScalerIntro != original.OptiScalerIntro
        || other.ReShadeUi != original.ReShadeUi || other.ReShadeIntro != original.ReShadeIntro
        || other.NrStrength != .75 || other.RuntimeProvider != "feeder")
        throw new Exception("Menu/intro settings were coupled or reset rendering settings");
}
Console.WriteLine("PASS: all 16 independent game-menu/welcome combinations round trip and merge without changing tuning.");
if (defaults.PanelHotkey != "End" || !OverlayShortcut.TryParse(defaults.PanelHotkey, out _, out var defaultKey, out _) || defaultKey != (0u, 0x23u))
    throw new Exception("Overlay must have a single-key End default");
foreach (var key in new[] { "End", "Home", "Ctrl+Shift+R", "Ctrl+Alt+R", "Ctrl+Shift+F10", "F8", "Ctrl+Num3", "Shift+Backtick", "Disabled" })
{
    var settings = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(new ForgeSettings { PanelHotkey = key, OverlayHelper = false, OverlayStartWithWindows = false, OverlayMaterial = "mica" }))!;
    if (settings.PanelHotkey != key || settings.OverlayHelper || settings.OverlayStartWithWindows || settings.OverlayMaterial != "mica")
        throw new Exception("Overlay choices were not retained");
    if (!OverlayShortcut.TryParse(key, out var normalized, out var decoded, out _) || normalized != key)
        throw new Exception("Custom shortcut could not be decoded: " + key);
    var (modifiers, code) = decoded;
    if (key == "F8" && (modifiers != 0 || code != 0x77) || key == "Disabled" && code != 0)
        throw new Exception("Single key or disabled shortcut changed");
}
var migrated = JsonSerializer.Deserialize<ForgeSettings>("{\"panel_hotkey\":\"Insert\",\"optiscaler_hotkey\":\"Insert\",\"nr_strength\":1.25,\"unrelated\":true}")!;
if (migrated.PanelHotkey != "End" || migrated.OptiScalerHotkey != "Insert" || migrated.NrStrength != 1.25
    || !migrated.AdditionalSettings["unrelated"].GetBoolean()) throw new Exception("Insert migration changed unrelated settings");
foreach (var invalid in new string?[] { null, "", "Insert", "Ctrl+Insert", "Ctrl", "Shift", "Win+R", "Ctrl+Ctrl+R", "R+Ctrl", "Ctrl++R", "Escape", "Tab", "F12", "Alt+F4", "Alt+Space", "Ctrl+Alt+Delete", "arbitrary" })
    if (OverlayShortcut.TryParse(invalid, out _, out var rejected, out _) || rejected != (0u, 0u))
        throw new Exception("Invalid/reserved shortcut was registered: " + invalid);
if (!OverlayShortcut.TryParse(" shift + ctrl + r ", out var canonical, out var canonicalKey, out _) || canonical != "Ctrl+Shift+R" || canonicalKey != (6u, 0x52u))
    throw new Exception("Custom modifiers were not normalized");
if (new ForgeSettings { PanelHotkey = "invalid" }.PanelHotkey != "invalid") throw new Exception("An invalid binding silently selected a different shortcut");
if (!migrated.PanelHotkeyMigrated || migrated.Clone().PanelHotkeyMigrated
    || JsonSerializer.Serialize(migrated).Contains("PanelHotkeyMigrated")) throw new Exception("Shortcut migration was not a one-time settings-only operation");
var shortcutCount = 0;
for (uint key = 0; key < 256; key++)
for (uint modifiers = 0; modifiers < 16; modifiers++)
{
    if (!OverlayShortcut.TryCreate(key, modifiers, out var label, out _)) continue;
    if (!OverlayShortcut.TryParse(label, out var roundTrip, out var decoded, out _) || roundTrip != label || decoded != (modifiers, key))
        throw new Exception("Recorder and persisted shortcut disagree: " + label);
    shortcutCount++;
}
Console.WriteLine($"PASS: End default, Insert migration, preserved legacy/disabled choices and {shortcutCount} custom binding round trips; reserved/malformed shortcuts refused.");
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
