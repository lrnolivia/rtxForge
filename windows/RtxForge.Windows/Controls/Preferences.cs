using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace RtxForge.Windows.Controls;

/// <summary>
/// Windows settings building blocks, built in code so pages read like their
/// rtxforge_gtk.py counterparts line for line. Adw.PreferencesGroup becomes a
/// Fluent section header over a stack of settings cards; Adw.ActionRow,
/// SwitchRow, ComboRow and EntryRow become settings cards with the matching
/// native control on the right.
/// </summary>
public sealed class PreferencesGroup
{
    public StackPanel Root { get; }

    /// <param name="action">Optional section action shown at the far right of the header (Adw.PreferencesGroup header suffix).</param>
    public PreferencesGroup(string? title, string? description = null, FrameworkElement? action = null)
    {
        Root = new StackPanel { Spacing = 4 };
        var header = new StackPanel();
        if (title is not null)
        {
            var heading = Prefs.Label(title, "ForgeHeadingTextStyle");
            heading.Margin = new Thickness(1, 24, 0, description is null ? 6 : 2);
            header.Children.Add(heading);
        }
        if (description is not null)
        {
            var text = Prefs.Label(description, "ForgeCaptionDimTextStyle");
            text.Margin = new Thickness(1, title is null ? 24 : 0, 0, 6);
            header.Children.Add(text);
        }
        if (action is null)
        {
            foreach (var child in header.Children.ToList()) { header.Children.Remove(child); Root.Children.Add(child); }
            return;
        }
        var row = new Grid { ColumnSpacing = 16 };
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        row.Children.Add(header);
        action.VerticalAlignment = VerticalAlignment.Bottom;
        action.Margin = new Thickness(0, 0, 0, 6);
        Grid.SetColumn(action, 1);
        row.Children.Add(action);
        Root.Children.Add(row);
    }

    public T Add<T>(T card) where T : UIElement
    {
        Root.Children.Add(card);
        return card;
    }

    public static implicit operator UIElement(PreferencesGroup group) => group.Root;
}

public static class Prefs
{
    public static Style GetStyle(string key) => (Style)Application.Current.Resources[key];

    public static TextBlock Label(string text, string style = "ForgeDimTextStyle") =>
        new() { Text = text, Style = GetStyle(style), TextWrapping = TextWrapping.Wrap };

    /// <summary>Settings card: optional icon, title, description, control on the right.</summary>
    public static Border Row(string title, string? subtitle = null, FrameworkElement? suffix = null, string? glyph = null)
    {
        var grid = new Grid { ColumnSpacing = 16 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        if (glyph is not null)
        {
            // Centered on the whole card, also when its control stacks under the text.
            // A fixed slot, so every card's text starts at the same edge whatever the glyph's width.
            var icon = new FontIcon { Glyph = glyph, FontSize = 20, Width = 24, VerticalAlignment = VerticalAlignment.Center };
            Grid.SetRowSpan(icon, 2);
            grid.Children.Add(icon);
        }

        var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Spacing = 1 };
        text.Children.Add(new TextBlock { Text = title, TextWrapping = TextWrapping.Wrap });
        if (!string.IsNullOrEmpty(subtitle))
            text.Children.Add(Label(subtitle, "ForgeCaptionDimTextStyle"));
        Grid.SetColumn(text, 1);
        grid.Children.Add(text);

        if (suffix is not null)
        {
            suffix.VerticalAlignment = VerticalAlignment.Center;
            Grid.SetColumn(suffix, 2);
            grid.Children.Add(suffix);
            // Narrow cards (phone width) put the control under the text instead of
            // squeezing the title into a column; a toggle still fits beside it.
            if (suffix is not ToggleSwitch)
            {
                grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                var alignment = suffix.HorizontalAlignment;
                var minimum = suffix.MinWidth;
                var stretch = suffix is ComboBox or TextBox or AutoSuggestBox or Button;
                grid.SizeChanged += (_, e) =>
                {
                    var stacked = e.NewSize.Width < StackWidth;
                    Grid.SetRow(suffix, stacked ? 1 : 0);
                    Grid.SetColumn(suffix, stacked ? 1 : 2);
                    Grid.SetColumnSpan(suffix, stacked ? 2 : 1);
                    suffix.Margin = new Thickness(0, stacked ? 10 : 0, 0, 0);
                    suffix.HorizontalAlignment = stacked ? stretch ? HorizontalAlignment.Stretch : HorizontalAlignment.Left : alignment;
                    suffix.MinWidth = stacked ? 0 : minimum;
                    // A row of buttons shares the full width under the text; swatches and
                    // other fixed pieces keep their size.
                    if (suffix is StackPanel { Orientation: Orientation.Horizontal } row)
                    {
                        var buttons = row.Children.OfType<Button>().ToList();
                        var fixedWidth = row.Children.OfType<FrameworkElement>().Where(child => child is not Button).Sum(child => child.ActualWidth)
                            + row.Spacing * Math.Max(0, row.Children.Count - 1);
                        var indent = grid.Children.Any(child => Grid.GetColumn((FrameworkElement)child) == 0)
                            ? grid.ColumnDefinitions[0].ActualWidth + grid.ColumnSpacing : 0;
                        var share = stacked && buttons.Count > 0
                            ? Math.Floor((e.NewSize.Width - indent - fixedWidth) / buttons.Count) : double.NaN;
                        foreach (var button in buttons) button.Width = share > 0 ? share : double.NaN;
                    }
                };
            }
        }
        return new Border { Style = GetStyle("ForgeSettingsCardStyle"), Child = grid };
    }

    /// <summary>Below this card width a row's control moves under its text.</summary>
    public const double StackWidth = 520;

    public static (Border Row, ToggleSwitch Toggle) SwitchRow(string title, string? subtitle, bool on, string? glyph = null)
    {
        var toggle = new ToggleSwitch { IsOn = on, MinWidth = 0 };
        AutomationName(toggle, title);
        return (Row(title, subtitle, toggle, glyph), toggle);
    }

    public static (Border Row, ComboBox Combo) ComboRow(string title, string? subtitle, IEnumerable<string> items, int selected, string? glyph = null)
    {
        var combo = new ComboBox { ItemsSource = items.ToList(), SelectedIndex = selected, MinWidth = 180 };
        AutomationName(combo, title);
        return (Row(title, subtitle, combo, glyph), combo);
    }

    public static (Border Row, TextBox Entry) EntryRow(string title, string? subtitle, string text, string? placeholder = null, string? glyph = null)
    {
        var entry = new TextBox { Text = text, PlaceholderText = placeholder ?? "", MinWidth = 320 };
        AutomationName(entry, title);
        return (Row(title, subtitle, entry, glyph), entry);
    }

    public static Button ActionButton(string text, RoutedEventHandler click, bool accent = false, string? glyph = null)
    {
        var button = new Button { Content = Content(text, glyph) };
        if (accent) button.Style = GetStyle("AccentButtonStyle");
        button.Click += click;
        return button;
    }

    /// <summary>Label with an optional Segoe Fluent icon, like icon_button().</summary>
    public static object Content(string text, string? glyph)
    {
        if (glyph is null) return text;
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        line.Children.Add(new FontIcon { Glyph = glyph, FontSize = 14 });
        line.Children.Add(new TextBlock { Text = text });
        return line;
    }

    static void AutomationName(DependencyObject element, string name) =>
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(element, name);
}
