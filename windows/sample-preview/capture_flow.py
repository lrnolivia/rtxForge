"""Private capture-only install pacing and compact startup controls."""
from pathlib import Path


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Capture source no longer matches the expected UI revision')
    return text.replace(old, new, 1)


def apply(project):
    project = Path(project)
    service = project / 'Services/ForgeService.cs'
    text = service.read_text(encoding='utf-8')
    text = replace_one(text, '            await Task.Delay(900, cancel);', '''            if (operation == "install")
                await SampleInstallProgress.WaitAsync(index, eligible.Count, game, progress, cancel);
            else await Task.Delay(900, cancel);''')
    service.write_text(text, encoding='utf-8')

    controls = project / 'Controls/PresetControlsView.cs'
    text = controls.read_text(encoding='utf-8')
    text = replace_one(text, 'bool embedded = false)\n', 'bool embedded = false, bool installation = false)\n')
    start = text.index('        var root = new StackPanel { Spacing = 24 };')
    end = text.index('        RefreshAvailability();', start)
    original = text[start:end]
    compact = '''        if (installation)
        {
            var root = new StackPanel { Spacing = 16 };
            var main = new PresetColumns(320, 2) { ColumnSpacing = 24, RowSpacing = 16 };
            main.Children.Add(Card(MfgControls()));
            var nr = Section("Neural rendering");
            nr.Spacing = 12;
            nr.Children.Add(Field("enabled"));
            nr.Children.Add(Field("style"));
            nr.Children.Add(Field("intensity"));
            main.Children.Add(Card(nr)); root.Children.Add(main);

            var more = new StackPanel { Spacing = 16 };
            more.Children.Add(Pair(Field("preset"), Field("passes")));
            var image = new StackPanel { Spacing = 12 };
            image.Children.Add(Pair(Field("detail"), Field("colour")));
            image.Children.Add(Pair(Field("structure"), Field("tone")));
            image.Children.Add(Pair(Field("skin"), Field("auto_mask")));
            more.Children.Add(Disclosure("Image tuning", image));
            var sharp = new StackPanel { Spacing = 12 };
            sharp.Children.Add(Field("sharpen"));
            sharp.Children.Add(Pair(Field("sharpen_shader"), Field("sharp_override")));
            sharp.Children.Add(Field("sharpness"));
            sharp.Children.Add(Pair(Field("motion_sharpen"), Field("motion_sharpness")));
            more.Children.Add(Disclosure("Sharpening", sharp));
            var performance = new StackPanel { Spacing = 12 };
            var fields = FeatureControlSchema.Shared.Controls.Where(f => f.Group == "Performance").ToArray();
            for (var i = 0; i < fields.Length; i += 2)
                performance.Children.Add(i + 1 < fields.Length ? Pair(Field(fields[i]), Field(fields[i + 1])) : Field(fields[i]));
            more.Children.Add(Disclosure("Performance", performance));
            root.Children.Add(Disclosure("More settings", more));
            Content = root;
        }
        else
        {
'''
    text = text[:start] + compact + original + '        }\n' + text[end:]
    controls.write_text(text, encoding='utf-8')

    dialog = project / 'Controls/OperationDialog.cs'
    text = dialog.read_text(encoding='utf-8')
    text = replace_one(text, 'Math.Min(960,', 'Math.Min(760,')
    text = replace_one(text, 'dialog.Resources["ContentDialogMaxWidth"] = 1120.0;', 'dialog.Resources["ContentDialogMaxWidth"] = 840.0;')
    text = replace_one(text, 'embedded: true) { Width = editorWidth }', 'embedded: true, installation: true) { Width = editorWidth }')
    text = replace_one(text, 'Adjust your presets or continue. You can change these settings later in OptiScaler.', 'Choose startup settings. You can adjust them later.')
    text = replace_one(text, '        dialog.PrimaryButtonText = "Continue";\n', '        dialog.PrimaryButtonText = "Review games";\n')
    dialog.write_text(text, encoding='utf-8')

    details = project / 'GameMode/GameModeView.Details.cs'
    text = details.read_text(encoding='utf-8')
    text = replace_one(text, 'bool embedded = false, bool dynamicSupported = true)\n',
                       'bool embedded = false, bool dynamicSupported = true, bool installation = false)\n')
    start = text.index('        var rows = new List<UIElement> { MfgControls() };')
    text = text[:start] + '''        if (installation)
        {
            var main = new Controls.PresetColumns(t.Px(420), 2) { ColumnSpacing = t.Px(24), RowSpacing = t.Px(20) };
            main.Children.Add(MfgControls());
            main.Children.Add(Card("Neural rendering", Field(Definition("enabled")), Choices("style"), Field(Definition("intensity"))));
            var performanceFields = controls.Where(f => f.Group == "Performance").Select(Field).ToArray();
            var morePerformance = new List<UIElement>();
            for (var i = 0; i < performanceFields.Length; i += 2)
                morePerformance.Add(i + 1 < performanceFields.Length ? Pair(performanceFields[i], performanceFields[i + 1]) : performanceFields[i]);
            var more = Disclosure("More settings",
                Pair(Field(Definition("preset")), Field(Definition("passes"))),
                Disclosure("Image tuning", Pair(Field(Definition("detail")), Field(Definition("colour"))),
                    Pair(Field(Definition("structure")), Field(Definition("tone"))), Pair(Field(Definition("skin")), Field(Definition("auto_mask")))),
                Disclosure("Sharpening", Field(Definition("sharpen")),
                    Pair(Field(Definition("sharpen_shader")), Field(Definition("sharp_override"))), Field(Definition("sharpness")),
                    Pair(Field(Definition("motion_sharpen")), Field(Definition("motion_sharpness")))),
                Disclosure("Performance", morePerformance.ToArray()));
            return ([main, more], () => FeatureControlSchema.Tuning(values));
        }
''' + text[start:]
    details.write_text(text, encoding='utf-8')

    operations = project / 'GameMode/GameModeView.Operations.cs'
    text = operations.read_text(encoding='utf-8')
    text = replace_one(text, '            dynamicSupported: shell.Settings.DynamicMfgSupported);',
                       '            dynamicSupported: shell.Settings.DynamicMfgSupported, installation: true);')
    text = replace_one(text, 'content.Children.Add(ui.P("Adjust your presets or continue. You can change these settings later in OptiScaler.", 0.92));',
                       'content.Children.Add(ui.P($"{ProviderName()} · Choose startup settings. You can adjust them later.", 0.8));')
    text = replace_one(text, '        content.Children.Add(ui.IconLabel("", ProviderName()).With(p => { foreach (var c in p.Children) if (c is TextBlock tb) tb.FontSize = t.Em(0.85); }));\n', '')
    text = replace_one(text, 'var next = ui.Button("Continue",', 'var next = ui.Button("Review games",')
    text = replace_one(text, 'ShowModal("Install Features", content, [cancel, next], Cancel, 1500, cancel);',
                       'ShowModal("Install Features", content, [cancel, next], Cancel, 1120, cancel);')
    operations.write_text(text, encoding='utf-8')
