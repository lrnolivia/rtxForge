"""Regression: repair must read v3 manifests without a NameError."""
import sys,pathlib,json,uuid
P=pathlib.Path
sys.path.insert(0,str(P(__file__).resolve().parents[1]/'scripts'))
import ownership,transactions as t,rtxforge as app
from storage import storage
root=storage(app.load_provider())/'verification'/uuid.uuid4().hex;root.mkdir(parents=True)
game=root/'Game';game.mkdir();proxy=game/'dxgi.dll';proxy.write_bytes(b'fixture')
manifest=root/'manifest.json';manifest.write_text(json.dumps({'games':[{'root':str(game),'exe':str(game/'Game.exe'),'installed':[{'path':str(proxy),'sha256':t.digest(proxy)}]}]}))
assert ownership.import_record(manifest,game,'Game.exe')=={'dxgi.dll':t.digest(proxy)}
manifest.write_text(json.dumps({'Games':[{'Root':'C:\\Game','Exe':'C:\\Game\\Game.exe','Status':'SUCCESS','Installs':[{'Path':'C:\\Game\\dxgi.dll','SHA256':t.digest(proxy)}]}]}))
assert ownership.import_record(manifest,game,'Game.exe')=={'dxgi.dll':t.digest(proxy)}
print('PASS: Linux v3 and Windows legacy repair ownership imports; no games modified')
