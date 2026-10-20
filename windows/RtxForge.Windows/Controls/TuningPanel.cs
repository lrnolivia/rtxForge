using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;
using Windows.Globalization.NumberFormatting;

namespace RtxForge.Windows.Controls;

/// <summary>
/// NR Strength · Sharpening · MFG pods (Window.tuning_controls).
/// NR 0.0–2.0 and Sharpening 0.0–1.0 in 0.1 steps, slider plus exact
/// numeric input; MFG In game / Off / 2×–6×.
/// </summary>
public sealed class TuningPanel : UserControl
{
    readonly Slider nr, sharpening;
    readonly ComboBox mfg;
    readonly List<FrameworkElement> nrPods = [];
    readonly Border mfgPod;
    bool syncing;
    readonly Tuning original;

    public event EventHandler? Changed;

    public TuningPanel(Tuning initial)
    {
        original = initial;
        var grid = new Grid { ColumnSpacing = 16 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        nr = AddStrengthPod(grid, 0, "NR Strength", 2.0, initial.NrStrength);
        sharpening = AddStrengthPod(grid, 1, "Sharpening", 1.0, initial.SharpeningStrength);

        var group = new StackPanel { Spacing = 6, VerticalAlignment = VerticalAlignment.Center };
        group.Children.Add(Prefs.Label("MFG", "ForgeHeadingTextStyle"));
        mfg = new ComboBox { ItemsSource = Tuning.MultiplierCaptions.ToList(), MinWidth = 120 };
        mfg.SelectedIndex = Math.Max(0, Array.IndexOf(Tuning.MultiplierValues, initial.MfgMultiplier));
        AutomationProperties.SetName(mfg, "MFG Multiplier");
        mfg.SelectionChanged += (_, _) => Changed?.Invoke(this, EventArgs.Empty);
        group.Children.Add(mfg);
        group.Children.Add(Prefs.Label("Requested ratio", "ForgeCaptionDimTextStyle"));
        mfgPod = new Border { Style = Prefs.GetStyle("ForgeControlPodStyle"), Child = group };
        Grid.SetColumn(mfgPod, 2);
        grid.Children.Add(mfgPod);

        Content = grid;
        SizeChanged += (_, e) => Arrange(grid, e.NewSize.Width < 720);
    }

    bool? stacked;

    /// <summary>Three pods across, or one per row when the panel is narrow.</summary>
    void Arrange(Grid grid, bool stack)
    {
        if (stacked == stack) return;
        stacked = stack;
        grid.ColumnDefinitions.Clear();
        grid.RowDefinitions.Clear();
        grid.RowSpacing = 12;
        var pods = new[] { nrPods[0], nrPods[1], mfgPod };
        if (stack)
        {
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            for (var i = 0; i < pods.Length; i++)
            {
                grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                Grid.SetRow(pods[i], i);
                Grid.SetColumn(pods[i], 0);
            }
        }
        else
        {
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            for (var i = 0; i < pods.Length; i++)
            {
                Grid.SetRow(pods[i], 0);
                Grid.SetColumn(pods[i], i);
            }
        }
    }

    Slider AddStrengthPod(Grid grid, int column, string title, double upper, double value)
    {
        value = Math.Clamp(Math.Round(value, 1), 0.0, upper);
        var group = new StackPanel { Spacing = 3, VerticalAlignment = VerticalAlignment.Center };

        var header = new Grid { ColumnSpacing = 8 };
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var heading = Prefs.Label(title, "ForgeHeadingTextStyle");
        heading.TextWrapping = TextWrapping.NoWrap;
        heading.VerticalAlignment = VerticalAlignment.Center;
        header.Children.Add(heading);

        var number = new NumberBox
        {
            Minimum = 0, Maximum = upper, SmallChange = 0.1, LargeChange = 0.1, Value = value,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact,
            NumberFormatter = new DecimalFormatter
            {
                IntegerDigits = 1, FractionDigits = 1,
                NumberRounder = new IncrementNumberRounder { Increment = 0.1, RoundingAlgorithm = RoundingAlgorithm.RoundHalfUp },
            },
            MinWidth = 88,
        };
        AutomationProperties.SetName(number, title + " exact value");
        Grid.SetColumn(number, 1);
        header.Children.Add(number);
        group.Children.Add(header);

        var slider = new Slider
        {
            Minimum = 0, Maximum = upper, StepFrequency = 0.1, SmallChange = 0.1, Value = value,
            MinWidth = 125, IsThumbToolTipEnabled = true,
        };
        AutomationProperties.SetName(slider, title);
        ToolTipService.SetToolTip(slider, upper == 2.0 ? "0.0 - 2.0 · 0.1 increments" : "0.0 - 1.0 · 0.1 increments");
        group.Children.Add(slider);

        var detail = Prefs.Label("", "ForgeCaptionDimTextStyle");
        group.Children.Add(detail);

        void Describe(double n) => detail.Text = n == 0.0 ? "Disabled"
            : title == "NR Strength" ? $"Intensity / skin · {n:0.0}" : $"Sharpness · {n:0.0}";
        Describe(value);

        slider.ValueChanged += (_, e) =>
        {
            var n = Math.Round(e.NewValue, 1);
            Describe(n);
            if (syncing) return;
            syncing = true; number.Value = n; syncing = false;
            Changed?.Invoke(this, EventArgs.Empty);
        };
        number.ValueChanged += (_, e) =>
        {
            if (syncing || double.IsNaN(e.NewValue)) return;
            syncing = true; slider.Value = Math.Clamp(Math.Round(e.NewValue, 1), 0, upper); syncing = false;
            Describe(Math.Round(slider.Value, 1));
            Changed?.Invoke(this, EventArgs.Empty);
        };
        slider.IsEnabledChanged += (_, _) => number.IsEnabled = slider.IsEnabled;

        var pod = new Border { Style = Prefs.GetStyle("ForgeControlPodStyle"), Child = group };
        Grid.SetColumn(pod, column);
        grid.Children.Add(pod);
        nrPods.Add(pod);
        return slider;
    }

    public Tuning Value
    {
        get
        {
            var result = original with { NrStrength = Math.Round(nr.Value, 1), SharpeningStrength = Math.Round(sharpening.Value, 1),
                MfgMultiplier = Tuning.MultiplierValues[Math.Max(0, mfg.SelectedIndex)] };
            if (result.FeatureControls is null) return result;
            var values = (System.Text.Json.Nodes.JsonObject)result.FeatureControls.DeepClone();
            values["intensity"] = result.NrStrength; values["sharpness"] = result.SharpeningStrength;
            values["multiplier"] = result.MfgMultiplier == "auto" ? -1 : int.Parse(result.MfgMultiplier);
            return result with { FeatureControls = values };
        }
        set
        {
            nr.Value = value.NrStrength;
            sharpening.Value = value.SharpeningStrength;
            mfg.SelectedIndex = Math.Max(0, Array.IndexOf(Tuning.MultiplierValues, value.MfgMultiplier));
        }
    }

    /// <summary>NR controls follow NR modes; MFG follows MFG modes (details page rule).</summary>
    public void SetMode(string mode, bool enabled = true)
    {
        nr.IsEnabled = enabled && mode != "mfg-only";
        sharpening.IsEnabled = enabled;
        mfg.IsEnabled = enabled && mode != "nr-only";
        mfgPod.Opacity = mfg.IsEnabled ? 1 : 0.55;
        nrPods[0].Opacity = nr.IsEnabled ? 1 : 0.55;
    }
}
