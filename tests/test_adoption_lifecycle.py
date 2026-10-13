from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import planning
import transactions as t


def make_pe(path):
    data = bytearray(70)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:] = b'PE\0\0\x64\x86'
    path.write_bytes(data)


def source_tree(tmp_path):
    root = tmp_path / 'sources'
    root.mkdir()
    files = {
        'OptiScaler.dll': b'OptiScaler managed proxy',
        'OptiScaler.ini': b'[FrameGen]\nEnabled=false\n',
        'OptiScaler/streamline/sl.interposer.dll': b'private streamline',
    }
    out = {}
    for name, data in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        out[name] = (p, t.digest(p))
    return out


def game_fixture(tmp_path):
    game = tmp_path / 'Game'
    game.mkdir()
    make_pe(game / 'Game.exe')
    (game / 'nvngx_dlssg.dll').write_bytes(b'native dlssg evidence')
    state = tmp_path / 'state'
    state.mkdir()
    target = {'name': 'Game', 'game': str(game), 'exe': 'Game.exe', 'mode': 'mfg-only'}
    return game, state, target


def test_recognize_previous_setting_does_not_block_clean_fresh_install(tmp_path):
    game, state, target = game_fixture(tmp_path)
    plan = planning.make(target, state, source_tree(tmp_path), adopt=True)
    assert plan['adopted'] is False
    assert not plan['conflicts']
    assert any(Path(row['path']).name.lower() == 'dxgi.dll' for row in plan['changes'])
    assert any(Path(row['path']).name.lower() == 'optiscaler.ini' for row in plan['changes'])


def test_recognizable_external_install_is_adopted(tmp_path):
    game, state, target = game_fixture(tmp_path)
    (game / 'dxgi.dll').write_bytes(b'External OptiScaler proxy')
    (game / 'OptiScaler.ini').write_text('[FrameGen]\nEnabled=false\n', encoding='utf-8')
    plan = planning.make(target, state, source_tree(tmp_path), adopt=True)
    assert plan['adopted'] is True
    assert not plan['conflicts']


def test_incomplete_external_install_is_not_silently_adopted(tmp_path):
    game, state, target = game_fixture(tmp_path)
    (game / 'OptiScaler.ini').write_text('[FrameGen]\nEnabled=false\n', encoding='utf-8')
    plan = planning.make(target, state, source_tree(tmp_path), adopt=True)
    assert plan['adopted'] is False
    assert plan['conflicts']

def test_install_uninstall_reinstall_with_real_transactions(tmp_path):
    game,state,target=game_fixture(tmp_path);sources=source_tree(tmp_path)
    history=state/'transactions'/t.sha(str(game).encode())[:20];history.mkdir(parents=True)
    install=planning.make(target,state,sources,adopt=True)
    t.apply_transaction(install,history/'001')
    removal=planning.remove(target,state)
    assert not removal['conflicts']
    t.apply_transaction(removal,history/'002')
    assert not (game/'dxgi.dll').exists() and not (game/'OptiScaler.ini').exists()
    again=planning.make(target,state,sources,adopt=True)
    assert not again['conflicts'] and not again['adopted']
    t.apply_transaction(again,history/'003')
    assert (game/'dxgi.dll').is_file() and (game/'OptiScaler.ini').is_file()
    # Steam Verify/external cleanup may remove every managed file while history remains.
    for row in again['managed']:(game/row['path']).unlink(missing_ok=True)
    clean=planning.make(target,state,sources,adopt=True)
    assert not clean['conflicts'] and not clean['adopted']
