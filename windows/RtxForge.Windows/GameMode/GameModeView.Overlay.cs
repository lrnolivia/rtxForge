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

    IReadOnlyList<SettingsGroup> OverlayGroups() =>
    [
        new("rtxForge panel", null,
        [
            Choice("Primary overlay", "Use the rtxForge panel in compatible packages, or the original OptiScaler, Feeder or ReShade menus.",
                ["game", "optiscaler"], ["rtxForge", "Native"], () => shell.Settings.OverlayRenderer == "optiscaler" ? "optiscaler" : "game", value => SetOverlay(s => s.OverlayRenderer = value), glyph: "\uE7F4"),
            Choice("Controls", "Advanced uses the package’s labels and original units.", ["unified", "classic"], ["Unified", "Advanced"],
                () => shell.Settings.OverlayControls, value => SetOverlay(s => s.OverlayControls = value), glyph: "\uE713"),
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
        new("Apply to games", "Menu and welcome changes take effect next launch.",
        [
            ui.RowButton("Review installed games", null, () => _ = ReviewOverlayGames(), description: "Apply saved choices with backups. Running games are skipped.", glyph: "\uE9D9"),
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
        await RunReviewAsync("Update in-game overlays", () => engine.ReviewOverlayPackagesAsync());
    }
}
