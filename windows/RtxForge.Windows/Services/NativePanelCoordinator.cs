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
    DateTime nextHdrFlush = DateTime.MinValue;
    IReadOnlyList<Game> targets = [];
    NativePanelChannel? channel;
    Game? game;
    int pid;
    EngineReview? review;
    bool busy, disposed, exitRequested;
    string? targetProblem, pollProblem;
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
            targetProblem = null;
            // Experimental Vulkan installs have external journals and may not
            // be marked installed in the manager's ordinary provider scan.
            await OverlayHelper.CacheGameIdentitiesAsync(targets);
        }
        catch (Exception error) { targets = []; targetProblem = error.Message; }
    }

    // Read-only helper diagnostics expose discovery separately from live NR/FG.
    // A running helper alone does not establish an attached game panel.
    internal JsonObject DiagnosticSnapshot() => new()
    {
        ["targets"] = new JsonArray(targets.Select(g => (JsonNode)new JsonObject
        { ["name"] = g.Name, ["game"] = g.Location, ["provider"] = g.RuntimeProvider }).ToArray()),
        ["pid"] = pid, ["channel_valid"] = channel?.IsValid == true,
        ["panel_visible"] = channel?.Visible == true,
        ["target_error"] = targetProblem, ["poll_error"] = pollProblem,
    };

    async Task PollAsync()
    {
        if (busy || disposed) return;
        busy = true; int request = 0;
        try
        {
            if (DateTime.UtcNow >= nextHdrFlush)
            { nextHdrFlush = DateTime.UtcNow.AddSeconds(3); await engine.FlushHdrSettingsAsync(); await engine.FlushNrAddonSettingsAsync(); }
            var active = await engine.ActiveCompanionAsync(targets, MainWindow.ForegroundProcessId(), pid);
            pollProblem = null;
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
            var visible = channel.Visible;
            if (!visible) ClearReview();
            if (!channel.TryRead(out request, out var message)) return;
            // Startup welcome preferences need a read-only handshake even
            // while the panel is closed. Actions still require an open panel.
            if (!visible && message?["op"]?.ToString() is not ("hello" or "status"))
                throw new InvalidOperationException("Open the overlay before changing game settings.");
            var result = await HandleAsync(message!, request);
            if (!disposed) channel?.Reply(request, result);
        }
        catch (Exception error)
        {
            pollProblem = error.Message;
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
        var values = GlassAppearance.OverlayOptions(s,game);
        if(game is not null)values["native_overlay_shortcuts"]=NativeShortcuts(game,values);
        values["overlay_appearance"]=GlassAppearance.Resolve(s,game);
        if(game is not null)values["game_poster"]=OverlayPreview.Poster(game,s)??"";
        OverlayShortcut.TryParse(values["panel_hotkey"]?.ToString(), out _, out var binding, out _);
        values["panel_key"] = (int)binding.Key;
        values["panel_modifiers"] = (int)binding.Modifiers;
        values["overlay_helper"] = s.OverlayHelper;
        values["overlay_start_with_windows"] = s.OverlayStartWithWindows;
        values["overlay_light"] = OverlayHelper.LightTheme(s, values["overlay_theme"]?.ToString());
        return values;
    }
    static JsonArray NativeShortcuts(Game game,JsonObject settings)
    {
        var result=new JsonArray();var root=Path.GetFullPath(game.Location);var folder=Path.GetDirectoryName(Path.GetFullPath(Path.Combine(root,game.EngineRow?["exe"]?.ToString()??"")))??root;
        if(!folder.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)&&!folder.Equals(root,StringComparison.OrdinalIgnoreCase))folder=root;
        string Key(int code)=>code is >=0x70 and <=0x87?"F"+(code-0x6f):code is >=48 and <=90?((char)code).ToString():code switch{0x2d=>"Insert",0x24=>"Home",0x23=>"End",0x2e=>"Delete",0x20=>"Space",0x09=>"Tab",0x1b=>"Escape",_=>"0x"+code.ToString("X2")};
        foreach(var (name,file,section,key) in new[]{("OptiScaler","OptiScaler.ini","Menu","ShortcutKey"),("ReShade","ReShade.ini","INPUT","KeyOverlay")})try{
            var path=new[]{folder,Path.Combine(folder,"OptiScaler"),root}.Select(basePath=>Path.Combine(basePath,file)).FirstOrDefault(File.Exists);if(path is null||new FileInfo(path).Length>256*1024)continue;
            var current="";var raw=name=="OptiScaler"?"0x2D":"36,0,0,0";var savedKey="36,0,0,0";
            foreach(var line in File.ReadLines(path)){var text=line.Trim();if(text.StartsWith('[')){current=text.Trim('[',']');continue;}var at=text.IndexOf('=');if(at<=0)continue;var field=text[..at].Trim();var value=text[(at+1)..].Split(';')[0].Trim();if(current.Equals(section,StringComparison.OrdinalIgnoreCase)&&field.Equals(key,StringComparison.OrdinalIgnoreCase))raw=value;if(current.Equals("rtxForge.UI",StringComparison.OrdinalIgnoreCase)&&field.Equals("ReShadeShortcut",StringComparison.OrdinalIgnoreCase))savedKey=value;}
            if(name=="OptiScaler")raw=settings["optiscaler_hotkey"]?.ToString() switch{"F8"=>"0x77","Disabled"=>"0",_=>"0x2D"};
            var parts=raw.Split(',');var number=parts[0].Trim();var code=Convert.ToInt32(number.StartsWith("0x",StringComparison.OrdinalIgnoreCase)?number[2..]:number,number.StartsWith("0x",StringComparison.OrdinalIgnoreCase)?16:10);if(code<0||code>255)continue;
            var enabled=code!=0&&(settings[name=="OptiScaler"?"optiscaler_ui":"reshade_ui"]?.GetValue<bool>()??true);
            if(name=="ReShade"&&code==0){parts=savedKey.Split(',');code=Convert.ToInt32(parts[0].Trim());if(code<0||code>255)continue;}
            var caption=name=="ReShade"?(parts.Length>1&&parts[1].Trim()=="1"?"Ctrl+":"")+(parts.Length>3&&parts[3].Trim()=="1"?"Alt+":"")+(parts.Length>2&&parts[2].Trim()=="1"?"Shift+":""):"";
            caption+=Key(code==0?name=="OptiScaler"?0x2d:0x24:code);
            result.Add(new JsonObject{["name"]=name,["key"]=caption,["enabled"]=enabled});
        }catch(Exception error)when(error is IOException or UnauthorizedAccessException or FormatException or OverflowException){ }
        return result;
    }
    static JsonArray Entries(IEnumerable<ReviewItem> entries) => new(entries.Select(item => (JsonNode)new JsonObject
    { ["title"] = item.Title, ["detail"] = item.Detail }).ToArray());
    void ClearReview() { if (review is not null) engine.DiscardReview(review); review = null; }

    async Task<JsonObject> HandleAsync(JsonObject message, int request)
    {
        var action = message["op"]?.GetValue<string>() ?? "";
        JsonObject Done(string text) => new() { ["op"] = action, ["message"] = text, ["settings"] = SettingsSnapshot() };
        switch (action)
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
                var hello = new JsonObject { ["op"] = action, ["settings"] = preferences, ["status"] = state };
                hello["hdr"] = await HdrWithAddonsAsync();
                if (state["can_save"]?.GetValue<bool>() == true)
                {
                    var library = await engine.CompanionAsync("preset_list", game!, pid: pid);
                    foreach (var pair in library) hello[pair.Key] = pair.Value?.DeepClone();
                }
                return hello;
            case "hdr-save":
                var hdrSaved = await engine.HdrSettingsAsync(game!, message["changes"] as JsonObject
                    ?? throw new InvalidOperationException("Choose an HDR setting."));
                hdrSaved["nr_addons"] = await engine.NrAddonSettingsAsync(game!);
                return new JsonObject { ["op"] = action, ["hdr"] = hdrSaved, ["settings"] = SettingsSnapshot(), ["message"] = "HDR preferences saved. Close and restart the game to apply." };
            case "nr-addons-save":
                var addonsSaved = await engine.NrAddonSettingsAsync(game!, message["changes"] as JsonObject
                    ?? throw new InvalidOperationException("Choose a Split Render setting."));
                var withHdr = await engine.HdrSettingsAsync(game!); withHdr["nr_addons"] = addonsSaved;
                return new JsonObject { ["op"] = action, ["hdr"] = withHdr, ["settings"] = SettingsSnapshot(), ["message"] = "Split Render settings saved. Close and restart the game to apply." };
            case "preset-save":
            case "preset-delete":
            case "preset-list":
                var named = await engine.CompanionAsync(action.Replace('-', '_'), game!, message["changes"] as JsonObject, pid);
                named["op"] = action; named["settings"] = SettingsSnapshot();
                return named;
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
            case "use-native-overlays":
                if(game is null)throw new InvalidOperationException("Open a game before choosing its overlays.");
                var globalDefault=message["global_default"]?.GetValue<bool>()??false;
                var nativeSettings=ForgeSettings.EditOverlay(s=>{
                    if(!s.GameOverlaySettings.TryGetValue(game.Id,out var local))s.GameOverlaySettings[game.Id]=local=new JsonObject();
                    local["overlay_renderer"]="optiscaler";local["optiscaler_ui"]=true;local["reshade_ui"]=true;
                    if(GlassAppearance.OverlayOptions(s,game)["optiscaler_hotkey"]?.ToString()=="Disabled")local["optiscaler_hotkey"]="Insert";
                    if(globalDefault){s.OverlayRenderer="optiscaler";s.OptiScalerUi=true;s.ReShadeUi=true;if(s.OptiScalerHotkey=="Disabled")s.OptiScalerHotkey="Insert";}
                });
                OverlayHelper.CacheRenderer(game,nativeSettings);engine.Settings.CopyOverlayFrom(nativeSettings);preferencesChanged();ClearReview();
                return Done("Native overlays selected. Restart the game if its menus are not available yet.");
            case "set-setting":
                SetPreference(message);
                return Done(message["key"]?.ToString() is "overlay_theme" or "overlay_appearance" ? "Saved" : "Saved · game-menu changes take effect after restarting the game");
            case "discard-review":
                ClearReview(); return Done("");
            case "global-review":
            case "menus-review":
            case "apply-review":
                throw new InvalidOperationException("Review library-wide changes in Desktop or Game Mode settings.");
            default: throw new InvalidOperationException("Unsupported panel request.");
        }
    }
    // NR add-on settings ride inside the hdr reply: installed Skynizz bridges
    // rebuild the panel reply from fixed keys and forward that object whole.
    async Task<JsonObject> HdrWithAddonsAsync()
    {
        var result = await engine.HdrSettingsAsync(game!);
        result["nr_addons"] = await engine.NrAddonSettingsAsync(game!);
        return result;
    }
    void SetPreference(JsonObject message)
    {
        var setting = message["key"]?.GetValue<string>();
        var value = message["value"] ?? throw new InvalidOperationException("Choose a setting value.");
        if(game is null || setting is "overlay_helper" or "overlay_start_with_windows")throw new InvalidOperationException("Change app defaults in Desktop or Game Mode settings.");
        var s = ForgeSettings.Load();
        {
            switch (setting)
            {
                case "overlay_appearance":
                    s.OverlayAppearance = GlassAppearance.Validate(value.AsObject());

                    break;
                case "overlay_controls": s.OverlayControls = value.GetValue<bool>() ? "classic" : "unified"; break;
                case "overlay_theme":
                    var theme = value.GetValue<string>();
                    if (!ForgeSettings.OverlayThemes.Contains(theme)) throw new InvalidOperationException("Choose an available overlay theme.");
                    s.OverlayTheme = theme; break;
                case "overlay_live_stats": s.OverlayLiveStats = value.GetValue<bool>(); break;
                case "overlay_welcome": s.OverlayWelcome = value.GetValue<bool>(); break;
                case "overlay_welcome_position":
                    var position = value.GetValue<string>();
                    if (!ForgeSettings.WelcomePositions.Contains(position)) throw new InvalidOperationException("Choose an available welcome position.");
                    s.OverlayWelcomePosition = position; break;
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
        }
        var key=setting=="panel_binding"?"panel_hotkey":setting!;
        var selected=s.GameOverlayOptions()[key]?.DeepClone() ?? throw new InvalidOperationException("Unsupported game setting.");
        var fresh=ForgeSettings.EditGameOverlay(game,values=>values[key]=selected);
        OverlayHelper.CacheRenderer(game,fresh);
        engine.Settings.CopyOverlayFrom(fresh); preferencesChanged();
        ClearReview(); exitRequested = !fresh.OverlayHelper;
    }
    public void Dispose()
    { disposed = true; timer.Stop(); ClearReview(); channel?.Dispose(); channel = null; }
}
