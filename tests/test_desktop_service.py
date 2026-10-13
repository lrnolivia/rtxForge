"""Retained desktop recovery for legacy batch records, on disposable fixtures."""
import json
from pathlib import Path
import struct
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from desktop_service import DesktopService
import planning
import transactions as t
import ui


def test_legacy_batch_review_apply_and_recovery():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory).resolve();state=root/'state';state.mkdir()
        service=DesktopService.__new__(DesktopService)
        service.config={'storage':{'root':str(state),'reserve_bytes':0}}
        source=root/'payload';source.mkdir();sources={}
        template=b'[DlssNr]\nEnabled=false\n[FrameGen]\nEnabled=false\n[DLSSG]\nAdaMfgUnlock=false\n'
        for name,data in {'OptiScaler.dll':b'OptiScaler synthetic','OptiScaler.ini':template,'OptiScaler/dlss-enabler-headless.dll':b'synthetic'}.items():
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);sources[name]=(path,t.digest(path))
        game=root/'Game';game.mkdir();pe=bytearray(70);pe[:2]=b'MZ';struct.pack_into('<I',pe,60,64);pe[64:]=b'PE\0\0\x64\x86'
        (game/'Game.exe').write_bytes(pe);(game/'nvngx_dlssg.dll').write_bytes(b'native');(game/'save.dat').write_bytes(b'preserve')
        plan=planning.make({'name':'Game','game':str(game),'exe':'Game.exe','mode':'mfg-only'},state,sources)
        assert not (game/'dxgi.dll').exists()
        events=[]
        with ui.report_to(events.append):
            record=service.execute({'kind':'batch','plans':[plan]})
            assert (game/'dxgi.dll').exists()
            recovery=service.review_recovery({'kind':'rollback','path':record})
            assert (game/'dxgi.dll').exists()  # Review is read-only.
            service.execute(recovery)
        assert not (game/'dxgi.dll').exists()
        assert (game/'save.dat').read_bytes()==b'preserve'
        assert any(event['kind']=='progress' for event in events)
