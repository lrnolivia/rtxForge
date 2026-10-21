using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Controls;

/// <summary>The same preferences in the manager and the independent overlay.</summary>
public sealed class OverlayPreferencesView : StackPanel
{
    readonly TextBlock feedback = new() { TextWrapping = TextWrapping.Wrap, FontSize = 12 };
    readonly List<PreferencesGroup> groups = [];
    readonly bool groupCards;
    PreferencesGroup? group;
    public IReadOnlyList<PreferencesGroup> Groups => groups;

    public OverlayPreferencesView(Action<ForgeSettings> applied, EngineForgeService? engine = null, bool groupCards = false)
    {
        this.groupCards = groupCards;
        Spacing = 20;
        var current = ForgeSettings.Load();
        Heading("rtxForge panel");
        var renderer = Choice("Overlay", ["rtxForge sidebar", "Original OptiScaler overlay", "rtxForge in-game (preview)"], current.OverlayRenderer == "game" ? 2 : current.OverlayRenderer == "optiscaler" ? 1 : 0,
            "The in-game preview needs the new renderer package. It draws inside the game and opens only there. The sidebar is a separate helper window.", glyph: "\uE7F4");
        var layout = Choice("Controls", ["Unified", "Advanced"], current.OverlayControls == "classic" ? 1 : 0,
            "Unified uses simple labels and percentages. Advanced uses OptiScaler labels and original units for the sidebar’s live controls.", glyph: "\uE713");
        var material = Choice("Window material", ["Acrylic", "Mica"], current.OverlayMaterial == "mica" ? 1 : 0, glyph: "\uE790");
        Heading("Shortcuts and helper");
        var key = new OverlayShortcutPicker(current.PanelHotkey, settingsRow: groupCards);
        AddControl(key);
        var helper = Switch("Background overlay helper", current.OverlayHelper,
            "Keep the rtxForge shortcut available after closing the manager. OptiScaler’s panel runs inside the game.", glyph: "\uE7F8");
        var startup = Switch("Start with Windows", current.OverlayStartWithWindows,
            "Starts only the helper, when the rtxForge overlay is selected.", glyph: "\uE7E8");
        Heading("OptiScaler");
        var optiUi = Switch("In-game menu", current.OptiScalerUi, glyph: "\uE700");
        var optiIntro = Switch("Intro message", current.OptiScalerIntro,
            "The startup message and the menu are separate. Turning either off keeps NR and MFG installed.", glyph: "\uE8F2");
        var nativeKey = Choice("OptiScaler shortcut", ["Insert", "F8", "Disabled"], current.OptiScalerHotkey == "F8" ? 1 : current.OptiScalerHotkey == "Disabled" ? 2 : 0,
            "Switching overlays or changing the OptiScaler key takes effect after restarting the game. Install the current rtxForge package in your game to use the original panel.", glyph: "\uE765");
        Heading("ReShade");
        var reshadeUi = Switch("In-game menu", current.ReShadeUi, glyph: "\uE700");
        var reshadeIntro = Switch("Welcome messages", current.ReShadeIntro,
            "Controls the ReShade guide and RenoDX welcome dialog, matching the TS4 and Mass Effect setup. Loading notices are separate. Feeder NR and effects stay running.", glyph: "\uE8F2");
        Heading("Apply to games");
        OverlayUiReviewView? gameReview = null;
        if (engine is not null) { gameReview = new(engine); AddControl(gameReview); }
        AddControl(feedback);
        void Availability()
        {
            var native = renderer.SelectedIndex == 1;
            layout.IsEnabled = key.IsEnabled = !native;
            material.IsEnabled = renderer.SelectedIndex == 0;
            helper.IsEnabled = startup.IsEnabled = !native;
            nativeKey.IsEnabled = optiUi.IsOn;
        }
        bool Save(Action<ForgeSettings> edit)
        {
            try
            {
                // The helper and manager may both be open. Patch only the edited
                // preference into fresh settings, preserving the other process's work.
                var fresh = ForgeSettings.EditOverlay(edit);
                OverlayHelper.ConfigureStartup(fresh); applied(fresh);
                gameReview?.Invalidate();
                feedback.Text = fresh.OverlayRenderer == "optiscaler"
                    ? "Saved · restart your game to use OptiScaler. Open this gear or the tray to switch back."
                    : "Saved";
            }
            catch (Exception error) { feedback.Text = error.Message; Availability(); return false; }
            Availability();
            return true;
        }
        renderer.SelectionChanged += (_, _) => Save(s => s.OverlayRenderer = renderer.SelectedIndex == 2 ? "game" : renderer.SelectedIndex == 1 ? "optiscaler" : "rtxforge");
        layout.SelectionChanged += (_, _) => Save(s => s.OverlayControls = layout.SelectedIndex == 1 ? "classic" : "unified");
        key.SaveBinding = value => Save(s => s.PanelHotkey = value);
        nativeKey.SelectionChanged += (_, _) => Save(s => s.OptiScalerHotkey = nativeKey.SelectedIndex == 1 ? "F8" : nativeKey.SelectedIndex == 2 ? "Disabled" : "Insert");
        material.SelectionChanged += (_, _) => Save(s => s.OverlayMaterial = material.SelectedIndex == 1 ? "mica" : "acrylic");
        helper.Toggled += (_, _) => Save(s => s.OverlayHelper = helper.IsOn);
        startup.Toggled += (_, _) => Save(s => s.OverlayStartWithWindows = startup.IsOn);
        optiUi.Toggled += (_, _) => Save(s => s.OptiScalerUi = optiUi.IsOn);
        optiIntro.Toggled += (_, _) => Save(s => s.OptiScalerIntro = optiIntro.IsOn);
        reshadeUi.Toggled += (_, _) => Save(s => s.ReShadeUi = reshadeUi.IsOn);
        reshadeIntro.Toggled += (_, _) => Save(s => s.ReShadeIntro = reshadeIntro.IsOn);
        Availability();
    }

    ComboBox Choice(string label, string[] choices, int index, string? description = null, string? glyph = null)
    {
        if (groupCards)
        {
            var (row, combo) = Prefs.ComboRow(label, description, choices, index, glyph);
            AddControl(row); return combo;
        }
        var control = new ComboBox { Header = label, ItemsSource = choices, SelectedIndex = index, HorizontalAlignment = HorizontalAlignment.Stretch };
        AddControl(control); if (description is not null) Note(description); return control;
    }
    ToggleSwitch Switch(string label, bool enabled, string? description = null, string? glyph = null)
    {
        if (groupCards)
        {
            var (row, toggle) = Prefs.SwitchRow(label, description, enabled, glyph);
            AddControl(row); return toggle;
        }
        var control = new ToggleSwitch { Header = label, IsOn = enabled };
        AddControl(control); if (description is not null) Note(description); return control;
    }
    TextBlock Note(string text)
    {
        var note = new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, FontSize = 12, Opacity = .8,
            Margin = groupCards ? new Thickness(0, 4, 0, 8) : new Thickness(0, -12, 0, 0) };
        AddControl(note); return note;
    }
    void AddControl(UIElement control)
    {
        if (groupCards) group!.Add(control); else Children.Add(control);
    }
    void Heading(string text)
    {
        if (groupCards) { group = new PreferencesGroup(text); groups.Add(group); }
        else Children.Add(new TextBlock
        { Text = text, FontSize = 16, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, Margin = new Thickness(0, 12, 0, 0) });
    }
}
