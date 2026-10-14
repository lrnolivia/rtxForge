"""Reversible desktop operations, captured at safe per-game boundaries."""
from pathlib import Path
import json,shutil,subprocess,uuid
import transactions as t

class Cancelled(Exception):pass

# Sessions the running process is executing right now; never offered for recovery.
LIVE=set()
# A session left in one of these states by a crash or forced shutdown can be recovered.
UNFINISHED=('preparing','applying','rolling-back')

def canonical(path):
    path=Path(path).absolute()
    # Bazzite exposes the host home through /home -> /var/home.
    if path.is_relative_to('/home'):path=Path('/home').resolve()/path.relative_to('/home')
    return path

def signature(path):
    path=canonical(path)
    if any(p.is_symlink() for p in (path,*path.parents)):raise t.Refusal('Linked recovery path: '+str(path))
    if not path.exists():return None
    if path.is_file():return t.digest(path)
    return {str(p.relative_to(path)):signature(p) for p in sorted(path.rglob('*')) if not p.is_dir() or p.is_symlink()}

class Session:
    def __init__(self,root):
        self.root=canonical(root)/('cancel-'+uuid.uuid4().hex);self.root.mkdir(parents=True,mode=0o700)
        # Each game's capture is one checkpoint; sealed once that game finished (or was undone).
        self.entries=[];self.checkpoints=[];self.status='preparing'
        LIVE.add(str(self.root))
    @classmethod
    def load(cls,root):
        """A session another run left behind, read back for review or recovery."""
        self=cls.__new__(cls);self.root=canonical(root)
        doc=json.loads((self.root/'session.json').read_text(encoding='utf-8'))
        self.entries=doc.get('entries',[]);self.checkpoints=doc.get('checkpoints');self.status=doc.get('status','')
        return self
    def save(self):
        t.atomic_file(self.root/'session.json',json.dumps({'status':self.status,'entries':self.entries,'checkpoints':self.checkpoints},indent=2).encode(),0o600)
    def capture(self,paths,label=''):
        paths=sorted(set(canonical(p) for p in paths),key=lambda p:len(p.parts))
        roots=[]
        for path in paths:
            if any(path==p or path.is_relative_to(p) for p in roots):continue
            roots.append(path)
        start=len(self.entries)
        for path in roots:
            before=signature(path);backup=self.root/str(len(self.entries))
            if before is not None:
                subprocess.run(['cp','-a','--reflink=auto','--',str(path),str(backup)],check=True)
                if signature(backup)!=before:raise t.Refusal('Recovery copy verification failed: '+str(path))
            self.entries.append({'path':str(path),'backup':str(backup),'before':before,'after':before})
        self.checkpoints.append({'start':start,'end':len(self.entries),'label':label,'sealed':False})
        self.status='applying';self.save();return start
    def seal(self,start):
        for entry in self.entries[start:]:entry['after']=signature(Path(entry['path']))
        for checkpoint in self.checkpoints:
            if checkpoint['start']>=start:checkpoint['sealed']=True
        self.save()
    def changed(self,start):
        """Paths this game's checkpoint saw change."""
        return [Path(e['path']) for e in self.entries[start:] if e['after']!=e['before']]
    def _restore(self,entries):
        for entry in reversed(entries):
            if entry['after']==entry['before']:continue
            path=Path(entry['path'])
            if signature(path)!=entry['after']:raise t.Refusal('A file changed outside this operation. Recovery retained at '+str(self.root))
            self._put_back(entry)
    def _put_back(self,entry):
        path=Path(entry['path'])
        if entry['before'] is not None and signature(Path(entry['backup']))!=entry['before']:raise t.Refusal('Recovery copy changed: '+entry['backup'])
        if path.is_dir():shutil.rmtree(path)
        elif path.exists():path.unlink()
        if entry['before'] is not None:
            path.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(['cp','-a','--reflink=auto','--',entry['backup'],str(path)],check=True)
        if signature(path)!=entry['before']:raise t.Refusal('Recovery verification failed. Copies retained at '+str(self.root))
    def undo(self,start):
        """Put one game's checkpoint back (after seal) and drop it from the session."""
        self._restore(self.entries[start:])
        for entry in self.entries[start:]:entry['after']=entry['before']
        self.save()
    def rollback(self):
        self.status='rolling-back';self.save()
        self._restore(self.entries)
        self.status='cancelled';self.save()
    def complete(self):
        self.status='complete';self.save()
        LIVE.discard(str(self.root))
        shutil.rmtree(self.root)

    # ---------- after a crash ----------

    def interrupted(self):
        """The checkpoint that never sealed (the game in progress when the run stopped), or None.

        Sessions written before checkpoints were recorded cannot say which game
        was in progress; they return None and can only be closed.
        """
        if self.checkpoints is None:return None
        open_=[c for c in self.checkpoints if not c['sealed']]
        return open_[-1] if open_ else None
    def recovery_plan(self,keep=lambda path:False):
        """What recovering this session would do: paths to put back and paths left as they are.

        Only the interrupted game's paths that differ from their backup are put
        back. Completed games keep their changes. keep(path) marks paths owned
        by someone else (for example Steam's own config) that are reported, not
        rewritten.
        """
        checkpoint=self.interrupted();restore=[];leave=[]
        if checkpoint:
            for entry in self.entries[checkpoint['start']:checkpoint['end']]:
                if signature(Path(entry['path']))==entry['before']:continue
                (leave if keep(Path(entry['path'])) else restore).append(entry)
        done=sum(1 for c in (self.checkpoints or []) if c['sealed'])
        return {'checkpoint':checkpoint,'restore':restore,'leave':leave,'completed':done}
    def recover(self,keep=lambda path:False):
        """Put back only the interrupted game, keep completed games, and close the session."""
        plan=self.recovery_plan(keep)
        for entry in reversed(plan['restore']):self._put_back(entry)
        self.close('recovered',keep_copies=False)
        return plan
    def close(self,status='closed',keep_copies=True):
        """Mark the session finished without restoring anything (copies kept unless asked)."""
        self.status=status;self.save()
        if keep_copies:return
        for child in self.root.iterdir():
            if child.name!='session.json':
                if child.is_dir():shutil.rmtree(child)
                else:child.unlink()

def unfinished(root):
    """Sessions under root that a crash left open (not ones this process is running)."""
    root=canonical(root)
    if not root.is_dir():return []
    found=[]
    for path in sorted(root.glob('cancel-*/session.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        if str(path.parent) in LIVE:continue
        try:session=Session.load(path.parent)
        except (OSError,ValueError):continue
        if session.status in UNFINISHED:found.append(session)
    return found
