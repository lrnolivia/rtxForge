using System.Text.Json;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

var count = 0;
if (!new ForgeSettings().AutoUpdate) throw new Exception("Automatic app updates must default on.");
var manualUpdates = JsonSerializer.Deserialize<ForgeSettings>("{\"auto_update\":false}")!;
if (manualUpdates.AutoUpdate || manualUpdates.Clone().AutoUpdate
    || JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(manualUpdates))!.AutoUpdate)
    throw new Exception("The automatic update opt-out did not persist.");
Console.WriteLine("PASS: automatic application updates default on and the opt-out survives clone and persistence.");
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
if (FeatureControlSchema.Shared.Controls.Length != 29 || FeatureControlSchema.Shared.Controls.Single(c => c.Key == "colour").Max != 4)
    throw new Exception("The app lost the shared control vocabulary or colour range.");
Console.WriteLine("PASS: all 29 ordered feature controls round trip with native units, including extended color and exact MFG choices.");
var defaults = new ForgeSettings();
if (!defaults.OptiScalerUi || !defaults.ReShadeUi || defaults.OptiScalerIntro || defaults.ReShadeIntro)
    throw new Exception("Game menus must be independent of the default-hidden welcome messages");
for (int mask = 0; mask < 16; mask++)
{
    var original = new ForgeSettings { OptiScalerUi = (mask & 1) != 0, OptiScalerIntro = (mask & 2) != 0,
        ReShadeUi = (mask & 4) != 0, ReShadeIntro = (mask & 8) != 0, NrStrength = 1.25 };
    var saved = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(original))!;
    var other = new ForgeSettings { NrStrength = .75, RuntimeProvider = "dlss-unlocked" };
    other.CopyOverlayFrom(saved);
    if (other.OptiScalerUi != original.OptiScalerUi || other.OptiScalerIntro != original.OptiScalerIntro
        || other.ReShadeUi != original.ReShadeUi || other.ReShadeIntro != original.ReShadeIntro
        || other.NrStrength != .75 || other.RuntimeProvider != "dlss-unlocked")
        throw new Exception("Menu/intro settings were coupled or reset rendering settings");
}
Console.WriteLine("PASS: all 16 independent game-menu/welcome combinations round trip and merge without changing tuning.");
if (defaults.PanelHotkey != "Delete" || !OverlayShortcut.TryParse(defaults.PanelHotkey, out _, out var defaultKey, out _) || defaultKey != (0u, 0x2Eu))
    throw new Exception("Overlay must have a single-key Delete default");
foreach (var key in new[] { "Delete", "ScrollLock", "Pause", "Home", "Ctrl+Shift+R", "Ctrl+Alt+R", "Ctrl+Shift+F10", "F8", "Ctrl+Num3", "Shift+Backtick", "Disabled" })
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
if (migrated.PanelHotkey != "Delete" || migrated.OptiScalerHotkey != "Insert" || migrated.NrStrength != 1.25
    || !migrated.AdditionalSettings["unrelated"].GetBoolean()) throw new Exception("Insert migration changed unrelated settings");
var retiredEnd = JsonSerializer.Deserialize<ForgeSettings>("{\"panel_hotkey\":\"End\",\"optiscaler_hotkey\":\"Insert\",\"reshade_ui\":true,\"nr_strength\":1.25}")!;
if (retiredEnd.PanelHotkey != "Delete" || !retiredEnd.PanelHotkeyMigrated || retiredEnd.OptiScalerHotkey != "Insert"
    || !retiredEnd.ReShadeUi || retiredEnd.NrStrength != 1.25) throw new Exception("End migration changed another overlay or tuning");
foreach (var invalid in new string?[] { null, "", "Insert", "Ctrl+Insert", "End", "Ctrl+End", "Ctrl", "Shift", "Win+R", "Ctrl+Ctrl+R", "R+Ctrl", "Ctrl++R", "Escape", "Tab", "F12", "Alt+F4", "Alt+Space", "Ctrl+Alt+Delete", "arbitrary" })
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
Console.WriteLine($"PASS: Delete default, retired Insert/End migration, unchanged other overlays and {shortcutCount} custom binding round trips; reserved/malformed shortcuts refused.");
foreach (var controls in new[] { "unified", "classic" })
foreach (var renderer in new[] { "game", "optiscaler" })
{
    var original = new ForgeSettings { OverlayControls = controls, OverlayRenderer = renderer, OptiScalerHotkey = "F8", NrStrength = 1.25 };
    var saved = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(original))!;
    var manager = new ForgeSettings { NrStrength = .75, RuntimeProvider = "dlss-unlocked" };
    manager.CopyOverlayFrom(saved);
    if (manager.OverlayControls != controls || manager.OverlayRenderer != renderer || manager.OptiScalerHotkey != "F8"
        || manager.NrStrength != .75 || manager.RuntimeProvider != "dlss-unlocked") throw new Exception("Overlay preferences changed game tuning");
}
if (JsonSerializer.Deserialize<ForgeSettings>("{\"runtime_provider\":\"feeder\"}")!.RuntimeProvider != "skynizz")
    throw new Exception("The retired Feeder-only package choice did not migrate to a DLSS package");
