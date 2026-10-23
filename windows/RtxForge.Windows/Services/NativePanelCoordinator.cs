using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.UI.Dispatching;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Services;

/// <summary>Explicit game-panel requests run off the game's render thread in the existing helper.</summary>
internal sealed class NativePanelCoordinator : IDisposable
{
    readonly EngineForgeService engine;
    readonly Action preferencesChanged;
    readonly Action stopHelper;
    readonly DispatcherQueue dispatcher;
    readonly DispatcherQueueTimer timer;
    IReadOnlyList<Game> targets = [];
    NativePanelChannel? channel;
    Game? game;
    int pid, reviewId;
    EngineReview? review;
    bool busy, disposed, exitRequested;
    public bool OwnsShortcut => channel?.OwnsShortcut == true;
    public bool Applying { get; private set; }

    public NativePanelCoordinator(EngineForgeService service, DispatcherQueue dispatcher, Action changed, Action stop)
    {
        engine = service; preferencesChanged = changed; stopHelper = stop; this.dispatcher = dispatcher;
        timer = dispatcher.CreateTimer(); timer.Interval = TimeSpan.FromSeconds(1);
        timer.Tick += async (_, _) => await PollAsync();
        _ = ReloadTargetsAsync(); timer.Start();
    }
    public async Task ReloadTargetsAsync()
    {
        try
        {
            targets = await engine.CompanionTargetsAsync();
            // Experimental Vulkan installs have external journals and may not
            // be marked installed in the manager's ordinary provider scan.
            await OverlayHelper.CacheGameIdentitiesAsync(targets);
        }
        catch (Exception) { targets = []; }
    }

    async Task PollAsync()
    {
        if (busy || disposed) return;
        busy = true; int request = 0;
        try
        {
            var active = await engine.ActiveCompanionAsync(targets, MainWindow.ForegroundProcessId(), pid);
            var foundPid = active["pid"]?.GetValue<int>() ?? 0;
            var location = active["row"]?["game"]?.ToString();
            var found = targets.FirstOrDefault(g => g.Id.Equals(location, StringComparison.OrdinalIgnoreCase));
            if (foundPid != pid || found?.Id != game?.Id)
            {
                ClearReview(); channel?.Dispose(); channel = null; pid = foundPid; game = found;
                preferencesChanged();
            }
            if (pid <= 0 || game is null) return;
            if (channel is not null && !channel.IsValid)
            { channel.Dispose(); channel = null; ClearReview(); preferencesChanged(); }
            if (channel is null)
            {
                try { channel = new NativePanelChannel(pid); preferencesChanged(); }
                catch (FileNotFoundException) { return; }
            }
            if (!channel.Visible) { ClearReview(); return; }
            if (!channel.TryRead(out request, out var message)) return;
            var result = await HandleAsync(message!, request);
            if (!disposed) channel?.Reply(request, result);
        }
        catch (Exception error)
        {
            if (!Applying) ClearReview();
            if (request > 0 && channel is not null && !disposed)
            {
                try { channel.Reply(request, new JsonObject { ["error"] = true, ["message"] = error.Message, ["settings"] = SettingsSnapshot() }); }
                catch (Exception) { }
            }
        }
        finally { busy = false; Applying = false; if (exitRequested && !disposed) dispatcher.TryEnqueue(() => stopHelper()); }
    }
    JsonObject SettingsSnapshot()
    {
        var s = ForgeSettings.Load();
        OverlayShortcut.TryParse(s.PanelHotkey, out _, out var binding, out _);
        return new JsonObject
        {
            ["overlay_controls"] = s.OverlayControls, ["overlay_renderer"] = s.OverlayRenderer,
            ["overlay_live_stats"] = s.OverlayLiveStats,
            ["overlay_welcome"] = s.OverlayWelcome, ["vulkan_mfg_native_menu"] = s.VulkanMfgNativeMenu,
            ["panel_hotkey"] = s.PanelHotkey, ["panel_key"] = (int)binding.Key, ["panel_modifiers"] = (int)binding.Modifiers,
            ["overlay_helper"] = s.OverlayHelper, ["overlay_start_with_windows"] = s.OverlayStartWithWindows,
            ["optiscaler_ui"] = s.OptiScalerUi, ["optiscaler_intro"] = s.OptiScalerIntro,
            ["optiscaler_hotkey"] = s.OptiScalerHotkey, ["reshade_ui"] = s.ReShadeUi, ["reshade_intro"] = s.ReShadeIntro,
        };
    }
    static JsonArray Entries(IEnumerable<ReviewItem> entries) => new(entries.Select(item => (JsonNode)new JsonObject
    { ["title"] = item.Title, ["detail"] = item.Detail }).ToArray());
    void ClearReview() { if (review is not null) engine.DiscardReview(review); review = null; }

