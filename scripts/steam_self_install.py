"""Add this installed rtxForge instance to Steam and apply its bundled artwork."""
from pathlib import Path
from types import SimpleNamespace
import hashlib, json, os, struct, uuid, zlib
import desktop_install, engine_bridge, steam_artwork, transactions as t
from storage import storage
ROOT=Path(__file__).resolve().parents[1]


def executable():
    installed=desktop_install.installed_path()
    path=installed if installed.is_file() else Path(os.environ['APPIMAGE']) if os.environ.get('APPIMAGE') else ROOT/'rtxforge'
    path=path.expanduser().resolve()
    if not path.is_file() or not os.access(path,os.X_OK):
        raise ValueError('Install rtxForge or launch its AppImage before adding it to Steam.')
    return path


def _string(key,value):
    if '\0' in key or '\0' in value:raise ValueError('NUL is not allowed in a Steam shortcut.')
    return b'\x01'+key.encode()+b'\0'+value.encode()+b'\0'


def _integer(key,value):return b'\x02'+key.encode()+b'\0'+struct.pack('<I',value&0xffffffff)


def append_shortcut(raw,entry,*,engine,name='rtxForge',icon=''):
    """Keep every existing object byte-for-byte; append only our own entry."""
    raw=raw if raw is not None else b'\0shortcuts\0\x08\x08'
    shortcuts=engine.parse_shortcuts_spans(raw)
    entry=Path(entry).resolve()
    matches=[]
    for obj in shortcuts:
        value=engine._shortcut_string(obj,'exe').strip().strip('"')
        if value and Path(value).is_absolute() and Path(value).resolve()==entry:matches.append(obj)
    if len(matches)>1:raise ValueError('Multiple Steam shortcuts already point to this rtxForge installation; keep one before syncing.')
    if matches:
        appid=engine._shortcut_int(matches[0],'appid')
        if not isinstance(appid,int) or not (appid&0xffffffff):raise ValueError('The existing rtxForge shortcut has no valid app ID.')
        return raw,appid&0xffffffff,False
    quoted='"'+str(entry)+'"'
    appid=(zlib.crc32((quoted+name).encode())|0x80000000)&0xffffffff
    if any((engine._shortcut_int(obj,'appid') or 0)&0xffffffff==appid for obj in shortcuts):
        raise ValueError('The rtxForge shortcut ID conflicts with another Steam shortcut. No configuration was changed.')
    keys={obj.key for obj in shortcuts};index=0
    while str(index) in keys:index+=1
    item=b'\0'+str(index).encode()+b'\0'+_integer('appid',appid)
    for key,value in [('AppName',name),('exe',quoted),('StartDir','"'+str(entry.parent)+'"'),('icon',icon),('ShortcutPath',''),('LaunchOptions',''),('DevkitGameID',''),('FlatpakAppID','')]:item+=_string(key,value)
    for key,value in [('IsHidden',0),('AllowDesktopConfig',1),('AllowOverlay',1),('OpenVR',0),('Devkit',0),('LastPlayTime',0)]:item+=_integer(key,value)
    item+=b'\0tags\0'+_string('0','Utilities')+b'\x08\x08'
    result=raw[:-2]+item+raw[-2:]
    parsed=engine.parse_shortcuts_spans(result)
    if len(parsed)!=len(shortcuts)+1:raise ValueError('Steam shortcut validation failed.')
    return result,appid,True


def bundled_image(path):
    if path.is_file():return path.read_bytes()
    svg=path.with_suffix('.svg')
    if not svg.is_file():raise ValueError('Bundled Steam artwork is missing: '+path.name)
    # Editable SVG is authoritative; some distributions regenerate the PNG here.
    from gi.repository import GdkPixbuf
    pixbuf=GdkPixbuf.Pixbuf.new_from_file(str(svg))
    success,data=pixbuf.save_to_bufferv('png',[],[])
    if not success:raise ValueError('Could not render bundled Steam artwork.')
    return bytes(data)


