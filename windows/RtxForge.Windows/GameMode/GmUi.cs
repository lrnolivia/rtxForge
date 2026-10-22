using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Services;
using Windows.UI;
using Windows.UI.Text;

namespace RtxForge.Windows.GameMode;

public enum GmKind { Card, Primary, Danger, Quiet, Transparent, Active, Dlss }

/// <summary>
/// Builders for the prototype's components (.rf-button, .rf-segments,
/// .rf-preference, .rf-stepper, .rf-action-row, .rf-key, .rf-badge) as
/// native WinUI controls, sized from the current theme unit.
/// </summary>
public sealed partial class GmUi(GmTheme t)
{
    public GmTheme T => t;
    public SolidColorBrush FocusBrush { get; } = GmTheme.B(t.Focus);
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

    /// <summary>Native button with a restrained, visible controller focus indicator.</summary>
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
            Background = enabled && bg.A > 0 ? t.Surface(bg, control: true) : GmTheme.B(bg),
            BorderBrush = enabled && bg.A > 0 ? t.SurfaceEdge() : GmTheme.B(Microsoft.UI.Colors.Transparent),
            Foreground = GmTheme.B(fg),
            FontSize = t.Em(em),
            FontWeight = kind == GmKind.Primary ? new FontWeight(650) : new FontWeight(550),
            CornerRadius = new CornerRadius(t.Px(radius)),
            Padding = padding ?? new Thickness(t.Px(kind == GmKind.Quiet ? 16 : 24), t.Px(kind == GmKind.Quiet ? 12 : 14),
                t.Px(kind == GmKind.Quiet ? 16 : 24), t.Px(kind == GmKind.Quiet ? 12 : 14)),
            MinHeight = t.Px(minHeight),
            IsEnabled = enabled,
        };
        if ((kind is GmKind.Card or GmKind.Active or GmKind.Primary or GmKind.Danger) && button.Content is UIElement contentElement)
            InheritButtonInk(contentElement);
        if (kind == GmKind.Dlss)
        {
            button.BorderBrush = GmTheme.B(t.DlssBorder);
            button.BorderThickness = new Thickness(t.Px(2));
        }
        Focusable(button);
        if (click is not null) button.Click += (_, _) => click();
        if (name is not null) Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, name);
        return button;
    }

    // Nested labels inherit the button's contrast choice rather than the
    // page's text color. Bright accent/danger surfaces retain their dark ink.
    static void InheritButtonInk(UIElement content)
    {
        if (content is TextBlock label) label.ClearValue(TextBlock.ForegroundProperty);
        else if (content is FontIcon icon) icon.ClearValue(IconElement.ForegroundProperty);
        else if (content is Panel panel) foreach (var child in panel.Children) InheritButtonInk(child);
        else if (content is Border { Child: UIElement child }) InheritButtonInk(child);
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
    public StackPanel IconLabel(string glyph, string text, double gap = 18)
    {
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(gap) };
        line.Children.Add(new FontIcon { Glyph = glyph, FontSize = t.Em(0.9), Width = t.Px(24), VerticalAlignment = VerticalAlignment.Center });
        line.Children.Add(PillText(text));
        return line;
    }

    /// <summary>Focus stays separate from selection without growing into neighbouring controls.</summary>
    public void Focusable(Control control, double offset = 0)
    {
        control.UseSystemFocusVisuals = control is not Microsoft.UI.Xaml.Controls.Button;
        control.FocusVisualPrimaryBrush = FocusBrush;
        control.FocusVisualPrimaryThickness = new Thickness(t.Px(t.IsLight ? 1.25 : 1.75));
        control.FocusVisualSecondaryThickness = new Thickness(0);
        control.FocusVisualMargin = new Thickness(-t.Px(offset + 2));
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
        if (!t.IsLight) element.Shadow ??= new ThemeShadow();
        void Set(bool on)
        {
            if (element is FrameworkElement fe) element.CenterPoint = new System.Numerics.Vector3((float)fe.ActualWidth / 2, (float)fe.ActualHeight / 2, 0);
            var grow = on && Animations ? (float)scale : 1f;
            element.Scale = new System.Numerics.Vector3(grow, grow, 1);
            element.Translation = new System.Numerics.Vector3(0, 0, on ? t.IsLight ? Math.Min(depth, 8) : depth : 0);
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

    /// <summary>Menu focus adds a surface and brighter ink; selection colours remain owned by the page.</summary>
    public void MenuFocus(Button button)
    {
        Brush? priorBackground = null, priorForeground = null;
        var focusedBackground = GmTheme.B(t.RowFocus);
        var focusedForeground = GmTheme.B(t.ActiveFg);
        button.GotFocus += (_, _) =>
        {
            if (button.FocusState == FocusState.Pointer) return;
            focusedBackground.Color = ArtAccent.Mix(FocusBrush.Color, t.Panel, t.IsLight ? .10 : .18);
            focusedForeground.Color = ArtAccent.Readable(FocusBrush.Color, focusedBackground.Color);
            priorBackground = button.Background; priorForeground = button.Foreground;
            button.Background = focusedBackground; button.Foreground = focusedForeground;
        };
        button.LostFocus += (_, _) =>
        {
            if (ReferenceEquals(button.Background, focusedBackground)) button.Background = priorBackground;
            if (ReferenceEquals(button.Foreground, focusedForeground)) button.Foreground = priorForeground;
        };
    }

    /// <summary>.rf-key: a controller/keyboard key cap.</summary>
    public Border Key(string text, double em = 0.85)
    {
        return new Border
        {
            MinWidth = t.Px(32), MinHeight = t.Px(32), CornerRadius = new CornerRadius(t.Px(6)),
            Background = t.Surface(t.Card, control: true), Padding = new Thickness(t.Px(10), t.Px(4), t.Px(10), t.Px(4)),
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
        var badgeColors = BadgeTheme.Light(foreground);
        if (t.IsLight) { background = badgeColors.Surface; foreground = badgeColors.Ink; }
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(6) };
        if (glyph is not null) line.Children.Add(new FontIcon { Glyph = glyph, FontSize = t.Em(em), Foreground = GmTheme.B(foreground), VerticalAlignment = VerticalAlignment.Center });
        line.Children.Add(PillText(text).With(x => { x.FontSize = t.Em(em); x.FontWeight = new FontWeight(650); x.Foreground = GmTheme.B(foreground); }));
        return Capsule(new Border
        {
            BorderBrush = t.IsLight ? GmTheme.B(badgeColors.Stroke) : null,
            BorderThickness = new Thickness(t.IsLight ? 1 : 0),
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
        return new Border { Background = t.Surface(background ?? t.Panel), CornerRadius = new CornerRadius(t.Px(16)), Child = stack };
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
        var titleText = Text(title, 0.96, danger ? t.Danger : enabled ? t.Fg : t.DisabledFg, FontWeights.SemiBold);
        titleLine.Children.Add(titleText);
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
        if (!danger)
        {
            MenuFocus(button);
            button.GotFocus += (_, _) => { if (button.FocusState != FocusState.Pointer) titleText.Foreground = GmTheme.B(t.ActiveFg); };
            button.LostFocus += (_, _) => titleText.Foreground = GmTheme.B(enabled ? t.Fg : t.DisabledFg);
        }
        return button;
    }

    /// <summary>Settings-specific cards: finite labels and a bounded trailing value field.</summary>
    public void StyleSettingsRow(Button button)
    {
        if (button.Content is not Grid grid || grid.Children.FirstOrDefault() is not StackPanel text) return;
        button.Background = GmTheme.B(t.Panel);
        button.CornerRadius = new CornerRadius(t.Px(12));
        button.Padding = new Thickness(t.Px(28), t.Px(22), t.Px(28), t.Px(22));
        button.MinHeight = t.Px(84);
        grid.ColumnSpacing = t.Px(24); text.Spacing = t.Px(10);
        if (text.Children.FirstOrDefault() is StackPanel titleLine)
        {
            if (titleLine.Children.OfType<TextBlock>().FirstOrDefault() is { } caption && titleLine.Children.Count == 1)
                titleLine.Children.Insert(0, Icon(SettingsGlyph(caption.Text), .95));
            var title = new Grid { ColumnSpacing = titleLine.Children.Count > 1 ? t.Px(10) : 0 };
            title.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
            title.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            foreach (var child in titleLine.Children.ToList())
            {
                titleLine.Children.Remove(child);
                if (child is TextBlock label)
                {
                    label.TextWrapping = TextWrapping.WrapWholeWords; label.FontSize = t.Em(.90);
                    Grid.SetColumn(label, 1);
                }
                title.Children.Add(child);
            }
            text.Children[0] = title;
        }
        foreach (var description in text.Children.OfType<TextBlock>()) description.FontSize = t.Em(.74);
        if (grid.Children.OfType<TextBlock>().FirstOrDefault() is not { } value)
        { Grid.SetColumnSpan(text, 2); return; }
        grid.Children.Remove(value);
        value.TextWrapping = TextWrapping.WrapWholeWords; value.MaxLines = 2;
        value.FontSize = t.Em(.83); value.Foreground = GmTheme.B(t.Fg);
        value.TextAlignment = TextAlignment.Center;
        var field = new Border
        {
            Background = GmTheme.B(t.Card), CornerRadius = new CornerRadius(t.Px(9)),
            Padding = new Thickness(t.Px(12), t.Px(10), t.Px(12), t.Px(10)),
            MinWidth = t.Px(160), MaxWidth = t.Px(280), Child = value,
            HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center,
        };
        Grid.SetColumn(field, 1); grid.Children.Add(field);
        grid.RowDefinitions.Add(new() { Height = GridLength.Auto });
        grid.RowDefinitions.Add(new() { Height = GridLength.Auto });
        var chevron = grid.Children.OfType<FontIcon>().Single();
        button.SizeChanged += (_, e) =>
        {
            var narrow = e.NewSize.Width < t.Px(540);
            Grid.SetColumnSpan(text, narrow ? 3 : 1);
            Grid.SetRow(field, narrow ? 1 : 0); Grid.SetColumn(field, narrow ? 0 : 1);
            Grid.SetColumnSpan(field, narrow ? 2 : 1); Grid.SetRow(chevron, narrow ? 1 : 0);
            grid.RowSpacing = narrow ? t.Px(12) : 0;
        };
    }

    static string SettingsGlyph(string title) => title switch
    {
        "Provider" => "\uE7F4", "Default mode" or "Enable NR on launch" => "\uE9E9",
        "Update DLSS files" => "\uE8A5", "4K borderless on install" => "\uE7F4",
        "Recognize existing features" => "\uE73E", "Theme" or "Accent color" => "\uE790",
        "UI scale" or "Game Mode scale" => "\uE740", "Controller labels" or "Controller hints" => "\uE7FC",
        "Navigation" or "Navigation position" => "\uE8A0", "Library layout" => "\uE8A9",
        "Shortcut" or "Live controls shortcut" => "\uE765", "Interface" => "\uE737",
        _ when title.Contains("artwork", StringComparison.OrdinalIgnoreCase) => "\uEB9F",
        _ when title.Contains("Steam", StringComparison.OrdinalIgnoreCase) => "\uE7FC",
        _ when title.Contains("folder", StringComparison.OrdinalIgnoreCase) => "\uE838",
        _ => "\uE713",
    };

    /// <summary>
    /// .rf-stepper inside a whole-row focus target: Left/Right adjust (controller,
    /// keyboard) and the − / + glyphs are clickable.
    /// </summary>
    public Button StepperRow(string title, string? description, Func<string> value, Action<int> adjust, bool enabled = true, bool compact = false)
    {
        var shown = Text(value(), 1.18, enabled ? t.Fg : t.DisabledFg, FontWeights.Bold);
        shown.HorizontalAlignment = HorizontalAlignment.Center;
        shown.MinWidth = t.Px(compact ? 60 : 90);
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
        var stepper = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(compact ? 12 : 28), MinWidth = compact ? 0 : t.Px(220) };
        stepper.Children.Add(Step("", -1));
        stepper.Children.Add(shown);
        stepper.Children.Add(Step("", 1));
        FrameworkElement row;
        if (compact)
        {
            var column = new StackPanel { Spacing = t.Px(8), Padding = new Thickness(t.Px(16), t.Px(12), t.Px(16), t.Px(12)) };
            column.Children.Add(Text(title, .85, weight: FontWeights.SemiBold, wrap: true));
            column.Children.Add(stepper);
            if (description is not null) column.Children.Add(P(description, .7));
            row = column;
        }
        else row = PreferenceRow(title, description, stepper);
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
            if (on) { button.Background = t.Surface(t.SegmentSelected, control: true); button.BorderBrush = t.SurfaceEdge(); button.Foreground = GmTheme.B(t.ActiveFg); }
            Focusable(button, -6);
            line.Children.Add(button);
        }
        return Capsule(new Border { Background = t.Surface(t.Card), CornerRadius = new CornerRadius(t.Px(12)), Padding = new Thickness(t.Px(4)), Child = line });
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
