using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    void SetOverlay(Action<ForgeSettings> edit)
    {
        var fresh = ForgeSettings.EditOverlay(edit);
        shell.Settings.CopyOverlayFrom(fresh);
        OverlayHelper.ConfigureStartup(fresh);
        shell.ConfigureCompanionShortcut();
    }
    Button OverlayToggle(string title, string description, Func<bool> get, Action<ForgeSettings, bool> set, string? glyph = null) =>
        Choice(title, description, ["on", "off"], ["On", "Off"], () => get() ? "on" : "off", value => SetOverlay(s => set(s, value == "on")), glyph);
    void SetGlass(Action edit)
    {
        edit(); GlassAppearance.Set("ScaleBaseline",120); SetOverlay(s => s.OverlayAppearance = GlassAppearance.Load().ToJson());
    }
    Button GlassChoice(string title, string key, string[] keys, string[] captions, bool custom = false) =>
        Choice(title, null, keys, captions, () => GlassAppearance.Load().ToJson()[key]!.ToString(),
            value => SetGlass(() => GlassAppearance.Set(key, value, custom)), glyph: "\uE790");
    UIElement AccentCharacterSetting()
    {
        var slider = new Slider { Minimum=0, Maximum=100, StepFrequency=1, SmallChange=1, LargeChange=5,
            Value=GlassAppearance.Load().Number("AccentCharacter",35,0,100), IsThumbToolTipEnabled=false,
            HorizontalAlignment=HorizontalAlignment.Stretch };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(slider,"Accent character: Clear, Light, Dark");
        ui.Focusable(slider);Key(slider,"overlay-accent-character");
        slider.Tag=new Adjustable(delta=>slider.Value=Math.Clamp(slider.Value+delta,0,100));
        slider.ValueChanged+=(_,e)=>SetGlass(()=>GlassAppearance.Set("AccentCharacter",(int)Math.Round(e.NewValue)));
        var content=new StackPanel { Spacing=t.Px(10), Padding=new Thickness(t.Px(28),t.Px(22),t.Px(28),t.Px(22)),
            Visibility=GlassAppearance.Load().Theme=="accent"?Visibility.Visible:Visibility.Collapsed };
        content.Children.Add(ui.PreferenceRow("Accent character","Clear → Light → Dark",null,minHeight:0,padding:new Thickness(0)));
        content.Children.Add(slider);return content;
    }
    OverlayLayoutPicker LayoutChoices()
    {
        var picker = new OverlayLayoutPicker(GlassAppearance.Load().Layout);
        picker.SelectionChanged += (_, _) => SetGlass(() => GlassAppearance.Set("Layout", GlassAppearance.Layouts[picker.SelectedIndex]));
        return picker;
    }

    IReadOnlyList<SettingsGroup> OverlayGroups() =>
    [
        new("rtxForge panel", null,
        [
            Choice("Primary overlay", "Use the rtxForge panel in compatible packages, or the original OptiScaler, Feeder or ReShade menus.",
                ["game", "optiscaler"], ["rtxForge", "Native"], () => shell.Settings.OverlayRenderer == "optiscaler" ? "optiscaler" : "game", value => SetOverlay(s => s.OverlayRenderer = value), glyph: "\uE7F4"),
            LayoutChoices(),
        ]),
        new("Appearance", null,
        [
            Choice("Theme", "Selecting a theme restores its material defaults.", GlassAppearance.Themes, ["Clear", "Light", "Dark", "Accent"],
                () => GlassAppearance.Load().Theme, value => { GlassAppearance.UseTheme(value); SetOverlay(s => { s.OverlayTheme = value; s.OverlayAppearance=GlassAppearance.Load().ToJson(); }); }, glyph: "\uE790"),
            AccentCharacterSetting(),
            GlassChoice("Text size","TextSize",["18","22","26"],["Aa  Smaller","Aa  Default","Aa  Larger"]),
            GlassChoice("Motion effects","Motion",["1","0"],["On","Off"]),
        ]),
        new("Status and notifications", null,
        [
            GlassChoice("Hotkey notifications","ShowNotifications",["1","0"],["On","Off"]),
            OverlayToggle("Live feature statistics", "Measured activity beside NR and frame generation controls.", () => shell.Settings.OverlayLiveStats, (s, value) => s.OverlayLiveStats = value, glyph: "\uE9D9"),
            OverlayToggle("Welcome message", "Show the rtxForge logo and assigned shortcut at game startup.", () => shell.Settings.OverlayWelcome, (s, value) => s.OverlayWelcome = value, glyph: "\uE8F2"),
            Choice("Welcome position", "Applies when the game starts.", ForgeSettings.WelcomePositions,
                ["Top center", "Top left", "Top right", "Bottom left", "Bottom right"], () => shell.Settings.OverlayWelcomePosition,
                value => SetOverlay(s => s.OverlayWelcomePosition = value), glyph: "\uE8B9"),
        ]),
        new("Shortcuts and helper", null,
        [
            ui.RowButton("rtxForge shortcut", shell.Settings.PanelHotkey, OpenOverlayShortcut, description: "Choose an unused key or combination. Other overlays keep their shortcuts.", glyph: "\uE765"),
            OverlayToggle("Background overlay helper", "Keep saved presets and panel settings available after closing the manager.", () => shell.Settings.OverlayHelper, (s, value) => s.OverlayHelper = value, glyph: "\uE7F8"),
            OverlayToggle("Start helper with Windows", "Starts the helper for the rtxForge panel.", () => shell.Settings.OverlayStartWithWindows, (s, value) => s.OverlayStartWithWindows = value, glyph: "\uE7E8"),
        ]),
        new("OptiScaler", "Menu access and the welcome message are independent.",
        [
            OverlayToggle("OptiScaler menu", "Keep NR and MFG installed when the menu is off.", () => shell.Settings.OptiScalerUi, (s, value) => s.OptiScalerUi = value, glyph: "\uE700"),
            Choice("OptiScaler shortcut", "Applies next game launch.", ["Insert", "F8", "Disabled"], ["Insert", "F8", "Disabled"], () => shell.Settings.OptiScalerHotkey, value => SetOverlay(s => s.OptiScalerHotkey = value), glyph: "\uE765"),
            OverlayToggle("OptiScaler intro", "Startup message only.", () => shell.Settings.OptiScalerIntro, (s, value) => s.OptiScalerIntro = value, glyph: "\uE8F2"),
        ]),
        new("ReShade", "Menu access and the welcome message are independent.",
        [
            OverlayToggle("ReShade menu", "Feeder NR and effects keep running when this is off.", () => shell.Settings.ReShadeUi, (s, value) => s.ReShadeUi = value, glyph: "\uE700"),
            OverlayToggle("ReShade welcome", "ReShade guide and RenoDX welcome dialog. Loading notices are separate.", () => shell.Settings.ReShadeIntro, (s, value) => s.ReShadeIntro = value, glyph: "\uE8F2"),
        ]),
        new("Vulkan MFG overlay", null,
        [
            OverlayToggle("Native MFG menu and hint", "Optional advanced menu. Frame generation keeps running when it is off.", () => shell.Settings.VulkanMfgNativeMenu, (s, value) => s.VulkanMfgNativeMenu = value, glyph: "\uE700"),
        ]),
        new("Apply to games", "Menu and welcome changes take effect next launch.",
        [
            ui.RowButton("Update Overlays", null, () => _ = ReviewOverlayPackages(), description: "Review overlay packages, menus, welcome messages and shortcuts for every installed game.", glyph: "\uE9D9"),
            ui.RowButton("Last overlay update",null,() => _ = shell.ShowOverlayUpdateDetailsAsync(),glyph:"\uE9D9"),
        ]),
    ];

    void OpenOverlayShortcut()
    {
        var picker = new OverlayShortcutPicker(ForgeSettings.Load().PanelHotkey);
        picker.SaveBinding = value =>
        {
            try { SetOverlay(s => s.PanelHotkey = value); return true; }
            catch (Exception error) { Toast(error.Message); return false; }
        };
        var done = ui.Button("Done", () => { CloseModal(); Render(keepFocus: true); }, GmKind.Card, .92);
        ShowModal("Overlay shortcut", picker, [done], () => { CloseModal(); Render(keepFocus: true); }, 900);
    }

    async Task ReviewOverlayGames()
    {
        if (shell.Service is not EngineForgeService engine) { Toast("Game-menu changes are available in the installed app."); return; }
        await RunReviewAsync("Review game menus", () => engine.ReviewOverlayUiAsync(ForgeSettings.Load().GameUiOptions()));
    }

    async Task ReviewOverlayPackages()
    {
        if (shell.Service is not EngineForgeService engine) { Toast("Overlay updates require the installed app."); return; }
        await RunReviewAsync("Update Overlays", () => engine.ReviewOverlayPackagesAsync());
    }

    void OpenGameOverlay(Game g)
    {
        var inherited = !shell.Settings.GameOverlaySettings.ContainsKey(g.Id);
        System.Text.Json.Nodes.JsonObject Values() => shell.Settings.GameOverlayOptions(g);
        void Save(Action<System.Text.Json.Nodes.JsonObject>? edit)
        {
            var fresh = ForgeSettings.EditGameOverlay(g, edit);
            shell.Settings.CopyOverlayFrom(fresh);
            shell.ConfigureCompanionShortcut();
        }
        var body = new StackPanel { Spacing = t.Px(12) };
        body.Children.Add(ui.P("The primary overlay follows the app setting. These menu and welcome choices apply only to this game."));
        body.Children.Add(Choice("Use app overlay settings", null, ["on", "off"], ["On", "Off"],
            () => inherited ? "on" : "off", value =>
            {
                Save(value == "on" ? null : _ => { });
                CloseModal(); OpenGameOverlay(g);
            }));
        Button Toggle(string title, string key) => Choice(title, null, ["on", "off"], ["On", "Off"],
            () => Values()[key]!.GetValue<bool>() ? "on" : "off", value => Save(v => v[key] = value == "on"));
        var rows = new List<UIElement>
        {
            Toggle("Welcome message", "overlay_welcome"),
            Choice("Welcome position", null, ForgeSettings.WelcomePositions,
                ["Top center", "Top left", "Top right", "Bottom left", "Bottom right"],
                () => Values()["overlay_welcome_position"]!.ToString(), value => Save(v => v["overlay_welcome_position"] = value)),
            Toggle("Live feature statistics", "overlay_live_stats"),
            Toggle("OptiScaler menu", "optiscaler_ui"), Toggle("OptiScaler intro", "optiscaler_intro"),
            Choice("OptiScaler shortcut", null, ["Insert", "F8", "Disabled"], ["Insert", "F8", "Disabled"],
                () => Values()["optiscaler_hotkey"]!.ToString(), value => Save(v => v["optiscaler_hotkey"] = value)),
            Toggle("ReShade menu", "reshade_ui"), Toggle("ReShade welcome", "reshade_intro"),
            Toggle("Native Vulkan MFG menu and hint", "vulkan_mfg_native_menu"),
        };
        var shortcut = new OverlayShortcutPicker(Values()["panel_hotkey"]!.ToString());
        shortcut.SaveBinding = value => { try { Save(v => v["panel_hotkey"] = value); return true; } catch (Exception error) { Toast(error.Message); return false; } };
        rows.Add(shortcut);
        foreach (var row in rows) if (row is Control control) control.IsEnabled = !inherited;
        var choices = ui.Group(rows);
        choices.IsHitTestVisible = !inherited; choices.Opacity = inherited ? .55 : 1;
        body.Children.Add(new ScrollViewer { Content = choices, MaxHeight = t.Px(640), HorizontalScrollMode = ScrollMode.Disabled });
        var done = ui.Button("Back", CloseModal, GmKind.Card, .85);
        var update = ui.Button("Update Overlays", () =>
        {
            CloseModal();
            if (shell.Service is EngineForgeService engine) _ = RunReviewAsync("Update Overlays", () => engine.ReviewOverlayPackagesAsync(games: [g.Id]));
        }, GmKind.Primary, .85, enabled: g.Installed && shell.Service is EngineForgeService);
        ShowModal("Overlay", body, [update, done], CloseModal, 1000);
    }
}
