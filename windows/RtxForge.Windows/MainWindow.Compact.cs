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
        CompactMfgOnly.IsEnabled = CompactNrMfg.IsEnabled = Settings.RuntimeProvider != "feeder";
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

    // Widths seen in each presentation, so a choice never depends on its own result.
    readonly Dictionary<string, double> compactWidths = [];
    int compactLevel;

    /// <summary>
    /// The titlebar row fits the window, not its own overflow: as room runs out the actions
    /// drop to icons (tooltips and accessible names stay), the Features selector tightens,
    /// then the wordmark gives way to the mark. Nothing runs under the caption buttons.
    /// </summary>
    void FitCompactBar(double scale)
    {
        var actions = PresetSelecting ? CompactPresetActions : CompactActions;
        var labels = actions.Children.OfType<Button>()
            .Select(button => (Button: button, Label: (button.Content as StackPanel)?.Children.OfType<TextBlock>().FirstOrDefault()))
            .Where(item => item.Label is not null).ToList();
        var modes = CompactModes.Visibility == Visibility.Visible;
        // Each width is remembered per presentation: actions with labels or icons, the
        // selector full or tight, the brand with or without its wordmark.
        string Key(string part, int level) => part switch
        {
            "actions" => (PresetSelecting ? "preset-" : "") + (level >= 1 ? "icons" : "labels"),
            "modes" => level >= 2 ? "modes-tight" : "modes",
            _ => level >= 4 ? "mark" : level >= 3 ? "brand-plain" : "brand",
        };
        void Seen(string part, double width) { if (width > 0) compactWidths[Key(part, compactLevel)] = width; }
        if (compactVisible)
        {
            Seen("actions", actions.ActualWidth);
            if (modes)
            {
                // The selector shares a star column, so its arranged width may already be squeezed.
                CompactModes.Measure(new global::Windows.Foundation.Size(double.PositiveInfinity, double.PositiveInfinity));
                Seen("modes", CompactModes.DesiredSize.Width);
                CompactModes.InvalidateMeasure();
            }
        }
        Seen("brand", BrandArea.ActualWidth);
        double Width(string part, int level, double estimate) =>
            compactWidths.TryGetValue(Key(part, level), out var seen) ? seen
            : compactWidths.TryGetValue(Key(part, 0), out var full) ? full * estimate : 0;
        var room = AppWindow.ClientSize.Width / scale - AppWindow.TitleBar.RightInset / scale - 8;
        var level = 0;
        var badge = Service.IsPreview;
        for (; level < 4; level++)
        {
            if (level == 3 && !badge) continue;
            var need = Math.Max(BrandColumn.MinWidth, Width("brand", level, level >= 4 ? .45 : level >= 3 ? .75 : 1))
                + (compactVisible ? Width("actions", level, level >= 1 ? .3 : 1) : 0)
                + (compactVisible && modes ? Width("modes", level, level >= 2 ? .75 : 1) : 0);
            if (need <= room) break;
        }
        if (level == compactLevel && compactWidths.Count > 0) return;
        compactLevel = level;
        foreach (var (button, label) in labels)
        {
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, label!.Text);
            label.Visibility = level >= 1 ? Visibility.Collapsed : Visibility.Visible;
        }
        foreach (var toggle in new[] { CompactNrOnly, CompactMfgOnly, CompactNrMfg })
        {
            toggle.MinWidth = level >= 2 ? 0 : 108;
            toggle.Padding = level >= 2 ? new Thickness(10, 5, 10, 6) : new Thickness(20, 5, 20, 6);
        }
        // The Preview badge gives way first, then the wordmark; the mark always stays.
        if (badge) PreviewBadge.Visibility = level >= 3 ? Visibility.Collapsed : Visibility.Visible;
        BrandWordmark.Visibility = level >= 4 ? Visibility.Collapsed : Visibility.Visible;
    }

    /// <summary>
    /// The titlebar drags the window; the compact selector and actions must take clicks instead
    /// (passthrough regions, in physical pixels). The actions keep clear of the caption buttons.
    /// </summary>
    void UpdateTitleBarRegions()
    {
        if (AppTitleBar.XamlRoot is not { } root) return;
        var scale = root.RasterizationScale;
        CompactActions.Margin = CompactPresetActions.Margin = new Thickness(0, 0, AppWindow.TitleBar.RightInset / scale + 8, 0);
        FitCompactBar(scale);
        var source = InputNonClientPointerSource.GetForWindowId(AppWindow.Id);
        global::Windows.Graphics.RectInt32 Rect(FrameworkElement element)
        {
            var bounds = element.TransformToVisual(null).TransformBounds(new global::Windows.Foundation.Rect(0, 0, element.ActualWidth, element.ActualHeight));
            return new((int)Math.Round(bounds.X * scale), (int)Math.Round(bounds.Y * scale),
                (int)Math.Round(bounds.Width * scale), (int)Math.Round(bounds.Height * scale));
        }
        var regions = new List<global::Windows.Graphics.RectInt32>();
        if (TitleBack.Visibility == Visibility.Visible) regions.Add(Rect(TitleBack));
        if (TitlePaneToggle.Visibility == Visibility.Visible) regions.Add(Rect(TitlePaneToggle));
        if (compactVisible)
        {
            if (PresetSelecting) regions.Add(Rect(CompactPresetActions));
            else { regions.Add(Rect(CompactModes)); regions.Add(Rect(CompactActions)); }
        }
        if (regions.Count == 0) source.ClearRegionRects(NonClientRegionKind.Passthrough);
        else source.SetRegionRects(NonClientRegionKind.Passthrough, regions.ToArray());
    }
}
