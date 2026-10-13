from pathlib import Path
import json,sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pipeline,transactions as t

def test_nr_layer_cannot_replace_mfg_or_keep_enabler():
    c=json.loads((Path(__file__).resolve().parents[1]/'provider.json').read_text())
    base={n:(Path(n),'shared-'+n) for n in ('OptiScaler.dll','OptiScaler/streamline/sl.interposer.dll','OptiScaler/streamline/sl.dlss_g.dll','OptiScaler/nvngx_dlssg.dll','OptiScaler/dlss-enabler-headless.dll','OptiScaler/nvngx.ini')}
    combined={**base,**{n:(Path(n),h) for n,h in c['nr']['components'].items()}}
    mfg=pipeline.compose(combined,'mfg-only',c);nr=pipeline.compose(combined,'nr-mfg',c)
    assert all(Path(n).name.lower() not in pipeline.NR_NAMES|pipeline.LEGACY_NAMES for n in mfg)
    assert all(Path(n).name.lower() not in pipeline.LEGACY_NAMES for n in nr)
    assert all(nr[n]==v for n,v in mfg.items())
    for missing in c['nr']['components']:
        bad=dict(combined);bad.pop(missing)
        with pytest.raises(t.Refusal):pipeline.compose(bad,'nr-mfg',c)
    bad=dict(combined);bad['nvngx_dlssnr.dll']=(Path('untrusted'),'changed')
    with pytest.raises(t.Refusal):pipeline.compose(bad,'nr-mfg',c)
