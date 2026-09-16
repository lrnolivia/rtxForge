#!/usr/bin/env python3
"""Build the Bazzite 44 GNOME-targeted AppImage; does not install OS packages."""
from pathlib import Path
import hashlib,json,shutil,subprocess,urllib.request
root=Path(__file__).resolve().parents[1];dist=root/'dist';version='0.5.6'
stage=dist/'AppImage-build';stage.mkdir(exist_ok=True)
app=stage/'RTXForge.AppDir'
if app.exists():shutil.rmtree(app)
app.mkdir();payload=app/'usr/share/rtxforge';payload.mkdir(parents=True)
for name in ['gui','scripts','providers']:
 shutil.copytree(root/name,payload/name,ignore=shutil.ignore_patterns('__pycache__'))
for name in ['provider.json','README.md']:shutil.copyfile(root/name,payload/name)
(payload/'engine').mkdir()
shutil.copyfile(root/'engine/rtxengine.py',payload/'engine/rtxengine.py')
# Provider archives are verified at preparation; no stale custom loader is bundled.
shutil.copyfile(root/'packaging/AppRun',app/'AppRun');(app/'AppRun').chmod(0o755)
icon='io.github.lrnolivia.RTXForge'
shutil.copyfile(root/f'gui/icons/hicolor/scalable/apps/{icon}.svg',app/f'{icon}.svg')
(app/f'{icon}.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=RTXForge\nExec=AppRun\nIcon={icon}\nCategories=Game;Utility;\nTerminal=false\n')
meta=json.loads((root/'packaging/runtime.json').read_text());runtime=dist/'appimage-runtime'
if not runtime.exists():runtime.write_bytes(urllib.request.urlopen(meta['url']).read())
assert hashlib.sha256(runtime.read_bytes()).hexdigest()==meta['sha256']
squash=stage/'payload.squashfs';squash.unlink(missing_ok=True)
cmd=['mksquashfs',str(app),str(squash),'-noappend','-comp','gzip','-all-root','-processors','1','-quiet']
if not shutil.which('mksquashfs'):cmd.insert(0,'distrobox-host-exec')
subprocess.run(cmd,check=True)
out=dist/f'RTXForge-{version}-Bazzite-x86_64.AppImage'
with out.open('wb') as f:
 for source in (runtime,squash):
  with source.open('rb') as src:shutil.copyfileobj(src,f)
out.chmod(0o755);out.with_suffix('.AppImage.sha256').write_text(hashlib.sha256(out.read_bytes()).hexdigest()+'  '+out.name+'\n');print(out)
