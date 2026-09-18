#!/usr/bin/env python3
"""Build the Bazzite 44 GNOME-targeted AppImage; does not install OS packages."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,urllib.request
root=Path(__file__).resolve().parents[1]
dist=root/'dist'
version=(root/'VERSION').read_text(encoding='utf-8').strip()
if not version:
    raise RuntimeError('VERSION is empty')
stage=dist/'AppImage-build';stage.mkdir(parents=True, exist_ok=True)
app=stage/'RTXForge.AppDir'
if app.exists():shutil.rmtree(app)
app.mkdir();payload=app/'usr/share/rtxforge';payload.mkdir(parents=True)

shutil.copyfile(root/'VERSION',payload/'VERSION')

build_sha=os.environ.get('GITHUB_SHA','').strip()
if not build_sha:
    try:
        build_sha=subprocess.check_output(
            ['git','rev-parse','HEAD'],
            cwd=root,
            text=True,
        ).strip()
    except Exception:
        build_sha='unknown'

(payload/'BUILD_INFO.json').write_text(
    json.dumps(
        {'version':version,'commit':build_sha},
        sort_keys=True,
    )+'\\n'
)

for name in ['gui','scripts','providers']:
 shutil.copytree(root/name,payload/name,ignore=shutil.ignore_patterns('__pycache__'))
for name in ['provider.json','README.md']:shutil.copyfile(root/name,payload/name)
(payload/'engine').mkdir()
shutil.copyfile(root/'engine/rtxengine.py',payload/'engine/rtxengine.py')
# Provider archives are verified at preparation; no stale custom loader is bundled.
shutil.copyfile(root/'packaging/AppRun',app/'AppRun');(app/'AppRun').chmod(0o755)
icon='io.github.lrnolivia.RTXForge'
shutil.copyfile(root/f'gui/icons/hicolor/512x512/apps/{icon}.png',app/f'{icon}.png')
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
