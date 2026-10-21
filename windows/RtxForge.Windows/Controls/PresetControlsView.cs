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
        var root = new StackPanel { Spacing = 12 };
        var mfg = Section("Frame generation", "Requested multiplier · enable frame generation in the game.");
        mfg.Children.Add(Field("multiplier", true)); root.Children.Add(Card(mfg));
        var primary = new PresetColumns(460, 2) { ColumnSpacing = 12, RowSpacing = 12 };
        var nr = Section("Neural rendering");
        nr.Children.Add(Field("enabled")); nr.Children.Add(Field("style")); nr.Children.Add(Field("intensity"));
        nr.Children.Add(Pair(Field("preset"), Field("passes"))); primary.Children.Add(Card(nr));
        var image = Section("Image tuning");
        image.Children.Add(Pair(Field("detail"), Field("colour")));
        var fine = new StackPanel { Spacing = 16 };
        fine.Children.Add(Pair(Field("structure"), Field("tone")));
        fine.Children.Add(Pair(Field("skin"), Field("auto_mask")));
        image.Children.Add(Disclosure("Fine tuning", fine));
        var secondary = new StackPanel { Spacing = 12 }; secondary.Children.Add(Card(image));
        var sharp = new StackPanel { Spacing = 16 };
        sharp.Children.Add(Field("sharpen")); sharp.Children.Add(Pair(Field("sharpen_shader"), Field("sharp_override")));
        sharp.Children.Add(Field("sharpness"));
        var motion = new StackPanel { Spacing = 16 };
        motion.Children.Add(Field("motion_sharpen")); motion.Children.Add(Field("motion_sharpness"));
        sharp.Children.Add(Disclosure("Motion sharpening", motion)); secondary.Children.Add(Card(Disclosure("Sharpening", sharp)));
        var performance = new StackPanel { Spacing = 16 };
        var fields = FeatureControlSchema.Shared.Controls.Where(f => f.Group == "Performance").ToArray();
        for (var i = 0; i < fields.Length; i += 2)
            performance.Children.Add(i + 1 < fields.Length ? Pair(Field(fields[i]), Field(fields[i + 1])) : Field(fields[i]));
        secondary.Children.Add(Card(Disclosure("Performance", performance)));
        primary.Children.Add(secondary); root.Children.Add(primary);
        Content = root;
        RefreshAvailability();
    }

    static StackPanel Section(string title, string? description = null)
    {
        var section = new StackPanel { Spacing = 12 };
        var heading = new StackPanel { Spacing = 4 };
        heading.Children.Add(Prefs.Label(title, "ForgeHeadingTextStyle"));
        if (description is not null) heading.Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
        section.Children.Add(heading); return section;
    }
    static Border Card(UIElement content) => new()
    { Style = Prefs.GetStyle("ForgeControlPodStyle"), Padding = new Thickness(16, 12, 16, 12), Child = content, VerticalAlignment = VerticalAlignment.Top };
    static PresetColumns Pair(params UIElement[] children)
    {
        var pair = new PresetColumns(210, 2) { ColumnSpacing = 20, RowSpacing = 16 };
        foreach (var child in children) pair.Children.Add(child); return pair;
    }
    static Expander Disclosure(string heading, StackPanel content) => new()
    {
        Header = heading, Content = content, HorizontalAlignment = HorizontalAlignment.Stretch,
        HorizontalContentAlignment = HorizontalAlignment.Stretch, Background = null, BorderThickness = new Thickness(0),
    };

    FrameworkElement Field(string key, bool hideLabel = false) => Field(FeatureControlSchema.Shared.Controls.Single(f => f.Key == key), hideLabel);
    FrameworkElement Field(FeatureControl field, bool hideLabel = false)
    {
        var value = FeatureControlSchema.Number(values, field);
        var row = new Grid { ColumnSpacing = 12, RowSpacing = 6 };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.RowDefinitions.Add(new() { Height = GridLength.Auto }); row.RowDefinitions.Add(new() { Height = GridLength.Auto });
        var title = field.Key == "enabled" ? "Enable NR on launch" : field.Caption(advanced);
        var label = Prefs.Label(title); label.VerticalAlignment = VerticalAlignment.Center;
        if (!hideLabel) row.Children.Add(label);
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
        else if (field.Key is "multiplier" or "style")
        {
            var choices = new PresetColumns(field.Key == "multiplier" ? 54 : 90, field.Values.Length) { ColumnSpacing = 2, RowSpacing = 2 };
            var buttons = new List<RadioButton>();
            var group = "preset-" + field.Key + "-" + Guid.NewGuid().ToString("N");
            for (var i = 0; i < field.Values.Length; i++)
            {
                var number = field.Values[i];
                var button = new RadioButton
                {
                    Content = field.Choices[i], GroupName = group, IsChecked = value == number,
                    Style = Prefs.GetStyle("ForgeSegmentStyle"), MinHeight = 36,
                    Padding = new Thickness(8, 6, 8, 8), HorizontalAlignment = HorizontalAlignment.Stretch,
                };
                AutomationProperties.SetName(button, title + " " + field.Choices[i]);
                button.Checked += (_, _) => Change(number);
                Grid.SetColumn(button, i); choices.Children.Add(button); buttons.Add(button);
            }
            var segments = new Border { Style = Prefs.GetStyle("ForgeSegmentGroupStyle"), Child = choices };
            Grid.SetRow(segments, hideLabel ? 0 : 1); Grid.SetColumnSpan(segments, 2); row.Children.Add(segments);
            setters[field.Key] = n => { for (var i = 0; i < buttons.Count; i++) buttons[i].IsChecked = field.Values[i] == n; };
        }
        else if (field.Kind == "choice")
        {
            var choice = new ComboBox { ItemsSource = field.Choices, SelectedIndex = Array.IndexOf(field.Values, value),
                MinWidth = 0, HorizontalAlignment = HorizontalAlignment.Stretch };
            AutomationProperties.SetName(choice, title); Grid.SetRow(choice, 1); Grid.SetColumnSpan(choice, 2); row.Children.Add(choice);
            choice.SelectionChanged += (_, _) => { if (choice.SelectedIndex >= 0) Change(field.Values[choice.SelectedIndex]); };
            setters[field.Key] = n => choice.SelectedIndex = Array.IndexOf(field.Values, n);
        }
        else
        {
            var exact = new NumberBox { Minimum = field.Min, Maximum = field.Max, Value = value, SmallChange = field.Step,
                LargeChange = field.Integer ? 1 : .1, Width = 96, MinWidth = 0, SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact,
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
                ToolTipService.SetToolTip(slider, $"{field.Min:0.##}–{field.Max:0.##}");
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

/// <summary>Paired cards and related fields stack only when their container needs room.</summary>
internal sealed class PresetColumns : Grid
{
    readonly double minimum;
    readonly int maximum;
    int columns;
    public PresetColumns(double minimum, int maximum)
    {
        this.minimum = minimum; this.maximum = maximum;
        ColumnSpacing = RowSpacing = 16;
        Loaded += (_, _) => ArrangeColumns(ActualWidth);
        SizeChanged += (_, e) => ArrangeColumns(e.NewSize.Width);
    }
    void ArrangeColumns(double width)
    {
        var count = Math.Clamp((int)((width + ColumnSpacing) / (minimum + ColumnSpacing)), 1, maximum);
        if (maximum == 4 && count == 3) count = 2;
        if (count == columns && RowDefinitions.Count == (Children.Count + count - 1) / count) return;
        columns = count; ColumnDefinitions.Clear(); RowDefinitions.Clear();
        for (var i = 0; i < count; i++) ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        for (var i = 0; i < (Children.Count + count - 1) / count; i++) RowDefinitions.Add(new() { Height = GridLength.Auto });
        for (var i = 0; i < Children.Count; i++)
            if (Children[i] is FrameworkElement child) { SetRow(child, i / count); SetColumn(child, i % count); }
    }
}
