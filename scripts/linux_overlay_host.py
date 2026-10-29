"""Proton panel helper using file-backed copies of the Windows wire protocols.

Only a managed executable mapped by a live process in the exact prefix can
bind a channel. Saving uses the existing recipe-bound preset store; replay
uses the game's acknowledged control mailbox, never a running game's INI.
"""
from pathlib import Path
import ctypes
import fcntl
import mmap
import os
import struct
import threading
import time

import linux_runtime
import proton_overlay
import proton_prefix
import transactions as t

controls = linux_runtime._shared('companion_controls')


def lock_path():
    runtime=os.environ.get('XDG_RUNTIME_DIR','')
    base=Path(runtime) if runtime and Path(runtime).is_absolute() else Path('/tmp')
    return base/f'rtxforge-panel-host-{os.getuid()}.lock'


def host_lock(path=None):
    """One panel host per user (the app window's or the helper's): the held fd, or None while another holds it."""
    fd=os.open(path or lock_path(),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd);return None
    return fd


def mapped_process(prefix, exe, channel, proc=Path('/proc')):
    """Bind both the Windows executable and channel to one actual Linux process."""
    prefix, exe, channel = (str(Path(p).resolve()) for p in (prefix, exe, channel))
    if proc == Path('/proc'):
        import flatpak_host
        if flatpak_host.sandboxed():
            return flatpak_host.probe('mapped-process', prefix, exe, channel)
    for entry in proc.iterdir():
        if not entry.name.isdigit(): continue
        try:
            env=(entry/'environ').read_bytes().split(b'\0')
            wine=next((item[11:] for item in env if item.startswith(b'WINEPREFIX=')),None)
            # Proton exports the prefix with a trailing slash ('.../pfx/').
            if not wine or str(Path(os.fsdecode(wine)).resolve())!=prefix: continue
            paths={line.split(None,5)[5].replace('\\040',' ') for line in (entry/'maps').read_text().splitlines() if len(line.split(None,5))==6}
            if exe in paths and channel in paths:
                return int(entry.name)
        except OSError: continue
    return None


def exe_processes(proc=Path('/proc')):
    """{executable name: [pids]} for every process with a mapped Windows .exe."""
    if proc == Path('/proc'):
        import flatpak_host
        if flatpak_host.sandboxed():
            return {name: [int(pid) for pid in pids] for name, pids in flatpak_host.probe('exe-processes').items()}
    found={}
    for entry in proc.iterdir():
        if not entry.name.isdigit():continue
        try:
            for line in (entry/'maps').read_text().splitlines():
                parts=line.split(None,5)
                if len(parts)==6 and parts[5].lower().endswith('.exe'):
                    found.setdefault(Path(parts[5].replace('\\040',' ')).name.casefold(),[]).append(int(entry.name))
        except OSError:continue
    return found


def open_mapping(path, size):
    """No symlink following or check/open race at the channel file."""
    fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        stat=os.fstat(fd)
        t.need(stat.st_uid==os.getuid() and stat.st_nlink==1 and stat.st_size==size,
               'Invalid Proton control channel.')
        return mmap.mmap(fd,size)
    finally:os.close(fd)


