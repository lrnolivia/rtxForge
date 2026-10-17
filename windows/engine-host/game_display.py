"""Reviewed, reversible display preferences for known Windows game schemas.

Only display keys are owned. Restore merges those keys into the current file,
preserving new saves, graphics options and preferences changed since install.
"""
from __future__ import annotations

import base64
import configparser
import ctypes
import hashlib
import json
import os
import re
from pathlib import Path

import transactions as t


def documents():
    # SHGetFolderPath follows redirected Documents (including OneDrive).
    buffer = ctypes.create_unicode_buffer(32768)
    t.need(ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0,
           'Windows Documents folder is unavailable')
    return Path(buffer.value)


def target(game, *, local=None, docs=None):
    local = Path(local or os.environ['LOCALAPPDATA'])
    appid = str(game.appid or '')
    exe = Path(game.exe or '').name.casefold()
    if appid == '2456740' or exe == 'inzoi-win64-shipping.exe':
        return local / 'BlueClient/Saved/Config/Windows/GameUserSettings.ini', '/Script/BlueClient.B1GameUserSettings', {
            'FullscreenMode': '1', 'LastConfirmedFullscreenMode': '1',
            'PreferredFullscreenMode': '1', 'LastUserConfirmedFullscreenMode': '1',
            'ResolutionSizeX': '3840', 'ResolutionSizeY': '2160',
            'LastUserConfirmedResolutionSizeX': '3840', 'LastUserConfirmedResolutionSizeY': '2160',
            'SelectedResolutionSizeX': '3840', 'SelectedResolutionSizeY': '2160'}
    if appid == '292030' or exe == 'witcher3.exe':
        return Path(docs or documents()) / 'The Witcher 3/dx12user.settings', 'Viewport', {
            'Resolution': '"3840x2160"', 'FullScreenMode': '2'}
    if appid == '1716740' or exe == 'starfield.exe':
        return Path(docs or documents()) / 'My Games/Starfield/StarfieldPrefs.ini', 'Display', {
            'iSize W': '3840', 'iSize H': '2160', 'bBorderless': '1', 'bFull Screen': '0'}
    return None


def parse(text):
    parser = configparser.RawConfigParser(strict=True)
    parser.optionxform = str
    parser.read_string(text)
    return parser


def value(text, section, key):
    parser = parse(text)
    return parser.get(section, key, fallback=None)


def replace(text, section, key, new):
    # Edit the exact line, retaining comments, order, encoding and line endings.
    parser = parse(text)
    t.need(parser.has_section(section), 'Display section is missing; launch the game once first')
    pattern = r'(?ms)(^\[' + re.escape(section) + r'\][^\r\n]*\r?\n)(.*?)(?=^\[|\Z)'
    found = re.search(pattern, text)
    t.need(found is not None, 'Display section is ambiguous')
    body = found[2]
    line = r'(?m)^' + re.escape(key) + r'[ \t]*=[^\r\n]*(?:\r?\n|$)'
    ending = '\r\n' if '\r\n' in text else '\n'
    replacement = '' if new is None else key + '=' + new + ending
    if re.search(line, body):
        body = re.sub(line, lambda _: replacement, body)
    elif new is not None:
        body = body.rstrip('\r\n') + ending + replacement
    return text[:found.start(2)] + body + text[found.end(2):]


def read(path):
    t.safe(path)
    t.need(path.is_file() and path.stat().st_size <= 1024 * 1024,
           'Launch this game once to create its display settings')
    raw = path.read_bytes()
    encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'
    text = raw.decode(encoding)
    parse(text)
    return raw, text, encoding


def state_path(engine, game):
    identity = hashlib.sha256(str(game.root.resolve()).casefold().encode()).hexdigest()
    return engine.STATE_ROOT / 'display-settings' / identity / 'record.json'


def prepare(engine, game, restore=False, **locations):
    found = target(game, **locations)
    if not found:
        return None, '4K borderless: configure in game (no verified settings adapter yet)'
    path, section, settings = found
    record_path = state_path(engine, game)
    if restore and not record_path.exists():
        return None, ''
    try:
        raw, text, encoding = read(path)
        record = json.loads(record_path.read_text()) if record_path.is_file() else None
        if record:
            t.need(record['path'] == str(path) and record['section'] == section, 'Display backup identity differs')
        plan = dict(path=path, section=section, settings=settings, before=t.sha(raw), text=text,
                    encoding=encoding, raw=raw, record_path=record_path, record=record, restore=restore)
        return plan, ('Restore recorded display preferences' if restore else '3840 × 2160 · Borderless · display settings backed up')
    except (OSError, ValueError, configparser.Error, t.Refusal) as error:
        return None, '4K borderless skipped: ' + str(error)


def apply(plan):
    path = plan['path']
    raw, text, encoding = read(path)
    t.need(t.sha(raw) == plan['before'], 'Display settings changed since review; review again')
    record = plan['record']
    if plan['restore']:
        preserved = []
        for key, original in record['original'].items():
            if value(text, plan['section'], key) == record['written'][key]:
                text = replace(text, plan['section'], key, original)
            else:
                preserved.append(key)
        record = dict(record, status='restored', preserved_user_changes=preserved)
    else:
        if not record or record.get('status') == 'restored':
            record = dict(schema=1, path=str(path), section=plan['section'],
                          backup_base64=base64.b64encode(raw).decode(), backup_sha256=t.sha(raw),
                          original={key: value(text, plan['section'], key) for key in plan['settings']})
        for key, new in plan['settings'].items():
            text = replace(text, plan['section'], key, new)
        record = dict(record, status='active', written=plan['settings'])
    output = text.encode(encoding)
    plan['record_path'].parent.mkdir(parents=True, exist_ok=True)
    # Durable originals precede the first target write. The outer operation
    # session also owns this file and rolls it back on failure or cancellation.
    t.atomic_file(plan['record_path'], (json.dumps(dict(record, status='preparing'), indent=2) + '\n').encode(), 0o600)
    if output != raw:
        t.atomic_file(path, output, path.stat().st_mode & 0o777)
        t.need(path.read_bytes() == output, 'Display write verification failed')
    record['after_sha256'] = t.sha(output)
    t.atomic_file(plan['record_path'], (json.dumps(record, indent=2) + '\n').encode(), 0o600)


def attach(review, enabled=False):
    if review.get('operation') not in ('install', 'repair', 'uninstall'):
        return
    restore = review['operation'] == 'uninstall'
    if not enabled and not restore:
        return
    for item, row in zip(review.get('plans', []), review.get('rows', [])):
        plan, description = prepare(review['engine'], item['game'], restore)
        if description:
            row['detail'] += ' · ' + description
            row['display_summary'] = (
                'Restore the display settings backed up by rtxForge.' if plan and restore else
                'Set 4K borderless. Your display settings will be backed up.' if plan else
                'Display settings will stay as they are. Set 4K borderless in the game for the overlay.'
            )
        if plan:
            item.setdefault('extra_checkpoint_paths', []).extend([plan['path'], plan['record_path'].parent])
            previous = item.get('after_game')
            def after(plan=plan, previous=previous):
                if previous:
                    previous()
                apply(plan)
            item['after_game'] = after
