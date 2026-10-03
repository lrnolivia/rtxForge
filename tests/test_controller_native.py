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
            sdl.SDL_JoystickDetachVirtual(index);controller.poll();self.assertIsNone(controller.handle)
        finally:
            sdl.SDL_JoystickClose(joystick)
            sdl.SDL_JoystickDetachVirtual(index)