class FileMailbox(controls.Mailbox):
    def __init__(self,prefix,exe,path):
        self.prefix,self.exe,self.path=Path(prefix),Path(exe),Path(path)
        self.linux_pid=mapped_process(prefix,exe,path)
        if self.linux_pid is None:raise OSError('No matching live game owns this channel.')
        self.mem=open_mapping(path,512)
        self.view=ctypes.addressof(ctypes.c_char.from_buffer(self.mem))
        self.pid=struct.unpack_from('<i',self.mem,8)[0]
        self.size=512
        self.process=self.linux_pid
        self.k=self
        try:self.read()
        except BaseException:self.close();raise

    def WaitForSingleObject(self,process,timeout):
        return 258 if mapped_process(self.prefix,self.exe,self.path)==self.linux_pid else 0

    def GetTickCount(self):return int(time.monotonic()*1000)&0xffffffff

    def close(self):
        self.view=None
        self.mem.close()

    def read(self):
        t.need(self.k.WaitForSingleObject(self.process, 0) == 258, 'The game has stopped.')
        for _ in range(12):
            raw = ctypes.string_at(self.view, self.size)
            sequence = struct.unpack_from('<i', raw, 12)[0]
            if not sequence & 1 and ctypes.c_int32.from_address(self.view + 12).value == sequence:
                return controls.decode(raw, self.pid)
            time.sleep(.001)
        raise t.Refusal('The game is busy. Try the control again.')

    def apply(self, changes):
        changes = controls.validate_changes(changes)
        before = self.read()
        t.need(set(changes) <= controls.supported_keys(before['version']),
               'Update this game package to use the additional NR controls.')
        t.need(before['version'] >= 5 or changes.get('colour', 0) <= 2,
               'Update this game package to use colour strength above 2.00.')
        t.need(not before.get('original_menu') or controls.shared_native_menu(), 'OptiScaler controls this session. Restart the game after switching overlays.')
        values = before['values'] | changes
        if 'multiplier' in changes and changes['multiplier'] > 0:
            t.need(before['backend_max'] >= changes['multiplier'] - 1, 'This game does not support that multiplier.')
        t.need(not changes.get('dynamic_mfg') or before['dynamic_supported'] is True,
               "This game doesn't support Dynamic Multi-Frame Generation.")
        sequence = max(before['command'], before['ack']) + 2
        sequence += sequence & 1
        ctypes.c_int32.from_address(self.view + 16).value = sequence - 1
        packed = struct.pack('<ifiiiiiff', values['enabled'], values['intensity'], values['multiplier'],
                             values['pre_sr'], values['cache'], values['interval'], values['style'], values['structure'], values['tone'])
        ctypes.memmove(self.view + 28, packed, len(packed))
        ctypes.c_int32.from_address(self.view + 128).value = values['preset']
        if before['version'] >= 3:
            for key, (offset, _, _) in controls.EXTRA.items():
                raw = struct.pack('<f' if key in controls._FLOATS else '<i', values[key])
                ctypes.memmove(self.view + offset - 32, raw, 4)
        if before['version'] >= 4:
            for key, (offset, _, _, _) in controls.SHARP.items():
                raw = struct.pack('<f' if key in controls._FLOATS else '<i', values[key])
                ctypes.memmove(self.view + offset - 24, raw, 4)
        if before['version'] >= 7:
            for key, (_, request) in controls.PROTOCOL7.items():
                ctypes.c_int32.from_address(self.view + request).value = values[key]
        ctypes.c_int32.from_address(self.view + 16).value = sequence
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            found = self.read()
            if found['ack'] == sequence:
                t.need(found['result'] == 1, 'The game refused that control value.')
                return found
            time.sleep(.025)
        raise t.Refusal('The game has not applied the change yet. Check its status before trying again.')


class LinuxControls(controls.Controls):
    def __init__(self,state):
        self.stop=threading.Event()
        self.host_active=False
        super().__init__(state)

    def _start_watcher(self):
        # The shared constructor reloads presets and asks to start replay.
        # A waiting host must not write to games before it owns the user lock.
        if self.host_active:
            super()._start_watcher()

    def start(self):
        self.host_active=True
        self._start_watcher()

    def _watch(self):
        while not self.stop.wait(2):
            with self.lock:
                records=list(self.presets.items())
            for key,record in records:
                if self.stop.is_set():break
                with self.lock:
                    try:
                        game=self._game({'row':record['row']})
                        if record.get('recipe')!=game['recipe']:continue
                        box=self._open(game,True)
                        if box is None:continue
                        with box:
                            identity=(box.linux_pid,box.path.stat().st_ino)
                            if self.last_pid.get(key)==identity:continue
                            current=self._present(game,box,box.read())
                            if not current['can_edit']:continue
                            if record['changes'].get('multiplier',0)>0 and current['backend_max']==0:continue
                            changes=controls.startup_changes(game,record['changes'])
                            t.need(game['can_mfg'] or 'multiplier' not in changes,'MFG ownership changed')
                            t.need(game['can_nr'] or changes.get('enabled',0)==0,'NR ownership changed')
                            if changes.get('dynamic_mfg') and current['dynamic_supported'] is not True:
                                changes.pop('dynamic_mfg')
                                self.preset_errors[key]='Dynamic MFG was not confirmed; the remaining preset was replayed.'
                            box.apply(changes)
                            self.last_pid[key]=identity
                    except (OSError,ValueError,KeyError,t.Refusal) as error:
                        self.preset_errors[key]=str(error)

    def _processes(self):
        return exe_processes()

    def _open(self,game,write=False):
        row=game['row']
        try:prefix=proton_prefix.find_prefix(row['game'],row.get('appid'))
        except proton_prefix.PrefixError:return None
        folder=proton_overlay.channel_path(prefix,0).parent
        for path in sorted(folder.glob('controls.*.map')):
            try:return FileMailbox(prefix,game['exe'],path)
            except (OSError,ValueError,t.Refusal):continue
        return None

    def save(self,params):
        if (params.get('changes') or {}).get('dynamic_mfg'):
            game=self._game(params);box=self._open(game)
            t.need(box is not None,'Start this game to verify Dynamic MFG support.')
            with box:t.need(box.read()['dynamic_supported'] is True,'Wait for this game to confirm Dynamic MFG support.')
        return super().save(params)


