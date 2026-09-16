#!/usr/bin/env python3
"""Add isolated native lab launch scripts to Steam, preserving existing VDF bytes."""
import argparse,importlib.util,json,os,struct,subprocess,sys,time,zlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');a=p.parse_args()
spec=importlib.util.spec_from_file_location('lab_engine',Path(__file__).resolve().parents[1]/'engine/rtxengine.py');e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)
lab=Path('/var/mnt/Games/Forge Lab');entries=sorted((lab/'Launchers').glob('*.sh'))
assert len(entries)==5
accounts=list((Path.home()/'.local/share/Steam/userdata').glob('*/config/shortcuts.vdf'))
assert len(accounts)==1,'Ambiguous Steam account; select explicitly before writing'
path=accounts[0];before=path.read_bytes();spans=e.parse_shortcuts_spans(before)
names={str(f.value) for s in spans for f in s.fields if f.key.lower()=='appname'}
index=max((int(s.key) for s in spans),default=-1)+1
c=lambda s:s.encode()+b'\0'
def string(k,v):return b'\1'+c(k)+c(v)
def number(k,v):return b'\2'+c(k)+struct.pack('<I',v)
extra=b'';added=[]
for script in entries:
 title='Forge Lab — '+script.stem
 if title in names:continue
 exe='"/usr/bin/bash"';appid=zlib.crc32((exe+title).encode())|0x80000000
 obj=number('appid',appid)+string('AppName',title)+string('Exe',exe)+string('StartDir','"'+str(lab/'Launchers')+'"')
 obj+=string('icon',str(Path.home()/'.local/share/icons/hicolor/256x256/apps/io.github.lrnolivia.RTXForge.png'))
 obj+=string('ShortcutPath','')+string('LaunchOptions','"'+str(script)+'"')
 for k,v in [('IsHidden',0),('AllowDesktopConfig',1),('AllowOverlay',1),('OpenVR',0),('Devkit',0),('LastPlayTime',0)]:obj+=number(k,v)
 obj+=string('DevkitGameID','')+b'\0'+c('tags')+string('0','Forge Lab')+b'\10'
 extra+=b'\0'+c(str(index))+obj+b'\10';index+=1;added.append(title)
after=before[:-2]+extra+before[-2:]
assert len(e.parse_shortcuts_spans(after))==len(spans)+len(added)
print(json.dumps({'account':str(path),'existing':len(spans),'add':added},indent=2))
if a.apply and added:
 assert subprocess.run(['pgrep','-x','steam'],stdout=subprocess.DEVNULL).returncode!=0,'Exit Steam first; no changes made'
 assert path.read_bytes()==before,'Steam shortcuts changed; retry'
 backup=lab/'reports'/('shortcuts-before-forge-lab-'+time.strftime('%Y%m%d-%H%M%S')+'.vdf');backup.write_bytes(before)
 stage=path.with_name('shortcuts.vdf.rtxforge-tmp')
 with stage.open('xb') as f:f.write(after);f.flush();os.fsync(f.fileno())
 stage.chmod(path.stat().st_mode & 0o777)
 assert path.read_bytes()==before,'Steam shortcuts changed; original untouched'
 os.replace(stage,path)
 assert path.read_bytes()==after
 print('Installed. Backup:',backup)
