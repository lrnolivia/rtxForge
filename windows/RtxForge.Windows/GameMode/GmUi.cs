using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.UI;
using Windows.UI.Text;

namespace RtxForge.Windows.GameMode;

public enum GmKind { Card, Primary, Danger, Quiet, Transparent, Active, Dlss }

/// <summary>
/// Builders for the prototype's components (.rf-button, .rf-segments,
/// .rf-preference, .rf-stepper, .rf-action-row, .rf-key, .rf-badge) as
/// native WinUI controls, sized from the current theme unit.
/// </summary>
public sealed class GmUi(GmTheme t)
{
    public GmTheme T => t;
    static Style Style(string key) => (Style)Application.Current.Resources[key];

    public TextBlock Text(string text, double em = 1, Color? color = null, FontWeight? weight = null, bool wrap = false, int maxLines = 0)
    {
        var block = new TextBlock
        {
            Text = text, FontSize = t.Em(em), Foreground = GmTheme.B(color ?? t.Fg),
            TextWrapping = wrap ? TextWrapping.WrapWholeWords : TextWrapping.NoWrap,
            TextTrimming = TextTrimming.CharacterEllipsis,
        };
        if (weight is { } w) block.FontWeight = w;
        if (maxLines > 0) block.MaxLines = maxLines;
        return block;
    }

    public TextBlock H1(string text, double em = 1.62) =>
        Text(text, em, weight: FontWeights.Bold).With(b => b.CharacterSpacing = -25);
    public TextBlock H2(string text, double em = 1.27) =>
        Text(text, em, weight: FontWeights.SemiBold).With(b => b.CharacterSpacing = -20);
    public TextBlock P(string text, double em = 0.85) => Text(text, em, t.Muted, wrap: true);

    public FontIcon Icon(string glyph, double em = 1, Color? color = null)
    {
        // No color: inherit the parent's foreground (setting null would make the glyph invisible).
        var icon = new FontIcon { Glyph = glyph, FontSize = t.Em(em) };
        if (color is { } c) icon.Foreground = GmTheme.B(c);
        return icon;
    }