if (JsonSerializer.Deserialize<ForgeSettings>("{\"runtime_provider\":\"y4my\"}")!.RuntimeProvider != "skynizz")
    throw new Exception("The hidden y4my package choice did not migrate to Skynizz on Windows");
{
    // A game's own package survives a save, repairs keep the installed package, and unknown keys fall back.
    var mixed = JsonSerializer.Deserialize<ForgeSettings>("{\"game_packages\":{\"C:\\\\Games\\\\A\":\"dlss-unlocked\",\"C:\\\\Games\\\\B\":\"custom-x\"}}")!;
    var a = new Game { Id = @"C:\Games\A", Name = "A" };
    var b = new Game { Id = @"C:\Games\B", Name = "B" };
    var installed = new Game { Id = @"C:\Games\A", Name = "A", Installed = true, RuntimeProvider = "skynizz" };
    if (mixed.PackageFor(a, "install") != "dlss-unlocked" || mixed.PackageFor(b, "install") != "skynizz"
        || mixed.PackageFor(installed, "repair") != "skynizz" || mixed.PackageFor(installed, "install") != "dlss-unlocked"
        || JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(mixed))!.GamePackage(a) != "dlss-unlocked")
        throw new Exception("Per-game package choices did not resolve");
}
if (JsonSerializer.Deserialize<ForgeSettings>("{\"overlay_renderer\":\"rtxforge\"}")!.OverlayRenderer != "game")
    throw new Exception("The retired desktop overlay did not migrate to the in-game panel");
Console.WriteLine("PASS: renderer/layout/native shortcut persistence and overlay-only merge preserve tuning; the retired desktop overlay reads as the in-game panel.");

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

foreach (var raw in new[] { "false", "null", "true", "\"unknown\"" })
{
    var game = new Game { Id = "feeder", Name = "Feeder candidate", EngineRow = System.Text.Json.Nodes.JsonNode.Parse(
        "{\"install_provider\":\"feeder\",\"feeder_available\":" + raw + "}")!.AsObject() };
    if (game.UsesFeeder != (raw == "true") || game.IsFeeder || game.Installed)
        throw new Exception("Feeder capability was mistaken for an installed or managed runtime");
    if (raw == "true" && game.InstallLabel != "Install Feeder NR") throw new Exception("Fresh Feeder target has an update-only action");
}
var installedFeeder = new Game { Id = "managed-feeder", Name = "Installed Feeder", Installed = true, RuntimeProvider = "feeder" };
if (!installedFeeder.UsesFeeder || installedFeeder.InstallLabel != "Update Feeder NR") throw new Exception("Existing Feeder update route changed");
Console.WriteLine("PASS: fresh Feeder capability stays separate from installation ownership and labels.");

var mfgValues = FeatureControlSchema.Resolve(new Tuning(1.25, .4, "auto"));
var mfgPreset = new MfgPreset(mfgValues);
foreach (var selection in Enumerable.Range(0, MfgPreset.Modes.Length))
foreach (var ratio in MfgPreset.Multipliers)
{
    mfgPreset.SetEnabled(true); mfgPreset.SetMode(selection); mfgPreset.SetMultiplier(ratio); mfgPreset.Store(mfgValues);
    var requested = FeatureControlSchema.Tuning(mfgValues);
    var persisted = FeatureControlSchema.Resolve(JsonSerializer.Deserialize<Tuning>(JsonSerializer.Serialize(requested))!);
    var restored = new MfgPreset(persisted);
    if (!restored.Enabled || restored.Mode != selection || selection != 0 && restored.Multiplier != ratio
        || requested.MfgMultiplier != (selection == 0 ? "auto" : ratio.ToString()) || requested.NrStrength != 1.25
        || FeatureControlSchema.Read(persisted["dynamic_mfg"]) != (selection == 2 ? 1 : 0))
        throw new Exception("MFG mode/ratio did not survive preset persistence");
    mfgPreset.SetEnabled(false); mfgPreset.Store(mfgValues);
    if (FeatureControlSchema.Tuning(mfgValues).MfgMultiplier != "0" || FeatureControlSchema.Read(mfgValues["dynamic_mfg"]) != 0)
        throw new Exception("MFG Off left a dynamic request enabled");
    var off = new MfgPreset(FeatureControlSchema.Resolve(FeatureControlSchema.Tuning(mfgValues)));
    if (off.Enabled || off.Mode != selection || off.Multiplier != ratio) throw new Exception("Saved Off lost the dormant mode or multiplier");
    mfgPreset.SetEnabled(true); mfgPreset.Store(mfgValues);
    if (mfgPreset.Mode != selection || mfgPreset.Multiplier != ratio) throw new Exception("MFG toggle lost its draft selection");
}
var dynamicField = FeatureControlSchema.Shared.Controls.Single(field => field.Key == "dynamic_mfg");
if (FeatureControlSchema.Available(dynamicField, "nr-only") || FeatureControlSchema.Available(dynamicField, "nr-mfg", true)
    || !FeatureControlSchema.Available(dynamicField, "mfg-only")) throw new Exception("Dynamic MFG availability crossed package boundaries");