def _shortcut_plan(config,settings,*,engine=None,entry=None):
    e=engine or engine_bridge.module(config);entry=Path(entry or executable()).resolve()
    accounts=steam_artwork.profiles(config,engine=e)
    selected=settings.get('steam_artwork_profile')
    if selected:
        matches=[a for a in accounts if a['root']==selected.get('root') and a['userid']==str(selected.get('userid'))]
        account=matches[0] if len(matches)==1 else None
    else:account=e.choose_steam_user_config([SimpleNamespace(root=entry.parent,exe=entry,name='rtxForge',appid=None)],assume_yes=True)
    if not account:raise ValueError('Choose an available Steam artwork profile first.')
    folder=t.safe(Path(account['config']).resolve())
    expected=Path(account['root']).resolve()/'userdata'/str(account['userid'])/'config'
    if folder!=expected or not folder.is_dir():raise ValueError('Steam account path could not be verified.')
    shortcut=t.safe(folder/'shortcuts.vdf');before=shortcut.read_bytes() if shortcut.exists() else None
    if before is not None and len(before)>16*1024*1024:raise ValueError('Steam shortcuts file exceeds the safe update bound.')
    objects=e.parse_shortcuts_spans(before) if before is not None else []
    matches=[obj for obj in objects if (value:=e._shortcut_string(obj,'exe').strip().strip('"')) and Path(value).is_absolute() and Path(value).resolve()==entry]
    if len(matches)>1:raise ValueError('More than one Steam shortcut points to this installation. Keep one before continuing.')
    identity={'entry':str(entry),'config':str(folder),'shortcut':t.sha(before) if before is not None else None}
    return {'engine':e,'entry':entry,'folder':folder,'shortcut':shortcut,'before':before,'objects':objects,'match':matches[0] if matches else None,'identity':identity}


def shortcut_status(config,settings,**kwargs):
    """Inspect only the selected profile's shortcut, without loading artwork."""
    plan=_shortcut_plan(config,settings,**kwargs)
    return {'added':plan['match'] is not None,'identity':plan['identity']}


def remove(config,settings,*,reviewed,**kwargs):
    plan=_shortcut_plan(config,settings,**kwargs)
    if reviewed.get('identity')!=plan['identity']:raise ValueError('Steam shortcuts changed since your review. Review the removal again.')
    if plan['engine'].steam_running():raise ValueError('Close Steam completely before removing rtxForge from its library.')
    obj=plan['match']
    if obj is None:raise ValueError('This rtxForge installation is no longer in Steam.')
    before=plan['before'];shortcut=plan['shortcut']
    # Object spans start after the binary type and key; remove that header too.
    after=before[:obj.start-len(obj.key.encode())-2]+before[obj.end:]
    if len(plan['engine'].parse_shortcuts_spans(after))!=len(plan['objects'])-1:raise ValueError('Steam shortcut validation failed. Nothing was changed.')
    backup=t.safe(storage(config,32*1024*1024)/'desktop/steam-shortcuts'/uuid.uuid4().hex);backup.mkdir(parents=True)
    t.atomic_file(backup/'shortcuts.vdf',before,0o600)
    t.atomic_file(backup/'record.json',(json.dumps({'path':str(shortcut),'operation':'remove','before_sha256':t.sha(before),'after_sha256':t.sha(after)},indent=2)+'\n').encode(),0o600)
    if shortcut.read_bytes()!=before:raise ValueError('Steam shortcuts changed during preparation. Nothing was removed.')
    if plan['engine'].steam_running():raise ValueError('Steam opened during preparation. Close it and try again.')
    t.atomic_file(shortcut,after,0o600)
    if shortcut.read_bytes()!=after:raise ValueError('Steam shortcut readback failed; your backup was kept.')
    return {'backup':str(backup)}


