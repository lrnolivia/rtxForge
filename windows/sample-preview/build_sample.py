"""Build an isolated capture fork from an exact committed Windows UI tree."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


def generate(repo, revision, output):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Use a new private output folder; previous builds are preserved')
    head = subprocess.check_output(['git', 'rev-parse', revision], cwd=repo, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', head], cwd=repo)
    output.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as files:
        files.extractall(output, filter='data')
    project = output / 'windows/RtxForge.Windows'
    tooling = Path(__file__).parent
    for source in project.rglob('*.cs'):
        text = source.read_text(encoding='utf-8-sig')
        text = text.replace('Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)', 'SampleProfile.LocalAppData')
        if source.name == 'Models.cs':
            text = text.replace('new Mutex(false, @"Local\\rtxForge.Settings")', 'new Mutex(false, SampleProfile.SettingsMutex)')
        text = text.replace('readonly HashSet<string> selectedIds = [];', 'readonly SampleSelection selectedIds = SampleProfile.Selection;')
        source.write_text(text, encoding='utf-8')
    service = project / 'Services/ForgeService.cs'
    text = service.read_text(encoding='utf-8')
    start = text.index('    const string Steam =', text.index('public sealed class PreviewForgeService'))
    end = text.index('    public bool IsPreview => true;', start)
    text = text[:start] + '    readonly List<Game> games = SampleProfile.LoadGames();\n\n' + text[end:]
    text = text.replace('        return count;\n', '        SampleProfile.SaveGameState(games);\n        return count;\n')
    service.write_text(text, encoding='utf-8')
    for original, replacement in [('App.xaml.cs', 'App.sample.cs'), ('Services/OverlayHelper.cs', 'OverlayHelper.sample.cs')]:
        (project / original).write_bytes((tooling / replacement).read_bytes())
    (project / 'SampleProfile.cs').write_bytes((tooling / 'SampleProfile.cs').read_bytes())
    engine = project / 'Services/EngineForgeService.cs'
    text = engine.read_text(encoding='utf-8')
    start = text.index('    public static async Task<(EngineForgeService? Service, string? Problem)> TryStartAsync(')
    end = text.index('    static string? FindEngineRoot()', start)
    text = text[:start] + '''    public static Task<(EngineForgeService? Service, string? Problem)> TryStartAsync(string logName = "engine.log") =>
        Task.FromResult<(EngineForgeService?, string?)>((null, "The real engine is disabled in this private sample."));

''' + text[end:]
    engine.write_text(text, encoding='utf-8')
    shell = project / 'MainWindow.xaml.cs'
    text = shell.read_text(encoding='utf-8').replace('        InitializeComponent();', '        InitializeComponent();\n        Nav.IsPaneOpen = true;', 1)
    shell.write_text(text, encoding='utf-8')
    xaml = project / 'MainWindow.xaml'
    xaml.write_text(xaml.read_text(encoding='utf-8').replace('Text="Preview"', 'Text="Sample"'), encoding='utf-8')
    # Core source stays in a private artifact folder, never in the product checkout.
    receipt = {'source': head, 'tooling': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in tooling.iterdir() if p.is_file()}, 'source_directory': str(output)}
    (output / 'sample-build-source.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return project


def package_resources(project, output):
    """A custom -o build does not always copy loose XBF resources itself."""
    project, output = Path(project), Path(output)
    intermediate = project / 'obj/x64/Release/net10.0-windows10.0.22621.0/win-x64'
    copied = []
    for source in intermediate.rglob('*.xbf'):
        relative = source.relative_to(intermediate)
        if relative.parts[0] == 'embed':
            continue
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        copied.append(str(relative))
    if not (output / 'MainWindow.xbf').is_file() or not (output / 'App.xbf').is_file():
        raise ValueError('Compiled native XAML is missing from the sample package')
    return copied


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(generate(args.repo, args.revision, args.output))
