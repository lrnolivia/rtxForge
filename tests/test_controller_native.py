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

class ModalTuningControllerTests(unittest.TestCase):
    """Execute the real modal routing with focused controls, without a GTK display."""

    def setUp(self):
        import ast
        from types import SimpleNamespace
        source=Path(__file__).resolve().parents[1]/'gui/rtxforge_gtk.py'
        tree=ast.parse(source.read_text())
        window=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Window')
        methods={'poll_controller','adjust_modal_controller_value'}
        cls=ast.ClassDef(name='ModalHarness',bases=[],keywords=[],body=[node for node in window.body if isinstance(node,ast.FunctionDef) and node.name in methods],decorator_list=[])
        module=ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[]))

        class Widget:
            def __init__(self,parent=None,sensitive=True):self.parent=parent;self.sensitive=sensitive;self.activations=0
            def get_parent(self):return self.parent
            def get_sensitive(self):return self.sensitive
            def activate(self):self.activations+=1;return True
        class Scale(Widget):
            def __init__(self,value=.5,lower=0,upper=1,step=.1,**kwargs):
                super().__init__(**kwargs);self.value=value
                self.adjustment=SimpleNamespace(get_lower=lambda:lower,get_upper=lambda:upper,get_step_increment=lambda:step)
            def get_adjustment(self):return self.adjustment
            def get_value(self):return self.value
            def set_value(self,value):self.value=value
        class SpinButton(Scale):pass
        class DropDown(Widget):
            def __init__(self,selected=0,count=7,**kwargs):super().__init__(**kwargs);self.selected=selected;self.count=count
            def get_model(self):return SimpleNamespace(get_n_items=lambda:self.count) if self.count is not None else None
            def get_selected(self):return self.selected
            def set_selected(self,value):self.selected=value
        class Dialog(Widget):
            def __init__(self):super().__init__();self.focus=None;self.moves=[];self.closed=False;self.can_close=True
            def get_focus(self):return self.focus
            def child_focus(self,direction):self.moves.append(direction)
            def get_can_close(self):return self.can_close
            def close(self):self.closed=True
        directions=SimpleNamespace(UP='up',DOWN='down',LEFT='left',RIGHT='right',TAB_BACKWARD='previous',TAB_FORWARD='next')
        namespace={'Gtk':SimpleNamespace(Scale=Scale,SpinButton=SpinButton,DropDown=DropDown,DirectionType=directions),'ResizablePanelWindow':type('Panel',(),{}),'time':SimpleNamespace(monotonic=lambda:1)}
        exec(compile(module,str(source),'exec'),namespace)
        self.widget=Widget;self.scale=Scale;self.spin=SpinButton;self.dropdown=DropDown
        self.dialog=Dialog();self.actions=[];self.shell_actions=[]
        self.window=namespace['ModalHarness']()
        self.window.dialog=self.dialog
        self.window.controller=SimpleNamespace(poll=lambda:list(self.actions))
        self.window.couch=SimpleNamespace(update_prompts=lambda:None,navigate=self.shell_actions.append)
        self.window.apply_display_preferences=lambda:None
        self.window.is_active=lambda:True
        self.window.set_input_kind=lambda kind:None
        self.window.get_visible_dialog=lambda:self.dialog

    def route(self,focus,*actions):
        self.dialog.focus=focus;self.actions=list(actions)
        self.assertTrue(self.window.poll_controller())

    def test_slider_changes_value_instead_of_moving_focus(self):
        focus=self.scale()
        self.route(focus,'right');self.assertAlmostEqual(focus.value,.6)
        self.route(focus,'left');self.assertAlmostEqual(focus.value,.5)
        self.assertEqual(self.dialog.moves,[]);self.assertEqual(self.shell_actions,[])

    def test_slider_stays_focused_at_both_limits(self):
        for value,action,expected in [(0,'left',0),(1,'right',1),(.95,'right',1)]:
            with self.subTest(value=value,action=action):
                focus=self.scale(value=value);self.route(focus,action)
                self.assertEqual(focus.value,expected)
        self.assertEqual(self.dialog.moves,[])

    def test_dropdown_cycles_mfg_options_with_inner_child_focus(self):
        dropdown=self.dropdown();child=self.widget(parent=dropdown)
        self.route(child,'left');self.assertEqual(dropdown.selected,6)
        self.route(child,'right');self.assertEqual(dropdown.selected,0)
        self.assertEqual(self.dialog.moves,[])

    def test_numeric_entry_child_adjusts_shared_value(self):
        spin=self.spin(value=1.4,upper=2);child=self.widget(parent=spin)
        self.route(child,'left');self.assertAlmostEqual(spin.value,1.3)
        self.route(child,'right');self.assertAlmostEqual(spin.value,1.4)
        self.assertEqual(self.dialog.moves,[])

    def test_empty_and_unselected_dropdowns_are_safe(self):
        for count in (0,None):
            with self.subTest(count=count):
                dropdown=self.dropdown(count=count);self.route(dropdown,'right')
                self.assertEqual(dropdown.selected,0)
        dropdown=self.dropdown(selected=4294967295)
        self.route(dropdown,'right');self.assertEqual(dropdown.selected,0)
        dropdown.selected=4294967295
        self.route(dropdown,'left');self.assertEqual(dropdown.selected,6)
        self.assertEqual(self.dialog.moves,[])

    def test_traversal_accept_and_back_are_preserved(self):
        control=self.scale()
        self.route(control,'up','down','previous','next','accept','back')
        self.assertEqual(self.dialog.moves,['up','down','previous','next'])
        self.assertEqual(control.value,.5);self.assertEqual(control.activations,1)
        self.assertTrue(self.dialog.closed)

    def test_other_controls_and_disabled_values_still_traverse(self):
        for focus in (None,self.widget(),self.scale(sensitive=False),self.dropdown(sensitive=False)):
            with self.subTest(focus=focus):self.route(focus,'right')
        self.assertEqual(self.dialog.moves,['right']*4)


