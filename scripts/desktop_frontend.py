#!/usr/bin/env python3
"""One application payload, two native toolkit entrypoints. No distro forks."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]

def choose(frontend):
    if frontend not in ('gtk','qt'):raise ValueError('Choose gtk or qt.')
    dependency='gi' if frontend=='gtk' else 'PySide6'
    if importlib.util.find_spec(dependency) is None:
        raise RuntimeError('GTK4/libadwaita Python bindings are required.' if frontend=='gtk' else 'Qt6/PySide6 and Kirigami are required for the KDE frontend.')
    return ROOT/'gui/rtxforge_gtk.py' if frontend=='gtk' else ROOT/'gui/qt/app.py'

def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--frontend',choices=('gtk','qt'),default='gtk')
    parser.add_argument('--frontend-doctor',action='store_true')
    args,remaining=parser.parse_known_args(argv)
    if args.frontend_doctor:
        print(json.dumps({'system':platform.system(),'architecture':platform.machine(),
            'desktop':os.environ.get('XDG_CURRENT_DESKTOP','unknown'),
            'session':os.environ.get('XDG_SESSION_TYPE','unknown'),
            'gtk_python':importlib.util.find_spec('gi') is not None,
            'qt_python':importlib.util.find_spec('PySide6') is not None,
            'selected_frontend':args.frontend,'runtime_verified':False},indent=2))
        return 0
    try:entry=choose(args.frontend)
    except (RuntimeError,ValueError) as ex:print(str(ex),file=sys.stderr);return 1
    os.execv(sys.executable,[sys.executable,'-B',str(entry),*remaining])
    return 1
if __name__=='__main__':raise SystemExit(main())
