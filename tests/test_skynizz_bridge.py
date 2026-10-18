"""Check the real compiled dependency produced by the Windows build."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import skynizz_provider


class PlacementCandidateTest(unittest.TestCase):
    def test_candidate_is_hash_bound_and_separate_from_the_default(self):
        root = ROOT / 'providers/skynizz-bridge'
        base = json.loads((root / 'source.json').read_text(encoding='utf-8-sig'))
        candidate = json.loads((root / 'placement-candidate.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(candidate['base_bridge_id'], base['id'])
        self.assertEqual(candidate['base_patch_sha256'], base['patch_sha256'])
        self.assertNotEqual(candidate['id'], base['id'])
        self.assertFalse(candidate['runtime_verified'])
        self.assertFalse(candidate['default_promoted'])
        for name, expected in ((candidate['patch'], candidate['patch_sha256']),
                               (candidate['header'], candidate['header_sha256'])):
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), expected)

    def test_real_route_header_restores_inputs_and_never_adds_a_second_pass(self):
        source = ROOT / 'providers/skynizz-bridge/nr-route-test.cpp'
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            executable = out / ('routes.exe' if os.name == 'nt' else 'routes')
            compiler = shutil.which('g++') or shutil.which('clang++')
            if compiler:
                command = [compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(executable)]
            elif os.name == 'nt':
                vswhere = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
                found = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires',
                    'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-find', r'MSBuild\**\Bin\MSBuild.exe'], text=True).splitlines()
                self.assertTrue(found, 'The Windows lane requires the C++ build tools')
                project = out / 'routes.vcxproj'
                project.write_text(f'''<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
<ItemGroup Label="ProjectConfigurations"><ProjectConfiguration Include="Release|x64"><Configuration>Release</Configuration><Platform>x64</Platform></ProjectConfiguration></ItemGroup>
<Import Project="$(VCTargetsPath)\\Microsoft.Cpp.Default.props" />
<PropertyGroup Label="Configuration"><ConfigurationType>Application</ConfigurationType><PlatformToolset>v143</PlatformToolset></PropertyGroup>
<Import Project="$(VCTargetsPath)\\Microsoft.Cpp.props" />
<PropertyGroup><OutDir>{escape(str(out))}\\</OutDir><IntDir>{escape(str(out))}\\obj\\</IntDir><TargetName>routes</TargetName></PropertyGroup>
<ItemDefinitionGroup><ClCompile><LanguageStandard>stdcpp20</LanguageStandard><ExceptionHandling>Sync</ExceptionHandling></ClCompile></ItemDefinitionGroup>
<ItemGroup><ClCompile Include="{escape(str(source))}" /></ItemGroup>
<Import Project="$(VCTargetsPath)\\Microsoft.Cpp.targets" /></Project>''', encoding='utf-8')
                command = [found[0], str(project), '/p:Configuration=Release', '/p:Platform=x64', '/v:q']
            else:
                self.skipTest('A C++ compiler is required for this source test')
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            ran = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            self.assertIn('native/internal SR, RR, FG, off, fallback and restoration', ran.stdout)


@unittest.skipUnless((ROOT / 'windows/out/skynizz-bridge/package.json').is_file(),
                     'The Windows build produces the compiled bridge')
class CompiledBridgeTest(unittest.TestCase):
    def test_compiled_archive_matches_its_source_receipt(self):
        record, archive = skynizz_provider.bundled_bridge()
        payload, meta = skynizz_provider.load_payload(archive, record)
        for source, destination in skynizz_provider.FILES.items():
            self.assertEqual(hashlib.sha256(payload[destination]).hexdigest(), record['files'][source])
        self.assertGreater(len(payload['dxgi.dll']), 64 * 1024)
        self.assertFalse(meta['runtime_verified'])
        skynizz_provider.require_mode('windows', 'nr-mfg', bridge=True)


if __name__ == '__main__':
    unittest.main()
