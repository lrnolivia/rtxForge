from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import library_media as media

class PreferencesTests(unittest.TestCase):
    def test_game_mode_view_setter_preserves_desktop_preference(self):
        import ast
        from types import SimpleNamespace
        source=Path(__file__).resolve().parents[1]/'gui/couch_shell.py'
        tree=ast.parse(source.read_text())
        cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='CouchShell')
        method=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='set_library_view')
        module=ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[]))
        calls=[]
        namespace={'VIEWS':('posters','capsules','list'),'library_media':SimpleNamespace(save_settings=lambda config,settings:calls.append(dict(settings)))}
        exec(compile(module,str(source),'exec'),namespace)
        shell=SimpleNamespace(owner=SimpleNamespace(settings={'library_view':'list','gaming_mode_view':'posters'},options=SimpleNamespace(demo=False),service=SimpleNamespace(config={})),current=2,render=lambda current:None)
        namespace['set_library_view'](shell,'capsules')
        self.assertEqual(shell.owner.settings,{'library_view':'list','gaming_mode_view':'capsules'})
        self.assertEqual(calls,[shell.owner.settings])

    def test_game_mode_theme_setter_preserves_desktop_theme(self):
        import ast
        from types import SimpleNamespace
        source=Path(__file__).resolve().parents[1]/'gui/couch_shell.py'
        tree=ast.parse(source.read_text())
        cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='CouchShell')
        method=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='appearance_setting')
        module=ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[]))
        calls=[]
        namespace={'library_media':SimpleNamespace(save_settings=lambda config,settings:calls.append(dict(settings)))}
        exec(compile(module,str(source),'exec'),namespace)
        owner=SimpleNamespace(settings={'theme':'light','dark':False,'gaming_mode_theme':'night'},options=SimpleNamespace(demo=False),service=SimpleNamespace(config={}),apply_input_theme=lambda:None)
        shell=SimpleNamespace(owner=owner,apply_theme=lambda:None)
        namespace['appearance_setting'](shell,'theme',1,['night','dark','light'])
        self.assertEqual(owner.settings,{'theme':'light','dark':False,'gaming_mode_theme':'dark'})
        self.assertEqual(calls,[owner.settings])

    def test_old_desktop_preferences_migrate_without_being_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder).resolve()/'settings.json';path.write_text(json.dumps({'theme':'light','library_view':'list'}))
            with patch.object(media,'settings_path',return_value=path):
                settings=media.load_settings({})
            self.assertEqual((settings['theme'],settings['library_view']),('light','list'))
            self.assertEqual((settings['gaming_mode_theme'],settings['gaming_mode_view']),('night','posters'))
    def test_game_mode_choices_persist_and_invalid_values_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder).resolve()/'settings.json'
            with patch.object(media,'settings_path',return_value=path):
                settings=media.load_settings({});settings.update(gaming_mode_theme='dark',gaming_mode_view='capsules')
                media.save_settings({},settings)
                reopened=media.load_settings({})
                self.assertEqual((reopened['gaming_mode_theme'],reopened['gaming_mode_view']),('dark','capsules'))
                reopened.update(gaming_mode_theme='invalid',gaming_mode_view='invalid');media.save_settings({},reopened)
                clean=media.load_settings({})
                self.assertEqual((clean['gaming_mode_theme'],clean['gaming_mode_view']),('night','posters'))

if __name__=='__main__':unittest.main()
