"""Editing state and recipe-bound named preset behavior, without touching games."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'windows/tests'), str(ROOT / 'windows/engine-host'), str(ROOT / 'scripts')]
from test_companion_controls import ControlsTest, snapshot
import companion_controls as control
import transactions as t


class NamedPresetTest(ControlsTest):
    def save_named(self, name, values=None):
        return self.controls.preset_save({'row': self.row, 'changes': {'name': name, 'values': values or {'intensity': .8}}})

    def test_named_presets_survive_restart_and_do_not_cross_games(self):
        self.save_named('Natural')
        self.save_named('Night', {'intensity': .5, 'passes': 2})
        reopened = control.Controls(self.root / 'state')
        entries = reopened.preset_list({'row': self.row})['named_presets']
        self.assertEqual([p['name'] for p in entries], ['Natural', 'Night'])
        self.assertEqual(entries[1]['values']['passes'], 2)
        other = dict(self.row, exe='Bin/Other.exe')
        (self.target / 'Other.exe').write_bytes(b'other')
        self.assertEqual(reopened.preset_list({'row': other})['named_presets'], [])

    def test_package_drift_retains_names_but_withholds_values(self):
        self.save_named('Natural')
        self.metadata['files']['nvngx_dlssnr.dll'] = 'b' * 64
        self.write_metadata()
        entry = self.controls.preset_list({'row': self.row})['named_presets'][0]
        self.assertEqual(entry, {'name': 'Natural', 'compatible': False, 'values': {}})

    def test_legacy_preset_migrates_and_deletion_does_not_resurrect_it(self):
        self.controls.save({'row': self.row, 'changes': {'intensity': .6}})
        self.assertEqual(self.controls.preset_list({'row': self.row})['named_presets'][0]['name'], 'Saved preset')
        self.controls.preset_delete({'row': self.row, 'changes': {'name': 'Saved preset'}})
        self.assertEqual(self.controls.preset_list({'row': self.row})['named_presets'], [])
        self.assertEqual(self.controls.presets[next(iter(self.controls.presets))]['changes']['intensity'], .6)

    def test_invalid_names_values_and_library_limit_preserve_existing_data(self):
        self.save_named('Natural')
        for name in ('', ' padded ', 'line\nbreak', 'x' * 61):
            with self.subTest(name=name), self.assertRaises(t.Refusal): self.save_named(name)
        for values in ({'unknown': 1}, {'intensity': float('nan')}, {'passes': 4}):
            with self.subTest(values=values), self.assertRaises(t.Refusal): self.save_named('Invalid', values)
        self.save_named('NATURAL', {'intensity': .7})
        self.assertEqual(len(self.controls.preset_list({'row': self.row})['named_presets']), 1)
        for n in range(11): self.save_named(f'Preset {n}')
        with self.assertRaises(t.Refusal): self.save_named('Too many')
        self.assertEqual(len(self.controls.preset_list({'row': self.row})['named_presets']), 12)

    def test_library_does_not_change_live_values_when_listing_or_deleting(self):
        self.save_named('Natural')
        with patch.object(self.controls, 'apply', side_effect=AssertionError('Unexpected live edit')):
            self.controls.preset_list({'row': self.row})
            self.controls.preset_delete({'row': self.row, 'changes': {'name': 'Natural'}})

    def test_invalid_library_is_reported_without_overwriting_it(self):
        self.save_named('Natural')
        path = next((self.controls.state / 'named').glob('*.json'))
        original = b'{broken'
        path.write_bytes(original)
        with self.assertRaises(ValueError): self.save_named('New')
        self.assertEqual(path.read_bytes(), original)

    def test_pass_controls_round_trip_only_in_protocol_eight(self):
        raw = snapshot(version=8)
        struct = __import__('struct')
        actual, _ = control.PROTOCOL8['pass2_strength']
        struct.pack_into('<f', raw, actual, .65)
        found = control.decode(raw, 123)
        self.assertAlmostEqual(found['values']['pass2_strength'], .65, places=5)
        self.assertEqual(found['values']['pass2_inherit'], 1)
        self.assertFalse(set(control.PROTOCOL8) & set(control.decode(snapshot(version=7), 123)['values']))
        for value in (float('nan'), -1, 2.01):
            struct.pack_into('<f', raw, actual, value)
            with self.assertRaises(t.Refusal): control.decode(raw, 123)
        raw = snapshot(version=8)
        struct.pack_into('<f', raw, control.PROTOCOL8['pass2_inherit'][0], .5)
        with self.assertRaises(t.Refusal): control.decode(raw, 123)
        with self.assertRaises(t.Refusal): control.decode(snapshot(version=8)[:512], 123)


class SessionStateTest(unittest.TestCase):
    def test_real_cpp_editing_state_and_missing_measurements(self):
        header = (ROOT / 'providers/skynizz-bridge/ForgeWorkbench.h').as_posix()
        code = r'''
#include "HEADER"
#include <cassert>
#include <limits>
using namespace ForgeWorkbench;
int main() {
    Values original{{"strength",1}, {"passes",1}}, modified=original;
    Edits edits; edits.Start(original);
    modified["strength"] = .8f;
    edits.Record(original,modified);
    assert(Equal(edits.Undo(modified), original));
    assert(Equal(edits.Redo(original), modified));
    edits.BeginComparison(modified);
    Values changed=modified; changed["passes"]=2;
    assert(Equal(edits.Compare(1,changed), modified));
    Values b=modified; b["strength"] = .3f;
    assert(Equal(edits.Compare(0,b), changed));
    assert(Equal(edits.Compare(1,changed), b));
    assert(Equal(edits.saved, original));
    edits.EndComparison(b); assert(!edits.comparing);
    auto undo=edits.Undo(modified);
    edits.Record(undo,b); assert(edits.future.empty());
    for(int i=0;i<100;++i) { Values next{{"strength",float(i)}}; edits.Record(b,next); b=next; }
    assert(edits.past.size()<=Edits::Limit);
    const auto count=edits.past.size(); edits.Record(b,b); assert(edits.past.size()==count);
    History history;
    history.Add(0,0,-1,std::numeric_limits<double>::quiet_NaN());
    assert(history.samples.front().nr==-1 && history.samples.front().displayed==-1);
    history.Add(.1,4,60,120); assert(history.samples.size()==1);
    for(int i=1;i<100;++i) history.Add(i,4,60,120);
    assert(history.samples.back().time-history.samples.front().time<=30);
    assert(history.samples.size()<=61);
    history.Add(1,4,60,120); assert(history.samples.size()==1);
    return 0;
}
'''.replace('HEADER', header)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            source = out / 'workbench.cpp'; source.write_text(code)
            binary = out / ('workbench.exe' if os.name == 'nt' else 'workbench')
            compiler = shutil.which('g++') or shutil.which('clang++')
            if compiler:
                command = [compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)]
            else:
                vswhere = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
                msbuild = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires',
                    'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-find', r'MSBuild\**\Bin\MSBuild.exe'], text=True).splitlines()[0]
                project = out / 'workbench.vcxproj'
                project.write_text(f'''<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
<ItemGroup Label="ProjectConfigurations"><ProjectConfiguration Include="Release|x64"><Configuration>Release</Configuration><Platform>x64</Platform></ProjectConfiguration></ItemGroup>
<Import Project="$(VCTargetsPath)\\Microsoft.Cpp.Default.props" />
<PropertyGroup Label="Configuration"><ConfigurationType>Application</ConfigurationType><PlatformToolset>v143</PlatformToolset></PropertyGroup>
<Import Project="$(VCTargetsPath)\\Microsoft.Cpp.props" />
<PropertyGroup><OutDir>{escape(str(out))}\\</OutDir><IntDir>{escape(str(out))}\\obj\\</IntDir><TargetName>workbench</TargetName></PropertyGroup>
<ItemDefinitionGroup><ClCompile><LanguageStandard>stdcpp20</LanguageStandard><UndefinePreprocessorDefinitions>NDEBUG</UndefinePreprocessorDefinitions></ClCompile></ItemDefinitionGroup>
<ItemGroup><ClCompile Include="{escape(str(source))}" /></ItemGroup><Import Project="$(VCTargetsPath)\\Microsoft.Cpp.targets" /></Project>''')
                command = [msbuild, str(project), '/p:Configuration=Release', '/p:Platform=x64', '/v:quiet', '/nologo']
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)


if __name__ == '__main__': unittest.main()
