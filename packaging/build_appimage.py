#!/usr/bin/env python3
"""Build the Bazzite 44 GNOME-targeted AppImage; does not install OS packages."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,urllib.request


def bundle_overlays(root,payload,expected_sha=None):
    """Stage the matching Windows renderers used by Proton, with verified receipts."""
    folders={name:root/'windows/out'/name for name in ('glass-overlay','skynizz-bridge','feeder-panel')}
    present=[(folder/'package.json').is_file() for folder in folders.values()]
    if not any(present):
        if os.environ.get('RTXFORGE_REQUIRE_GLASS')=='1':raise RuntimeError('Native overlay artifacts are missing')
        return False
    if not all(present):raise RuntimeError('Native overlay artifacts are incomplete')
    receipts={name:json.loads((folder/'package.json').read_text(encoding='utf-8-sig')) for name,folder in folders.items()}
    expected_sha=expected_sha or os.environ.get('GITHUB_SHA')
    if expected_sha and any(r.get('commit')!=expected_sha for r in receipts.values()):
        raise RuntimeError('Native overlays were built from a different source revision')
    glass=receipts['glass-overlay'];bridge=receipts['skynizz-bridge'];feeder=receipts['feeder-panel']
    policy=json.loads((root/'providers/glass-overlay/rollout-policy.json').read_text(encoding='utf-8'))
    if glass.get('schema')!=1 or glass.get('renderer')!='rmlui' or glass.get('revision')!=policy.get('revision'):
        raise RuntimeError('Invalid glass overlay receipt')
    if bridge.get('variant')!='nr-mfg-bridge' or feeder.get('schema')!=2:
        raise RuntimeError('Invalid native overlay package')
    digest=glass['files']['rtxforge-glass.dll']['sha256']
    if bridge.get('glass_sha256')!=digest or (feeder.get('files',{}).get('rtxforge-glass.dll') or {}).get('sha256')!=digest:
        raise RuntimeError('Native packages contain different glass renderers')
    def copy_checked(folder,name,info,destination):
        if Path(name).name!=name or '/' in name or '\\' in name:raise RuntimeError('Unsafe native artifact name')
        source=folder/name
        if source.is_symlink() or not source.is_file() or source.stat().st_size!=info.get('size') or hashlib.sha256(source.read_bytes()).hexdigest()!=info.get('sha256'):
            raise RuntimeError('Native overlay artifact changed: '+name)
        destination.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination/name)
    for name,folder in folders.items():
        destination=payload/'providers'/name
        receipt=receipts[name]
        if name=='skynizz-bridge':
            if receipt.get('archive')!='rtxForge-Skynizz-'+receipt.get('tag','')+'-MFG.zip':raise RuntimeError('Unsafe bridge archive')
            copy_checked(folder,receipt['archive'],{'size':receipt['release_size'],'sha256':receipt['sha256']},destination)
        else:
            allowed={'rtxforge-glass.dll'} if name=='glass-overlay' else {'rtxforge-panel.addon64','rtxforge-quiet.addon64','rtxforge-glass.dll'}
            if name=='feeder-panel' and policy.get('revision',0)>=3:allowed.add('rtxforge-effects.addon64')
            if set(receipt.get('files',{}))!=allowed:raise RuntimeError('Incomplete native overlay receipt')
            for filename,info in receipt['files'].items():copy_checked(folder,filename,info,destination)
        shutil.copyfile(folder/'package.json',destination/'package.json')
        for notice in folder.glob('*.txt'):shutil.copyfile(notice,destination/notice.name)
        for notices in ('notices','glass-notices'):
            if (folder/notices).is_dir():shutil.copytree(folder/notices,destination/notices,dirs_exist_ok=True)
    shutil.copyfile(root/'providers/glass-overlay/rollout-policy.json',payload/'providers/glass-overlay/rollout.json')
    return True

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

def stage_payload(root, payload):
    """The application payload shared by the AppImage and the Flatpak (usr/share/rtxforge, /app/share/rtxforge)."""
    import ast,sys
    version=(root/'VERSION').read_text(encoding='utf-8').strip()
    if not version:
        raise RuntimeError('VERSION is empty')
    payload.mkdir(parents=True)
    shutil.copyfile(root/'VERSION',payload/'VERSION')
    build_sha=os.environ.get('GITHUB_SHA','').strip()
    if not build_sha:
        try:
            build_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        except Exception:
            build_sha='unknown'
    (payload/'BUILD_INFO.json').write_text(json.dumps({'version':version,'commit':build_sha},sort_keys=True)+'\n')
    for name in ['gui','scripts','providers']:
        shutil.copytree(root/name,payload/name,ignore=shutil.ignore_patterns('__pycache__'))
    bundle_overlays(root,payload)
    vulkan = root/'windows/out/vulkan-provider'
    if (vulkan/'candidate.json').is_file():
        shutil.copytree(vulkan,payload/'providers/vulkan-dlssg/runtime',ignore=shutil.ignore_patterns('*.part'),dirs_exist_ok=True)
    shutil.copytree(root/'assets/game-mode',payload/'assets/game-mode')
    for name in ['provider.json','README.md']:shutil.copyfile(root/name,payload/name)
    (payload/'engine').mkdir()
    # Reviewed Global and game-menu bulk changes share the Windows host's platform-neutral modules.
    (payload/'windows/engine-host').mkdir(parents=True)
    for name in ('global_controls.py','overlay_ui.py','overlay_packages.py','overlay_package_routes.py','app_storage.py','companion_controls.py','feeder_controls.py'):
        shutil.copyfile(root/'windows/engine-host'/name,payload/'windows/engine-host'/name)
    # A shared module importing another host module the bundle lacks only fails at runtime (the panel helper), so refuse the build.
    local={p.stem for d in ('scripts','windows/engine-host','gui') for p in (payload/d).glob('*.py')}
    for module in (payload/'windows/engine-host').glob('*.py'):
        for node in ast.walk(ast.parse(module.read_text(encoding='utf-8'))):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module and not node.level else []
            for name in names:
                top=name.split('.')[0]
                if top not in local and top not in sys.stdlib_module_names and (root/'windows/engine-host'/(top+'.py')).is_file():
                    raise RuntimeError(f'{module.name} imports {top}, which the bundle does not include')
    shutil.copyfile(root/'engine/rtxengine.py',payload/'engine/rtxengine.py')
    bundle_steam_artwork(root, payload)
    return version


def main():
    root=Path(__file__).resolve().parents[1]
    dist=root/'dist'
    stage=dist/'AppImage-build';stage.mkdir(parents=True, exist_ok=True)
    app=stage/'RTXForge.AppDir'
    if app.exists():shutil.rmtree(app)
    app.mkdir()
    version=stage_payload(root,app/'usr/share/rtxforge')
    # Provider archives are verified at preparation; no stale custom loader is bundled.
    (app/'AppRun').write_bytes((root/'packaging/AppRun').read_bytes().replace(b'\r\n',b'\n'));(app/'AppRun').chmod(0o755)
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


if __name__=='__main__':
    main()