Console.WriteLine("PASS: Auto/Custom/Dynamic, 2×–6×, independent On/Off and unchanged NR survive preset persistence.");
foreach (var raw in new[] { "true", "false", "null", "\"unknown\"" })
{
    var game = new Game { Id = "route", Name = "MFG route", RuntimeProvider = "skynizz",
        EngineRow = System.Text.Json.Nodes.JsonNode.Parse("{\"dynamic_mfg_available\":" + raw + "}")!.AsObject() };
    if (game.DynamicMfgAvailable != (raw == "true")) throw new Exception("Dynamic MFG availability was invented for an unknown route");
}
foreach (var (stored, expected) in new[] { ("{\"mfg_provider\":\"integrated\"}", "universal"),
             ("{\"mfg_provider\":\"integrated\",\"mfg_default_revision\":1}", "integrated"),
             ("{\"mfg_provider\":\"mfg-unlock\"}", "mfg-unlock"), ("{}", "universal") })
{
    var loaded = JsonSerializer.Deserialize<ForgeSettings>(stored)!.Migrated();
    if (loaded.MfgProvider != expected || loaded.MfgDefaultRevision != 1)
        throw new Exception("The Universal default migration changed a deliberate choice or skipped the old default: " + stored);
    if (JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(loaded))!.Migrated().MfgProvider != expected)
        throw new Exception("The Universal default migration ran twice");
}
Console.WriteLine("PASS: the old integrated default moves to Universal once; later choices stay.");

var defaultStats = JsonSerializer.Deserialize<ForgeSettings>("{}")!;
if (!defaultStats.OverlayLiveStats) throw new Exception("Legacy settings lost default live-stat visibility");
var hiddenStats = JsonSerializer.Deserialize<ForgeSettings>("{\"overlay_live_stats\":false,\"game_accents\":{\"sample\":\"#97c2bb\"}}")!;
var copiedStats = new ForgeSettings(); copiedStats.CopyOverlayFrom(hiddenStats);
if (copiedStats.OverlayLiveStats || JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(hiddenStats))!.OverlayLiveStats
    || hiddenStats.GameAccents["sample"] != "#97c2bb") throw new Exception("Live-stat preference did not survive copy/persistence");
Console.WriteLine("PASS: live statistics default on, persist off and copy without altering saved accents.");
if(!defaultStats.OverlayWelcome || defaultStats.VulkanMfgNativeMenu)
    throw new Exception("Welcome/native MFG UI defaults changed");
var quiet = JsonSerializer.Deserialize<ForgeSettings>("{\"overlay_welcome\":false,\"vulkan_mfg_native_menu\":true}")!;
var quietCopy = new ForgeSettings(); quietCopy.CopyOverlayFrom(quiet);
var quietSaved = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(quietCopy))!;
if(quietSaved.OverlayWelcome || !quietSaved.VulkanMfgNativeMenu)
    throw new Exception("Welcome and native MFG menu preferences are not independent/persistent");
Console.WriteLine("PASS: shared welcome on/native MFG menu off defaults, independent copy and persistence.");
if(defaultStats.OverlayWelcomePosition != "top-center") throw new Exception("Approved welcome default moved");
foreach(var position in ForgeSettings.WelcomePositions)
{
    var stored = JsonSerializer.Deserialize<ForgeSettings>("{\"overlay_welcome_position\":\"" + position + "\",\"overlay_welcome\":false}")!;
    var copy = new ForgeSettings(); copy.CopyOverlayFrom(stored);
    var roundTrip = JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(copy))!;
    if(roundTrip.OverlayWelcomePosition != position || roundTrip.OverlayWelcome)
        throw new Exception("Welcome position did not survive independent copy/persistence");
}
foreach(var value in new[] { "unknown", "", "TOP-RIGHT" })
    if(JsonSerializer.Deserialize<ForgeSettings>("{\"overlay_welcome_position\":\"" + value + "\"}")!.OverlayWelcomePosition != "top-center")
        throw new Exception("Unknown welcome position lost the safe default");
