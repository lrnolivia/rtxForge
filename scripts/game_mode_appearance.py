"""Shared native Game Mode appearance, independent of game/runtime settings."""
from pathlib import Path
import base64
import json
import os
import re
import sys
import tempfile

ACCENT_CHOICES = (('green', 'rtxForge Green'), ('system', 'System'), ('custom', 'Custom'))
FORGE_GREEN = '#76b900'
DEFAULTS = dict(theme='clear', detailsTheme='same', tint=True, tintStrength=50, accentMode='custom',
                accentSource='custom', accent='#d8d5ce', motion=True, text='standard', navigation='top',
                detailsNavigation='sidebar', scale='auto', libraryScale=100,
                appearanceDefaultsVersion=2, libraryScaleVersion=1, detailsNavigationVersion=1)
MAX_BYTES = 1700000


def appearance_path(config=None):
    if os.name == 'nt':
        local = os.environ.get('LOCALAPPDATA')
        if not local or not Path(local).is_absolute():
            raise ValueError('The Windows application-data folder is unavailable.')
        return Path(local) / 'rtxForge' / 'game-mode-appearance.json'
    import library_media
    if config is None:
        import rtxforge
        config = rtxforge.load_provider()
    return library_media.settings_path(config).with_name('game-mode-appearance.json')


def normalize(value):
    if not isinstance(value, dict):
        raise ValueError('Game Mode appearance must be an object.')
    if set(value) - set(DEFAULTS) - {'background'}:
        raise ValueError('Unsupported Game Mode appearance option.')
    result = DEFAULTS | value
    for key, choices in {'theme': ('light', 'clear', 'dark'),
                         'detailsTheme': ('same', 'light', 'clear', 'dark'),
                         'accentMode': ('theme', 'adaptive', 'custom'),
                         'accentSource': tuple(key for key, _ in ACCENT_CHOICES),
                         'text': ('standard', 'large'), 'navigation': ('top', 'bottom'),
                         'detailsNavigation': ('tabs', 'sidebar')}.items():
        if result[key] not in choices:
            raise ValueError('Invalid Game Mode appearance: ' + key)
    for key in ('tint', 'motion'):
        if type(result[key]) is not bool:
            raise ValueError('Invalid Game Mode appearance: ' + key)
    for key, low, high in (('tintStrength', 0, 100), ('libraryScale', 70, 140)):
        if type(result[key]) not in (int, float) or not low <= result[key] <= high:
            raise ValueError('Invalid Game Mode appearance: ' + key)
    if result['scale'] != 'auto' and (type(result['scale']) is not int or result['scale'] not in (100, 125, 130, 150, 175, 200)):
        raise ValueError('Invalid Game Mode display scale.')
    if not isinstance(result['accent'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', result['accent']):
        raise ValueError('Choose a six-digit accent color.')
    result['accent'] = result['accent'].lower()
    background = result.get('background')
    if background is None:
        result.pop('background', None)
    if background is not None:
        if not isinstance(background, str) or len(background) > 1600000:
            raise ValueError('Game Mode background is too large.')
        if background:
            match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([a-zA-Z0-9+/=]+)', background)
            if not match:
                raise ValueError('Choose a PNG, JPEG or WebP background.')
            try:
                base64.b64decode(match[2], validate=True)
            except ValueError as error:
                raise ValueError('The background image data is invalid.') from error
        else:
            result.pop('background', None)
    result.update(appearanceDefaultsVersion=2, libraryScaleVersion=1, detailsNavigationVersion=1)
    result['tint'] = result['accentMode'] != 'theme' and result['tintStrength'] > 0
    return result


def _check_path(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Appearance storage must use an absolute path.')
    if any(parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)() for parent in (path, *path.parents)):
        raise ValueError('Linked appearance storage is not supported.')
    return path


def load(config=None, path=None):
    path = _check_path(path or appearance_path(config))
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Game Mode appearance storage is invalid.')
    return normalize(json.loads(path.read_text(encoding='utf-8-sig')))


def save(value, config=None, path=None):
    result = normalize(value)
    data = (json.dumps(result, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
    if len(data) > MAX_BYTES:
        raise ValueError('Game Mode appearance is too large.')
    path = _check_path(path or appearance_path(config))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.game-mode-appearance-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return result


def main():
    if sys.argv[1:] == ['read']:
        result = load()
    elif sys.argv[1:] == ['write']:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Game Mode appearance is too large.')
        result = save(json.loads(raw.decode('utf-8-sig')))
    else:
        raise SystemExit('Use game_mode_appearance.py read|write')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        main()
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
