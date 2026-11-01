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
    readonly Action<ForgeSettings> applied;
    readonly OverlayPresentationView presentation;
    PreferencesGroup? group;
    public IReadOnlyList<PreferencesGroup> Groups => groups;

    public OverlayPreferencesView(Action<ForgeSettings> applied, EngineForgeService? engine = null, bool groupCards = false)
    {
        this.groupCards = groupCards;
        this.applied = applied;
        Spacing = 20;
        var current = ForgeSettings.Load();
        var glass = GlassAppearance.Load();
        Heading("rtxForge panel");
        var renderer = Choice("Overlay", ["rtxForge", "Native"], current.OverlayRenderer == "optiscaler" ? 1 : 0,
            "Use the rtxForge panel in compatible packages, or the original menus provided by OptiScaler, Feeder or ReShade.", glyph: "\uE7F4");
        presentation = new OverlayPresentationView(EditGlass, engine);
        AddControl(new Border { Style = Prefs.GetStyle("ForgeSettingsCardStyle"), Child = presentation });
        var type = Choice("Text size", ["Aa  Smaller", "Aa  Default", "Aa  Larger"], glass.Number("TextSize", 22, 16, 26) < 22 ? 0 : glass.Number("TextSize", 22, 16, 26) > 22 ? 2 : 1, glyph: "\uE8D2");
        var originalLabels = Switch("Original labels", glass.On("OriginalLabels",false), "Use upstream control names instead of friendly labels.", glyph: "\uE8D2");
        var motion = Switch("Motion effects", glass.On("Motion"), glyph: "\uE768");
        Heading("Status and notifications");
        var liveStats = Switch("Live feature statistics", current.OverlayLiveStats,
            "Show measured activity and performance beside NR and frame generation controls, when the injector supplies them.", glyph: "\uE9D9");
        var welcome = Switch("Welcome message", current.OverlayWelcome,
            "Show the rtxForge logo and the assigned overlay shortcut briefly when the game starts.", glyph: "\uE8F2");
        var notifications = Switch("Hotkey notifications", glass.On("ShowNotifications"), "Show preset changes and feature toggles in the same slim toast.", glyph: "\uE7E7");
        var welcomePosition = Choice("Welcome position", ["Top center", "Top left", "Top right", "Bottom left", "Bottom right"],
            Array.IndexOf(ForgeSettings.WelcomePositions, current.OverlayWelcomePosition), "Applies when the game starts.", glyph: "\uE8B9");
        Heading("Shortcuts and helper");
        var key = new OverlayShortcutPicker(current.PanelHotkey, settingsRow: groupCards);
        AddControl(key);
        var helper = Switch("Background overlay helper", current.OverlayHelper,
            "Keep saved presets and panel settings available after closing the manager.", glyph: "\uE7F8");
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
            "Controls the ReShade guide and RenoDX welcome dialog. Loading notices are separate. Feeder NR and effects stay running.", glyph: "\uE8F2");
        Heading("Vulkan MFG overlay");
        var vulkanMenu = Switch("Native MFG menu and hint", current.VulkanMfgNativeMenu,
            "Optional advanced MFG Unlocker panel. Off by default; frame generation keeps running. The rtxForge welcome message has its own setting.", glyph: "\uE700");
        Heading("Apply to games");
        OverlayUiReviewView? gameReview = null;
        if (engine is not null) { gameReview = new(engine, settingsRows: true); AddControl(gameReview); }
        var history = Prefs.ActionButton("View details", async (_, _) =>
        { if (App.Main is { } main) await main.ShowOverlayUpdateDetailsAsync(); });
        AddControl(Prefs.Row("Last overlay update", "See which games were updated and whether any still need attention.", history, glyph: "\uE81C"));
        var feedbackCard = new Border { Style = Prefs.GetStyle("ForgeSettingsCardStyle"), Child = feedback, Visibility = Visibility.Collapsed };
        feedback.RegisterPropertyChangedCallback(TextBlock.TextProperty, (_, _) =>
            feedbackCard.Visibility = string.IsNullOrEmpty(feedback.Text) ? Visibility.Collapsed : Visibility.Visible);
        AddControl(feedbackCard);
        void Availability()
        {
            var native = renderer.SelectedIndex == 1;
            key.IsEnabled = !native;
            presentation.SetRendererEnabled(!native);
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
                    ? "Saved · restart your game to use its native overlay."
                    : "Saved";
            }
            catch (Exception error) { feedback.Text = error.Message; Availability(); return false; }
            Availability();
            return true;
        }
        renderer.SelectionChanged += (_, _) => Save(s => s.OverlayRenderer = renderer.SelectedIndex == 1 ? "optiscaler" : "game");
        type.SelectionChanged += (_, _) => EditGlass(() => GlassAppearance.Set("TextSize", type.SelectedIndex == 0 ? 20 : type.SelectedIndex == 2 ? 24 : 22));
        originalLabels.Toggled += (_, _) => EditGlass(() => GlassAppearance.Set("OriginalLabels", originalLabels.IsOn ? 1 : 0));
        motion.Toggled += (_, _) => EditGlass(() => GlassAppearance.Set("Motion", motion.IsOn ? 1 : 0));
        notifications.Toggled += (_, _) => EditGlass(() => GlassAppearance.Set("ShowNotifications", notifications.IsOn ? 1 : 0));
        liveStats.Toggled += (_, _) => Save(s => s.OverlayLiveStats = liveStats.IsOn);
        welcome.Toggled += (_, _) => Save(s => s.OverlayWelcome = welcome.IsOn);
        welcomePosition.SelectionChanged += (_, _) =>
        { if (welcomePosition.SelectedIndex >= 0) Save(s => s.OverlayWelcomePosition = ForgeSettings.WelcomePositions[welcomePosition.SelectedIndex]); };
        vulkanMenu.Toggled += (_, _) => Save(s => s.VulkanMfgNativeMenu = vulkanMenu.IsOn);
        key.SaveBinding = value => Save(s => s.PanelHotkey = value);
        nativeKey.SelectionChanged += (_, _) => Save(s => s.OptiScalerHotkey = nativeKey.SelectedIndex == 1 ? "F8" : nativeKey.SelectedIndex == 2 ? "Disabled" : "Insert");
        helper.Toggled += (_, _) => Save(s => s.OverlayHelper = helper.IsOn);
        startup.Toggled += (_, _) => Save(s => s.OverlayStartWithWindows = startup.IsOn);
        optiUi.Toggled += (_, _) => Save(s => s.OptiScalerUi = optiUi.IsOn);
        optiIntro.Toggled += (_, _) => Save(s => s.OptiScalerIntro = optiIntro.IsOn);
        reshadeUi.Toggled += (_, _) => Save(s => s.ReShadeUi = reshadeUi.IsOn);
        reshadeIntro.Toggled += (_, _) => Save(s => s.ReShadeIntro = reshadeIntro.IsOn);
        Availability();
    }

    void EditGlass(Action edit)
    {
        try
        {
            edit(); presentation.RefreshAppearance(); var appearance = GlassAppearance.Load();
            var fresh = ForgeSettings.EditOverlay(s => { s.OverlayAppearance = appearance.ToJson(); s.OverlayTheme = appearance.Theme; });
            OverlayHelper.ConfigureStartup(fresh); applied(fresh);
            feedback.Text = appearance.Custom ? "Saved · Custom appearance" : "Saved";
        }
        catch (Exception error) { feedback.Text = error.Message; }
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
