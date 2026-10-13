"""Regression for attribution text and unrelated native-DLL false positives."""
import sys,pathlib,uuid,struct
P=pathlib.Path
sys.path.insert(0,str(P(__file__).resolve().parents[1]/'scripts'))
import rtxforge as app,planning,transactions as t
from storage import storage
root=storage(app.load_provider())/'verification'/uuid.uuid4().hex;root.mkdir(parents=True)
game=root/'Game';game.mkdir();pe=bytearray(70);pe[:2]=b'MZ';struct.pack_into('<I',pe,60,64);pe[64:]=b'PE\0\0\x64\x86';(game/'Game.exe').write_bytes(pe)
(game/'nvngx_dlssg.dll').write_bytes(b'native')
for rel in ('Licenses/RenoDX_ATTRIBUTION.txt','Engine/Binaries/ThirdParty/DbgHelp/dbghelp.dll','d3d12on7/d3d12.dll'):
 p=game/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'preserve')
(game/'dbghelp.dll').write_bytes(('CompanyName\0Microsoft Corporation\0OriginalFilename\0DBGHELP.DLL\0FileDescription\0Windows Image Helper\0').encode('utf-16le'))
source=root/'source';source.mkdir();sources={}
for n,b in {'OptiScaler.dll':b'loader','OptiScaler.ini':b'[FrameGen]\nEnabled=true\n'}.items():
 p=source/n;p.write_bytes(b);sources[n]=(p,t.digest(p))
target={'game':str(game),'exe':'Game.exe','mode':'mfg-only'}
p=planning.make(target,root/'state',sources,'repair');assert not p['conflicts'],p['conflicts']
assert all(r['path'] in ('dxgi.dll','OptiScaler.ini') for r in p['changes'])
(game/'winmm.dll').write_bytes(b'unknown loader');p=planning.make(target,root/'state',sources,'repair');assert any('winmm.dll' in s for s in p['conflicts'])
print('PASS: attribution/native dependencies preserved; unknown adjacent loader still blocks')
