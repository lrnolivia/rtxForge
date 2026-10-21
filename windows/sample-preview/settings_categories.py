"""Keep Game Mode-only preferences in its own settings category."""
from pathlib import Path
from capture_flow import replace_one


def apply(project):
    project = Path(project)
    desktop = project / 'Views/SettingsPage.xaml.cs'
    text = desktop.read_text(encoding='utf-8')
    text = replace_one(text, 'new PreferencesGroup("Theme and scale")', 'new PreferencesGroup("Theme")')
    text = replace_one(text, 'new PreferencesGroup("Navigation and labels")', 'new PreferencesGroup("Navigation")')
    text = replace_one(text, '        var interfaceGroup = new PreferencesGroup(',
                       '        var gameModeLayout = new PreferencesGroup("Layout and labels");\n        var interfaceGroup = new PreferencesGroup(')
    text = replace_one(text, '            if (title == "Game Mode scale") appearance.Add(row); else navigation.Add(row);',
                       '            gameModeLayout.Add(row);')
    text = replace_one(text, '        glyphs.Toggled += (_, _) => { Settings.ButtonGlyphs = glyphs.IsOn; Save(); };\n        navigation.Add(row);',
                       '        glyphs.Toggled += (_, _) => { Settings.ButtonGlyphs = glyphs.IsOn; Save(); };\n        gameModeLayout.Add(row);')
    text = replace_one(text, 'sections["Gaming Mode"] = [interfaceGroup, controller];',
                       'sections["Gaming Mode"] = [interfaceGroup, gameModeLayout, controller];')
    desktop.write_text(text, encoding='utf-8')

    game_mode = project / 'GameMode/GameModeView.Pages.cs'
    text = game_mode.read_text(encoding='utf-8')
    scale = '''                    Choice("UI scale", "Automatic uses a 130% reference at 4K and adapts to the window.", ["auto", "100", "125", "130", "150", "175", "200"],
                        ["Automatic", "100%", "125%", "130%", "150%", "175%", "200%"], () => shell.Settings.UiScaleKey,
                        value => { shell.Settings.UiScaleKey = value; DispatcherQueue.TryEnqueue(ApplySettings); }),
'''
    navigation = '''                new("Navigation and labels", null,
                [
                    Choice("Navigation placement", null, ["top", "bottom"], ["Top", "Bottom"], () => shell.Settings.NavigationPosition, value => shell.Settings.NavigationPosition = value),
                    SettingToggle("Button glyphs", "Show icons beside action labels.", () => shell.Settings.ButtonGlyphs, value => shell.Settings.ButtonGlyphs = value),
                ]),
'''
    text = replace_one(text, scale, '')
    text = replace_one(text, navigation, '')
    text = replace_one(text, 'new("Theme and scale", null,', 'new("Theme", null,')
    group = '''                new("Layout and labels", null,
                [
''' + scale.replace('Choice("UI scale"', 'Choice("Game Mode scale"') + '''                    Choice("Navigation placement", null, ["top", "bottom"], ["Top", "Bottom"], () => shell.Settings.NavigationPosition, value => shell.Settings.NavigationPosition = value),
                    SettingToggle("Button glyphs", "Show icons beside action labels.", () => shell.Settings.ButtonGlyphs, value => shell.Settings.ButtonGlyphs = value),
                ]),
'''
    text = replace_one(text, '                new("Controller", null,', group + '                new("Controller", null,')
    game_mode.write_text(text, encoding='utf-8')
