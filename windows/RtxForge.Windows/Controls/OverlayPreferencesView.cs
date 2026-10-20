using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Controls;

/// <summary>The same preferences in the manager and the independent overlay.</summary>
public sealed class OverlayPreferencesView : StackPanel
{
    readonly TextBlock feedback = new() { TextWrapping = TextWrapping.Wrap, FontSize = 12 };

    public OverlayPreferencesView(Action<ForgeSettings> applied, EngineForgeService? engine = null)
    {
        Spacing = 20;
        var current = ForgeSettings.Load();
        var renderer = Choice("Overlay", ["rtxForge", "Original OptiScaler overlay"], current.OverlayRenderer == "optiscaler" ? 1 : 0);
        Note("rtxForge opens a floating sidebar on the left. OptiScaler opens its original in-game panel, including all upstream options.");
        var layout = Choice("Controls", ["Unified", "Advanced"], current.OverlayControls == "classic" ? 1 : 0);
        Note("Unified uses simple labels and percentages. Advanced uses OptiScaler labels and original units for the sidebar’s live controls.");
        var key = new OverlayShortcutPicker(current.PanelHotkey);
        Children.Add(key);
        Heading("OptiScaler");
        var optiUi = Switch("In-game menu", current.OptiScalerUi);
        var optiIntro = Switch("Intro message", current.OptiScalerIntro);
        Note("The startup message and the menu are separate. Turning either off keeps NR and MFG installed.");
        var nativeKey = Choice("OptiScaler shortcut", ["Insert", "F8", "Disabled"], current.OptiScalerHotkey == "F8" ? 1 : current.OptiScalerHotkey == "Disabled" ? 2 : 0);
        var restart = Note("Switching overlays or changing the OptiScaler key takes effect after restarting the game. Install the current rtxForge package in your game to use the original panel.");
        Heading("ReShade");
        var reshadeUi = Switch("In-game menu", current.ReShadeUi);
        var reshadeIntro = Switch("Welcome messages", current.ReShadeIntro);
        Note("Controls the ReShade guide and RenoDX welcome dialog, matching the TS4 and Mass Effect setup. Loading notices are separate. Feeder NR and effects stay running.");
        OverlayUiReviewView? gameReview = null;
        if (engine is not null) { gameReview = new(engine); Children.Add(gameReview); }
        Heading("rtxForge helper");
        var material = Choice("Window material", ["Acrylic", "Mica"], current.OverlayMaterial == "mica" ? 1 : 0);
        var helper = Switch("Background overlay helper", current.OverlayHelper);
        Note("Keep the rtxForge shortcut available after closing the manager. OptiScaler’s panel runs inside the game.");
        var startup = Switch("Start with Windows", current.OverlayStartWithWindows);
        Note("Starts only the helper, when the rtxForge overlay is selected.");
        Children.Add(feedback);
        void Availability()
        {
            var native = renderer.SelectedIndex == 1;
            layout.IsEnabled = key.IsEnabled = material.IsEnabled = helper.IsEnabled = startup.IsEnabled = !native;
            nativeKey.IsEnabled = optiUi.IsOn;
            restart.Visibility = Visibility.Visible;
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
        renderer.SelectionChanged += (_, _) => Save(s => s.OverlayRenderer = renderer.SelectedIndex == 1 ? "optiscaler" : "rtxforge");
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

    ComboBox Choice(string label, string[] choices, int index)
    {
        var control = new ComboBox { Header = label, ItemsSource = choices, SelectedIndex = index, HorizontalAlignment = HorizontalAlignment.Stretch };
        Children.Add(control); return control;
    }
    ToggleSwitch Switch(string label, bool enabled)
    {
        var control = new ToggleSwitch { Header = label, IsOn = enabled };
        Children.Add(control); return control;
    }
    TextBlock Note(string text)
    {
        var note = new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, FontSize = 12, Opacity = .8, Margin = new Thickness(0, -12, 0, 0) };
        Children.Add(note); return note;
    }
    void Heading(string text) => Children.Add(new TextBlock
    { Text = text, FontSize = 16, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, Margin = new Thickness(0, 12, 0, 0) });
}
