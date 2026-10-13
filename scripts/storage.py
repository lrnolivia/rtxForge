import os,pathlib,shutil,sys
import transactions as e
P=pathlib.Path

STATE_MARKERS=('desktop','packages','transactions','cleanup','batches','verification')

def _portable_root():
    raw=os.environ.get('XDG_STATE_HOME','').strip()
    base=P(raw).expanduser() if raw else P.home()/'.local/state'
    e.need(base.is_absolute(),'XDG_STATE_HOME must be an absolute path')
    return base/'rtxforge'

def _looks_like_existing_state(path):
    path=P(path)
    return path.is_dir() and any((path/name).exists() for name in STATE_MARKERS)

def storage(c,required=0):
    e.need(sys.platform=='linux','Windows: preview/configuration reuse supported; Linux storage adapter required for mutation')
    s=c.get('storage') or {}
    override=os.environ.get('RTXFORGE_STATE_ROOT','').strip()
    configured=str(s.get('root') or '').strip()
    legacy=str(s.get('legacy_root') or '').strip()

    if override:
        root=e.safe(P(override).expanduser())
    elif configured:
        root=e.safe(P(configured).expanduser())
    elif legacy and _looks_like_existing_state(legacy):
        root=e.safe(P(legacy))
    else:
        root=e.safe(_portable_root())

    e.need(root not in (P('/'),P.home()),'Refusing unsafe rtxForge state root')
    parent=root
    while not parent.exists():
        parent=parent.parent
    e.need(parent.is_dir(),'State parent is not a directory')

    reserve=int(s.get('reserve_bytes',2*1024**3))
    e.need(reserve>=0 and required>=0,'Invalid storage reservation')
    e.need(shutil.disk_usage(parent).free>=reserve+required,'Insufficient free space for rtxForge state and recovery data')
    return root
