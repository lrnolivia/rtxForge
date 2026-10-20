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
    Button OverlayToggle(string title, string description, Func<bool> get, Action<ForgeSettings, bool> set) =>
        Choice(title, description, ["on", "off"], ["On", "Off"], () => get() ? "on" : "off", value => SetOverlay(s => set(s, value == "on")));

    List<UIElement> OverlayRows() =>
    [
        Choice("Primary overlay", "Keep the rtxForge sidebar alongside the native menus, or use OptiScaler alone.",
            ["rtxforge", "optiscaler", "game"], ["rtxForge sidebar", "Original OptiScaler", "rtxForge in-game (preview)"], () => shell.Settings.OverlayRenderer, v => SetOverlay(s => s.OverlayRenderer = v)),
        Choice("Controls", "Advanced uses OptiScaler labels and original units.", ["unified", "classic"], ["Unified", "Advanced"],
            () => shell.Settings.OverlayControls, v => SetOverlay(s => s.OverlayControls = v)),
        ui.RowButton("rtxForge shortcut", shell.Settings.PanelHotkey, OpenOverlayShortcut, description: "Default: Scroll Lock. Record an unused key or combination; other overlays keep their shortcuts."),
        OverlayToggle("OptiScaler menu", "Keep NR and MFG installed when the menu is off.", () => shell.Settings.OptiScalerUi, (s, v) => s.OptiScalerUi = v),
        OverlayToggle("OptiScaler intro", "The startup message is separate from menu access.", () => shell.Settings.OptiScalerIntro, (s, v) => s.OptiScalerIntro = v),
        Choice("OptiScaler shortcut", "Independent of the rtxForge shortcut. Applies next game launch.",
            ["Insert", "F8", "Disabled"], ["Insert", "F8", "Disabled"], () => shell.Settings.OptiScalerHotkey, v => SetOverlay(s => s.OptiScalerHotkey = v)),
        OverlayToggle("ReShade menu", "Keyboard and gamepad menu access. Feeder NR and effects keep running when this is off.", () => shell.Settings.ReShadeUi, (s, v) => s.ReShadeUi = v),
        OverlayToggle("ReShade welcome", "ReShade guide and RenoDX welcome dialog. Loading notices are separate.", () => shell.Settings.ReShadeIntro, (s, v) => s.ReShadeIntro = v),
        ui.RowButton("Review installed games", null, () => _ = ReviewOverlayGames(), description: "Apply saved menu and welcome choices with backups. Running games are skipped."),
        Choice("Window material", null, ["acrylic", "mica"], ["Acrylic", "Mica"], () => shell.Settings.OverlayMaterial, v => SetOverlay(s => s.OverlayMaterial = v)),
        OverlayToggle("Background overlay helper", "Keep the sidebar shortcut available after closing the manager.", () => shell.Settings.OverlayHelper, (s, v) => s.OverlayHelper = v),
        OverlayToggle("Start helper with Windows", "Starts the helper for the rtxForge sidebar.", () => shell.Settings.OverlayStartWithWindows, (s, v) => s.OverlayStartWithWindows = v),
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
}
