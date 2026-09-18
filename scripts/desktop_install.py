"""Install this AppImage under the user's persistent XDG data directory."""
from pathlib import Path
import os,shutil,subprocess,tempfile

def install():
    source=Path(os.environ['APPIMAGE']).resolve(strict=True)
    data=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))
    if not data.is_absolute():raise ValueError('XDG_DATA_HOME must be absolute')
    root=data/'rtxforge/application';root.mkdir(parents=True,exist_ok=True)
    target=root/'RTXForge.AppImage'
    if source!=target:
        fd,name=tempfile.mkstemp(prefix='.update-',dir=root);os.close(fd);stage=Path(name)
        try:
            shutil.copyfile(source,stage);stage.chmod(0o755)
            with stage.open('rb') as f:os.fsync(f.fileno())
            if target.exists():shutil.copyfile(target,root/'RTXForge.previous.AppImage');(root/'RTXForge.previous.AppImage').chmod(0o755)
            os.replace(stage,target)
        finally:stage.unlink(missing_ok=True)
    assets=Path(__file__).resolve().parents[1]/'gui/icons/hicolor'
    for size in ('64x64','128x128','256x256','512x512'):
        icon=data/f'icons/hicolor/{size}/apps/io.github.lrnolivia.RTXForge.png'
        icon.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(assets/f'{size}/apps/{icon.name}',icon)
    icon=data/'icons/hicolor/512x512/apps/io.github.lrnolivia.RTXForge.png'
    apps=data/'applications';apps.mkdir(parents=True,exist_ok=True)
    # Desktop Exec quoting is distinct from shell quoting; percent signs are field codes.
    quoted=str(target).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
    desktop=apps/'io.github.lrnolivia.RTXForge.desktop'
    desktop.write_text('[Desktop Entry]\nType=Application\nName=RTXForge\nComment=GeForce tools for Linux\nExec="'+quoted+'"\nIcon='+str(icon)+'\nTerminal=false\nCategories=Game;Utility;\nStartupWMClass=io.github.lrnolivia.RTXForge\n')
    if shutil.which('update-desktop-database'):subprocess.run(['update-desktop-database',str(apps)],check=False,capture_output=True)
    if shutil.which('gtk-update-icon-cache'):subprocess.run(['gtk-update-icon-cache','-f','-t',str(data/'icons/hicolor')],check=False,capture_output=True)
    return str(target)

if __name__=='__main__':print(install())
