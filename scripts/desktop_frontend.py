#!/usr/bin/env python3
"""One application payload, two native toolkit entrypoints. No distro forks."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
# Hosts without GTK4/libadwaita (SteamOS, minimal installs) can run the same
# payload in a distrobox that shares home, mounted drives, /proc and the NVIDIA driver.
CONTAINER='rtxforge'
CONTAINER_IMAGE='docker.io/library/archlinux:latest'
CONTAINER_PACKAGES='python python-gobject gtk4 libadwaita adwaita-icon-theme ttf-dejavu'
# Steam and links open on the host, not in the container.
CONTAINER_HOOK=('for c in steam xdg-open; do [ -e /usr/local/bin/$c ] || '
                'ln -sf /usr/bin/distrobox-host-exec /usr/local/bin/$c; done')

# Package names that bring PyGObject, GTK4 and libadwaita 1.7+ (Adw.ToggleGroup).
INSTALL_COMMANDS=(
    (('arch','cachyos','endeavouros','manjaro','garuda'),'sudo pacman -S --needed python-gobject gtk4 libadwaita'),
    (('fedora',),'sudo dnf install python3-gobject gtk4 libadwaita'),
    (('opensuse','suse'),'sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1'),
    (('debian','ubuntu','pop','linuxmint'),'sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1'),
)
IMMUTABLE=('steamos','bazzite','silverblue','kinoite','bluefin','aurora','chimeraos','holo')


def os_release(path=Path('/etc/os-release')):
    data={}
    try:
        for line in path.read_text().splitlines():
            key,_,value=line.partition('=')
            if value:data[key]=value.strip().strip('"')
    except OSError:pass
    return data


def gtk_missing():
    """Why the host cannot run the GTK frontend, or None."""
    if importlib.util.find_spec('gi') is None:return 'PyGObject (python3-gi) is not installed.'
    try:
        import gi
        gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
        from gi.repository import Adw
    except (ImportError,ValueError) as ex:return f'GTK4 or libadwaita is not installed ({ex}).'
    if not hasattr(Adw,'ToggleGroup'):
        version='.'.join(str(n) for n in (Adw.get_major_version(),Adw.get_minor_version()))
        return f'libadwaita {version} is too old; rtxForge needs 1.7 or newer.'
    return None


def guidance(release,missing=''):
    """Plain next steps for this distro; the container route needs no root."""
    ids=' '.join([release.get('ID',''),release.get('ID_LIKE',''),release.get('VARIANT_ID','')]).lower().split()
    lines=[]
    # A distro whose libadwaita is too old cannot fix it by installing packages.
    command=None if 'too old' in missing or any(i in IMMUTABLE for i in ids) else next((cmd for names,cmd in INSTALL_COMMANDS if any(i in names for i in ids)),None)
    if command:lines.append('Install the desktop libraries, then open rtxForge again:\n  '+command)
    if shutil.which('distrobox'):
        lines.append(('Or' if command else 'Run')+' rtxForge in a container (one-time setup, about 600 MB, no root):\n  '+launch_command()+' --container')
    elif not command:
        lines.append('Install distrobox, or GTK4 and libadwaita 1.7+ with Python bindings, to open the desktop app.')
    lines.append('The terminal version works without them:\n  '+launch_command()+' --cli --help')
    return '\n\n'.join(lines)


def launch_command():
    return os.environ.get('APPIMAGE') or sys.executable+' '+str(Path(__file__).resolve())


def notify(title,text):
    """Desktop launches have no terminal, so show the message where it will be seen."""
    if sys.stderr.isatty():return
    for argv in (['kdialog','--title',title,'--error',text],['zenity','--error','--title',title,'--text',text],['notify-send',title,text]):
        if shutil.which(argv[0]):
            try:subprocess.run(argv,timeout=600,check=False);return
            except (OSError,subprocess.SubprocessError):continue


def notify_progress(title,text):
    if not sys.stderr.isatty() and shutil.which('notify-send'):
        subprocess.run(['notify-send',title,text],check=False)


def ask(title,text):
    """A yes/no dialog for desktop launches; False when none is available or on a terminal."""
    if sys.stderr.isatty():return False
    for argv in (['kdialog','--title',title,'--yesno',text],['zenity','--question','--title',title,'--text',text]):
        if shutil.which(argv[0]):
            try:return subprocess.run(argv,timeout=600,check=False).returncode==0
            except (OSError,subprocess.SubprocessError):continue
    return False


def container_exists():
    try:out=subprocess.run(['distrobox','list','--no-color'],text=True,capture_output=True,timeout=60).stdout
    except (OSError,subprocess.SubprocessError):return False
    return any(len(cols)>1 and cols[1].strip()==CONTAINER for cols in (line.split('|') for line in out.splitlines()[1:]))


def container_argv(remaining):
    """Re-enter this payload inside the container."""
    # GTK's Vulkan renderer picks the container's Mesa driver and drops the Wayland connection.
    # Keep the host's canonical home (e.g. /var/home on Bazzite) so state and recovery paths match.
    inner=['env','RTXFORGE_IN_CONTAINER=1','HOME='+str(Path.home().resolve()),'GSK_RENDERER='+os.environ.get('GSK_RENDERER','ngl')]
    # The host keeps an AppImage mounted under /tmp while this launcher waits, and the
    # container shares /tmp, so it runs the mounted payload without FUSE or extraction.
    inner+=['python3','-B',str(Path(__file__).resolve())]
    return ['distrobox','enter',CONTAINER,'--',*inner,*remaining]


def run_container(remaining):
    if os.environ.get('RTXFORGE_IN_CONTAINER'):
        print('The rtxForge container is missing GTK4/libadwaita. Remove it with: distrobox rm '+CONTAINER,file=sys.stderr);return 1
    if not shutil.which('distrobox'):
        print('distrobox is not installed.',file=sys.stderr);return 1
    if not container_exists():
        print(f'Creating the {CONTAINER} container from {CONTAINER_IMAGE}. This happens once.',flush=True)
        notify_progress('Setting up rtxForge','Creating the container. rtxForge opens when it is ready.')
        create=['distrobox','create','--yes','--name',CONTAINER,'--image',CONTAINER_IMAGE,
                '--additional-packages',CONTAINER_PACKAGES,'--init-hooks',CONTAINER_HOOK]
        if Path('/proc/driver/nvidia').is_dir() and '--nvidia' in subprocess.run(['distrobox','create','--help'],text=True,capture_output=True).stdout:
            create.append('--nvidia')
        if subprocess.run(create).returncode!=0:
            print('The container could not be created.',file=sys.stderr);return 1
    os.execvp('distrobox',container_argv(remaining))
    return 1


def choose(frontend):
    if frontend not in ('gtk','qt'):raise ValueError('Choose gtk or qt.')
    if frontend=='gtk':
        missing=gtk_missing()
        if missing:raise RuntimeError(missing)
    elif importlib.util.find_spec('PySide6') is None:
        raise RuntimeError('Qt6/PySide6 and Kirigami are required for the KDE frontend.')
    return ROOT/'gui/rtxforge_gtk.py' if frontend=='gtk' else ROOT/'gui/qt/app.py'


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--frontend',choices=('gtk','qt'),default='gtk')
    parser.add_argument('--frontend-doctor',action='store_true')
    parser.add_argument('--container',action='store_true')
    parser.add_argument('--overlay-helper',action='store_true')
    args,remaining=parser.parse_known_args(argv)
    if args.overlay_helper:
        # Headless and host-side: no toolkit, no container.
        import linux_overlay_helper
        return linux_overlay_helper.main()
    if args.frontend_doctor:
        release=os_release()
        print(json.dumps({'system':platform.system(),'architecture':platform.machine(),
            'distribution':release.get('PRETTY_NAME','unknown'),
            'desktop':os.environ.get('XDG_CURRENT_DESKTOP','unknown'),
            'session':os.environ.get('XDG_SESSION_TYPE','unknown'),
            'gtk_python':importlib.util.find_spec('gi') is not None,
            'gtk_missing':gtk_missing(),
            'qt_python':importlib.util.find_spec('PySide6') is not None,
            'distrobox':shutil.which('distrobox') is not None,
            'in_container':bool(os.environ.get('RTXFORGE_IN_CONTAINER')),
            'selected_frontend':args.frontend,'runtime_verified':False},indent=2))
        return 0
    if args.container and args.frontend=='gtk' and not os.environ.get('RTXFORGE_IN_CONTAINER'):
        return run_container(remaining)
    try:entry=choose(args.frontend)
    except (RuntimeError,ValueError) as ex:
        # A container made earlier keeps working from the launcher without the flag.
        if args.frontend=='gtk' and not os.environ.get('RTXFORGE_IN_CONTAINER') and shutil.which('distrobox') and container_exists():
            return run_container(remaining)
        text=str(ex)+('\n\n'+guidance(os_release(),str(ex)) if args.frontend=='gtk' else '')
        print(text,file=sys.stderr)
        if args.frontend=='gtk' and not os.environ.get('RTXFORGE_IN_CONTAINER') and shutil.which('distrobox'):
            if ask('rtxForge needs desktop libraries',str(ex)+'\n\nSet up the rtxforge container now? It downloads about 600 MB once and takes a few minutes.'):
                return run_container(remaining)
        else:notify('rtxForge needs desktop libraries',text)
        return 1
    os.execv(sys.executable,[sys.executable,'-B',str(entry),*remaining])
    return 1
if __name__=='__main__':raise SystemExit(main())