    /// <summary>.rf-button with the prototype's 4px focus outline at a 4px offset.</summary>
    public Button Button(object content, Action? click, GmKind kind = GmKind.Card, double em = 1, bool enabled = true,
        double radius = 32, Thickness? padding = null, double minHeight = 60, string? name = null)
    {
        var (bg, fg) = kind switch
        {
            GmKind.Primary => (GmTheme.Accent, GmTheme.AccentInk),
            GmKind.Danger => (t.DangerBg, t.Danger),
            GmKind.Quiet or GmKind.Transparent => (Microsoft.UI.Colors.Transparent, t.Fg),
            GmKind.Active => (t.Active, t.ActiveFg),
            GmKind.Dlss => (t.DlssSurface, t.DlssInk),
            _ => (t.Card, t.Fg),
        };
        if (!enabled) (bg, fg) = (kind is GmKind.Quiet or GmKind.Transparent ? Microsoft.UI.Colors.Transparent : t.Disabled, t.DisabledFg);
        var button = new Button
        {
            Style = Style("GmButtonStyle"),
            Content = content is string s ? Label(s, kind) : content,
            Background = GmTheme.B(bg),
            Foreground = GmTheme.B(fg),
            FontSize = t.Em(em),
            FontWeight = kind == GmKind.Primary ? new FontWeight(650) : new FontWeight(550),
            CornerRadius = new CornerRadius(t.Px(radius)),
            Padding = padding ?? new Thickness(t.Px(kind == GmKind.Quiet ? 16 : 24), t.Px(kind == GmKind.Quiet ? 12 : 14),
                t.Px(kind == GmKind.Quiet ? 16 : 24), t.Px(kind == GmKind.Quiet ? 12 : 14)),
            MinHeight = t.Px(minHeight),
            IsEnabled = enabled,
        };
        if (kind == GmKind.Dlss)
        {
            button.BorderBrush = GmTheme.B(t.DlssBorder);
            button.BorderThickness = new Thickness(t.Px(2));
        }
        Focusable(button);
        Lift(button);
        if (click is not null) button.Click += (_, _) => click();
        if (name is not null) Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, name);
        return button;
    }

    /// <summary>
    /// A pill label centered on its letters: the line box is trimmed to cap height and baseline,
    /// so text sits in the optical middle of the pill instead of riding low on the descender space.
    /// </summary>
    public static TextBlock PillText(string text) => new()
    {
        Text = text, TextTrimming = TextTrimming.CharacterEllipsis, TextLineBounds = TextLineBounds.Tight, VerticalAlignment = VerticalAlignment.Center,
    };

    static object Label(string text, GmKind kind) => PillText(text);

    /// <summary>Content with a leading icon (button glyphs preference).</summary>
    public StackPanel IconLabel(string glyph, string text, double gap = 12)
    {
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(gap) };
        line.Children.Add(new FontIcon { Glyph = glyph, FontSize = t.Em(0.9), VerticalAlignment = VerticalAlignment.Center });
        line.Children.Add(PillText(text));
        return line;
    }

    /// <summary>Prototype focus: 4px outline in --focus, offset 4px, following the control's corners.</summary>
    public void Focusable(Control control, double offset = 4)
    {
        control.UseSystemFocusVisuals = true;
        control.FocusVisualPrimaryBrush = GmTheme.B(t.Focus);
        control.FocusVisualPrimaryThickness = new Thickness(t.Px(4));
        control.FocusVisualSecondaryThickness = new Thickness(0);
        control.FocusVisualMargin = new Thickness(-t.Px(offset + 4));
        control.IsTabStop = true;
    }

    /// <summary>Whether Windows animations are on (Settings › Accessibility › Visual effects).</summary>
    public static bool Animations => new global::Windows.UI.ViewManagement.UISettings().AnimationsEnabled;

    /// <summary>
    /// Controller/keyboard focus lifts the element: it grows (prototype
    /// scale(1.025), cards more) and casts a shadow. Pointer focus does not
    /// lift; reduced motion keeps only the shadow.
    /// </summary>
    public void Lift(UIElement element, double scale = 1.025, float depth = 24)
    {
        element.ScaleTransition = new Vector3Transition { Duration = TimeSpan.FromMilliseconds(150) };
        element.TranslationTransition = new Vector3Transition { Duration = TimeSpan.FromMilliseconds(150) };
        element.Shadow ??= new ThemeShadow();
        void Set(bool on)
        {
            if (element is FrameworkElement fe) element.CenterPoint = new System.Numerics.Vector3((float)fe.ActualWidth / 2, (float)fe.ActualHeight / 2, 0);
            var grow = on && Animations ? (float)scale : 1f;
            element.Scale = new System.Numerics.Vector3(grow, grow, 1);
            element.Translation = new System.Numerics.Vector3(0, 0, on ? depth : 0);
        }
        element.GotFocus += (_, _) => Set(element is Control c && c.FocusState != FocusState.Pointer);
        element.LostFocus += (_, _) => Set(false);
    }

    /// <summary>No grow or shadow on focus (rows that sit edge to edge).</summary>
    public static void NoLift(UIElement element)
    {
        element.ScaleTransition = null;
        element.TranslationTransition = null;
        element.Shadow = null;
        element.GotFocus += (_, _) => { element.Scale = System.Numerics.Vector3.One; element.Translation = System.Numerics.Vector3.Zero; };
    }

    /// <summary>Rows inside a rounded group: inner, rounded focus ring; no lift (would overlap neighbours).</summary>
    public void RowFocus(Button button)
    {
        Focusable(button, -8);
        button.CornerRadius = new CornerRadius(t.Px(12));
        button.ScaleTransition = null;
        button.TranslationTransition = null;
        button.Shadow = null;
        button.GotFocus += (_, _) => { button.Scale = System.Numerics.Vector3.One; button.Translation = System.Numerics.Vector3.Zero; };
    }

    /// <summary>.rf-key: a controller/keyboard key cap.</summary>
    public Border Key(string text, double em = 0.85)
    {
        return new Border
        {
            MinWidth = t.Px(32), MinHeight = t.Px(32), CornerRadius = new CornerRadius(t.Px(6)),
            Background = GmTheme.B(t.Card), Padding = new Thickness(t.Px(10), t.Px(4), t.Px(10), t.Px(4)),
            VerticalAlignment = VerticalAlignment.Center,
            Child = new TextBlock
            {
                Text = text, FontSize = t.Em(em * 0.85), FontWeight = new FontWeight(650), Foreground = GmTheme.B(t.Fg),
                HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
            },
        };
    }

    /// <summary>.rf-badge pill.</summary>
    public Border Badge(string text, Color background, Color foreground, double em = 0.62, string? glyph = null)
    {
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(6) };
        if (glyph is not null) line.Children.Add(new FontIcon { Glyph = glyph, FontSize = t.Em(em), Foreground = GmTheme.B(foreground), VerticalAlignment = VerticalAlignment.Center });
        line.Children.Add(PillText(text).With(x => { x.FontSize = t.Em(em); x.FontWeight = new FontWeight(650); x.Foreground = GmTheme.B(foreground); }));
        return Capsule(new Border
        {
            Background = GmTheme.B(background), CornerRadius = new CornerRadius(t.Px(18)),
            Padding = new Thickness(t.Px(12), t.Px(7), t.Px(12), t.Px(7)), Child = line,
            VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Left,
        });
    }

    /// <summary>.rf-group: a rounded panel of rows separated by --line.</summary>
    public Border Group(IEnumerable<UIElement> rows, Color? background = null)
    {
        var stack = new StackPanel();
        var list = rows.ToList();
        for (var i = 0; i < list.Count; i++)
        {
            stack.Children.Add(list[i]);
            if (i < list.Count - 1) stack.Children.Add(new Border { Height = 1, Background = GmTheme.B(t.Line) });
        }
        return new Border { Background = GmTheme.B(background ?? t.Panel), CornerRadius = new CornerRadius(t.Px(16)), Child = stack };
    }

    /// <summary>.rf-preference: title (+ description) with a value or control on the right.</summary>
    public Grid PreferenceRow(string title, string? description, UIElement? right, double minHeight = 100, Thickness? padding = null)
    {
        var grid = new Grid
        {
            MinHeight = t.Px(t.Compact ? minHeight * 0.78 : minHeight),
            Padding = padding ?? new Thickness(t.Px(30), t.Px(t.Compact ? 16 : 26), t.Px(30), t.Px(t.Compact ? 16 : 26)),
            ColumnSpacing = t.Px(28),
        };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Spacing = t.Px(8) };
        text.Children.Add(Text(title, 0.96, weight: FontWeights.SemiBold, wrap: true));
        if (description is not null)
            text.Children.Add(P(description, 0.83).With(p => { p.MaxWidth = t.Em(0.83) * 30; p.HorizontalAlignment = HorizontalAlignment.Left; }));
        grid.Children.Add(text);
        if (right is not null)
        {
            if (right is FrameworkElement element) element.VerticalAlignment = VerticalAlignment.Center;
            Grid.SetColumn((FrameworkElement)right, 1);
            grid.Children.Add(right);
        }
        return grid;
    }

    /// <summary>A whole-row button (.rf-action-row / choice rows) with a trailing chevron.</summary>
    public Button RowButton(string title, string? value, Action? click, bool danger = false, string? description = null,
        string? glyph = null, bool enabled = true, double minHeight = 88)
    {
        var grid = new Grid { ColumnSpacing = t.Px(22) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var text = new StackPanel { Spacing = t.Px(8), VerticalAlignment = VerticalAlignment.Center };
        var titleLine = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(12) };
        if (glyph is not null) titleLine.Children.Add(Icon(glyph, 0.85, danger ? t.Danger : null));
        titleLine.Children.Add(Text(title, 0.96, danger ? t.Danger : enabled ? t.Fg : t.DisabledFg, FontWeights.SemiBold));
        text.Children.Add(titleLine);
        if (description is not null) text.Children.Add(P(description, 0.83));
        grid.Children.Add(text);
        if (value is not null)
        {
            var v = Text(value, 0.85, t.Muted);
            v.VerticalAlignment = VerticalAlignment.Center;
            Grid.SetColumn(v, 1);
            grid.Children.Add(v);
        }
        var chevron = Icon("", 0.6, danger ? t.Danger : t.Fg);
        chevron.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(chevron, 2);
        grid.Children.Add(chevron);
        var button = Button(grid, click, GmKind.Transparent, 1, enabled, radius: 0,
            padding: new Thickness(t.Px(30), t.Px(t.Compact ? 16 : 24), t.Px(30), t.Px(t.Compact ? 16 : 24)),
            minHeight: t.Compact ? minHeight * 0.8 : minHeight);
        button.HorizontalAlignment = HorizontalAlignment.Stretch;
        button.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        if (!enabled) button.Background = GmTheme.B(Microsoft.UI.Colors.Transparent);
        RowFocus(button);   // ring inside the row: rows sit edge to edge in a rounded group
        return button;
    }

    /// <summary>
    /// .rf-stepper inside a whole-row focus target: Left/Right adjust (controller,
    /// keyboard) and the − / + glyphs are clickable.
    /// </summary>
    public Button StepperRow(string title, string? description, Func<string> value, Action<int> adjust, bool enabled = true)
    {
        var shown = Text(value(), 1.18, enabled ? t.Fg : t.DisabledFg, FontWeights.Bold);
        shown.HorizontalAlignment = HorizontalAlignment.Center;
        shown.MinWidth = t.Px(90);
        shown.TextAlignment = TextAlignment.Center;
        Border Step(string glyph, int delta)
        {
            var border = new Border
            {
                Background = GmTheme.B(t.Card), CornerRadius = new CornerRadius(t.Px(8)), Padding = new Thickness(t.Px(8)),
                Child = Icon(glyph, 0.7, enabled ? t.Fg : t.DisabledFg),
            };
            if (enabled) border.Tapped += (_, e) => { adjust(delta); shown.Text = value(); e.Handled = true; };
            return border;
        }
        var stepper = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(28), MinWidth = t.Px(220) };
        stepper.Children.Add(Step("", -1));
        stepper.Children.Add(shown);
        stepper.Children.Add(Step("", 1));
        var row = PreferenceRow(title, description, stepper);
        var button = Button(row, null, GmKind.Transparent, 1, enabled, radius: 0, padding: new Thickness(0), minHeight: 0);
        button.HorizontalAlignment = HorizontalAlignment.Stretch;
        button.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        button.Tag = new Adjustable(delta => { adjust(delta); shown.Text = value(); });
        RowFocus(button);
        return button;
    }

    /// <summary>.rf-segments: a pill group of mutually exclusive choices.</summary>
    public Border Segments(IReadOnlyList<(string Key, string Label, bool Enabled)> items, string selected, Action<string> pick, double em = 0.85)
    {
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(4) };
        foreach (var (key, label, enabled) in items)
        {
            var on = key == selected;
            var button = Capsule(Button(label, () => pick(key), GmKind.Transparent, em, enabled, radius: 8,
                padding: new Thickness(t.Px(22), t.Px(10), t.Px(22), t.Px(10)), minHeight: t.Compact ? 40 : 54));
            if (on) { button.Background = GmTheme.B(t.SegmentSelected); button.Foreground = GmTheme.B(t.ActiveFg); }
            Focusable(button, -6);
            line.Children.Add(button);
        }
        return Capsule(new Border { Background = GmTheme.B(t.Card), CornerRadius = new CornerRadius(t.Px(12)), Padding = new Thickness(t.Px(4)), Child = line });
    }

    public static Border Spacer(double height) => new() { Height = height };

    /// <summary>
    /// A true pill (.rf-badge, .rf-segments): corners always half the element's height, so the
    /// ends stay round at every UI scale instead of a fixed radius turning into a rounded rectangle.
    /// </summary>
    public static T Capsule<T>(T element) where T : FrameworkElement
    {
        void Round(double height)
        {
            var radius = new CornerRadius(Math.Max(0, height / 2));
            if (element is Border border) border.CornerRadius = radius;
            else if (element is Control control) control.CornerRadius = radius;
        }
        element.SizeChanged += (_, e) => Round(e.NewSize.Height);
        return element;
    }
}

/// <summary>A focus target Left/Right adjusts instead of moving focus.</summary>
public sealed record Adjustable(Action<int> Adjust);

static class GmExtensions
{
    public static T With<T>(this T value, Action<T> configure)
    {
        configure(value);
        return value;
    }
}