class PresetScopeTests(unittest.TestCase):
    """Exercise actual routing method bodies without requiring a display server."""
    def shell(self):
        import ast
        from types import SimpleNamespace
        source=Path(__file__).resolve().parents[1]/'gui/couch_shell.py'
        tree=ast.parse(source.read_text())
        original=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='CouchShell')
        methods={'entry','open','preset_targets','apply_presets','select_preset_games','toggle_dlss_game','library_primary_action','back','build_entries','has_dirty_presets','leave'}
        cls=ast.ClassDef(name='ScopeHarness',bases=[],keywords=[],body=[node for node in original.body if isinstance(node,ast.FunctionDef) and node.name in methods],decorator_list=[])
        module=ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[]))
        class Alert:
            last=None
            def __init__(self,**kwargs):Alert.last=self;self.callbacks={};self.responses=[]
            def add_response(self,key,title):self.responses.append((key,title))
            def set_default_response(self,key):self.default=key
            def set_close_response(self,key):self.close=key
            def connect(self,signal,callback):self.callbacks[signal]=callback
            def present(self,owner):self.owner=owner
            def respond(self,key):self.callbacks['response'](self,key)
        namespace={'PAGES':('library','presets','settings'),'VIEWS':('posters','capsules','list'),'Adw':SimpleNamespace(AlertDialog=Alert)}
        exec(compile(module,str(source),'exec'),namespace)
        shell=namespace['ScopeHarness']()
        shell.page='dashboard';shell.game_origin='library';shell.preset_origin='library';shell.utility_origin='dashboard'
        shell.dlss_selection=None;shell.selection_kind='dlss';shell.pending={};shell.entries=[];shell.current=0;shell.zone='content'
        shell.pending_origin={};shell.details_panel=None;shell.library_origin=None;shell.restoring_library=False;shell.alert=Alert
        shell.hint=SimpleNamespace(set_text=lambda text:None);shell.detail=shell.hint
        games=[{'game':'a','name':'A','installed':True,'feature_mode':'nr-mfg'}, {'game':'b','name':'B','installed':True}, {'game':'c','name':'C','installed':False}, {'game':'d','name':'D','installed':True,'blocked':'protected'}]
        shell.calls=[]
        shell.owner=SimpleNamespace(games=games,settings={'library_view':'posters','nr_strength':1.0,'mfg_multiplier':3,'sharpening_strength':.2},options=SimpleNamespace(demo=True),busy=False,get_focus=lambda:None,launch_action=lambda op,**kwargs:shell.calls.append((op,kwargs)))
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

    def test_dirty_navigation_waits_for_response_and_stay_preserves_values(self):
        shell=self.shell();shell.open('presets');shell.pending['nr_strength']=.7
        shell.open('library')
        self.assertEqual(shell.page,'presets');self.assertEqual(shell.alert.last.default,'stay')
        shell.alert.last.respond('stay')
        self.assertEqual(shell.page,'presets');self.assertEqual(shell.pending['nr_strength'],.7)

    def test_discard_resets_values_before_departure(self):
        shell=self.shell();shell.open('presets');original=dict(shell.pending);shell.pending['nr_strength']=.7
        shell.open('library');shell.alert.last.respond('discard')
        self.assertEqual(shell.page,'library');self.assertEqual(shell.pending,original)
