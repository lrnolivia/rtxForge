"""Preserve verified current updater bytes without creating historical Git refs."""
from pathlib import Path
import hashlib,json,re,shutil,sys

def prepare(source:Path,destination:Path):
    source=Path(source);destination=Path(destination)
    manifest_file=source/'rtxforge-update.json';manifest=json.loads(manifest_file.read_text())
    name=manifest.get('appimage','');commit=manifest.get('commit','');digest=manifest.get('sha256','')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*\.AppImage',name):raise ValueError('Invalid previous AppImage filename')
    if not re.fullmatch(r'[a-fA-F0-9]{40}',commit) or not re.fullmatch(r'[a-fA-F0-9]{64}',digest):raise ValueError('Invalid previous build identity')
    app=source/name
    if app.is_symlink() or not app.is_file():raise ValueError('Previous AppImage missing or linked')
    if app.stat().st_size!=manifest.get('size') or hashlib.sha256(app.read_bytes()).hexdigest()!=digest.lower():raise ValueError('Previous AppImage failed checksum verification')
    suffix='.previous-'+commit[:12]+'-'+digest[:12]
    destination.mkdir(parents=True,exist_ok=True)
    files=[]
    for original in (app,manifest_file):
        target=destination/(original.name+suffix)
        if target.exists() and target.read_bytes()!=original.read_bytes():raise ValueError('Existing backup differs; preserve both and stop')
        shutil.copyfile(original,target)
        if target.read_bytes()!=original.read_bytes():raise ValueError('Backup copy verification failed')
        files.append(target)
    checksum=destination/(name+'.sha256'+suffix);checksum.write_text(digest+'  '+name+suffix+'\n');files.append(checksum)
    return files

if __name__=='__main__':
    for path in prepare(Path(sys.argv[1]),Path(sys.argv[2])):print(path)
