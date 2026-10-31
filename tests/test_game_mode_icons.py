"""Game Mode uses the same complete, licensed symbol family on both hosts."""
import hashlib
import json
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
ICONS=ROOT/'assets/game-mode/icons'


class GameModeIcons(unittest.TestCase):
    def test_shared_symbols_and_pinned_font_are_complete(self):
        spec=json.loads((ICONS/'icons.json').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256((ICONS/'Phosphor.ttf').read_bytes()).hexdigest(),spec['font_sha256'])
        self.assertIn('MIT License',(ICONS/'LICENSE.txt').read_text(encoding='utf-8'))
        for symbol in set(spec['windows'].values())|set(spec['linux'].values()):
            self.assertGreater(spec['codepoints'][symbol],0)
            svg=ET.parse(ICONS/'hicolor/scalable/actions'/('ph-'+symbol+'-symbolic.svg'))
            self.assertTrue(svg.getroot().find('{http://www.w3.org/2000/svg}path').get('d'))
        for path in (ROOT/'windows/RtxForge.Windows/GameMode').glob('*.cs'):
            if path.name=='Phosphor.cs':continue
            text=path.read_text(encoding='utf-8')
            for match in re.finditer(r'\\u([EeFf][0-9a-fA-F]{3})|([\ue000-\uf8ff])',text):
                key=match.group(1).upper() if match.group(1) else f'{ord(match.group(2)):04X}'
                self.assertIn(key,spec['windows'],f'{path.name}: missing {key}')
        for path in (ROOT/'gui').glob('game_mode*.py'):
            for name in re.findall(r"['\"]([a-z][a-z0-9-]*-symbolic)['\"]",path.read_text(encoding='utf-8')):
                if name=='rtx-steam-symbolic':continue
                self.assertIn(name,spec['linux'],f'{path.name}: missing {name}')
        for windows,linux in [('E713','rtx-gm-settings-symbolic'),('E7B8','drive-multidisk-symbolic'),('E9F5','rtx-gm-presets-symbolic'),('E72B','go-previous-symbolic'),('E9E9','rtx-gm-neural-symbolic')]:
            self.assertEqual(spec['windows'][windows],spec['linux'][linux])


if __name__=='__main__':unittest.main()