Console.WriteLine("PASS: all five welcome positions persist and copy; legacy/unknown values retain top center.");
var perGame = JsonSerializer.Deserialize<ForgeSettings>("{\"vulkan_experimental\":true,\"runtime_provider\":\"vulkan-native\",\"game_overlay_settings\":{\"one\":{\"overlay_welcome\":false,\"panel_hotkey\":\"F8\"}}}")!;
var gameOne = new Game { Id = "one", Name = "One", Location = "one" };
var gameTwo = new Game { Id = "two", Name = "Two", Location = "two" };
if (perGame.GameOverlayOptions(gameOne)["overlay_welcome"]!.GetValue<bool>() || !perGame.GameOverlayOptions(gameTwo)["overlay_welcome"]!.GetValue<bool>())
    throw new Exception("A per-game overlay choice leaked into another game.");
var copied = new ForgeSettings(); copied.CopyOverlayFrom(perGame);
copied.GameOverlaySettings["one"]["panel_hotkey"] = "Delete";
if (perGame.GameOverlaySettings["one"]["panel_hotkey"]!.ToString() != "F8" || perGame.RuntimeProvider != "skynizz")
    throw new Exception("Per-game overlay persistence was lost, or a saved Vulkan package choice did not read as automatic.");
if (perGame.OverlayReviewOptions(["one"])["target_games"]!.AsArray().Count != 1)
    throw new Exception("Overlay update review lost its explicit game scope.");
Console.WriteLine("PASS: per-game overlay isolation, independent copies, exact update scope and automatic Vulkan package.");

foreach (var theme in ForgeSettings.OverlayThemes)
{
    var settings = JsonSerializer.Deserialize<ForgeSettings>("{\"overlay_theme\":\"" + theme + "\"}")!;
    var copy = new ForgeSettings(); copy.CopyOverlayFrom(settings);
    if (JsonSerializer.Deserialize<ForgeSettings>(JsonSerializer.Serialize(copy))!.OverlayTheme != theme
        || copy.GameOverlayOptions()["overlay_theme"]!.ToString() != theme)
        throw new Exception("Overlay theme did not survive copy, persistence and helper settings");
}
if (JsonSerializer.Deserialize<ForgeSettings>("{\"overlay_theme\":\"unknown\"}")!.OverlayTheme != "dark")
    throw new Exception("Unknown overlay theme must preserve the existing dark default");
Console.WriteLine("PASS: Dark, Light and Follow app overlay themes persist and reach the helper; unknown themes retain Dark.");

var executableSettings = new ForgeSettings { GameExecutables = new() { ["G:/Games/One"] = "bin/game.exe" } };
var executableCopy = executableSettings.Clone();
if (executableCopy.GameExecutables["G:/Games/One"] != "bin/game.exe") throw new Exception("Executable choice was not persisted.");
var oldChoiceKey = executableSettings.ExecutableSelectionKey;
executableCopy.GameExecutables["G:/Games/One"] = "other.exe";
if (executableSettings.ExecutableSelectionKey != oldChoiceKey || executableCopy.ExecutableSelectionKey == oldChoiceKey)
    throw new Exception("Executable choices share storage or do not invalidate cached support.");
Console.WriteLine("PASS: per-game executable choices persist, clone independently and invalidate cached support.");
var offlinePart = new OperationReview("install", "offline-token", [], []) { OfflineNotice = "Offline only" };
var mixedReview = new OperationReview("install", "", [], []) { Steps = [offlinePart] };
if (mixedReview.RequiredTrust != "Offline only" || mixedReview.OfflineAcknowledged || mixedReview.Steps[0].OfflineAcknowledged)
    throw new Exception("Offline acknowledgement was missing or preselected.");
var acceptedOffline = mixedReview.AcknowledgeOffline(true);
if (!acceptedOffline.Steps[0].OfflineAcknowledged || mixedReview.Steps[0].OfflineAcknowledged
    || acceptedOffline.AcknowledgeOffline(false).Steps[0].OfflineAcknowledged)
    throw new Exception("Offline acknowledgement did not follow the exact operation steps independently.");
Console.WriteLine("PASS: offline acknowledgement starts unchecked and follows mixed-package review steps.");
