"""Focused production-path verification, sequential. Every fixture lives on verified Games."""
import pathlib,sys,json,struct,uuid,contextlib,io
from unittest.mock import patch
P=pathlib.Path
sys.path.insert(0,str(P(__file__).resolve().parents[1]/'scripts'))
import rtxforge as app,transactions as t,planning,profiles,compatibility
from storage import storage
c=app.load_provider();root=storage(c,512*1024**2)/'verification'/uuid.uuid4().hex;root.mkdir(parents=True);c['storage']['root']=str(root/'state');state=storage(c);state.mkdir()
fixture=root/'payload';fixture.mkdir();template='[DlssNr]\nEnabled=false\nPreUpscale=true\nDualFeature=false\n[FrameGen]\nEnabled=false\n[DLSSG]\nAdaMfgUnlock=false\n'
files={'OptiScaler.dll':b'OptiScaler synthetic','OptiScaler.ini':template.encode(),'nvngx.dll_dlssnr.dll':b'forwarder','nvngx_dlssnr.dll':b'NR model','OptiScaler/dlss-enabler-headless.dll':b'Artur synthetic','OptiScaler/nvngx.ini':b'[Preferences]\nCustom=keep\n','OptiScaler/nvngx_dlssg.dll':b'private DLSSG','OptiScaler/streamline/sl.interposer.dll':b'private Streamline'}
sources={}
for n,data in files.items():p=fixture/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);sources[n]=(p,t.digest(p))
targets=[]
for i,mode in enumerate(['nr-mfg','mfg-only']):
 game=root/('Game '+str(i));game.mkdir();pe=bytearray(70);pe[:2]=b'MZ';struct.pack_into('<I',pe,60,64);pe[64:]=b'PE\0\0\x64\x86';(game/'Game.exe').write_bytes(pe)
 for n,data in {'nvngx_dlssg.dll':b'native FG','sl.interposer.dll':b'native SL','save.dat':b'save control'}.items():(game/n).write_bytes(data)
 targets.append({'game':str(game),'exe':'Game.exe','mode':mode})
checks=[];log=io.StringIO()
# Route policy regression: generic/Cyberpunk use native Streamline.
assert compatibility.route_for({'name':'Generic Game','game':'/games/Generic','exe':'Game.exe'})['key']=='native-streamline'
assert compatibility.route_for({'name':'Cyberpunk 2077','game':'/games/Cyberpunk 2077','exe':'bin/x64/Cyberpunk2077.exe'})['key']=='native-streamline'
checks.append('compatibility policy: native Streamline default/Cyberpunk')

with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
 plans=[planning.make(r,state,sources) for r in targets];batch=app.apply_batch(c,plans)
 for r in targets:
  g=P(r['game']);ini=t.ini((g/'OptiScaler.ini').read_text());nr=r['mode']=='nr-mfg'
  assert ini['DlssNr']['Enabled']==str(nr).lower() and ini['RTXForge']['NrPanel']==('1' if nr else '0')
  assert (g/'nvngx_dlssnr.dll').exists()==nr and (g/'nvngx.dll_dlssnr.dll').exists()==nr
  assert ini['FrameGen']['FGInput']=='dlssg' and ini['FrameGen']['FGOutput']=='dlssg' and ini['FrameGen']['FGNvngxReplacement']=='none' and ini['FrameGen']['Enabled']=='true'
  if nr:assert ini['DlssNr']['WorkingScale']=='0.70' and ini['DlssNr']['PreUpscale']=='false' and ini['DlssNr']['DualFeature']=='true'
 checks.append('mixed-route batch: NR starts on; MFG Only excludes both NR files; native Streamline DLSS-G route active')
 # Switch an existing NR route to MFG Only and restore the batch.
 target={**targets[0],'mode':'mfg-only'};p=planning.make(target,state,sources);switch=app.apply_batch(c,[p]);g=P(target['game']);assert not (g/'nvngx_dlssnr.dll').exists()
 args=app.parser().parse_args(['rollback','--batch',str(switch),'--apply','--confirm','ROLLBACK']);app.rollback(args,c);assert (g/'nvngx_dlssnr.dll').exists();checks.append('route-switch removal and batch rollback restore NR bytes')
 # Overlay edits survive; NR toggle is deliberately forced back ON before launch.
 ini=g/'OptiScaler.ini';s=ini.read_text();s=t.setvalue(s,'Sharpness','Sharpness','0.44');s=t.setvalue(s,'DlssNr','Enabled','false');ini.write_text(s)
 p=planning.make(targets[0],state,sources);out=next(x['text'] for x in p['changes'] if P(x['path']).name=='OptiScaler.ini');parsed=t.ini(out);assert parsed['Sharpness']['Sharpness']=='0.44' and parsed['DlssNr']['Enabled']=='true'
 checks.append('existing v3 route preserves tuning; selected NR re-enabled at install')
 # A failure stops the batch with a recoverable journal, without silently continuing.
 original=t.atomic_file;count=0
 def fail(*a,**kw):
  global count
  count+=1
  if count==2:raise OSError('injected write failure')
  return original(*a,**kw)
 (g/'dxgi.dll').write_bytes(b'changed owned');p=planning.make(targets[0],state,sources,'repair');before={x['path']:t.digest(g/x['path']) if (g/x['path']).exists() else None for x in p['changes']}
 with patch.object(t,'atomic_file',side_effect=fail):
  try:app.apply_batch(c,[p]);raise AssertionError('failure expected')
  except OSError:pass
 broken=next(x for x in (state/'batches').glob('*/batch.json') if t.read_json(x)['status']=='interrupted');args.batch=broken;app.rollback(args,c)
 assert before=={n:t.digest(g/n) if (g/n).exists() else None for n in before};checks.append('interrupted write: journal retained; batch rollback restores before state')
 # Data/proxies outside the selected game stay unchanged. A competing provider blocks.
 other=P(targets[1]['game']);(other/'dinput8.dll').write_bytes(b'unrelated ASI loader');p=planning.make(targets[1],state,sources);assert p['conflicts'];(other/'dinput8.dll').unlink()
 try:app.normalize_targets([targets[0],targets[0]]);raise AssertionError('duplicate accepted')
 except t.Refusal:pass
 checks.append('competing injector and duplicate/overlapping batch targets refused')
 for r in targets:
  g=P(r['game']);assert (g/'save.dat').read_bytes()==b'save control' and (g/'sl.interposer.dll').read_bytes()==b'native SL' and (g/'nvngx_dlssg.dll').read_bytes()==b'native FG'
 # Remove only owned files; private modules removed, native modules preserved.
 p=planning.remove(targets[1],state);removed=app.apply_batch(c,[p]);assert not (other/'OptiScaler/nvngx_dlssg.dll').exists() and (other/'nvngx_dlssg.dll').exists();args.batch=removed;app.rollback(args,c);assert (other/'OptiScaler/nvngx_dlssg.dll').exists()
 checks.append('owned uninstall/rollback: private modules managed; native files and saves preserved')
report={'observed_utc':t.now(),'success':True,'checks':checks,'fixtures':str(root),'real_games_modified':False,'runtime_verified':False,'log':log.getvalue()};(root/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='log'},indent=2));print('Report:',root/'result.json')
