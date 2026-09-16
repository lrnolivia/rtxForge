#!/usr/bin/env python3
"""Apply pinned packages only inside an explicit lab. Never writes Steam metadata."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import engine_bridge as b,rtxforge

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--lab',type=Path,required=True);p.add_argument('--game',required=True)
 p.add_argument('--provider',choices=tuple(b.providers()),default='y4my')
 p.add_argument('--profile',choices=('mfg-only','nr-only','nr-mfg'),default='mfg-only')
 p.add_argument('action',choices=('install','uninstall'));a=p.parse_args()
 lab=a.lab.resolve(strict=True);root=lab/'games'/a.game
 if not root.is_dir() or root.is_symlink() or not root.resolve().is_relative_to(lab/'games'):p.error('Game must be a real directory inside lab/games')
 b.storage=lambda config,required=0: lab/'cache'
 config=rtxforge.load_provider();e=b.module(config,a.provider,a.profile);e.STATE_ROOT=lab/'state'
 g=e.inspect_game(e.Game('',a.game,root,'Folder'))
 if a.action=='uninstall':result=e.restore_target(g)
 else:
  baseline=e.load_baseline(g.target_dir)
  if baseline and (baseline.get('current') or {}).get('provider_id','y4my')!=a.provider:p.error('Uninstall before switching providers')
  data,meta=b.payload(e,config,a.profile)
  result=e.install_target(g,data,meta,'ada',feature_mode=a.profile,enable_effects=True)
 out=lab/'reports'/(a.game+'-'+a.provider+'-'+a.action+'.json');out.write_text(json.dumps(result,indent=2))
 print(out)
 if a.action=='install':print('UMU/Wine native override: '+Path(result['proxy']).stem+'=n,b')
if __name__=='__main__':main()
