"""Reversible desktop operations, captured at safe per-game boundaries."""
from pathlib import Path
import json,shutil,subprocess,uuid
import transactions as t

class Cancelled(Exception):pass

def signature(path):
    if any(p.is_symlink() for p in (path,*path.parents)):raise t.Refusal('Linked recovery path: '+str(path))
    if not path.exists():return None
    if path.is_file():return t.digest(path)
    return {str(p.relative_to(path)):signature(p) for p in sorted(path.rglob('*')) if not p.is_dir() or p.is_symlink()}

class Session:
    def __init__(self,root):
        self.root=Path(root)/('cancel-'+uuid.uuid4().hex);self.root.mkdir(parents=True,mode=0o700)
        self.entries=[];self.status='preparing'
    def save(self):
        t.atomic_file(self.root/'session.json',json.dumps({'status':self.status,'entries':self.entries},indent=2).encode(),0o600)
    def capture(self,paths):
        paths=sorted(set(Path(p).absolute() for p in paths),key=lambda p:len(p.parts))
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
        self.status='applying';self.save();return start
    def seal(self,start):
        for entry in self.entries[start:]:entry['after']=signature(Path(entry['path']))
        self.save()
    def rollback(self):
        self.status='rolling-back';self.save()
        for entry in reversed(self.entries):
            path=Path(entry['path'])
            if signature(path)!=entry['after']:raise t.Refusal('A file changed outside this operation. Recovery retained at '+str(self.root))
            if entry['before'] is not None and signature(Path(entry['backup']))!=entry['before']:raise t.Refusal('Recovery copy changed: '+entry['backup'])
            if path.is_dir():shutil.rmtree(path)
            elif path.exists():path.unlink()
            if entry['before'] is not None:
                path.parent.mkdir(parents=True,exist_ok=True)
                subprocess.run(['cp','-a','--reflink=auto','--',entry['backup'],str(path)],check=True)
            if signature(path)!=entry['before']:raise t.Refusal('Recovery verification failed. Copies retained at '+str(self.root))
        self.status='cancelled';self.save()
    def complete(self):
        self.status='complete';self.save()
        shutil.rmtree(self.root)