class Host:
    def __init__(self,state,settings,engine_state,engine=None):
        self.controls=LinuxControls(state)
        self.controls.installations=Path(engine_state)/'targets'
        self.settings=settings
        self.engine=engine
        self.reviews={}
        self.review_id=0
        controls.shared_native_menu=lambda:self.settings().get('overlay_renderer','game') in ('game','rtxforge')
        self.channels={}
        self.stop=threading.Event()

    def handle(self,message,row,pid,session=None):
        op=message.get('op') if isinstance(message,dict) else ''
        import overlay_settings
        settings=self.settings()
        response={'op':op,'settings':proton_overlay.settings_snapshot(overlay_settings.effective(settings,row['game']),settings.get('theme'))}
        try:
            params={'row':row,'pid':pid}
            if op in ('hello','status'):response['status']=self.controls.status(params)
            elif op=='save':
                self.controls.save(params|{'changes':message.get('changes')})
                response['message']='Preset saved. It will replay for this installed package.'
            elif op=='reset':
                response['status']=self.controls.reset(params)
                response['message']='Saved game configuration restored.'
            elif op in ('global-review','menus-review'):
                t.need(self.engine is not None,'Open the app before reviewing installed games.')
                key=(row['game'],row['exe'],session or pid)
                self.reviews.pop(key,None)
                if op=='global-review':
                    review=linux_runtime.global_review(self.engine,message.get('changes') or {})
                else:
                    settings=self.settings()
                    review=linux_runtime.menus_review(self.engine,{k:settings[k] for k in
                        ('optiscaler_ui','optiscaler_intro','reshade_ui','reshade_intro','optiscaler_hotkey') if k in settings})
                self.reviews={k:v for k,v in self.reviews.items() if time.monotonic()-v[1]<300}
                t.need(len(self.reviews)<100,'Close old reviews before opening another.')
                self.review_id+=1
                self.reviews[key]=(self.review_id,time.monotonic(),review)
                plans=review.get('plans',[])
                response.update(review_id=self.review_id,ready=bool(plans),
                    message=f'{len(plans)} games ready. Review every change before applying.',
                    items=[{'title':p['name'],'detail':p.get('summary','')} for p in plans],
                    blocked=[{'title':p.get('title',''),'detail':p.get('detail','')} for p in review.get('blocked',[])],
                    skipped=[{'title':p.get('title',''),'detail':p.get('detail','')} for p in review.get('skipped',[])])
            elif op=='apply-review':
                key=(row['game'],row['exe'],session or pid)
                pending=self.reviews.pop(key,None)
                t.need(pending is not None and type(message.get('review_id')) is int
                       and message['review_id']==pending[0] and time.monotonic()-pending[1]<300,
                       'Review the games again before applying.')
                result=linux_runtime.apply_review(pending[2])
                self.controls.reload_presets()
                response['message']=result.get('message','Done.')
            elif op=='discard-review':
                self.reviews.pop((row['game'],row['exe'],session or pid),None)
                response['message']=''
            else:response.update(error=True,message='Use the app to review library and overlay settings changes.')
        except (OSError,ValueError,KeyError,t.Refusal) as error:
            response.update(error=True,message=str(error))
        return response

    def poll(self):
        active=set()
        for row in self.controls.targets():
            try:
                prefix=proton_prefix.find_prefix(row['game'],row.get('appid'))
                exe=Path(row['game'])/row['exe']
                for path in proton_overlay.channel_path(prefix,0).parent.glob('panel.*.map'):
                    linux_pid=mapped_process(prefix,exe,path)
                    if linux_pid is None:continue
                    active.add(path)
                    cached=self.channels.get(path)
                    if cached and cached[0]!=linux_pid:
                        cached[1].close();cached=None
                    if not cached:
                        cached=(linux_pid,proton_overlay.PanelChannelFile(path))
                        self.channels[path]=cached
                    channel=cached[1]
                    if not channel.valid:continue
                    request=channel.try_read()
                    if request:
                        identity,message=request
                        channel.reply(identity,self.handle(message,row,channel.header()['pid'],(linux_pid,path.stat().st_ino)))
            except (OSError,ValueError,KeyError,t.Refusal):continue
        for path in list(self.channels):
            if path not in active:
                self.channels.pop(path)[1].close()

    def run(self,lock=None):
        # The second host waits instead of answering the same channels twice,
        # and takes over when the first one exits.
        held=None
        started=False
        try:
            while not self.stop.is_set():
                if held is None:held=host_lock(lock)
                if held is None:
                    self.stop.wait(1);continue
                if not started:
                    self.controls.start();started=True
                self.poll();self.stop.wait(.25)
        finally:
            self.controls.stop.set()
            try:
                if self.controls.watcher is not None:
                    self.controls.watcher.join(timeout=3)
                for _,channel in self.channels.values():channel.close()
                self.channels.clear()
            finally:
                if held is not None:os.close(held)
