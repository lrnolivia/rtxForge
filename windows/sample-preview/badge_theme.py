"""Theme-correct status surfaces for the private sample UI."""
from pathlib import Path
from capture_flow import replace_one


def apply(project):
    project = Path(project)
    (project / 'SampleBadgeTheme.cs').write_bytes((Path(__file__).parent / 'SampleBadgeTheme.cs').read_bytes())

    operation = project / 'Controls/OperationDialog.cs'
    text = operation.read_text(encoding='utf-8')
    text = replace_one(text, '        if (ready && game is not null) _ = ReviewAccentAsync(thumb, pill, pillLine, game);',
        '''        if (ready && game is not null) _ = ReviewAccentAsync(thumb, pill, pillLine, game);
        else SampleBadgeTheme.AttachLight(pill, ready
            ? global::Windows.UI.Color.FromArgb(255, 49, 91, 21)
            : global::Windows.UI.Color.FromArgb(255, 155, 48, 40));''')
    text = replace_one(text, '            if (child is TextBlock text) text.Foreground = palette.Brush(palette.BadgeFg);\n        }',
                       '            if (child is TextBlock text) text.Foreground = palette.Brush(palette.BadgeFg);\n        }\n        SampleBadgeTheme.AttachLight(badge, palette.Color);')
    operation.write_text(text, encoding='utf-8')

    review = project / 'Controls/ReviewDialog.cs'
    text = review.read_text(encoding='utf-8')
    text = replace_one(text, '            Grid.SetColumn(pill, 2);', '''            SampleBadgeTheme.AttachLight(pill, ready
                ? global::Windows.UI.Color.FromArgb(255, 49, 91, 21)
                : global::Windows.UI.Color.FromArgb(255, 155, 48, 40));
            Grid.SetColumn(pill, 2);''')
    review.write_text(text, encoding='utf-8')

    supported = project / 'Controls/SupportedFeatureCard.cs'
    text = supported.read_text(encoding='utf-8')
    text = replace_one(text, '        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(pill,',
                       '        SampleBadgeTheme.AttachLight(pill, colour);\n        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(pill,')
    supported.write_text(text, encoding='utf-8')

    ui = project / 'GameMode/GmUi.cs'
    text = ui.read_text(encoding='utf-8')
    signature = '    public Border Badge(string text, Color background, Color foreground, double em = 0.62, string? glyph = null)\n    {\n'
    text = replace_one(text, signature, signature + '''        var badgeColors = SampleBadgeTheme.Light(foreground);
        if (t.IsLight) { background = badgeColors.Surface; foreground = badgeColors.Ink; }
''')
    start = text.index(signature)
    before, after = text[:start], text[start:]
    after = replace_one(after, '            Background = GmTheme.B(background), CornerRadius = new CornerRadius(t.Px(18)),',
                       '''            BorderBrush = t.IsLight ? GmTheme.B(badgeColors.Stroke) : null,
            BorderThickness = new Thickness(t.IsLight ? 1 : 0),
            Background = GmTheme.B(background), CornerRadius = new CornerRadius(t.Px(18)),''')
    ui.write_text(before + after, encoding='utf-8')

    gm_operations = project / 'GameMode/GameModeView.Operations.cs'
    text = gm_operations.read_text(encoding='utf-8')
    text = replace_one(text, '        if (badge.Child is StackPanel line) foreach (var c in line.Children.OfType<TextBlock>()) c.Foreground = GmTheme.B(colors.TintText);',
                       '        if (badge.Child is StackPanel line) foreach (var c in line.Children.OfType<TextBlock>()) c.Foreground = GmTheme.B(colors.TintText);\n        if (t.IsLight) SampleBadgeTheme.AttachLight(badge, colors.Accent);')
    gm_operations.write_text(text, encoding='utf-8')

    library = project / 'GameMode/GameModeView.Library.cs'
    text = library.read_text(encoding='utf-8')
    text = replace_one(text, '                chip.BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Transparent);',
                       '                chip.BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Transparent);\n                if (t.IsLight) SampleBadgeTheme.AttachLight(chip, colors.Accent);')
    library.write_text(text, encoding='utf-8')

    game_item = project / 'ViewModels/GameItem.cs'
    text = game_item.read_text(encoding='utf-8')
    anchor = '    public Brush CardStatusPillFill => '
    start = text.index(anchor)
    end = text.index('\n\n', start)
    original = text[start:end]
    # The existing dark selected/unselected expressions remain intact.
    lines = original.splitlines()
    roles = [
        ('LightStatusColors.Surface', 'LightStatusColors.Ink'),
        ('LightTestColors.Surface', 'LightTestColors.Ink'),
    ]
    for index, expression in enumerate([roles[0][0], roles[0][1], roles[1][0], roles[1][1]]):
        lines[index] = lines[index].replace('=> ', '=> IsLight ? new SolidColorBrush(' + expression + ') : ', 1)
    helpers = '''    bool IsLight => themeHost?.ActualTheme == ElementTheme.Light;
    SampleBadgeColors LightStatusColors => SampleBadgeTheme.Light(selected && palette is not null
        ? palette.Color : Color.FromArgb(255, 85, 85, 85));
    SampleBadgeColors LightTestColors => SampleBadgeTheme.Light(Color.FromArgb(255, 49, 91, 21));
'''
    text = text[:start] + helpers + '\n'.join(lines) + text[end:]
    text = replace_one(text, '    public Brush RowChipFill => ',
                       '    public Brush RowChipFill => IsLight ? new SolidColorBrush(LightStatusColors.Surface) : ')
    game_item.write_text(text, encoding='utf-8')