def _prepare(config,settings,*,engine=None,entry=None,art_root=None,load_image=bundled_image):
    plan=_shortcut_plan(config,settings,engine=engine,entry=entry)
    e=plan['engine'];entry=plan['entry'];folder=plan['folder'];shortcut=plan['shortcut'];before=plan['before']
    icon=ROOT/'gui/icons/hicolor/scalable/apps/io.github.lrnolivia.RTXForge.svg'
    if not icon.is_file():raise ValueError('The bundled rtxForge icon is missing. Reinstall the app before adding it to Steam.')
    after,appid,created=append_shortcut(before,entry,engine=e,icon=str(icon))
    if created and e.steam_running():
        raise ValueError('Close Steam completely, then use Add rtxForge to Steam from Desktop Mode. Existing game artwork can still sync while Steam is open.')
    base=Path(art_root or ROOT/'packaging/steam-artwork/exports')
    names={'poster':'rtxforge-steam-portrait.png','capsule':'rtxforge-steam-wide.png','hero':'rtxforge-steam-hero.png','logo':'rtxforge-logo-white.png'}
    images={role:load_image(base/name) for role,name in names.items()}
    for data in images.values():steam_artwork.image_extension(data)
    slots={role:steam_artwork.slot_hashes(folder/'grid',str(appid),role) for role in images}
    roles=[]
    for role,data in images.items():
        desired={str(appid)+steam_artwork.SUFFIX[role]+steam_artwork.image_extension(data):t.sha(data)}
        status='unchanged' if slots[role]==desired else 'replace' if slots[role] else 'add'
        roles.append({'role':role,'status':status,'files':list(slots[role])})
    identity={'icon':t.digest(icon),'entry':str(entry),'config':str(folder),'appid':appid,'shortcut':t.sha(before) if before is not None else None,
              'images':{role:t.sha(data) for role,data in images.items()},'slots':slots}
    return {'engine':e,'folder':folder,'shortcut':shortcut,'before':before,'after':after,'images':images,
            'summary':{'identity':identity,'created':created,'profile':folder.parent.name,'roles':roles}}


def review(config,settings,**kwargs):
    """Inspect the shortcut and every artwork slot without writing any state."""
    return _prepare(config,settings,**kwargs)['summary']


def install(config,settings,*,reviewed=None,**kwargs):
    plan=_prepare(config,settings,**kwargs)
    summary=plan['summary']
    if reviewed is not None and reviewed.get('identity')!=summary['identity']:
        raise ValueError('Steam artwork or the shortcut changed since your review. Nothing was changed; review it again.')
    e=plan['engine'];folder=plan['folder'];shortcut=plan['shortcut']
    before=plan['before'];after=plan['after'];images=plan['images']
    appid=summary['identity']['appid'];created=summary['created']
    backup=t.safe(storage(config,32*1024*1024)/'desktop/steam-shortcuts'/uuid.uuid4().hex);backup.mkdir(parents=True)
    if before is not None:t.atomic_file(backup/'shortcuts.vdf',before,0o600)
    record={'path':str(shortcut),'existed':before is not None,'before_sha256':hashlib.sha256(before).hexdigest() if before is not None else None,'after_sha256':hashlib.sha256(after).hexdigest(),'appid':appid,'created':created}
    t.atomic_file(backup/'record.json',(json.dumps(record,indent=2)+'\n').encode(),0o600)
    if created:
        if (shortcut.read_bytes() if shortcut.exists() else None)!=before:raise ValueError('Steam shortcuts changed during preparation; try again after closing Steam.')
        if e.steam_running():raise ValueError('Steam started during preparation; no shortcut was written.')
        t.atomic_file(shortcut,after,0o600)
        if shortcut.read_bytes()!=after:raise ValueError('Steam shortcut readback failed; backup retained.')
    results=[];errors=[];preserved=[]
    for role,data in images.items():
        slot=next(item for item in summary['roles'] if item['role']==role)
        if reviewed is None and slot['status']=='replace':
            preserved.append(role);continue
        try:results.append(steam_artwork.write_slot(config,folder/'grid',str(appid),role,data,expected_before=summary['identity']['slots'][role]))
        except Exception as error:errors.append(role+': '+str(error))
    return {'created':created,'appid':appid,'artwork':results,'errors':errors,'preserved':preserved,'backup':str(backup),'restart_required':created or bool(results)}
