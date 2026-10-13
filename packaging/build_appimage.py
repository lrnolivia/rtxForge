#!/usr/bin/env python3
"""Build the Bazzite 44 GNOME-targeted AppImage; does not install OS packages."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,urllib.request

def bundle_steam_artwork(source_root, payload_root):
    """Keep the installer's four artwork roles and their licensed source assets."""
    artwork = source_root / 'packaging' / 'steam-artwork'
    exports = artwork / 'exports'
    required = ('rtxforge-steam-portrait', 'rtxforge-steam-wide',
                'rtxforge-steam-hero', 'rtxforge-logo-white')
    selected = []
    for stem in required:
        candidates = [exports / (stem + suffix) for suffix in ('.png', '.svg')]
        existing = [p for p in candidates if p.is_file()]
        if not existing:
            raise RuntimeError('Missing bundled Steam artwork: ' + stem)
        for path in existing:
            if path.stat().st_size == 0:
                raise RuntimeError('Empty bundled Steam artwork: ' + path.name)
        selected.extend(existing)
    destination = payload_root / 'packaging' / 'steam-artwork'
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(artwork, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
    for source in selected:
        copied = destination / source.relative_to(artwork)
        if not copied.is_file() or copied.read_bytes() != source.read_bytes():
            raise RuntimeError('Steam artwork copy verification failed: ' + source.name)
    return destination

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
    )+'\n'
)

for name in ['gui','scripts','providers']:
 shutil.copytree(root/name,payload/name,ignore=shutil.ignore_patterns('__pycache__'))
for name in ['provider.json','README.md']:shutil.copyfile(root/name,payload/name)
(payload/'engine').mkdir()
shutil.copyfile(root/'engine/rtxengine.py',payload/'engine/rtxengine.py')
bundle_steam_artwork(root, payload)
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
