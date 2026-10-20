using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;
using Windows.Globalization.NumberFormatting;

namespace RtxForge.Windows.Controls;

/// <summary>Native preset editor. The game panel and controller pages use this same ordered schema.</summary>
public sealed class PresetControlsView : UserControl
{
    JsonObject values;
    readonly bool advanced;
    readonly Dictionary<FeatureControl, Control> rows = [];
    readonly Dictionary<string, Action<double>> setters = [];
    bool syncing;
    string mode = "nr-mfg";
    bool available = true, legacy;
    public event EventHandler? Changed;

    public PresetControlsView(Tuning initial, bool advanced = false)
    {
        this.advanced = advanced; values = FeatureControlSchema.Resolve(initial);
        var root = new StackPanel { Spacing = 24 };
        var groups = FeatureControlSchema.Shared.Groups;
        foreach (var group in groups.Where(g => g.Parent is null))
        {
            var section = new StackPanel { Spacing = 16 };
            foreach (var field in FeatureControlSchema.Shared.Controls.Where(f => f.Group == group.Name)) section.Children.Add(Field(field));
            foreach (var child in groups.Where(g => g.Parent == group.Name))
            {
                var nested = new StackPanel { Spacing = 16 };
                foreach (var field in FeatureControlSchema.Shared.Controls.Where(f => f.Group == child.Name)) nested.Children.Add(Field(field));
                section.Children.Add(Disclosure(child.Name, nested));
            }
            if (!group.Expanded) root.Children.Add(Disclosure(group.Name, section));
            else
            {
                var heading = Prefs.Label(group.Name, "ForgeHeadingTextStyle");
                heading.Margin = new Thickness(0, root.Children.Count == 0 ? 0 : 8, 0, 0);
                root.Children.Add(heading); root.Children.Add(section);
            }
        }
        root.Children.Add(Prefs.Label("Saved presets apply on launch. Enable frame generation in the game to use MFG.", "ForgeCaptionDimTextStyle"));
        Content = root;
        RefreshAvailability();
    }

    static Expander Disclosure(string heading, StackPanel content) => new()
    {
        Header = heading, Content = content, HorizontalAlignment = HorizontalAlignment.Stretch,
        HorizontalContentAlignment = HorizontalAlignment.Stretch, Background = null, BorderThickness = new Thickness(0),
    };

    FrameworkElement Field(FeatureControl field)
    {
        var value = FeatureControlSchema.Number(values, field);
        var row = new Grid { ColumnSpacing = 20, RowSpacing = 8 };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.RowDefinitions.Add(new() { Height = GridLength.Auto }); row.RowDefinitions.Add(new() { Height = GridLength.Auto });
        var title = field.Key == "enabled" ? "Enable NR on launch" : field.Caption(advanced);
        var label = Prefs.Label(title); label.VerticalAlignment = VerticalAlignment.Center;
        row.Children.Add(label);
        void Change(double next)
        {
            if (syncing) return;
            FeatureControlSchema.Put(values, field, next);
            RefreshAvailability(); Changed?.Invoke(this, EventArgs.Empty);
        }
        if (field.Kind == "toggle")
        {
            var toggle = new ToggleSwitch { IsOn = value != 0, OnContent = "", OffContent = "", MinWidth = 0 };
            AutomationProperties.SetName(toggle, title); Grid.SetColumn(toggle, 1); row.Children.Add(toggle);
            toggle.Toggled += (_, _) => Change(toggle.IsOn ? 1 : 0);
            setters[field.Key] = n => toggle.IsOn = n != 0;
        }
        else if (field.Kind == "choice")
        {
            var choice = new ComboBox { ItemsSource = field.Choices, SelectedIndex = Array.IndexOf(field.Values, value),
                MinWidth = 170, HorizontalAlignment = HorizontalAlignment.Stretch };
            AutomationProperties.SetName(choice, title); Grid.SetRow(choice, 1); Grid.SetColumnSpan(choice, 2); row.Children.Add(choice);
            choice.SelectionChanged += (_, _) => { if (choice.SelectedIndex >= 0) Change(field.Values[choice.SelectedIndex]); };
            setters[field.Key] = n => choice.SelectedIndex = Array.IndexOf(field.Values, n);
        }
        else
        {
            var exact = new NumberBox { Minimum = field.Min, Maximum = field.Max, Value = value, SmallChange = field.Step,
                LargeChange = field.Integer ? 1 : .1, MinWidth = 104, SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact,
                NumberFormatter = new DecimalFormatter { IntegerDigits = 1, FractionDigits = field.Integer ? 0 : 2 } };
            AutomationProperties.SetName(exact, title + " exact value"); Grid.SetColumn(exact, 1); row.Children.Add(exact);
            if (field.Kind == "slider")
            {
                var slider = new Slider { Minimum = field.Min, Maximum = field.Max, Value = value, StepFrequency = field.Step,
                    SmallChange = field.Step, IsThumbToolTipEnabled = false };
                AutomationProperties.SetName(slider, title); Grid.SetRow(slider, 1); Grid.SetColumnSpan(slider, 2); row.Children.Add(slider);
                slider.ValueChanged += (_, e) => { if (syncing) return; syncing = true; exact.Value = e.NewValue; syncing = false; Change(e.NewValue); };
                exact.ValueChanged += (_, e) => { if (syncing || !double.IsFinite(e.NewValue)) return; syncing = true; slider.Value = e.NewValue; syncing = false; Change(e.NewValue); };
                setters[field.Key] = n => { slider.Value = n; exact.Value = n; };
                ToolTipService.SetToolTip(slider, $"{field.Min:0.##}–{field.Max:0.##} · {field.Display(value, advanced)}");
            }
            else
            {
                exact.ValueChanged += (_, e) => { if (double.IsFinite(e.NewValue) && e.NewValue == Math.Truncate(e.NewValue)) Change(e.NewValue); };
                setters[field.Key] = n => exact.Value = n;
            }
        }
        var control = new UserControl { Content = row };
        rows[field] = control;
        return control;
    }

    public Tuning Value
    {
        get => FeatureControlSchema.Tuning(values);
        set
        {
            values = FeatureControlSchema.Resolve(value); syncing = true;
            try { foreach (var definition in FeatureControlSchema.Shared.Controls) setters[definition.Key](FeatureControlSchema.Number(values, definition)); }
            finally { syncing = false; }
            RefreshAvailability(); Changed?.Invoke(this, EventArgs.Empty);
        }
    }
    public bool HasChanges(Tuning reference) => !JsonNode.DeepEquals(values, FeatureControlSchema.Resolve(reference));
    public void SetMode(string selected, bool enabled = true, bool legacy = false)
    { mode = selected; available = enabled; this.legacy = legacy; RefreshAvailability(); }
    void RefreshAvailability()
    {
        bool On(string key) => FeatureControlSchema.Read(values[key]) != 0;
        foreach (var (field, row) in rows)
        {
            row.IsEnabled = available && FeatureControlSchema.Available(field, mode, legacy) && (field.Key switch
            {
                "reduced" => On("pre_sr"), "work_scale" => !On("pre_sr") || On("reduced"), "interval" => On("cache"),
                "sharpness" => On("sharpen") && On("sharp_override"), "motion_sharpness" => On("sharpen") && On("motion_sharpen"), _ => true,
            });
            row.Opacity = row.IsEnabled ? 1 : .55;
        }
    }
}
