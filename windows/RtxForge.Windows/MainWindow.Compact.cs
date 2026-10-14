using Microsoft.UI.Input;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Animation;

namespace RtxForge.Windows;

/// <summary>
/// The compact dashboard in the titlebar (Linux sticky_brand / sticky_profile_group /
/// sticky_actions in the HeaderBar). The Library page decides when it shows (compact
/// header, or its dashboard scrolled away) and stays the owner of mode and actions.
/// </summary>
public sealed partial class MainWindow
{
    bool syncingCompact;
    bool compactVisible;

    /// <summary>A mode chosen in the compact selector.</summary>
    public event Action<string>? CompactModeChosen;
    /// <summary>install, uninstall or update-dlss from the compact actions; apply-selected in presets mode.</summary>
    public event Action<string>? CompactActionInvoked;

    /// <summary>
    /// Presets › Select games to apply presets: the Library without the Features selector and
    /// install actions. Clicking a game applies the library presets to it; checked games apply together.
    /// </summary>
    public bool PresetSelecting { get; private set; }
    public event Action? PresetModeChanged;

    public void BeginPresetSelection()
    {
        PresetSelecting = true;
        CompactPresetsSummary.Text = "Applying presets · " + PresetSummary(Settings.Presets) + " · click a game, or check several";
        Navigate("Library");
        PresetModeChanged?.Invoke();
    }

    public void EndPresetSelection()
    {
        if (!PresetSelecting) return;
        PresetSelecting = false;
        PresetModeChanged?.Invoke();
    }

    public static string PresetSummary(Models.Tuning t) =>
        $"NR {t.NrStrength:0.0} · Sharpening {t.SharpeningStrength:0.0} · MFG " + (t.MfgMultiplier switch { "auto" => "In game", "0" => "Off", var m => m + "×" });

    public void SyncCompactPresets(int selected)
    {
        CompactApplyText.Text = selected > 0 ? $"Apply to selected ({selected})" : "Apply to selected";
        CompactApplySelected.IsEnabled = selected > 0 && !Busy;
    }

    void OnCompactApplySelected(object sender, RoutedEventArgs e) => CompactActionInvoked?.Invoke("apply-selected");
    void OnCompactEditPresets(object sender, RoutedEventArgs e) => Navigate("Presets");
    void OnCompactPresetsDone(object sender, RoutedEventArgs e) => EndPresetSelection();

    /// <summary>Caption buttons as tall as the 48px titlebar, so they share its center line.</summary>
    void SizeCaptionButtons() => AppWindow.TitleBar.PreferredHeightOption = TitleBarHeightOption.Tall;

    public void ShowCompactDashboard(bool visible)
    {
        compactVisible = visible;
        ApplyCompactPanels();
        UpdateTitleBarRegions();
    }

    bool brandShown = true;
    Storyboard? brandMotion;

    /// <summary>
    /// The titlebar brand stays out of the way while the Library's full dashboard hero shows the
    /// mark and wordmark, then slides in from the left and fades up when it is needed again.
    /// </summary>
    public void ShowBrand(bool visible)
    {
        if (visible == brandShown) return;
        brandShown = visible;
        brandMotion?.Stop();
        var ease = new CubicEase { EasingMode = visible ? EasingMode.EaseOut : EasingMode.EaseIn };
        var duration = TimeSpan.FromMilliseconds(visible ? 280 : 140);
        DoubleAnimation To(DependencyObject target, string property, double value)
        {
            var animation = new DoubleAnimation { To = value, Duration = duration, EasingFunction = ease };
            Storyboard.SetTarget(animation, target);
            Storyboard.SetTargetProperty(animation, property);
            return animation;
        }
        brandMotion = new Storyboard { Children = { To(CompactBrand, "Opacity", visible ? 1 : 0), To(BrandShift, "X", visible ? 0 : -16) } };
        brandMotion.Begin();
    }

    /// <summary>Beside the brand: the Features selector and library actions, or the presets-mode options.</summary>
    void ApplyCompactPanels()
    {
        Visibility Show(bool on) => on ? Visibility.Visible : Visibility.Collapsed;
        // The brand stays put on every page; only the selector and actions come and go.

        CompactModes.Visibility = CompactActions.Visibility = Show(compactVisible && !PresetSelecting);
        CompactPresetsSummary.Visibility = CompactPresetActions.Visibility = Show(compactVisible && PresetSelecting);
    }

    public void SyncCompactDashboard(string mode, bool nrOnlyAvailable, string installText)
    {
        syncingCompact = true;
        foreach (var toggle in new[] { CompactNrOnly, CompactMfgOnly, CompactNrMfg })
            toggle.IsChecked = (string)toggle.Tag == mode;
        syncingCompact = false;
        CompactNrOnly.IsEnabled = nrOnlyAvailable;
        CompactInstallText.Text = installText;
    }

    void OnCompactModeChecked(object sender, RoutedEventArgs e)
    {
        if (!syncingCompact) CompactModeChosen?.Invoke((string)((FrameworkElement)sender).Tag);
    }

    void OnCompactInstall(object sender, RoutedEventArgs e) => CompactActionInvoked?.Invoke("install");
    void OnCompactRestore(object sender, RoutedEventArgs e) => CompactActionInvoked?.Invoke("uninstall");
    void OnCompactUpdateDlss(object sender, RoutedEventArgs e) => CompactActionInvoked?.Invoke("update-dlss");

    void OnCompactBarSizeChanged(object sender, SizeChangedEventArgs e) => UpdateTitleBarRegions();

    /// <summary>
    /// The titlebar drags the window; the compact selector and actions must take clicks instead
    /// (passthrough regions, in physical pixels). The actions keep clear of the caption buttons.
    /// </summary>
    void UpdateTitleBarRegions()
    {
        if (AppTitleBar.XamlRoot is not { } root) return;
        var scale = root.RasterizationScale;
        CompactActions.Margin = CompactPresetActions.Margin = new Thickness(0, 0, AppWindow.TitleBar.RightInset / scale + 8, 0);
        var source = InputNonClientPointerSource.GetForWindowId(AppWindow.Id);
        if (!compactVisible) { source.ClearRegionRects(NonClientRegionKind.Passthrough); return; }
        global::Windows.Graphics.RectInt32 Rect(FrameworkElement element)
        {
            var bounds = element.TransformToVisual(null).TransformBounds(new global::Windows.Foundation.Rect(0, 0, element.ActualWidth, element.ActualHeight));
            return new((int)Math.Round(bounds.X * scale), (int)Math.Round(bounds.Y * scale),
                (int)Math.Round(bounds.Width * scale), (int)Math.Round(bounds.Height * scale));
        }
        source.SetRegionRects(NonClientRegionKind.Passthrough, PresetSelecting
            ? [Rect(CompactPresetActions)]
            : [Rect(CompactModes), Rect(CompactActions)]);
    }
}
