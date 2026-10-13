from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import compatibility
import profiles
import transactions as t

TEMPLATE = '''[FrameGen]\nEnabled=false\nFGInput=nofg\nFGOutput=nofg\nFGNvngxReplacement=none\n[DLSSG]\nAdaMfgUnlock=false\nAdaBlackwellKernels=false\n[DlssNr]\nEnabled=false\n'''


def parsed(route='native-streamline', existing=None):
    return t.ini(profiles.render(TEMPLATE, existing, 'mfg-only', route))


def test_native_streamline_is_default():
    ini = parsed()
    assert ini['FrameGen']['Enabled'] == 'true'
    assert ini['FrameGen']['FGInput'] == 'dlssg'
    assert ini['FrameGen']['FGOutput'] == 'dlssg'
    assert ini['FrameGen']['FGNvngxReplacement'] == 'none'
    assert ini['DLSSG']['AdaMfgUnlock'] == 'true'
    assert ini['DLSSG']['AdaBlackwellKernels'] == 'true'


def test_known_compatibility_routes():
    assert compatibility.route_for({'name':'Cyberpunk 2077','game':'/games/Cyberpunk 2077','exe':'Cyberpunk2077.exe'})['key'] == 'native-streamline'


def test_enabler_route_is_not_supported():
    import pytest
    with pytest.raises(t.Refusal):parsed('enabler')


def test_route_sentinel_preserves_manual_choice_after_seed():
    first = profiles.render(TEMPLATE, None, 'mfg-only', 'native-streamline')
    first = t.setvalue(first, 'FrameGen', 'FGInput', 'nvngxfg')
    first = t.setvalue(first, 'FrameGen', 'FGNvngxReplacement', 'arturs')
    ini = parsed('native-streamline', first)
    assert ini['FrameGen']['FGInput'] == 'nvngxfg'
    assert ini['FrameGen']['FGNvngxReplacement'] == 'arturs'


def test_old_route_sentinel_migrates_to_native_streamline():
    old = t.setvalue(TEMPLATE, 'BazziteInstaller', 'MfgRoute', 'arturs-headless-proton-stable-v3')
    old = t.setvalue(old, 'FrameGen', 'FGInput', 'nvngxfg')
    old = t.setvalue(old, 'FrameGen', 'FGNvngxReplacement', 'arturs')
    ini = parsed('native-streamline', old)
    assert ini['FrameGen']['FGInput'] == 'dlssg'
    assert ini['FrameGen']['FGNvngxReplacement'] == 'none'
    assert ini['BazziteInstaller']['MfgRoute'] == 'native-streamline-dlssg-ada-v5'
