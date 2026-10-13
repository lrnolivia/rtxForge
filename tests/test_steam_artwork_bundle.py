import ast
from pathlib import Path
import shutil
import tempfile
import unittest

BUILD = Path(__file__).resolve().parents[1] / 'packaging' / 'build_appimage.py'
tree = ast.parse(BUILD.read_text(encoding='utf-8'))
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'bundle_steam_artwork')
namespace = {'shutil': shutil}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(BUILD), 'exec'), namespace)
bundle = namespace['bundle_steam_artwork']

class SteamArtworkBundleTests(unittest.TestCase):
    stems = ('rtxforge-steam-portrait', 'rtxforge-steam-wide', 'rtxforge-steam-hero', 'rtxforge-logo-white')

    def prepare(self, base, suffix='.svg'):
        source = base / 'source'
        exports = source / 'packaging' / 'steam-artwork' / 'exports'
        exports.mkdir(parents=True)
        for stem in self.stems:
            (exports / (stem + suffix)).write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
        licenses = exports.parent / 'source'
        licenses.mkdir()
        (licenses / 'OFL-BakbakOne.txt').write_text('fixture license', encoding='utf-8')
        return source, exports

    def test_svg_fallback_assets_and_licenses_keep_installer_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, exports = self.prepare(base)
            destination = bundle(source, base / 'payload')
            self.assertEqual(destination, base / 'payload/packaging/steam-artwork')
            for stem in self.stems:
                self.assertEqual((destination / 'exports' / (stem + '.svg')).read_bytes(), (exports / (stem + '.svg')).read_bytes())
            self.assertTrue((destination / 'source/OFL-BakbakOne.txt').is_file())

    def test_png_assets_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, _ = self.prepare(base, '.png')
            destination = bundle(source, base / 'payload')
            self.assertTrue((destination / 'exports/rtxforge-logo-white.png').is_file())

    def test_missing_role_fails_before_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, exports = self.prepare(base)
            (exports / 'rtxforge-steam-hero.svg').unlink()
            with self.assertRaisesRegex(RuntimeError, 'Missing bundled'):
                bundle(source, base / 'payload')
            self.assertFalse((base / 'payload/packaging/steam-artwork').exists())

    def test_empty_preferred_png_fails_even_with_svg_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, exports = self.prepare(base)
            (exports / 'rtxforge-logo-white.png').write_bytes(b'')
            with self.assertRaisesRegex(RuntimeError, 'Empty bundled'):
                bundle(source, base / 'payload')

    def test_build_invokes_bundle(self):
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'bundle_steam_artwork']
        self.assertTrue(calls)

if __name__ == '__main__':
    unittest.main()
