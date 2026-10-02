#!/usr/bin/env python3
"""Bazzite setup: check host, prepare pinned archives, install app; never edit games."""
import argparse
import json
import os
from pathlib import Path
import platform
import sys

import desktop_install
import discovery
import engine_bridge
import hardware
import library_media
import packages
import rtxforge
import transactions as t
from storage import storage

MODES = ('mfg-only', 'nr-only', 'nr-mfg')


def selected_settings(config, mode=None):
    """Keep existing preferences byte-for-byte unless the user selects a profile."""
    path = library_media.settings_path(config)
    if path.exists():
        t.safe(path)
        existing = t.read_json(path)
        t.need(isinstance(existing, dict), 'Existing settings are not an object; repair them before setup.')
        settings = {**library_media.DEFAULTS, **existing}
    else:
        settings = {**library_media.DEFAULTS, 'runtime_provider': 'dlss-unlocked'}
    if mode:
        settings.update(runtime_provider='dlss-unlocked', default_profile=mode)
    provider = settings['runtime_provider']
    profile = settings['default_profile']
    t.need(provider in engine_bridge.providers(), 'Unknown saved provider; choose an explicit --profile.')
    t.need(profile in MODES, 'Unknown saved profile; choose an explicit --profile.')
    t.need(provider != 'y4my' or profile != 'nr-only', 'NR-only requires DLSS-Unlocked.')
    return settings, not path.exists() or mode is not None


def host_report(config):
    checks = []
    def add(name, ok, detail):
        checks.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    add('Bazzite GNOME host', release.get('ID') == 'bazzite', release.get('PRETTY_NAME', 'Unknown OS'))
    add('64-bit Linux', sys.platform == 'linux' and platform.machine() == 'x86_64', platform.machine())
    gpu = hardware.detect()
    add('NVIDIA RTX 40-series driver', gpu['ready'], f"{gpu['gpu']} · {gpu['driver']} · {gpu['reason']}")
    try:
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Adw, Gtk
        add('GTK/libadwaita', hasattr(Adw, 'ToggleGroup'),
            f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}, libadwaita {Adw.get_major_version()}.{Adw.get_minor_version()}")
    except (ImportError, ValueError) as exc:
        add('GTK/libadwaita', False, f'Host Python GTK4/libadwaita required: {exc}')
    steam = discovery.steam_roots()
    add('Steam installation', bool(steam), ', '.join(map(str, steam)) or 'Open Steam once, then rerun setup.')
    try:
        root = storage(config, 2 * 1024**3)
        add('Runtime and recovery space', True, root)
    except (OSError, t.Refusal) as exc:
        add('Runtime and recovery space', False, exc)
    return {'ready': all(c['ok'] for c in checks), 'checks': checks,
            'session': os.environ.get('XDG_SESSION_TYPE', 'unknown'),
            'runtime_verified': False,
            'note': 'Host readiness does not verify MFG, NR, HDR or a game launch.'}


def prepare_runtime(config, settings):
    provider = settings['runtime_provider']
    mode = settings['default_profile']
    engine = engine_bridge.module(config, provider, mode)
    payload, meta = engine_bridge.payload(engine, config, mode)
    if mode in ('nr-only', 'nr-mfg'):
        t.need('nvngx_dlssnr.dll' in payload,
               'This provider needs a separate local NR model. Choose DLSS-Unlocked with --profile or configure the model in the app.')
    return {'provider': provider, 'profile': mode, 'tag': engine.Y4MY_PROVIDER['tag'],
            'archive_sha256': engine.Y4MY_PROVIDER['sha256'], 'payload_files': len(payload),
            'runtime_verified': False}


def save_preferences(config, settings, change):
    if not change:
        return None
    path = library_media.settings_path(config)
    if path.exists():
        backup = storage(config) / 'setup-backups' / (t.now().replace(':', '-') + '-settings.json')
        t.atomic_file(backup, path.read_bytes(), 0o600)
    # Keep unknown settings too; a setup operation must not discard future keys.
    t.atomic_file(path, (json.dumps(settings, indent=2) + '\n').encode(), 0o600)
    return str(path)


def rollback_app():
    target = desktop_install.installed_path()
    previous = target.with_name('RTXForge.previous.AppImage')
    t.need(previous.is_file() and not previous.is_symlink(), 'No previous AppImage is available.')
    # install_from stages the previous file before rotating the current backup.
    return desktop_install.install_from(previous)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'prepare', 'install', 'rollback'), nargs='?', default='check')
    parser.add_argument('--profile', choices=MODES, help='Explicitly select DLSS-Unlocked and this profile; back up saved preferences.')
    parser.add_argument('--json', action='store_true', help='Print host checks as JSON.')
    args = parser.parse_args(argv)
    try:
        config = rtxforge.load_provider()
        if args.action == 'rollback':
            t.need(os.geteuid() != 0, 'Run setup as your desktop user, without sudo.')
            print('Restored previous application:', rollback_app())
            return 0
        report = host_report(config)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            for check in report['checks']:
                print(('PASS' if check['ok'] else 'CHECK') + ' · ' + check['name'] + ': ' + check['detail'])
            print(report['note'])
        if args.action == 'check':
            return 0 if report['ready'] else 1
        t.need(os.geteuid() != 0, 'Run setup as your desktop user, without sudo.')
        t.need(report['ready'], 'Resolve the host checks above before installation. No app or game files changed.')
        settings, change = selected_settings(config, args.profile)
        print(f"Preparing {settings['runtime_provider']} · {settings['default_profile']} (verified download; no game writes)")
        # Verify before replacing an installed application or saving preferences.
        receipt = prepare_runtime(config, settings)
        if args.action == 'install':
            print('Installed:', desktop_install.install())
            save_preferences(config, settings, change)
        root = storage(config) / 'setup'
        receipt.update(action=args.action, host=report, commit=build_commit(), created=t.now())
        t.atomic_file(root / 'last-setup.json', (json.dumps(receipt, indent=2) + '\n').encode(), 0o600)
        print('Runtime prepared. Open rtxForge, select one game, and review Install Features.')
        print('DLSS-Unlocked NR starts off; F10 toggles it. Enable frame generation in the game for MFG.')
        print('Change an already installed game profile/provider only after Restore Original Files.')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Setup stopped: {exc}', file=sys.stderr)
        return 1


def build_commit():
    path = Path(__file__).resolve().parents[1] / 'BUILD_INFO.json'
    return json.loads(path.read_text()).get('commit', 'unknown') if path.is_file() else 'source checkout'


if __name__ == '__main__':
    sys.exit(main())
