using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Controls;

/// <summary>Shared native appearance choices and a lightweight game-scene preview.</summary>
sealed class OverlayPresentationView : Grid
{
    readonly OverlayLayoutPicker layout;
    readonly ComboBox side;
    readonly ComboBox bar;
    readonly OverlayThemePicker theme;
    readonly ToggleSwitch tint;
    readonly OverlayPreviewView? preview;

    public OverlayPresentationView(Action<Action> edit, EngineForgeService? engine, Game? game = null)
    {
        var glass = GlassAppearance.Load();
        layout = new(glass.Layout, card: false);
        theme = new(glass.BaseTheme);
        side = new() { ItemsSource = new[] { "Left", "Right" }, SelectedIndex = glass.SidePanelSide == "right" ? 1 : 0, MinWidth = 100 };
        bar = new() { ItemsSource = new[] { "Bottom", "Top" }, SelectedIndex = glass.BarPosition == "top" ? 1 : 0, MinWidth = 100 };
        tint = new() { IsOn = glass.AccentEnabled, VerticalAlignment = VerticalAlignment.Center };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(side, "Side Panel position");
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(bar, "Bar position");
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(tint, "Accent Tint");
        var sideRow = Prefs.Row("Side Panel position", "Choose which edge the Side Panel opens on.", side, glyph: "\uE8A0");
        var barRow = Prefs.Row("Bar position", "Open the Bar at the top or bottom of the screen.", bar, glyph: "\uE8A0");
        var options = new StackPanel { Spacing = 16 };
        options.Children.Add(layout); options.Children.Add(sideRow); options.Children.Add(barRow); options.Children.Add(theme);
        options.Children.Add(Prefs.Row("Accent Tint", "Use the game's accent on overlay surfaces.", tint, glyph: "\uE790"));
        ColumnSpacing = 24; RowSpacing = 16;
        ColumnDefinitions.Add(new()); ColumnDefinitions.Add(new() { Width = new GridLength(440) });
        RowDefinitions.Add(new() { Height = GridLength.Auto }); RowDefinitions.Add(new() { Height = GridLength.Auto });
        Children.Add(options);
        Grid? previewSection = null;
        if (engine is not null)
        {
            preview = new(engine, App.Main?.Games ?? [], game);
            previewSection = new() { RowSpacing = 12 };
            previewSection.RowDefinitions.Add(new() { Height = GridLength.Auto }); previewSection.RowDefinitions.Add(new());
            previewSection.Children.Add(new TextBlock { Text = "Preview" });
            var card = new Border { Child = preview, Padding = new Thickness(16), CornerRadius = new CornerRadius(12),
                Background = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["ControlAltFillColorSecondaryBrush"] };
            Grid.SetRow(card, 1); previewSection.Children.Add(card); Grid.SetColumn(previewSection, 1); Children.Add(previewSection);
        }
        SizeChanged += (_, e) =>
        {
            var wide = e.NewSize.Width >= 820 && engine is not null;
            ColumnDefinitions[0].Width = new GridLength(1, GridUnitType.Star);
            ColumnDefinitions[1].Width = wide ? new GridLength(440) : new GridLength(0);
            if (previewSection is not null) { Grid.SetColumn(previewSection, wide ? 1 : 0); Grid.SetRow(previewSection, wide ? 0 : 1); }
        };
        void SideVisibility() { sideRow.Visibility = layout.SelectedIndex == 0 ? Visibility.Visible : Visibility.Collapsed; barRow.Visibility = layout.SelectedIndex == 2 ? Visibility.Visible : Visibility.Collapsed; }
        void Change(Action action) { edit(action); preview?.RefreshAppearance(); }
        layout.SelectionChanged += (_, _) => { if (layout.SelectedIndex >= 0) Change(() => GlassAppearance.Set("Layout", GlassAppearance.Layouts[layout.SelectedIndex])); SideVisibility(); };
        side.SelectionChanged += (_, _) => { if (side.SelectedIndex >= 0) Change(() => GlassAppearance.Set("SidePanelSide", side.SelectedIndex == 1 ? "right" : "left")); };
        bar.SelectionChanged += (_, _) => { if (bar.SelectedIndex >= 0) Change(() => GlassAppearance.Set("BarPosition", bar.SelectedIndex == 1 ? "top" : "bottom")); };
        theme.SelectionChanged += (_, _) => { if (theme.SelectedIndex >= 0) Change(() => GlassAppearance.UseAppearance(new[] { "clear", "light", "dark" }[theme.SelectedIndex])); };
        tint.Toggled += (_, _) => Change(() => GlassAppearance.UseAppearance(tint: tint.IsOn));
        SideVisibility();
    }

    public void SetRendererEnabled(bool enabled) => layout.IsEnabled = side.IsEnabled = bar.IsEnabled = theme.IsEnabled = tint.IsEnabled = enabled;
    public void RefreshAppearance() => preview?.RefreshAppearance();
}
