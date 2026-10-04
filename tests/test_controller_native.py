"""Exercise optional SDL polling using an in-process virtual controller."""
import ctypes as C
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from controller_input import Controller

class NativeControllerTest(unittest.TestCase):
    def test_hotplug_press_release_and_disconnect(self):
        controller=Controller()
        if not controller.sdl:self.skipTest('SDL2 unavailable: '+controller.error)
        self.addCleanup(controller.close)
        sdl=controller.sdl
        for name,args,result in [
            ('SDL_JoystickAttachVirtual',[C.c_int]*4,C.c_int),
            ('SDL_JoystickDetachVirtual',[C.c_int],C.c_int),
            ('SDL_JoystickOpen',[C.c_int],C.c_void_p),
            ('SDL_JoystickClose',[C.c_void_p],None),
            ('SDL_JoystickSetVirtualButton',[C.c_void_p,C.c_int,C.c_uint8],C.c_int)]:
            if not hasattr(sdl,name):self.skipTest('SDL version lacks virtual-controller testing')
            fn=getattr(sdl,name);fn.argtypes=args;fn.restype=result
        index=sdl.SDL_JoystickAttachVirtual(1,6,15,0)
        self.assertGreaterEqual(index,0)
        joystick=sdl.SDL_JoystickOpen(index);self.assertTrue(joystick)
        try:
            controller.next_scan=0;controller.poll();self.assertTrue(controller.handle)
            self.assertEqual(sdl.SDL_JoystickSetVirtualButton(joystick,0,1),0)
            self.assertIn('accept',controller.poll());self.assertNotIn('accept',controller.poll())
            sdl.SDL_JoystickSetVirtualButton(joystick,0,0);controller.poll()
            sdl.SDL_JoystickSetVirtualButton(joystick,6,1);self.assertIn('menu',controller.poll())
            sdl.SDL_JoystickSetVirtualButton(joystick,6,0);controller.poll()
            sdl.SDL_JoystickSetVirtualButton(joystick,4,1);self.assertIn('settings',controller.poll())
            sdl.SDL_JoystickDetachVirtual(index);controller.poll();self.assertIsNone(controller.handle)
        finally:
            sdl.SDL_JoystickClose(joystick)
            sdl.SDL_JoystickDetachVirtual(index)

class PresetScopeTests(unittest.TestCase):
    """Exercise actual routing method bodies without requiring a display server."""
    def shell(self):
        import ast
        from types import SimpleNamespace
        source=Path(__file__).resolve().parents[1]/'gui/couch_shell.py'
        tree=ast.parse(source.read_text())
        original=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='CouchShell')
        methods={'entry','open','preset_targets','apply_presets','select_preset_games','toggle_dlss_game','library_primary_action','back','build_entries'}
        cls=ast.ClassDef(name='ScopeHarness',bases=[],keywords=[],body=[node for node in original.body if isinstance(node,ast.FunctionDef) and node.name in methods],decorator_list=[])
        module=ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[]))
        namespace={'PAGES':('dashboard','library','presets','dlss'),'VIEWS':('posters','capsules','list')}
        exec(compile(module,str(source),'exec'),namespace)
        shell=namespace['ScopeHarness']()
        shell.page='dashboard';shell.game_origin='library';shell.preset_origin='library';shell.utility_origin='dashboard'
        shell.dlss_selection=None;shell.selection_kind='dlss';shell.pending={};shell.entries=[];shell.current=0;shell.zone='content'
        shell.hint=SimpleNamespace(set_text=lambda text:None);shell.detail=shell.hint
        games=[{'game':'a','name':'A','installed':True,'feature_mode':'nr-mfg'}, {'game':'b','name':'B','installed':True}, {'game':'c','name':'C','installed':False}, {'game':'d','name':'D','installed':True,'blocked':'protected'}]
        shell.calls=[]
        shell.owner=SimpleNamespace(games=games,settings={'library_view':'posters','nr_strength':1.0,'mfg_multiplier':3,'sharpening_strength':.2},options=SimpleNamespace(demo=True),busy=False,launch_action=lambda op,**kwargs:shell.calls.append((op,kwargs)))
        shell.game=games[0]
        shell.library_action=SimpleNamespace(get_sensitive=lambda:True)
        shell.render=lambda *args:shell.build_entries()
        shell.update_tabs=lambda:None
        shell.accent_targets=[]
        shell.apply_accent=lambda game:shell.accent_targets.append(game)
        return shell

    def test_global_scope_never_implicitly_targets_selected_game(self):
        shell=self.shell();shell.open('presets')
        self.assertIsNone(shell.accent_targets[-1])
        shell.entries[-2]['action']()
        self.assertEqual([g['game'] for g in shell.calls[-1][1]['targets']],['a','b'])
        self.assertNotIn('entire',shell.calls[-1][1])
        shell.entries[-1]['action']()
        self.assertEqual(shell.dlss_selection,set())
        shell.toggle_dlss_game(shell.owner.games[1]);shell.library_primary_action()
        self.assertEqual([g['game'] for g in shell.calls[-1][1]['targets']],['b'])

    def test_selection_cancel_preserves_values_and_excludes_unconfigured(self):
        shell=self.shell();shell.open('presets');shell.pending['nr_strength']=.7
        shell.select_preset_games();shell.toggle_dlss_game(shell.owner.games[2]);shell.toggle_dlss_game(shell.owner.games[3])
        self.assertEqual(shell.dlss_selection,set())
        shell.back();self.assertEqual(shell.page,'presets');self.assertEqual(shell.pending['nr_strength'],.7)

    def test_per_game_scope_and_dashboard_back(self):
        shell=self.shell();shell.open('game_presets');shell.entries[-1]['action']()
        self.assertIs(shell.accent_targets[-1],shell.game)
        self.assertEqual([g['game'] for g in shell.calls[-1][1]['targets']],['a'])
        shell.page='dashboard';shell.back();self.assertEqual(shell.page,'dashboard')
