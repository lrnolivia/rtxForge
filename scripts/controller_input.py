"""Optional SDL2 controller input. No Steam account/API or background daemon."""
import ctypes as C
import ctypes.util
import time

GLYPHS={
    'xbox':('A','B','Y','Menu'),
    'playstation':('×','○','△','Options'),
    'nintendo':('B','A','X','+'),
    'generic':('South','East','North','Start'),
}

def family(kind):
    return 'playstation' if kind in (3,4,7) else 'nintendo' if kind in (5,11,12,13) else 'xbox' if kind in (1,2) else 'generic'

class Edges:
    def __init__(self):self.previous=set();self.repeats={}
    def update(self,pressed,now=None):
        now=time.monotonic() if now is None else now
        actions=[]
        for action in sorted(pressed):
            if action not in self.previous:
                actions.append(action);self.repeats[action]=now+0.4
            elif action in ('up','down','left','right') and now>=self.repeats.get(action,now):
                actions.append(action);self.repeats[action]=now+0.13
        self.previous=set(pressed)
        self.repeats={k:v for k,v in self.repeats.items() if k in pressed}
        return actions

class Controller:
    def __init__(self):
        self.handle=None;self.sdl=None;self.error='';self.family='generic';self.edges=Edges();self.next_scan=0
        try:
            self.sdl=C.CDLL(ctypes.util.find_library('SDL2') or 'libSDL2-2.0.so.0')
            signatures={
                'SDL_InitSubSystem':([C.c_uint32],C.c_int),
                'SDL_QuitSubSystem':([C.c_uint32],None),
                'SDL_SetHint':([C.c_char_p,C.c_char_p],C.c_int),
                'SDL_NumJoysticks':([],C.c_int),
                'SDL_IsGameController':([C.c_int],C.c_int),
                'SDL_GameControllerOpen':([C.c_int],C.c_void_p),
                'SDL_GameControllerClose':([C.c_void_p],None),
                'SDL_GameControllerGetAttached':([C.c_void_p],C.c_int),
                'SDL_GameControllerGetType':([C.c_void_p],C.c_int),
                'SDL_GameControllerGetButton':([C.c_void_p,C.c_int],C.c_uint8),
                'SDL_GameControllerGetAxis':([C.c_void_p,C.c_int],C.c_int16),
                'SDL_GameControllerUpdate':([],None),
                'SDL_PumpEvents':([],None),
                'SDL_FlushEvents':([C.c_uint32,C.c_uint32],None),
            }
            for name,(args,result) in signatures.items():
                fn=getattr(self.sdl,name);fn.argtypes=args;fn.restype=result
            self.sdl.SDL_SetHint(b'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS',b'1')
            if self.sdl.SDL_InitSubSystem(0x2000)!=0:raise RuntimeError('SDL controller initialization failed')
        except (OSError,AttributeError,RuntimeError) as exc:
            self.error=str(exc);self.sdl=None

    def poll(self):
        if not self.sdl:return []
        self.sdl.SDL_PumpEvents();self.sdl.SDL_GameControllerUpdate()
        self.sdl.SDL_FlushEvents(0x600,0x6ff)
        if self.handle and not self.sdl.SDL_GameControllerGetAttached(self.handle):
            self.sdl.SDL_GameControllerClose(self.handle);self.handle=None;self.edges=Edges()
        if not self.handle and time.monotonic()>=self.next_scan:
            self.next_scan=time.monotonic()+2
            for index in range(self.sdl.SDL_NumJoysticks()):
                if self.sdl.SDL_IsGameController(index):
                    self.handle=self.sdl.SDL_GameControllerOpen(index)
                    if self.handle:break
            if self.handle:self.family=family(self.sdl.SDL_GameControllerGetType(self.handle))
        if not self.handle:return []
        mapping={0:'accept',1:'back',3:'search',6:'menu',9:'previous',10:'next',11:'up',12:'down',13:'left',14:'right'}
        pressed={action for index,action in mapping.items() if self.sdl.SDL_GameControllerGetButton(self.handle,index)}
        for axis,negative,positive in ((0,'left','right'),(1,'up','down')):
            value=self.sdl.SDL_GameControllerGetAxis(self.handle,axis)
            if value < -18000:pressed.add(negative)
            elif value > 18000:pressed.add(positive)
        return self.edges.update(pressed)

    def close(self):
        if self.sdl:
            if self.handle:self.sdl.SDL_GameControllerClose(self.handle)
            self.sdl.SDL_QuitSubSystem(0x2000)
        self.handle=None;self.sdl=None
