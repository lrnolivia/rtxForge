"""Focused reversible-cleanup check on disposable fixtures only."""
import json,pathlib,sys,tempfile
P=pathlib.Path
sys.path.insert(0,str(P(__file__).resolve().parents[1]/'scripts'))
import rtxforge as app,cleanup,transactions as t
from storage import storage

with tempfile.TemporaryDirectory(prefix='rtxforge-cleanup-') as tmp:
    root=P(tmp)
    c=app.load_provider()
    c['storage']['root']=str(root/'state')
    c['storage']['reserve_bytes']=0

    state=storage(c);state.mkdir(parents=True)
    hidden_model=state/'nvngx_dlssnr.dll';hidden_model.write_bytes(b'rtxForge state fixture')
    hidden_backup=state/'_DLSS5_Backup';hidden_backup.mkdir();(hidden_backup/'state.dll').write_bytes(b'state fixture')

    game=root/'fixture';game.mkdir()
    model=game/'nvngx_dlssnr.dll';model.write_bytes(b'NR fixture')
    backup=game/'_DLSS5_Backup';(backup/'empty').mkdir(parents=True);(backup/'original.dll').write_bytes(b'original fixture')
    control=game/'unrelated.dll';control.write_bytes(b'keep')

    items=[{'path':str(p),**cleanup.snapshot(p)} for p in (model,backup)]
    discovered=cleanup.discover([root],c)
    assert {row['path'] for row in discovered}=={str(model),str(backup)}
    assert all(not P(row['path']).is_relative_to(state) for row in discovered)

    record=cleanup.apply(c,items)
    assert not model.exists() and not backup.exists() and control.read_bytes()==b'keep'
    assert hidden_model.read_bytes()==b'rtxForge state fixture'
    assert (hidden_backup/'state.dll').read_bytes()==b'state fixture'

    model.write_bytes(b'external change')
    try:cleanup.restore(c,record);raise AssertionError('drift accepted')
    except t.Refusal:pass

    model.unlink();assert cleanup.restore(c,record)==2
    cleanup.restore(c,record,True)
    assert [{'path':str(p),**cleanup.snapshot(p)} for p in (model,backup)]==items
    assert control.read_bytes()==b'keep'
    assert hidden_model.read_bytes()==b'rtxForge state fixture'
    assert (hidden_backup/'state.dll').read_bytes()==b'state fixture'

    report={
        'observed_utc':t.now(),
        'success':True,
        'checks':[
            'all backups verified before cleanup',
            'recovery restores files and empty directories',
            'external drift refused',
            'unrelated files retained',
            'configured rtxForge state/recovery excluded from scan',
            'ordinary sibling game cleanup candidates remain discoverable',
        ],
        'real_games_modified':False,
        'runtime_verified':False,
    }
    print(json.dumps(report,indent=2))