    async Task<JsonObject> HandleAsync(JsonObject message, int request)
    {
        bool progressOpen = true;
        var action = message["op"]?.GetValue<string>() ?? "";
        JsonObject Done(string text) => new() { ["op"] = action, ["message"] = text, ["settings"] = SettingsSnapshot() };
        void Progress(PrepareProgress progress)
        {
            if (!progressOpen || disposed || channel is null) return;
            try { channel.Reply(request, new JsonObject { ["op"] = action, ["busy"] = true,
                ["message"] = progress.Total > 0 ? $"{progress.Label} · {progress.Checked} of {progress.Total}" : progress.Label }); }
            catch (Exception) { }
        }
        try { switch (action)
        {
            case "hello":
            case "status":
                var state = await engine.CompanionAsync("status", game!);
                var preferences = SettingsSnapshot();
                // A launcher may present a different HKCU view to the game.
                // Deliver identity with the same verified per-process reply as
                // the file states instead of depending on that registry cache.
                var palette = await OverlayAccent.ForGameAsync(game!);
                var color = palette.Color;
                preferences["game_title"] = game!.Name;
                preferences["game_accent"] = $"#{color.R:X2}{color.G:X2}{color.B:X2}";
                return new JsonObject { ["op"] = action, ["settings"] = preferences, ["status"] = state };
            case "save":
                var changes = message["changes"] as JsonObject ?? throw new InvalidOperationException("Choose a preset to save.");
                foreach (var pair in changes)
                {
                    var field = FeatureControlSchema.Shared.Controls.SingleOrDefault(f => f.Key == pair.Key)
                        ?? throw new InvalidOperationException("Unsupported preset control.");
                    var validated = new JsonObject(); FeatureControlSchema.Put(validated, field, FeatureControlSchema.Read(pair.Value));
                }
                // Feeder games load tuning at launch; the engine says so in panel_message.
                var saved = await engine.CompanionAsync("save", game!, changes, pid);
                return Done(saved["panel_message"]?.GetValue<string>() ?? "Preset saved for this game");
            case "reset":
                var reset = await engine.CompanionAsync("reset", game!, pid: pid);
                return Done(reset["panel_message"]?.GetValue<string>() ?? "Reset to this game's installed settings");
            case "set-setting":
                SetPreference(message);
                return Done("Saved · game-menu changes take effect after restarting the game");
            case "discard-review":
                ClearReview(); return Done("");
            case "global-review":
            case "menus-review":
                ClearReview();
                review = action == "global-review"
                    ? await engine.ReviewGlobalControlsAsync(message["changes"] as JsonObject ?? new(), new Progress<PrepareProgress>(Progress))
                    : await engine.ReviewOverlayUiAsync(ForgeSettings.Load().GameUiOptions(), new Progress<PrepareProgress>(Progress));
                if (disposed || channel?.Visible != true) { ClearReview(); return Done("Review closed"); }
                reviewId++;
                return new JsonObject { ["op"] = action, ["review_id"] = reviewId, ["ready"] = review.Ready,
                    ["message"] = review.Summary, ["items"] = Entries(review.Items), ["blocked"] = Entries(review.Blocked), ["skipped"] = Entries(review.Skipped) };
            case "apply-review":
                if (review is null || message["review_id"]?.GetValue<int>() != reviewId)
                    throw new InvalidOperationException("Review the games again before applying.");
                var pending = review; review = null; Applying = true;
                var result = await engine.RunReviewAsync(pending, new Progress<PrepareProgress>(Progress));
                await engine.ReloadCompanionPresetsAsync();
                return Done(result.Message + (result.Errors.Count > 0 ? "\n" + string.Join("\n", result.Errors) : ""));
            default: throw new InvalidOperationException("Unsupported panel request.");
        } }
        finally { progressOpen = false; }
    }
    void SetPreference(JsonObject message)
    {
        var setting = message["key"]?.GetValue<string>();
        var value = message["value"] ?? throw new InvalidOperationException("Choose a setting value.");
        var fresh = ForgeSettings.EditOverlay(s =>
        {
            switch (setting)
            {
                case "overlay_controls": s.OverlayControls = value.GetValue<bool>() ? "classic" : "unified"; break;
                case "overlay_live_stats": s.OverlayLiveStats = value.GetValue<bool>(); break;
                case "overlay_welcome": s.OverlayWelcome = value.GetValue<bool>(); break;
                case "vulkan_mfg_native_menu": s.VulkanMfgNativeMenu = value.GetValue<bool>(); break;
                case "overlay_renderer":
                    var renderer = value.GetValue<string>();
                    if (renderer is not ("game" or "optiscaler")) throw new InvalidOperationException("Choose an available overlay.");
                    s.OverlayRenderer = renderer; break;
                case "panel_binding":
                    var code = value["key"]?.GetValue<int>() ?? -1; var modifiers = value["modifiers"]?.GetValue<int>() ?? -1;
                    if (code == 0 && modifiers == 0) s.PanelHotkey = OverlayShortcut.Disabled;
                    else
                    {
                        if (!OverlayShortcut.TryCreate((uint)code, (uint)modifiers, out var name, out var error)) throw new InvalidOperationException(error);
                        s.PanelHotkey = name;
                    }
                    break;
                case "optiscaler_ui": s.OptiScalerUi = value.GetValue<bool>(); break;
                case "optiscaler_intro": s.OptiScalerIntro = value.GetValue<bool>(); break;
                case "reshade_ui": s.ReShadeUi = value.GetValue<bool>(); break;
                case "reshade_intro": s.ReShadeIntro = value.GetValue<bool>(); break;
                case "overlay_helper": s.OverlayHelper = value.GetValue<bool>(); break;
                case "overlay_start_with_windows": s.OverlayStartWithWindows = value.GetValue<bool>(); break;
                case "optiscaler_hotkey":
                    var native = value.GetValue<string>();
                    if (native is not ("Insert" or "F8" or "Disabled")) throw new InvalidOperationException("Choose an available native shortcut.");
                    s.OptiScalerHotkey = native; break;
                default: throw new InvalidOperationException("Unsupported overlay setting.");
            }
        });
        OverlayHelper.ConfigureStartup(fresh); engine.Settings.CopyOverlayFrom(fresh); preferencesChanged();
        ClearReview(); exitRequested = !fresh.OverlayHelper;
    }
    public void Dispose()
    { disposed = true; timer.Stop(); ClearReview(); channel?.Dispose(); channel = null; }
}
