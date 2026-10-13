"""Small accessible ANSI interface; no network/UI dependencies."""
import os,sys,re,time,threading,shutil,contextvars,contextlib
COLORS={'green':'38;2;118;185;0','cyan':'38;2;93;220;232','red':'38;2;255;111;105','dim':'2','bold':'1'}
def clean(value):return re.sub(r'[\x00-\x1f\x7f-\x9f]',' ',str(value))
def style(text,color='green'):
    text=clean(text)
    return '\033['+COLORS[color]+'m'+text+'\033[0m' if sys.stdout.isatty() and not os.environ.get('NO_COLOR') and not _reporter.get() else text

def banner():
    print('\n'+style('  rtxForge','bold')+'  '+style('GEFORCE TOOLS · BUILT FOR LINUX','green'))
    print(style('  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━','green'))
    print('  Your library. Your settings. A reversible upgrade.\n')
def title(s):emit('\n  '+style(s,'cyan'))
def line(label,value):emit('  '+style(label.ljust(17),'dim')+clean(value))
def error(s):emit('  '+style('STOP  '+str(s),'red'),file=sys.stderr)
def prompt(s):
    if not sys.stdin.isatty():raise RuntimeError('Interactive input needs a terminal; use --targets and the documented --apply --confirm option')
    return input('  '+s+' ').strip()
def table(rows):
    print('  '+style(f'{"CODE":<7}{"GAME":<43}PROFILE','dim'))
    for code,name,profile in rows:print('  '+style(str(code).ljust(7))+clean(name)[:41].ljust(43)+style(profile,'cyan'))
def selection(raw,codes):
    raw=raw.upper().strip()
    if raw=='ALL':return set(codes)
    chosen=set(re.split(r'[\s,;]+',raw))-{''}
    if not chosen.issubset(set(codes)):raise ValueError('Unknown game code(s): '+', '.join(chosen-set(codes)))
    return chosen


_reporter=contextvars.ContextVar('rtxforge_reporter',default=None)
@contextlib.contextmanager
def report_to(callback):
    token=_reporter.set(callback)
    try:yield
    finally:_reporter.reset(token)

_display_lock=threading.RLock()
_active=False

def emit(*args,**kwargs):
    if _reporter.get():
        _reporter.get()({'kind':'log','text':clean(' '.join(str(a) for a in args))});return
    with _display_lock:
        if _active:sys.stdout.write('\r\033[2K');sys.stdout.flush()
        print(*args,**kwargs,flush=True)

def progress(label,**details):
    if _reporter.get():_reporter.get()({'kind':'progress','label':clean(label),**details})
    else:line('Working',label)

def work(label,action,*args,**kwargs):
    """Animate display only; all file operations remain on the calling thread."""
    global _active
    label=clean(label);started=time.monotonic();stop=threading.Event()
    if _reporter.get():
        report=_reporter.get();report({'kind':'progress','label':label})
        try:
            result=action(*args,**kwargs)
        except BaseException:
            report({'kind':'log','text':'Failed: '+label});raise
        report({'kind':'log','text':f'Completed: {label} ({time.monotonic()-started:.1f}s)'})
        return result
    animated=sys.stdout.isatty() and os.environ.get('TERM')!='dumb'
    frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    def draw(frame):
        width=max(12,shutil.get_terminal_size((80,24)).columns-2)
        message=f'  {frame} {label} · {int(time.monotonic()-started)}s'
        with _display_lock:
            sys.stdout.write('\r\033[2K'+style(message[:width],'cyan'));sys.stdout.flush()
    def animate():
        index=0
        while not stop.wait(0.12):
            index=(index+1)%len(frames);draw(frames[index])
    animation_thread=None;success=False
    if animated:
        _active=True;draw(frames[0]);animation_thread=threading.Thread(target=animate,daemon=True);animation_thread.start()
    else:emit('  … '+label)
    try:
        result=action(*args,**kwargs);success=True;return result
    finally:
        stop.set()
        if animation_thread:animation_thread.join()
        with _display_lock:
            if animated:sys.stdout.write('\r\033[2K')
            _active=False
            marker='✓' if success else '!'
            emit(style(f'  {marker} {label} · {time.monotonic()-started:.1f}s','green' if success else 'red'))
